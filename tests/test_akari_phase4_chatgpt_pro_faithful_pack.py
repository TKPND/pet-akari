import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from pet_akari import akari_phase4_chatgpt_pro_faithful_pack as faithful_pack


class Phase4ChatgptProFaithfulPackTests(unittest.TestCase):
    def write_include_hat_source(self, root, *, omit=None):
        source_dir = root / "include_hat"
        source_dir.mkdir()
        files = {
            "000-base.png": (255, 120, 80),
            "1-idle.png": (20, 40, 60),
            "2-thinking.png": (40, 80, 120),
            "3-working.png": (60, 100, 140),
            "4-attention.png": (80, 120, 160),
            "5-notification.png": (100, 140, 180),
            "6-error.png": (120, 160, 200),
            "7-sleeping.png": (140, 180, 220),
        }
        for name, color in files.items():
            if name == omit:
                continue
            image = Image.new("RGB", (32, 48), "white")
            for x in range(8, 24):
                for y in range(10, 38):
                    image.putpixel((x, y), color)
            image.save(source_dir / name)
        return source_dir

    def test_collect_source_images_finds_base_and_all_states(self):
        with tempfile.TemporaryDirectory() as tmp:
            source_dir = self.write_include_hat_source(Path(tmp))

            images = faithful_pack.collect_source_images(source_dir)

            self.assertEqual(source_dir / "000-base.png", images["base"])
            self.assertEqual(list(faithful_pack.REQUIRED_STATES), list(images["states"]))
            self.assertEqual(source_dir / "3-working.png", images["states"]["working"])

    def test_collect_source_images_rejects_missing_state_base(self):
        with tempfile.TemporaryDirectory() as tmp:
            source_dir = self.write_include_hat_source(Path(tmp), omit="7-sleeping.png")

            with self.assertRaisesRegex(FileNotFoundError, "7-sleeping.png"):
                faithful_pack.collect_source_images(source_dir)

    def test_build_manifest_lists_a_faithful_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            pack_dir = Path(tmp) / "akari-stage2-faithful-pack"

            manifest_path = faithful_pack.write_manifest(pack_dir)

            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(1, manifest["schemaVersion"])
            self.assertEqual("akari-stage2-faithful-pack", manifest["packId"])
            self.assertEqual("A Faithful", manifest["candidateLane"])
            self.assertEqual("references/000-base.png", manifest["referenceImage"])
            self.assertEqual(
                list(faithful_pack.REQUIRED_STATES),
                [entry["state"] for entry in manifest["states"]],
            )
            self.assertEqual("state_bases/working.png", manifest["states"][2]["input"])
            self.assertEqual("working-a-faithful.png", manifest["states"][2]["outputName"])
            self.assertIn("desk", manifest["states"][2]["stateIntent"])

    def test_write_prompt_uses_two_step_chatgpt_pro_flow(self):
        with tempfile.TemporaryDirectory() as tmp:
            pack_dir = Path(tmp) / "akari-stage2-faithful-pack"

            prompt_path = faithful_pack.write_prompt(pack_dir)

            prompt = prompt_path.read_text(encoding="utf-8")
            self.assertIn("最初の応答では画像生成しない", prompt)
            self.assertIn("A Faithful", prompt)
            self.assertIn("references/000-base.png", prompt)
            self.assertIn("state_bases/working.png", prompt)
            self.assertIn("1024x1536", prompt)
            self.assertIn("transparent", prompt.lower())
            self.assertIn("ローカル側", prompt)
