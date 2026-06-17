import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from pet_akari import akari_phase4_webui_base_import as importer


class Phase4WebuiBaseImportTests(unittest.TestCase):
    def write_state_inputs(self, root):
        input_dir = root / "akari_clawd_base_images"
        input_dir.mkdir()
        for name in [
            "1-idle.png",
            "2-thinking.png",
            "3-working.png",
            "4-attention.png",
            "5-notification.png",
            "6-error.png",
            "7-sleeping.png",
            "000-base.png",
            "states_overview.png",
        ]:
            Image.new("RGB", (16, 16), "white").save(input_dir / name)
        return input_dir

    def test_collect_state_images_resolves_required_states(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_dir = self.write_state_inputs(root)

            states = importer.collect_state_images(input_dir)

            self.assertEqual(list(states), list(importer.REQUIRED_STATES))
            self.assertEqual("1-idle.png", states["idle"].name)
            self.assertEqual("5-notification.png", states["notification"].name)
            self.assertNotIn("base", states)

    def test_collect_state_images_fails_when_required_state_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_dir = self.write_state_inputs(root)
            (input_dir / "5-notification.png").unlink()

            with self.assertRaisesRegex(ValueError, "missing required state image: notification"):
                importer.collect_state_images(input_dir)

    def test_write_json_creates_parent_and_sorts_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "qa" / "validation.json"

            importer.write_json(output, {"b": 2, "a": 1})

            self.assertEqual({"a": 1, "b": 2}, json.loads(output.read_text(encoding="utf-8")))
            self.assertTrue(output.read_text(encoding="utf-8").endswith("\n"))
