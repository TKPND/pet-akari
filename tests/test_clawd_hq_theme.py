import json
import os
import shutil
import tempfile
import unittest
import zipfile
from contextlib import contextmanager
from pathlib import Path

from PIL import Image, ImageDraw, ImageSequence

from pet_akari import clawd_hq_theme as hq


@contextmanager
def temporary_theme_sizes(master_size=(256, 320), runtime_size=(48, 60), reference_runtime_size=(1536, 1920)):
    original = (hq.MASTER_SIZE, hq.RUNTIME_SIZE, hq.REFERENCE_RUNTIME_SIZE)
    hq.MASTER_SIZE = master_size
    hq.RUNTIME_SIZE = runtime_size
    hq.REFERENCE_RUNTIME_SIZE = reference_runtime_size
    try:
        yield
    finally:
        hq.MASTER_SIZE, hq.RUNTIME_SIZE, hq.REFERENCE_RUNTIME_SIZE = original


def write_mixed_synthetic_masters(masters_dir):
    masters_dir = hq.ensure_dir(masters_dir)
    outputs = []
    for state in hq.CORE_STATES:
        frame_count = 12 if state in ("working", "attention") else 8
        state_dir = hq.ensure_dir(masters_dir / state)
        for index in range(frame_count):
            frame = hq._draw_synthetic_frame(state, index, frame_count)
            output = state_dir / f"{index + 1:02d}.png"
            frame.save(output)
            outputs.append(output)
    return outputs


def write_motion_contract(path):
    contract = {"states": {state: {"durationMs": 125, "inbetweens": 4} for state in hq.CORE_STATES}}
    contract["states"]["working"] = {"durationMs": 100, "inbetweens": 3}
    contract["states"]["attention"] = {"durationMs": 100, "inbetweens": 3}
    path.write_text(json.dumps(contract, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return contract


def rewrite_apng_with_durations(path, durations):
    path = Path(path)
    with Image.open(path) as image:
        frames = [frame.copy().convert("RGBA") for frame in ImageSequence.Iterator(image)]
    output = path.with_name(f"{path.stem}-durations.apng")
    frames[0].save(
        output,
        format="PNG",
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        loop=0,
        disposal=2,
        blend=0,
    )
    output.replace(path)


class ClawdHqThemeTests(unittest.TestCase):
    def test_theme_json_uses_hq_apng_contract(self):
        theme = hq.build_theme_json()

        self.assertEqual(hq.MASTER_SIZE, (2048, 2560))
        self.assertEqual(hq.REFERENCE_RUNTIME_SIZE, (1536, 1920))
        self.assertEqual(hq.RUNTIME_SIZE, (384, 480))
        self.assertEqual(hq.DEFAULT_DURATION_MS, 125)
        self.assertEqual(hq.DEFAULT_INBETWEENS, 9)
        self.assertEqual(
            hq.CORE_STATES,
            ("idle", "thinking", "working", "notification", "attention", "error", "sleeping"),
        )
        self.assertEqual(theme["schemaVersion"], 1)
        self.assertEqual(theme["name"], "Akari HQ APNG")
        self.assertEqual(theme["author"], "Takahiro and Akari")
        self.assertEqual(theme["description"], "Transparent APNG Clawd theme for Short Coral Akari.")
        self.assertEqual(theme["version"], "1.0.0")
        self.assertEqual(
            theme["viewBox"],
            {"x": 0, "y": 0, "width": hq.RUNTIME_SIZE[0], "height": hq.RUNTIME_SIZE[1]},
        )
        self.assertEqual(theme["viewBox"], {"x": 0, "y": 0, "width": 384, "height": 480})
        self.assertEqual(theme["eyeTracking"], {"enabled": False, "states": []})
        self.assertEqual(theme["sleepSequence"], {"mode": "direct"})
        self.assertEqual(theme["miniMode"], {"supported": False})

        self.assertEqual(
            set(theme["layout"]),
            {"contentBox", "centerX", "baselineY", "visibleHeightRatio", "baselineBottomRatio"},
        )
        self.assertEqual(
            theme["layout"]["contentBox"],
            {"x": 0, "y": 0, "width": hq.RUNTIME_SIZE[0], "height": hq.RUNTIME_SIZE[1]},
        )
        self.assertEqual(theme["layout"]["centerX"], hq.RUNTIME_SIZE[0] / 2)
        self.assertEqual(theme["layout"]["baselineY"], hq.RUNTIME_SIZE[1] * 0.94)
        self.assertEqual(theme["layout"]["visibleHeightRatio"], 0.7)
        self.assertEqual(theme["layout"]["baselineBottomRatio"], 0.04)

        for hit_box in ("default", "sleeping"):
            self.assertEqual(set(theme["hitBoxes"][hit_box]), {"x", "y", "w", "h"})
            self.assertGreater(theme["hitBoxes"][hit_box]["w"], 0)
            self.assertGreater(theme["hitBoxes"][hit_box]["h"], 0)
            self.assertLessEqual(theme["hitBoxes"][hit_box]["x"] + theme["hitBoxes"][hit_box]["w"], hq.RUNTIME_SIZE[0])
            self.assertLessEqual(theme["hitBoxes"][hit_box]["y"] + theme["hitBoxes"][hit_box]["h"], hq.RUNTIME_SIZE[1])
        self.assertEqual(theme["hitBoxes"]["default"], {"x": 30, "y": 20, "w": 324, "h": 440})
        self.assertEqual(theme["hitBoxes"]["sleeping"], {"x": 30, "y": 130, "w": 324, "h": 225})

        self.assertEqual(theme["workingTiers"], [{"minSessions": 1, "file": "akari-working.apng"}])
        self.assertEqual(theme["jugglingTiers"], [{"minSessions": 1, "file": "akari-working.apng"}])

        self.assertEqual(set(theme["objectScale"]), {"widthRatio", "heightRatio", "offsetX", "offsetY"})
        self.assertGreater(theme["objectScale"]["widthRatio"], 0)
        self.assertGreater(theme["objectScale"]["heightRatio"], 0)

        for state in hq.CORE_STATES:
            self.assertEqual(theme["states"][state], [f"akari-{state}.apng"])
        self.assertEqual(theme["states"]["juggling"], ["akari-working.apng"])
        self.assertEqual(theme["states"]["sweeping"], ["akari-working.apng"])
        self.assertEqual(theme["states"]["carrying"], ["akari-working.apng"])

    def test_split_strip_removes_flat_chroma_key_background(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            strip_path = root / "strip.png"
            strip = Image.new("RGBA", (400, 200), (0, 255, 0, 255))
            draw = ImageDraw.Draw(strip)
            draw.rectangle((150, 40, 249, 179), fill=(255, 139, 84, 255))
            strip.save(strip_path)

            hq.split_strip_to_masters(strip_path, root / "masters", frames=1)

            frame = Image.open(root / "masters" / "01.png").convert("RGBA")
            self.assertEqual(frame.getpixel((0, 0))[3], 0)
            body_pixel = (
                hq.MASTER_SIZE[0] // 2,
                int(hq.MASTER_SIZE[1] * 0.8),
            )
            self.assertEqual(frame.getpixel(body_pixel)[3], 255)

    def test_synthetic_masters_support_small_test_sizes(self):
        with tempfile.TemporaryDirectory() as tmp, temporary_theme_sizes():
            root = Path(tmp)

            hq.write_synthetic_masters(root / "masters", frame_count=2)

            with Image.open(root / "masters" / "idle" / "01.png") as frame:
                frame = frame.convert("RGBA")
                self.assertEqual(frame.size, hq.MASTER_SIZE)
                self.assertIsNotNone(frame.getchannel("A").getbbox())

    def test_split_strip_accepts_non_divisible_generated_width(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            strip_path = root / "strip.png"
            width = 1774
            height = 200
            frames = 4
            strip = Image.new("RGBA", (width, height), (0, 255, 0, 255))
            draw = ImageDraw.Draw(strip)
            for index in range(frames):
                left = round(index * width / frames)
                right = round((index + 1) * width / frames)
                center_x = (left + right) // 2
                draw.rectangle((center_x - 35, 60, center_x + 35, 139), fill=(255, 139, 84, 255))
            strip.save(strip_path)

            outputs = hq.split_strip_to_masters(strip_path, root / "masters", frames=frames)

            self.assertEqual(len(outputs), frames)
            for output in outputs:
                self.assertTrue(output.is_file())
                with Image.open(output) as frame:
                    self.assertIsNotNone(frame.convert("RGBA").getchannel("A").getbbox())

    def test_split_strip_components_handles_uneven_spacing(self):
        with tempfile.TemporaryDirectory() as tmp, temporary_theme_sizes():
            root = Path(tmp)
            strip_path = root / "strip.png"
            strip = Image.new("RGBA", (520, 120), (0, 255, 0, 255))
            draw = ImageDraw.Draw(strip)
            colors = [
                (220, 50, 50, 255),
                (50, 160, 220, 255),
                (230, 190, 60, 255),
                (170, 80, 210, 255),
            ]
            boxes = [
                (20, 28, 74, 104),
                (132, 28, 187, 104),
                (246, 28, 302, 104),
                (420, 28, 496, 104),
            ]
            for color, box in zip(colors, boxes):
                draw.rectangle(box, fill=color)
            strip.save(strip_path)

            outputs = hq.split_strip_to_masters(strip_path, root / "masters", frames=4, split_mode="components")

            self.assertEqual(len(outputs), 4)
            for output, expected in zip(outputs, colors):
                with Image.open(output) as frame:
                    frame = frame.convert("RGBA")
                    bbox = frame.getchannel("A").getbbox()
                    self.assertIsNotNone(bbox)
                    center = ((bbox[0] + bbox[2]) // 2, (bbox[1] + bbox[3]) // 2)
                    actual = frame.getpixel(center)
                self.assertEqual(actual[:3], expected[:3])

    def test_split_strip_components_preserves_sparse_edge_details(self):
        strip = Image.new("RGBA", (160, 100), (0, 255, 0, 255))
        draw = ImageDraw.Draw(strip)
        draw.rectangle((55, 25, 110, 85), fill=(220, 50, 50, 255))
        draw.line((42, 52, 54, 52), fill=(220, 50, 50, 255), width=1)

        crop = hq.split_strip_by_components(strip, frames=1)[0]
        bbox = crop.getchannel("A").getbbox()

        self.assertIsNotNone(bbox)
        self.assertGreaterEqual(crop.width, 69)
        self.assertLessEqual(bbox[0], 1)
        self.assertIn(255, [crop.getpixel((0, y))[3] for y in range(crop.height)])

    def test_split_strip_components_rejects_component_count_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            strip_path = root / "strip.png"
            strip = Image.new("RGBA", (300, 120), (0, 255, 0, 255))
            draw = ImageDraw.Draw(strip)
            draw.rectangle((20, 30, 80, 100), fill=(255, 139, 84, 255))
            draw.rectangle((180, 30, 240, 100), fill=(42, 50, 84, 255))
            strip.save(strip_path)

            with self.assertRaisesRegex(ValueError, "found 2 components, expected 3"):
                hq.split_strip_to_masters(strip_path, root / "masters", frames=3, split_mode="components")

    def test_normalize_removes_green_dominant_background_and_preserves_teal(self):
        image = Image.new("RGBA", (160, 120), (8, 210, 20, 255))
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 70, 159, 119), fill=(0, 230, 12, 255))
        draw.rectangle((45, 35, 85, 85), fill=(255, 139, 84, 255))
        draw.rectangle((98, 40, 128, 80), fill=(0, 180, 190, 255))

        cleaned = hq.remove_chroma_key(image)
        frame = hq.normalize_to_master(image)

        self.assertEqual(cleaned.getpixel((0, 0))[3], 0)
        self.assertEqual(cleaned.getpixel((110, 60))[3], 255)

        pixels = frame.get_flattened_data() if hasattr(frame, "get_flattened_data") else frame.getdata()
        visible_teal = [
            pixel for pixel in pixels if pixel[3] == 255 and pixel[0] <= 40 and pixel[1] >= 150 and pixel[2] >= 150
        ]
        self.assertGreater(len(visible_teal), 0)

    def test_synthetic_pipeline_writes_masters_runtime_and_package(self):
        with tempfile.TemporaryDirectory() as tmp, temporary_theme_sizes():
            root = Path(tmp)
            theme_dir = root / "theme"
            package_path = root / "akari-hq-apng.zip"

            hq.write_synthetic_masters(root / "masters", frame_count=3)
            hq.export_theme(
                root / "masters",
                theme_dir,
                include_ultra=True,
                duration_ms=120,
                inbetweens=0,
            )
            hq.validate_theme_assets(theme_dir, require_ultra=True)
            hq.write_contact_sheet(theme_dir, root / "contact-sheet.png")
            hq.package_theme(theme_dir, package_path)

            self.assertTrue((theme_dir / "theme.json").is_file())
            self.assertTrue((theme_dir / "assets" / "akari-idle.apng").is_file())
            self.assertTrue((theme_dir / "assets-ultra" / "akari-idle.apng").is_file())
            self.assertTrue((root / "contact-sheet.png").is_file())
            self.assertTrue(package_path.is_file())

            with Image.open(theme_dir / "assets" / "akari-idle.apng") as idle:
                self.assertTrue(getattr(idle, "is_animated", False))
                self.assertEqual(idle.n_frames, 3)
                self.assertEqual(idle.size, hq.RUNTIME_SIZE)
                self.assertEqual(idle.convert("RGBA").mode, "RGBA")

            with zipfile.ZipFile(package_path) as archive:
                names = set(archive.namelist())
            self.assertIn("akari-hq-apng/theme.json", names)
            self.assertIn("akari-hq-apng/assets/akari-idle.apng", names)

    def test_export_theme_defaults_to_sample_like_runtime_motion(self):
        with tempfile.TemporaryDirectory() as tmp, temporary_theme_sizes():
            root = Path(tmp)
            theme_dir = root / "theme"

            hq.write_synthetic_masters(root / "masters", frame_count=4)
            hq.export_theme(root / "masters", theme_dir)

            theme = json.loads((theme_dir / "theme.json").read_text(encoding="utf-8"))
            self.assertEqual(hq.RUNTIME_SIZE, (48, 60))
            self.assertEqual(
                theme["viewBox"],
                {"x": 0, "y": 0, "width": hq.RUNTIME_SIZE[0], "height": hq.RUNTIME_SIZE[1]},
            )
            self.assertEqual(
                theme["hitBoxes"]["default"],
                {"x": 4, "y": 2, "w": 40, "h": 55},
            )
            self.assertEqual(
                theme["hitBoxes"]["sleeping"],
                {"x": 4, "y": 16, "w": 40, "h": 28},
            )

            with Image.open(theme_dir / "assets" / "akari-idle.apng") as idle:
                durations = [frame.info.get("duration") for frame in ImageSequence.Iterator(idle)]
                self.assertEqual(idle.size, hq.RUNTIME_SIZE)
                self.assertEqual(idle.n_frames, 40)

            self.assertEqual(durations, [125.0] * 40)
            self.assertEqual(sum(durations), 5000.0)

    def test_export_theme_writes_build_manifest_with_source_and_runtime_hashes(self):
        with tempfile.TemporaryDirectory() as tmp, temporary_theme_sizes():
            root = Path(tmp)
            masters_dir = root / "masters"
            theme_dir = root / "theme"
            hq.write_synthetic_masters(masters_dir, frame_count=4)

            hq.export_theme(masters_dir, theme_dir)

            manifest_path = theme_dir / "qa" / "build-manifest.json"
            self.assertTrue(manifest_path.is_file())
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["manifestVersion"], 1)
            self.assertEqual(manifest["exporter"]["tool"], "python -m pet_akari.clawd_hq_theme")
            self.assertEqual(manifest["exporter"]["runtimeSize"], [hq.RUNTIME_SIZE[0], hq.RUNTIME_SIZE[1]])
            self.assertEqual(set(manifest["states"]), set(hq.CORE_STATES))

            idle = manifest["states"]["idle"]
            self.assertEqual(idle["trueSourceFrames"], 4)
            self.assertEqual(idle["encodedFrames"], 40)
            self.assertEqual(idle["durationMs"], 125)
            self.assertEqual(idle["inbetweens"], 9)
            self.assertEqual(idle["keyframeIndices"], [0, 10, 20, 30])
            self.assertEqual(idle["runtimeAsset"], "assets/akari-idle.apng")
            self.assertFalse(Path(idle["sourceMasterDir"]).is_absolute())
            self.assertEqual(idle["sourceMasterDir"], "../masters/idle")
            self.assertEqual(len(idle["sourceMasterFiles"]), 4)
            self.assertFalse(Path(idle["sourceMasterFiles"][0]["path"]).is_absolute())
            self.assertEqual(idle["sourceMasterFiles"][0]["path"], "../masters/idle/01.png")
            self.assertTrue(idle["runtimeSha256"])
            self.assertTrue(idle["sourceMasterFiles"][0]["sha256"])

    def test_validate_lineage_accepts_relocated_export_tree(self):
        with tempfile.TemporaryDirectory() as tmp, temporary_theme_sizes():
            root = Path(tmp)
            hq.write_synthetic_masters(root / "masters", frame_count=4)
            hq.export_theme(root / "masters", root / "theme")

            moved_root = root / "moved"
            shutil.copytree(root / "masters", moved_root / "masters")
            shutil.copytree(root / "theme", moved_root / "theme")
            shutil.rmtree(root / "masters")
            shutil.rmtree(root / "theme")

            self.assertTrue(hq.validate_lineage(moved_root / "theme"))

    def test_validate_lineage_accepts_theme_copy_without_sibling_masters(self):
        with tempfile.TemporaryDirectory() as tmp, temporary_theme_sizes():
            root = Path(tmp)
            hq.write_synthetic_masters(root / "masters", frame_count=4)
            hq.export_theme(root / "masters", root / "theme")

            promoted_theme = root / "promoted" / "theme"
            shutil.copytree(root / "theme", promoted_theme)

            self.assertTrue(hq.validate_lineage(promoted_theme))

    def test_resolve_manifest_file_prefers_theme_relative_path_over_cwd_shadow(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            theme_dir = root / "export" / "theme"
            expected = root / "export" / "masters" / "idle" / "01.png"
            shadow_cwd = root / "cwd" / "theme"
            shadow = root / "cwd" / "masters" / "idle" / "01.png"
            theme_dir.mkdir(parents=True)
            expected.parent.mkdir(parents=True)
            shadow.parent.mkdir(parents=True)
            shadow_cwd.mkdir(parents=True)
            expected.write_text("expected\n", encoding="utf-8")
            shadow.write_text("shadow\n", encoding="utf-8")

            original_cwd = Path.cwd()
            try:
                os.chdir(shadow_cwd)
                resolved = hq._resolve_manifest_file("../masters/idle/01.png", theme_dir)
            finally:
                os.chdir(original_cwd)

            self.assertEqual(resolved.resolve(), expected)

    def test_export_theme_accepts_per_state_motion_contract(self):
        with tempfile.TemporaryDirectory() as tmp, temporary_theme_sizes():
            root = Path(tmp)
            masters_dir = root / "masters"
            theme_dir = root / "theme"
            write_mixed_synthetic_masters(masters_dir)
            contract = write_motion_contract(root / "motion-contract.json")

            hq.export_theme(masters_dir, theme_dir, motion_contract=contract)

            manifest = json.loads((theme_dir / "qa" / "build-manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["states"]["idle"]["trueSourceFrames"], 8)
            self.assertEqual(manifest["states"]["idle"]["encodedFrames"], 40)
            self.assertEqual(manifest["states"]["idle"]["durationMs"], 125)
            self.assertEqual(manifest["states"]["idle"]["inbetweens"], 4)
            self.assertEqual(manifest["states"]["idle"]["keyframeIndices"], [0, 5, 10, 15, 20, 25, 30, 35])

            self.assertEqual(manifest["states"]["working"]["trueSourceFrames"], 12)
            self.assertEqual(manifest["states"]["working"]["encodedFrames"], 48)
            self.assertEqual(manifest["states"]["working"]["durationMs"], 100)
            self.assertEqual(manifest["states"]["working"]["inbetweens"], 3)
            self.assertEqual(
                manifest["states"]["working"]["keyframeIndices"],
                [0, 4, 8, 12, 16, 20, 24, 28, 32, 36, 40, 44],
            )

            with Image.open(theme_dir / "assets" / "akari-idle.apng") as idle:
                idle_durations = [frame.info.get("duration") for frame in ImageSequence.Iterator(idle)]
                self.assertEqual(idle.n_frames, 40)
            self.assertEqual(idle_durations, [125.0] * 40)

            with Image.open(theme_dir / "assets" / "akari-working.apng") as working:
                working_durations = [frame.info.get("duration") for frame in ImageSequence.Iterator(working)]
                self.assertEqual(working.n_frames, 48)
            self.assertEqual(working_durations, [100.0] * 48)

    def test_export_theme_can_package_pre_rendered_true_frames_without_inbetweens(self):
        with tempfile.TemporaryDirectory() as tmp, temporary_theme_sizes():
            root = Path(tmp)
            masters_dir = root / "masters"
            theme_dir = root / "theme"
            hq.write_synthetic_masters(masters_dir, frame_count=5)
            contract = {"states": {state: {"durationMs": 63, "inbetweens": 0} for state in hq.CORE_STATES}}

            hq.export_theme(masters_dir, theme_dir, motion_contract=contract)

            manifest = json.loads((theme_dir / "qa" / "build-manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["states"]["idle"]["trueSourceFrames"], 5)
            self.assertEqual(manifest["states"]["idle"]["encodedFrames"], 5)
            self.assertEqual(manifest["states"]["idle"]["keyframeIndices"], [0, 1, 2, 3, 4])

    def test_assert_no_exporter_inbetweens_rejects_nonzero_contract(self):
        contract = {"states": {state: {"durationMs": 63, "inbetweens": 0} for state in hq.CORE_STATES}}
        contract["states"]["idle"]["inbetweens"] = 1

        with self.assertRaisesRegex(ValueError, "exporter inbetweens"):
            hq.assert_no_exporter_inbetweens(contract)

    def test_validate_theme_assets_accepts_motion_contract(self):
        with tempfile.TemporaryDirectory() as tmp, temporary_theme_sizes():
            root = Path(tmp)
            masters_dir = root / "masters"
            theme_dir = root / "theme"
            contract_path = root / "motion-contract.json"
            write_mixed_synthetic_masters(masters_dir)
            contract = write_motion_contract(contract_path)
            hq.export_theme(masters_dir, theme_dir, motion_contract=contract)

            self.assertTrue(hq.validate_theme_assets(theme_dir, motion_contract=contract_path))

            frames = hq.list_master_frames(masters_dir, "working")
            hq.encode_apng(
                frames,
                theme_dir / "assets" / "akari-working.apng",
                hq.RUNTIME_SIZE,
                duration_ms=125,
                inbetweens=4,
            )
            with self.assertRaisesRegex(ValueError, "frame count|total duration"):
                hq.validate_theme_assets(theme_dir, motion_contract=contract_path)

    def test_validate_theme_assets_rejects_motion_contract_frame_duration_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp, temporary_theme_sizes():
            root = Path(tmp)
            masters_dir = root / "masters"
            theme_dir = root / "theme"
            contract_path = root / "motion-contract.json"
            write_mixed_synthetic_masters(masters_dir)
            contract = write_motion_contract(contract_path)
            hq.export_theme(masters_dir, theme_dir, motion_contract=contract)

            rewrite_apng_with_durations(
                theme_dir / "assets" / "akari-idle.apng",
                [100, 150] * 20,
            )

            with self.assertRaisesRegex(ValueError, "frame duration"):
                hq.validate_theme_assets(theme_dir, motion_contract=contract_path)

    def test_validate_theme_assets_rejects_falsy_invalid_motion_contract(self):
        with tempfile.TemporaryDirectory() as tmp, temporary_theme_sizes():
            root = Path(tmp)
            theme_dir = root / "theme"
            hq.write_synthetic_masters(root / "masters", frame_count=4)
            hq.export_theme(root / "masters", theme_dir)

            with self.assertRaisesRegex(ValueError, "motion contract"):
                hq.validate_theme_assets(theme_dir, motion_contract={})

    def test_validate_theme_assets_rejects_ultra_motion_contract_frame_duration_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp, temporary_theme_sizes():
            root = Path(tmp)
            masters_dir = root / "masters"
            theme_dir = root / "theme"
            contract_path = root / "motion-contract.json"
            write_mixed_synthetic_masters(masters_dir)
            contract = write_motion_contract(contract_path)
            hq.export_theme(masters_dir, theme_dir, include_ultra=True, motion_contract=contract)

            rewrite_apng_with_durations(
                theme_dir / "assets-ultra" / "akari-idle.apng",
                [100, 150] * 20,
            )

            with self.assertRaisesRegex(ValueError, "frame duration"):
                hq.validate_theme_assets(theme_dir, require_ultra=True, motion_contract=contract_path)

    def test_normalize_motion_contract_rejects_invalid_shape_and_types(self):
        valid_states = {state: {"durationMs": 125, "inbetweens": 4} for state in hq.CORE_STATES}
        cases = (
            [],
            {"states": []},
            {"states": {state: [] for state in hq.CORE_STATES}},
            {"states": {**valid_states, "idle": {"durationMs": 125.9, "inbetweens": 4}}},
            {"states": {**valid_states, "idle": {"durationMs": 125, "inbetweens": True}}},
        )

        for contract in cases:
            with self.subTest(contract=contract):
                with self.assertRaisesRegex(ValueError, "motion contract"):
                    hq.normalize_motion_contract(contract)

    def test_cli_accepts_motion_contract(self):
        with tempfile.TemporaryDirectory() as tmp, temporary_theme_sizes():
            root = Path(tmp)
            masters_dir = root / "masters"
            theme_dir = root / "theme"
            contract_path = root / "motion-contract.json"
            write_mixed_synthetic_masters(masters_dir)
            write_motion_contract(contract_path)

            hq.main(
                [
                    "export-theme",
                    "--masters",
                    str(masters_dir),
                    "--theme-dir",
                    str(theme_dir),
                    "--motion-contract",
                    str(contract_path),
                ]
            )
            hq.main(
                [
                    "validate-assets",
                    "--theme-dir",
                    str(theme_dir),
                    "--motion-contract",
                    str(contract_path),
                ]
            )

            with Image.open(theme_dir / "assets" / "akari-attention.apng") as attention:
                self.assertEqual(attention.n_frames, 48)

    def test_validate_lineage_accepts_matching_export(self):
        with tempfile.TemporaryDirectory() as tmp, temporary_theme_sizes():
            root = Path(tmp)
            hq.write_synthetic_masters(root / "masters", frame_count=4)
            hq.export_theme(root / "masters", root / "theme")

            self.assertTrue(hq.validate_lineage(root / "theme"))

    def test_validate_lineage_rejects_stale_source_master(self):
        with tempfile.TemporaryDirectory() as tmp, temporary_theme_sizes():
            root = Path(tmp)
            hq.write_synthetic_masters(root / "masters", frame_count=4)
            hq.export_theme(root / "masters", root / "theme")

            Image.new("RGBA", hq.MASTER_SIZE, (255, 0, 0, 255)).save(root / "masters" / "idle" / "01.png")

            with self.assertRaisesRegex(ValueError, "source master sha256"):
                hq.validate_lineage(root / "theme")

    def test_validate_lineage_rejects_runtime_keyframe_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp, temporary_theme_sizes():
            root = Path(tmp)
            hq.write_synthetic_masters(root / "masters", frame_count=4)
            hq.export_theme(root / "masters", root / "theme")

            frames = hq.list_master_frames(root / "masters", "thinking")
            hq.encode_apng(
                frames,
                root / "theme" / "assets" / "akari-idle.apng",
                hq.RUNTIME_SIZE,
                duration_ms=125,
                inbetweens=9,
            )

            with self.assertRaisesRegex(ValueError, "runtime asset sha256|keyframe"):
                hq.validate_lineage(root / "theme")

    def test_validate_theme_assets_can_enforce_runtime_motion_contract(self):
        with tempfile.TemporaryDirectory() as tmp, temporary_theme_sizes():
            root = Path(tmp)
            theme_dir = root / "theme"
            hq.write_synthetic_masters(root / "masters", frame_count=4)
            hq.export_theme(root / "masters", theme_dir)

            self.assertTrue(
                hq.validate_theme_assets(
                    theme_dir,
                    expected_frames=40,
                    expected_total_duration_ms=5000,
                )
            )

            frames = hq.list_master_frames(root / "masters", "idle")
            hq.encode_apng(
                frames,
                theme_dir / "assets" / "akari-idle.apng",
                hq.RUNTIME_SIZE,
                duration_ms=125,
                inbetweens=0,
            )

            with self.assertRaisesRegex(ValueError, "frame count"):
                hq.validate_theme_assets(
                    theme_dir,
                    expected_frames=40,
                    expected_total_duration_ms=5000,
                )

    def test_stabilize_masters_aligns_feet_without_clipping(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_dir = root / "masters" / "idle"
            source_dir.mkdir(parents=True)
            for index, left in enumerate((300, 460, 380), start=1):
                frame = Image.new("RGBA", hq.MASTER_SIZE, (0, 0, 0, 0))
                draw = ImageDraw.Draw(frame)
                draw.rectangle((left, 300, left + 260, 2300), fill=(255, 139, 84, 255))
                draw.rectangle((left + 80, 2301, left + 180, 2406), fill=(20, 20, 24, 255))
                frame.save(source_dir / f"{index:02d}.png")

            outputs = hq.stabilize_masters(root / "masters", root / "stable", states=("idle",))

            self.assertEqual(len(outputs), 3)
            cxs = []
            for path in sorted((root / "stable" / "idle").glob("*.png")):
                frame = Image.open(path).convert("RGBA")
                self.assertEqual(frame.size, hq.MASTER_SIZE)
                self.assertEqual(frame.getchannel("A").getbbox()[3], 2407)
                cxs.append(hq.frame_feet_center_x(frame))
            self.assertLessEqual(max(cxs) - min(cxs), 1.0)

    def test_encode_apng_can_insert_loop_inbetweens(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            frames_dir = root / "frames"
            frames_dir.mkdir()
            colors = ((255, 0, 0, 255), (0, 255, 0, 255), (0, 0, 255, 255))
            for index, color in enumerate(colors, start=1):
                frame = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
                ImageDraw.Draw(frame).rectangle((8, 8, 23, 23), fill=color)
                frame.save(frames_dir / f"{index:02d}.png")

            hq.encode_apng(
                sorted(frames_dir.glob("*.png")),
                root / "inbetween.apng",
                (32, 32),
                duration_ms=60,
                inbetweens=1,
            )

            with Image.open(root / "inbetween.apng") as image:
                self.assertEqual(image.n_frames, 6)
                durations = []
                samples = []
                for index in range(image.n_frames):
                    image.seek(index)
                    durations.append(image.info.get("duration"))
                    frame = image.convert("RGBA")
                    samples.append(frame.getpixel((12, 12)))
            self.assertEqual(durations, [60.0] * 6)
            self.assertEqual(samples[0], (255, 0, 0, 255))
            self.assertEqual(samples[2], (0, 255, 0, 255))
            self.assertEqual(samples[4], (0, 0, 255, 255))
            self.assertGreater(samples[1][0], 0)
            self.assertGreater(samples[1][1], 0)

    def test_encode_apng_preserves_symmetric_true_frame_durations(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            frames_dir = root / "frames"
            frames_dir.mkdir()
            offsets = (0, -1, -2, -4, -5, -4, -2, -1)
            for index, dy in enumerate(offsets, start=1):
                frame = Image.new("RGBA", (32, 40), (0, 0, 0, 0))
                ImageDraw.Draw(frame).rectangle((10, 12 + dy, 21, 31 + dy), fill=(255, 0, 0, 255))
                frame.save(frames_dir / f"{index:02d}.png")

            hq.encode_apng(
                sorted(frames_dir.glob("*.png")),
                root / "symmetric.apng",
                (32, 40),
                duration_ms=63,
                inbetweens=0,
            )

            metadata = hq.apng_metadata(root / "symmetric.apng")
            self.assertEqual(metadata["frames"], 8)
            self.assertEqual(metadata["durationsMs"], [63.0] * 8)
            with Image.open(root / "symmetric.apng") as image:
                image.seek(1)
                second = image.convert("RGBA")
            self.assertEqual(second.getpixel((10, 31)), (0, 0, 0, 0))
            self.assertEqual(second.getpixel((10, 11)), (255, 0, 0, 255))

    def test_lineage_frame_match_tolerates_invisible_edge_pixel_cleanup(self):
        expected = Image.new("RGBA", (4, 4), (0, 0, 0, 0))
        actual = Image.new("RGBA", (4, 4), (0, 0, 0, 0))
        expected.putpixel((2, 3), (0, 255, 0, 3))

        self.assertTrue(hq.lineage_frames_match(actual, expected))

    def test_lineage_frame_match_rejects_visible_pixel_drift(self):
        expected = Image.new("RGBA", (4, 4), (255, 139, 84, 255))
        actual = Image.new("RGBA", (4, 4), (255, 139, 84, 255))
        actual.putpixel((2, 2), (0, 255, 0, 255))

        self.assertFalse(hq.lineage_frames_match(actual, expected))

    def test_cli_accepts_plan_compatible_flags(self):
        with tempfile.TemporaryDirectory() as tmp, temporary_theme_sizes():
            root = Path(tmp)
            masters_dir = root / "masters"
            stable_dir = root / "stable"
            theme_dir = root / "theme"
            contact_sheet = root / "contact-sheet.png"
            package_path = root / "theme.zip"

            hq.main(["synthetic-masters", "--out", str(masters_dir), "--frames", "3"])
            hq.main(["stabilize-masters", "--masters", str(masters_dir), "--out", str(stable_dir)])

            strip_path = root / "strip.png"
            strip = Image.new("RGBA", (400, 200), (0, 255, 0, 255))
            draw = ImageDraw.Draw(strip)
            draw.rectangle((150, 40, 249, 179), fill=(255, 139, 84, 255))
            strip.save(strip_path)
            hq.main(["split-strip", "--strip", str(strip_path), "--out", str(root / "split"), "--frames", "1"])

            hq.main(
                [
                    "export-theme",
                    "--masters",
                    str(masters_dir),
                    "--theme-dir",
                    str(theme_dir),
                    "--include-ultra",
                    "--inbetweens",
                    "1",
                    "--duration-ms",
                    "60",
                ]
            )
            hq.main(
                [
                    "validate-assets",
                    "--theme-dir",
                    str(theme_dir),
                    "--require-ultra",
                    "--expected-frames",
                    "6",
                    "--expected-total-ms",
                    "360",
                ]
            )
            hq.main(["validate-lineage", "--theme-dir", str(theme_dir)])
            hq.main(["contact-sheet", "--theme-dir", str(theme_dir), "--out", str(contact_sheet)])
            hq.main(["package", "--theme-dir", str(theme_dir), "--out", str(package_path)])

            self.assertTrue((root / "split" / "01.png").is_file())
            self.assertTrue((stable_dir / "idle" / "01.png").is_file())
            self.assertTrue((theme_dir / "assets" / "akari-idle.apng").is_file())
            self.assertTrue((theme_dir / "assets-ultra" / "akari-idle.apng").is_file())
            self.assertTrue(contact_sheet.is_file())
            self.assertTrue(package_path.is_file())
            with Image.open(theme_dir / "assets" / "akari-idle.apng") as idle:
                self.assertEqual(idle.n_frames, 6)

    def test_validate_apng_rejects_blank_transparent_animation(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "blank.apng"
            first = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
            second = Image.new("RGBA", (32, 32), (255, 255, 255, 0))
            first.save(
                path,
                format="PNG",
                save_all=True,
                append_images=[second],
                duration=[120, 120],
                loop=0,
                disposal=2,
                blend=0,
            )

            with self.assertRaisesRegex(ValueError, "visible pixels|blank"):
                hq.validate_apng(path, (32, 32))

    def test_export_theme_requires_state_directories(self):
        with tempfile.TemporaryDirectory() as tmp, temporary_theme_sizes():
            root = Path(tmp)
            masters_dir = root / "masters"
            hq.write_synthetic_masters(masters_dir, frame_count=2)
            shutil.rmtree(masters_dir / "sleeping")
            Image.new("RGBA", hq.MASTER_SIZE, (255, 139, 84, 255)).save(masters_dir / "01.png")

            with self.assertRaises(FileNotFoundError):
                hq.export_theme(masters_dir, root / "theme")

    def test_validate_theme_assets_rejects_required_contract_drift(self):
        def export_theme(root):
            theme_dir = root / "theme"
            hq.write_synthetic_masters(root / "masters", frame_count=2)
            hq.export_theme(root / "masters", theme_dir)
            return theme_dir

        cases = (
            ("missing layout", lambda theme: theme.pop("layout")),
            (
                "working tier missing file",
                lambda theme: theme.update(
                    {
                        "workingTiers": [{"tier": "broken", "state": "working", "minSessions": 0}],
                    }
                ),
            ),
            ("corrupt mini mode", lambda theme: theme["miniMode"].update({"supported": True})),
        )
        for name, mutate in cases:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp, temporary_theme_sizes():
                root = Path(tmp)
                theme_dir = export_theme(root)
                theme_path = theme_dir / "theme.json"
                theme = json.loads(theme_path.read_text(encoding="utf-8"))
                mutate(theme)
                theme_path.write_text(json.dumps(theme, indent=2) + "\n", encoding="utf-8")

                with self.assertRaises(ValueError):
                    hq.validate_theme_assets(theme_dir)


if __name__ == "__main__":
    unittest.main()
