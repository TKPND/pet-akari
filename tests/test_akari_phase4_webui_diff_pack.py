import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from pet_akari import akari_phase4_webui_diff_pack as diff_pack


class Phase4WebuiDiffPackTests(unittest.TestCase):
    def write_webui_import(self, root, *, status="review", state_order=None, omit_state=None):
        import_dir = root / "webui-base-001"
        normalized_dir = import_dir / "normalized"
        qa_dir = import_dir / "qa"
        normalized_dir.mkdir(parents=True)
        qa_dir.mkdir()
        state_order = list(diff_pack.REQUIRED_STATES) if state_order is None else state_order
        for state in diff_pack.REQUIRED_STATES:
            if state == omit_state:
                continue
            (normalized_dir / f"{state}.png").write_bytes(b"not-an-image-yet")
        validation = {
            "humanReview": {"visualAcceptance": "pending"},
            "schemaVersion": 1,
            "stateOrder": state_order,
            "status": status,
        }
        (qa_dir / "webui-base-import-validation.json").write_text(
            json.dumps(validation, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return import_dir

    def test_load_webui_import_accepts_review_pending(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            import_dir = self.write_webui_import(root)

            data = diff_pack.load_webui_import(import_dir)

            self.assertEqual("review", data["validation"]["status"])
            self.assertEqual(list(diff_pack.REQUIRED_STATES), list(data["normalizedPaths"]))
            self.assertEqual(import_dir / "normalized" / "idle.png", data["normalizedPaths"]["idle"])

    def test_load_webui_import_rejects_failed_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            import_dir = self.write_webui_import(root, status="fail")

            with self.assertRaisesRegex(ValueError, "WebUI import validation status is fail"):
                diff_pack.load_webui_import(import_dir)

    def test_load_webui_import_rejects_state_order_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bad_order = list(reversed(diff_pack.REQUIRED_STATES))
            import_dir = self.write_webui_import(root, state_order=bad_order)

            with self.assertRaisesRegex(ValueError, "WebUI import stateOrder must match hq.CORE_STATES"):
                diff_pack.load_webui_import(import_dir)

    def test_load_webui_import_rejects_missing_normalized_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            import_dir = self.write_webui_import(root, omit_state="notification")

            with self.assertRaisesRegex(FileNotFoundError, "notification.png"):
                diff_pack.load_webui_import(import_dir)

    def test_write_json_creates_parent_and_sorts_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "qa" / "manifest.json"

            diff_pack.write_json(output, {"b": 2, "a": 1})

            self.assertEqual({"a": 1, "b": 2}, json.loads(output.read_text(encoding="utf-8")))
            self.assertTrue(output.read_text(encoding="utf-8").endswith("\n"))

    def write_theme(self, root, *, omit_state=None):
        theme_dir = root / "theme"
        assets_dir = theme_dir / "assets"
        assets_dir.mkdir(parents=True)
        for index, state in enumerate(diff_pack.REQUIRED_STATES):
            if state == omit_state:
                continue
            first = Image.new("RGBA", (24, 32), (0, 0, 0, 0))
            second = Image.new("RGBA", (24, 32), (0, 0, 0, 0))
            first.putpixel((4 + index, 8), (255, 0, 0, 255))
            second.putpixel((10, 12 + index), (0, 128, 255, 255))
            first.save(
                assets_dir / f"akari-{state}.apng",
                format="PNG",
                save_all=True,
                append_images=[second],
                duration=[100, 100],
                loop=0,
            )
        return theme_dir

    def write_real_webui_import(self, root, *, omit_state=None):
        import_dir = root / "webui-base-001"
        normalized_dir = import_dir / "normalized"
        qa_dir = import_dir / "qa"
        normalized_dir.mkdir(parents=True)
        qa_dir.mkdir()
        for index, state in enumerate(diff_pack.REQUIRED_STATES):
            if state == omit_state:
                continue
            image = Image.new("RGBA", (30, 40), (0, 0, 0, 0))
            image.putpixel((12 + index, 16), (255, 120, 80, 255))
            image.save(normalized_dir / f"{state}.png")
        validation = {
            "humanReview": {"visualAcceptance": "pending"},
            "schemaVersion": 1,
            "stateOrder": list(diff_pack.REQUIRED_STATES),
            "status": "review",
        }
        (qa_dir / "webui-base-import-validation.json").write_text(
            json.dumps(validation, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return import_dir

    def test_collect_current_theme_frames_loads_required_apngs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            theme_dir = self.write_theme(root)

            frames = diff_pack.collect_current_theme_frames(theme_dir)

            self.assertEqual(list(diff_pack.REQUIRED_STATES), list(frames))
            self.assertEqual((24, 32), frames["idle"].size)
            self.assertEqual("RGBA", frames["idle"].mode)

    def test_collect_current_theme_frames_rejects_missing_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            theme_dir = self.write_theme(root, omit_state="error")

            with self.assertRaisesRegex(FileNotFoundError, "akari-error.apng"):
                diff_pack.collect_current_theme_frames(theme_dir)

    def test_image_metrics_records_bbox_and_opaque_ratio(self):
        image = Image.new("RGBA", (10, 12), (0, 0, 0, 0))
        image.putpixel((2, 3), (255, 0, 0, 255))
        image.putpixel((4, 6), (255, 0, 0, 255))

        metrics = diff_pack.image_metrics(image)

        self.assertEqual([10, 12], metrics["size"])
        self.assertEqual([2, 3, 5, 7], metrics["alphaBBox"])
        self.assertAlmostEqual(2 / 120, metrics["opaqueRatio"])

    def test_image_metrics_rejects_empty_alpha_bbox(self):
        image = Image.new("RGBA", (10, 12), (0, 0, 0, 0))

        with self.assertRaisesRegex(ValueError, "foreground bbox is empty"):
            diff_pack.image_metrics(image)

    def test_pixel_diff_summary_resizes_before_comparing(self):
        current = Image.new("RGBA", (12, 16), (0, 0, 0, 0))
        webui = Image.new("RGBA", (30, 40), (0, 0, 0, 0))
        current.putpixel((4, 4), (255, 0, 0, 255))
        webui.putpixel((10, 12), (0, 128, 255, 255))

        summary = diff_pack.pixel_diff_summary(current, webui, preview_size=32)

        self.assertEqual(32, summary["previewSize"])
        self.assertGreater(summary["changedPixels"], 0)
        self.assertGreater(summary["meanChannelDelta"], 0)

    def test_write_state_diff_writes_side_by_side_preview(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            current = Image.new("RGBA", (24, 32), (0, 0, 0, 0))
            webui = Image.new("RGBA", (30, 40), (0, 0, 0, 0))
            current.putpixel((8, 10), (255, 0, 0, 255))
            webui.putpixel((12, 16), (0, 128, 255, 255))

            output = diff_pack.write_state_diff(
                root / "state-diffs" / "idle.png", "idle", current, webui, preview_size=64
            )

            self.assertTrue(output.is_file())
            with Image.open(output) as image:
                self.assertEqual((64 * 2, 64 + 44), image.size)
                self.assertEqual("RGB", image.mode)

    def test_write_contact_sheet_writes_all_state_diffs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state_diff_paths = {}
            for state in diff_pack.REQUIRED_STATES:
                path = root / "state-diffs" / f"{state}.png"
                path.parent.mkdir(parents=True, exist_ok=True)
                Image.new("RGB", (64 * 2, 64 + 44), "white").save(path)
                state_diff_paths[state] = path

            output = diff_pack.write_contact_sheet(
                root / "qa" / "diff-contact-sheet-64.png", state_diff_paths, preview_size=64
            )

            self.assertTrue(output.is_file())
            with Image.open(output) as image:
                self.assertEqual((64 * 2 * 4, (64 + 44 + 22) * 2), image.size)
                self.assertEqual("RGB", image.mode)
