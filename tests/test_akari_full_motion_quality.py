import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageChops
from test_clawd_hq_theme import temporary_theme_sizes

from pet_akari import akari_full_motion_quality as fq
from pet_akari import clawd_hq_theme as hq


def semitransparent_split_sample(size=(120, 120)):
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    for y in range(10, 45):
        for x in range(45, 75):
            alpha = 128 if y in (43, 44) else 255
            image.putpixel((x, y), (255, 0, 0, alpha))
    for y in range(45, 105):
        for x in range(35, 85):
            alpha = 128 if y in (45, 46) else 255
            image.putpixel((x, y), (0, 0, 255, alpha))
    return image


class AkariFullMotionQualityTests(unittest.TestCase):
    def test_build_motion_contract_uses_only_true_frames(self):
        contract = fq.build_motion_contract()

        self.assertEqual(set(contract["states"]), set(hq.CORE_STATES))
        for state in hq.CORE_STATES:
            self.assertEqual(contract["states"][state]["durationMs"], 63)
            self.assertEqual(contract["states"][state]["inbetweens"], 0)
            self.assertEqual(contract["states"][state]["renderedFrames"], 64)

    def test_prepare_run_creates_staging_without_touching_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "run"
            outputs_dir = root / "outputs" / "akari-hq-apng-theme"
            outputs_dir.mkdir(parents=True)
            sentinel = outputs_dir / "sentinel.txt"
            sentinel.write_text("keep\n", encoding="utf-8")

            result = fq.prepare_run(run_dir, outputs_dir=outputs_dir)

            self.assertEqual(result.run_dir, run_dir)
            self.assertTrue((run_dir / "motion-contract.json").is_file())
            self.assertTrue((run_dir / "frames").is_dir())
            self.assertTrue((run_dir / "masters").is_dir())
            self.assertTrue((run_dir / "staging-theme").is_dir())
            self.assertTrue((run_dir / "qa" / "metrics").is_dir())
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep\n")

    def test_preflight_reports_missing_required_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = fq.run_preflight(
                source_root=root / "missing-source",
                clawd_root=root / "missing-clawd",
                outputs_dir=root / "outputs",
            )

            self.assertFalse(result.ok)
            self.assertIn("source_root", result.missing)
            self.assertIn("clawd_validator", result.missing)
            self.assertIn("source recovery", "\n".join(result.recovery))

    def test_measure_frame_metrics_reports_bbox_area_and_baseline(self):
        image = Image.new("RGBA", (100, 120), (0, 0, 0, 0))
        for y in range(40, 100):
            for x in range(30, 70):
                image.putpixel((x, y), (255, 0, 0, 255))

        metrics = fq.measure_frame_metrics(image)

        self.assertEqual(metrics.bbox, (30, 40, 70, 100))
        self.assertEqual(metrics.visible_width, 40)
        self.assertEqual(metrics.visible_height, 60)
        self.assertEqual(metrics.alpha_area, 2400)
        self.assertEqual(metrics.upper_alpha_area, 880)
        self.assertEqual(metrics.upper_visible_width, 40)
        self.assertEqual(metrics.baseline_y, 99)

    def test_sleeping_size_gate_rejects_shrunken_sleeping(self):
        standing = fq.FrameMetrics(
            bbox=(10, 10, 90, 110),
            visible_width=80,
            visible_height=100,
            alpha_area=8000,
            upper_alpha_area=3040,
            upper_visible_width=80,
            baseline_y=109,
            center_x=50.0,
            center_y=70.0,
        )
        sleeping = fq.FrameMetrics(
            bbox=(35, 70, 65, 105),
            visible_width=30,
            visible_height=35,
            alpha_area=1050,
            upper_alpha_area=390,
            upper_visible_width=30,
            baseline_y=104,
            center_x=50.0,
            center_y=90.0,
        )

        gate = fq.evaluate_sleeping_size_gate(
            sleeping=sleeping,
            standing_reference=[standing],
            min_area_ratio=0.55,
            min_head_readability_ratio=0.45,
        )

        self.assertFalse(gate["ok"])
        self.assertLess(gate["areaRatio"], 0.55)

    def test_extract_basic_layers_erases_moved_regions_from_body_base(self):
        image = Image.new("RGBA", (100, 120), (0, 0, 0, 0))
        for y in range(10, 45):
            for x in range(35, 65):
                image.putpixel((x, y), (255, 0, 0, 255))
        for y in range(45, 105):
            for x in range(25, 75):
                image.putpixel((x, y), (0, 0, 255, 255))

        layers = fq.extract_basic_layers(image)

        self.assertIn("body_base", layers)
        self.assertIn("head", layers)
        self.assertIn("torso_base", layers)
        self.assertIn("right_side", layers)
        self.assertEqual(layers["body_base"].size, image.size)
        self.assertIsNotNone(layers["head"].getchannel("A").getbbox())
        self.assertIsNone(layers["body_base"].crop((35, 10, 65, 45)).getchannel("A").getbbox())
        self.assertEqual(fq.layer_overlap_pixels(layers["torso_base"], layers["right_side"]), 0)

    def test_render_puppet_frame_identity_preserves_semitransparent_split_pixels(self):
        image = semitransparent_split_sample()

        rendered = fq.render_puppet_frame(image, "idle", frame_index=0, frame_count=8)

        self.assertIsNone(ImageChops.difference(image, rendered).getbbox())

    def test_layer_partition_report_rejects_body_residual_overlap(self):
        image = semitransparent_split_sample()

        layers = fq.extract_basic_layers(image)
        report = fq.build_layer_partition_report(layers)

        self.assertTrue(report["ok"])
        self.assertEqual(report["bodyResidualOverlapPixels"], 0)
        self.assertEqual(report["opaqueOverlapPixels"], 0)
        self.assertEqual(report["unexpectedOverlapPixels"], 0)
        self.assertEqual(report["allowedFeatherOverlapPixels"], 0)

    def test_render_state_frames_uses_all_source_anchors_without_crossfade(self):
        with (
            tempfile.TemporaryDirectory() as tmp,
            temporary_theme_sizes(
                master_size=(128, 160),
                runtime_size=(32, 40),
            ),
        ):
            root = Path(tmp)
            sources = []
            for anchor_index, red in enumerate((80, 140, 220)):
                source = root / f"source-{anchor_index}.png"
                image = Image.new("RGBA", hq.MASTER_SIZE, (0, 0, 0, 0))
                for y in range(20, 130):
                    for x in range(40 + anchor_index * 2, 90 + anchor_index * 2):
                        image.putpixel((x, y), (red, 100, 80, 255))
                image.save(source)
                sources.append(source)

            outputs = fq.render_state_frames("idle", sources, root / "frames" / "idle", frame_count=8)

            self.assertEqual(len(outputs), 8)
            self.assertTrue(all(path.is_file() for path in outputs))
            self.assertTrue((root / "frames" / "idle" / "layer-partition.json").is_file())
            hashes = {hq.sha256_file(path) for path in outputs}
            self.assertGreaterEqual(len(hashes), 3)

    def test_working_motion_has_no_adjacent_runtime_plateaus_with_six_frame_segments(self):
        with (
            tempfile.TemporaryDirectory() as tmp,
            temporary_theme_sizes(
                master_size=(128, 160),
                runtime_size=(32, 40),
            ),
        ):
            root = Path(tmp)
            sources = []
            for anchor_index in range(12):
                source = root / f"source-{anchor_index}.png"
                image = Image.new("RGBA", hq.MASTER_SIZE, (0, 0, 0, 0))
                for y in range(20, 130):
                    for x in range(36 + anchor_index, 86 + anchor_index):
                        image.putpixel((x, y), (255, 20 + anchor_index * 10, 10, 255))
                image.save(source)
                sources.append(source)

            outputs = fq.render_state_frames("working", sources, root / "frames" / "working", frame_count=64)

            duplicates = []
            previous = None
            for index, path in enumerate(outputs, start=1):
                with Image.open(path) as image:
                    runtime = image.convert("RGBA").resize(hq.RUNTIME_SIZE, hq._resample_filter())
                current = runtime.tobytes()
                if current == previous:
                    duplicates.append((index - 1, index))
                previous = current
            self.assertEqual(duplicates, [])

    def test_attention_motion_does_not_open_horizontal_alpha_gaps(self):
        with (
            tempfile.TemporaryDirectory() as tmp,
            temporary_theme_sizes(
                master_size=(128, 160),
                runtime_size=(32, 40),
            ),
        ):
            root = Path(tmp)
            source = root / "source.png"
            image = Image.new("RGBA", hq.MASTER_SIZE, (0, 0, 0, 0))
            for y in range(20, 130):
                for x in range(36, 86):
                    image.putpixel((x, y), (255, 0, 0, 255))
            image.save(source)

            outputs = fq.render_state_frames("attention", [source], root / "frames" / "attention", frame_count=8)

            gap_rows = []
            for path in outputs:
                with Image.open(path) as frame:
                    alpha = frame.convert("RGBA").getchannel("A")
                bbox = alpha.getbbox()
                self.assertIsNotNone(bbox)
                left, top, right, bottom = bbox
                for y in range(top, bottom):
                    if not any(alpha.getpixel((x, y)) for x in range(left, right)):
                        gap_rows.append((path.name, y))
            self.assertEqual(gap_rows, [])

    def test_transform_layer_clips_negative_offsets(self):
        image = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
        for y in range(0, 12):
            for x in range(0, 12):
                image.putpixel((x, y), (255, 0, 0, 255))

        moved = fq._transform_layer(image, fq.Transform(dx=-20, dy=-20))

        self.assertEqual(moved.size, image.size)

    def test_side_motion_does_not_leave_opaque_torso_duplicate(self):
        image = Image.new("RGBA", (120, 120), (0, 0, 0, 0))
        for y in range(10, 45):
            for x in range(45, 75):
                image.putpixel((x, y), (255, 0, 0, 255))
        for y in range(45, 105):
            for x in range(35, 85):
                image.putpixel((x, y), (0, 0, 255, 255))

        layers = fq.extract_basic_layers(image)
        canvas = Image.new("RGBA", image.size, (0, 0, 0, 0))
        canvas.alpha_composite(layers["torso_base"])
        canvas.alpha_composite(fq._transform_layer(layers["right_side"], fq.Transform(dy=-35)))

        self.assertIsNone(canvas.crop((66, 71, 85, 105)).getchannel("A").getbbox())

    def test_state_specific_recipes_do_not_fall_through_to_idle_breathing(self):
        self.assertEqual(
            fq.recipe_transform("sleeping", "left_side", 1, 4),
            fq.recipe_transform("sleeping", "torso_base", 1, 4),
        )
        self.assertEqual(
            fq.recipe_transform("sleeping", "right_side", 1, 4),
            fq.recipe_transform("sleeping", "torso_base", 1, 4),
        )
        self.assertEqual(
            fq.recipe_transform("working", "head", 1, 4),
            fq.recipe_transform("working", "torso_base", 1, 4),
        )

    def test_ghosting_score_flags_double_contours(self):
        clean = Image.new("RGBA", (80, 80), (0, 0, 0, 0))
        for y in range(20, 60):
            for x in range(25, 55):
                clean.putpixel((x, y), (255, 0, 0, 255))
        ghosted = clean.copy()
        for y in range(20, 60):
            for x in range(35, 65):
                ghosted.putpixel((x, y), (255, 0, 0, 100))

        self.assertLess(fq.ghosting_score(clean), fq.ghosting_score(ghosted))

    def test_write_seam_probe_records_identity_and_motion_samples(self):
        with (
            tempfile.TemporaryDirectory() as tmp,
            temporary_theme_sizes(
                master_size=(128, 160),
                runtime_size=(32, 40),
            ),
        ):
            root = Path(tmp)
            source_root = root / "sources"
            for state in hq.CORE_STATES:
                state_dir = source_root / state
                state_dir.mkdir(parents=True)
                image = Image.new("RGBA", hq.MASTER_SIZE, (0, 0, 0, 0))
                for y in range(20, 130):
                    for x in range(36, 86):
                        alpha = 128 if y in (62, 63) else 255
                        image.putpixel((x, y), (255, 60, 20, alpha))
                image.save(state_dir / "01.png")

            report_path = fq.write_seam_probe(source_root=source_root, output_dir=root / "probe")
            report = json.loads(report_path.read_text(encoding="utf-8"))

            self.assertEqual(
                {sample["state"] for sample in report["samples"]},
                {"idle", "working", "notification", "attention"},
            )
            self.assertTrue((root / "probe" / "idle-00-source.png").is_file())
            self.assertTrue((root / "probe" / "working-02-exact-dark.png").is_file())
            for sample in report["samples"]:
                self.assertIn("legacyMeanAbsDiff", sample)
                self.assertIn("exactMeanAbsDiff", sample)
                self.assertEqual(sample["partition"]["bodyResidualOverlapPixels"], 0)

    def test_body_base_prevents_opaque_duplicate_after_moving_head(self):
        image = Image.new("RGBA", (120, 120), (0, 0, 0, 0))
        for y in range(10, 45):
            for x in range(45, 75):
                image.putpixel((x, y), (255, 0, 0, 255))
        for y in range(45, 105):
            for x in range(35, 85):
                image.putpixel((x, y), (0, 0, 255, 255))

        layers = fq.extract_basic_layers(image)
        canvas = Image.new("RGBA", image.size, (0, 0, 0, 0))
        canvas.alpha_composite(layers["body_base"])
        canvas.alpha_composite(fq._transform_layer(layers["head"], fq.Transform(dx=40)))

        self.assertIsNone(canvas.crop((45, 10, 75, 45)).getchannel("A").getbbox())

    def test_state_quality_report_marks_needs_human_review_for_uncertain_gate(self):
        report = fq.build_state_quality_report(
            state="sleeping",
            metrics={"scale": {"ok": True}, "ghosting": {"ok": True}, "semantics": {"ok": None}},
        )

        self.assertEqual(report["status"], "needs-human-review")

    def test_evaluate_rendered_state_can_pass_semantics_with_visual_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            frame_paths = []
            for index in range(8):
                frame = Image.new("RGBA", (64, 80), (0, 0, 0, 0))
                for y in range(20, 70):
                    for x in range(20 + index, 44 + index):
                        frame.putpixel((x, y), (255, 0, 0, 255))
                path = root / f"{index:03d}.png"
                frame.save(path)
                frame_paths.append(path)
            (root / "layer-partition.json").write_text(
                json.dumps([{"ok": True, "maxOverlapPixels": 0, "overlaps": {}}]) + "\n",
                encoding="utf-8",
            )

            standing = [fq.measure_frame_metrics(Image.open(frame_paths[0]).convert("RGBA"))]
            report = fq.evaluate_rendered_state(
                "idle",
                frame_paths,
                standing,
                visual_approval={"states": {"idle": {"approved": True, "notes": "synthetic ok"}}},
            )

            self.assertEqual(report["status"], "pass")

    def test_export_staging_theme_uses_zero_inbetweens_contract(self):
        with (
            tempfile.TemporaryDirectory() as tmp,
            temporary_theme_sizes(
                master_size=(128, 160),
                runtime_size=(32, 40),
            ),
        ):
            root = Path(tmp)
            run = fq.prepare_run(root / "run", outputs_dir=root / "outputs")
            for state in hq.CORE_STATES:
                state_dir = run.masters_dir / state
                state_dir.mkdir(parents=True)
                for index in range(3):
                    frame = Image.new("RGBA", hq.MASTER_SIZE, (0, 0, 0, 0))
                    for y in range(30, 120):
                        for x in range(40, 90):
                            frame.putpixel((x + index, y), (255, 0, 0, 255))
                    frame.save(state_dir / f"{index + 1:03d}.png")

            fq.export_staging_theme(run, frame_count=3)

            manifest = json.loads((run.staging_theme_dir / "qa" / "build-manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["states"]["idle"]["inbetweens"], 0)
            self.assertEqual(manifest["states"]["idle"]["encodedFrames"], 3)

    def test_promote_requires_all_states_to_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = fq.prepare_run(root / "run", outputs_dir=root / "outputs")
            (run.staging_theme_dir / "theme.json").write_text("{}\n", encoding="utf-8")
            summary = {"states": {state: {"status": "pass"} for state in hq.CORE_STATES}}
            summary["states"]["sleeping"] = {"status": "needs-human-review"}
            approval = {"states": {state: {"approved": True} for state in hq.CORE_STATES}}

            with self.assertRaisesRegex(ValueError, "not all states passed"):
                fq.promote_staging_theme(run, summary, visual_approval=approval)

    def test_promote_requires_visual_approval_for_every_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = fq.prepare_run(root / "run", outputs_dir=root / "outputs")
            (run.staging_theme_dir / "theme.json").write_text("{}\n", encoding="utf-8")
            summary = {"states": {state: {"status": "pass"} for state in hq.CORE_STATES}}
            approval = {"states": {state: {"approved": True} for state in hq.CORE_STATES if state != "sleeping"}}

            with self.assertRaisesRegex(ValueError, "visual approval"):
                fq.promote_staging_theme(run, summary, visual_approval=approval)

    def test_write_run_summary_records_paths_and_states(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = fq.prepare_run(root / "run", outputs_dir=root / "outputs")
            states = {state: {"status": "pass"} for state in hq.CORE_STATES}
            approval = {"states": {state: {"approved": True} for state in hq.CORE_STATES}}

            path = fq.write_run_summary(run, states=states, promoted=False, visual_approval=approval)

            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertFalse(data["promoted"])
            self.assertTrue(data["ok"])
            self.assertTrue(data["visualApproved"])
            self.assertEqual(set(data["states"]), set(hq.CORE_STATES))
            self.assertEqual(data["paths"]["stagingTheme"], str(run.staging_theme_dir))

    def test_default_package_path_appends_zip_without_replacing_dotted_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            self.assertEqual(fq._default_package_path(root / "custom.theme"), root / "custom.theme.zip")

    def test_render_all_states_copies_layer_partition_reports_to_masters(self):
        with (
            tempfile.TemporaryDirectory() as tmp,
            temporary_theme_sizes(
                master_size=(128, 160),
                runtime_size=(32, 40),
            ),
        ):
            root = Path(tmp)
            source_root = root / "source"
            run = fq.prepare_run(root / "run", outputs_dir=root / "outputs")
            for state in hq.CORE_STATES:
                state_dir = source_root / state
                state_dir.mkdir(parents=True)
                for anchor_index in range(8):
                    frame = Image.new("RGBA", hq.MASTER_SIZE, (0, 0, 0, 0))
                    for y in range(20, 130):
                        for x in range(40 + anchor_index, 90 + anchor_index):
                            frame.putpixel((x, y), (255 - anchor_index, 0, 0, 255))
                    frame.save(state_dir / f"{anchor_index + 1:03d}.png")

            rendered = fq.render_all_states(run, source_root=source_root, frame_count=8)

            self.assertEqual(set(rendered), set(hq.CORE_STATES))
            self.assertTrue((run.masters_dir / "idle" / "layer-partition.json").is_file())

    def test_run_pipeline_promotes_custom_outputs_and_package_path(self):
        with (
            tempfile.TemporaryDirectory() as tmp,
            temporary_theme_sizes(
                master_size=(128, 160),
                runtime_size=(32, 40),
            ),
        ):
            root = Path(tmp)
            source_root = root / "source"
            clawd_root = root / "clawd"
            outputs_dir = root / "custom-theme"
            package_path = root / "custom-theme.zip"
            approval_path = root / "visual-approval.json"
            (clawd_root / "scripts").mkdir(parents=True)
            (clawd_root / "scripts" / "validate-theme.js").write_text(
                "// test validator placeholder\n", encoding="utf-8"
            )
            (clawd_root / "assets" / "svg").mkdir(parents=True)
            approval_path.write_text(
                json.dumps(
                    {"states": {state: {"approved": True, "notes": "synthetic ok"} for state in hq.CORE_STATES}},
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            for state in hq.CORE_STATES:
                state_dir = source_root / state
                state_dir.mkdir(parents=True)
                for anchor_index in range(8):
                    frame = Image.new("RGBA", hq.MASTER_SIZE, (0, 0, 0, 0))
                    for y in range(20, 130):
                        for x in range(36 + anchor_index * 2, 86 + anchor_index * 2):
                            frame.putpixel((x, y), (255, 20 + anchor_index * 20, 10, 255))
                    frame.save(state_dir / f"{anchor_index + 1:03d}.png")

            summary_path = fq.run_pipeline(
                run_dir=root / "run",
                source_root=source_root,
                clawd_root=clawd_root,
                outputs_dir=outputs_dir,
                promote=True,
                visual_approval_path=approval_path,
                package_path=package_path,
            )

            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            self.assertTrue(summary["ok"])
            self.assertTrue(summary["promoted"])
            self.assertTrue((outputs_dir / "theme.json").is_file())
            self.assertTrue(package_path.is_file())
