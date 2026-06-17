import json
import tempfile
import unittest
from pathlib import Path

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
