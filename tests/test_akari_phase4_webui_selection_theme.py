import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from pet_akari import akari_phase4_webui_diff_pack as diff_pack
from pet_akari import akari_phase4_webui_selection_theme as selection_theme
from pet_akari import clawd_hq_theme as hq


class Phase4WebuiSelectionThemeTests(unittest.TestCase):
    def write_theme(self, root):
        theme_dir = root / "theme"
        assets_dir = theme_dir / "assets"
        assets_dir.mkdir(parents=True)
        hq.write_theme_json(theme_dir)
        for index, state in enumerate(diff_pack.REQUIRED_STATES):
            first = Image.new("RGBA", hq.RUNTIME_SIZE, (0, 0, 0, 0))
            second = Image.new("RGBA", hq.RUNTIME_SIZE, (0, 0, 0, 0))
            first.putpixel((12 + index, 20), (20, 40, 60, 255))
            second.putpixel((18 + index, 28), (40, 80, 120, 255))
            first.save(
                assets_dir / f"akari-{state}.apng",
                format="PNG",
                save_all=True,
                append_images=[second],
                duration=[100, 100],
                loop=0,
            )
        return theme_dir

    def write_selection(self, root, *, blank_state=None):
        import_dir = root / "webui-base-001"
        normalized_dir = import_dir / "normalized"
        normalized_dir.mkdir(parents=True)
        selections = []
        for index, state in enumerate(diff_pack.REQUIRED_STATES):
            image = Image.new("RGBA", hq.RUNTIME_SIZE, (0, 0, 0, 0))
            image.putpixel((48 + index, 64), (200, 120, 80, 255))
            webui_path = normalized_dir / f"{state}.png"
            image.save(webui_path)
            selections.append(
                {
                    "allowedDecisions": ["adopt", "hold", "reject"],
                    "currentPreview": f"state-diffs/{state}.png",
                    "decision": "" if state == blank_state else ("reject" if state == "error" else "adopt"),
                    "diffPreview": f"state-diffs/{state}.png",
                    "notes": "",
                    "state": state,
                    "webuiPreview": webui_path.as_posix(),
                }
            )
        selection_path = root / "selection-template.json"
        selection_path.write_text(
            json.dumps(
                {
                    "allowedDecisions": ["adopt", "hold", "reject"],
                    "schemaVersion": 1,
                    "selections": selections,
                    "status": "reviewed",
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        return selection_path

    def test_build_selection_theme_replaces_adopted_states_and_keeps_rejected_states(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            theme_dir = self.write_theme(root)
            selection_path = self.write_selection(root)

            result = selection_theme.build_selection_theme(
                theme_dir=theme_dir,
                selection_path=selection_path,
                output_dir=root / "out" / "theme",
                package_path=root / "out" / "akari-webui-selection.zip",
            )

            self.assertTrue((result["themeDir"] / "theme.json").is_file())
            self.assertTrue(result["package"].is_file())
            self.assertTrue(result["manifest"].is_file())
            hq.validate_theme_assets(result["themeDir"], expected_frames=2, expected_total_duration_ms=200)

            idle_asset = result["themeDir"] / "assets" / "akari-idle.apng"
            with Image.open(idle_asset) as image:
                self.assertTrue(image.is_animated)
                self.assertEqual(2, image.n_frames)
                image.seek(0)
                self.assertEqual((200, 120, 80, 255), image.convert("RGBA").getpixel((48, 64)))
                image.seek(1)
                self.assertEqual((200, 120, 80, 255), image.convert("RGBA").getpixel((48, 64)))

            error_asset = result["themeDir"] / "assets" / "akari-error.apng"
            with Image.open(error_asset) as image:
                image.seek(0)
                self.assertEqual((20, 40, 60, 255), image.convert("RGBA").getpixel((12 + 5, 20)))

            manifest = json.loads(result["manifest"].read_text(encoding="utf-8"))
            self.assertEqual("review", manifest["status"])
            self.assertTrue(result["diffContactSheet"].is_file())
            self.assertTrue((result["themeDir"] / "qa" / "selection-diffs" / "idle.png").is_file())
            self.assertEqual("adopt", manifest["states"]["idle"]["decision"])
            self.assertEqual("reject", manifest["states"]["error"]["decision"])
            self.assertEqual("webui-static-apng", manifest["states"]["idle"]["source"])
            self.assertEqual("current-theme", manifest["states"]["error"]["source"])
            self.assertEqual(
                (result["themeDir"] / "qa" / "selection-diffs" / "idle.png").as_posix(),
                manifest["states"]["idle"]["diffPreview"],
            )

    def test_build_selection_theme_rejects_incomplete_selection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            theme_dir = self.write_theme(root)
            selection_path = self.write_selection(root, blank_state="thinking")

            with self.assertRaisesRegex(ValueError, "selection for thinking is not decided"):
                selection_theme.build_selection_theme(
                    theme_dir=theme_dir,
                    selection_path=selection_path,
                    output_dir=root / "out" / "theme",
                    package_path=root / "out" / "akari-webui-selection.zip",
                )

    def test_write_static_apng_preserves_source_foreground_aspect_ratio(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.png"
            output = root / "out.apng"
            image = Image.new("RGBA", (1024, 1024), (0, 0, 0, 0))
            for x in range(250, 750):
                for y in range(100, 900):
                    image.putpixel((x, y), (200, 120, 80, 255))
            image.save(source)

            selection_theme.write_static_apng(source, output)

            with Image.open(output) as result:
                self.assertTrue(result.is_animated)
                self.assertEqual(2, result.n_frames)
                result.seek(0)
                frame = result.convert("RGBA")
            bbox = frame.getchannel("A").getbbox()
            self.assertIsNotNone(bbox)
            self.assertGreaterEqual(bbox[0], selection_theme.STATIC_APNG_PADDING_PX)
            self.assertGreaterEqual(bbox[1], selection_theme.STATIC_APNG_PADDING_PX)
            self.assertLessEqual(bbox[2], hq.RUNTIME_SIZE[0] - selection_theme.STATIC_APNG_PADDING_PX)
            self.assertLessEqual(bbox[3], hq.RUNTIME_SIZE[1] - selection_theme.STATIC_APNG_PADDING_PX)
            width = bbox[2] - bbox[0]
            height = bbox[3] - bbox[1]
            self.assertAlmostEqual(500 / 800, width / height, delta=0.01)
