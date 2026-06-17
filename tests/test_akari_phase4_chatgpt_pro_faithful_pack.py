import json
import tarfile
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

    def test_build_faithful_pack_copies_assets_and_writes_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_dir = self.write_include_hat_source(root)

            result = faithful_pack.build_faithful_pack(
                source_dir=source_dir,
                output_root=root / "out",
                pack_id="akari-stage2-faithful-pack",
                preview_size=64,
            )

            pack_dir = result["packDir"]
            self.assertTrue((pack_dir / "PROMPT.md").is_file())
            self.assertTrue((pack_dir / "MANIFEST.json").is_file())
            self.assertTrue((pack_dir / "references" / "000-base.png").is_file())
            self.assertTrue((pack_dir / "state_bases" / "idle.png").is_file())
            self.assertTrue((pack_dir / "state_bases" / "working.png").is_file())
            self.assertTrue(result["contactSheet"].is_file())
            self.assertTrue(result["archive"].is_file())

            with tarfile.open(result["archive"], "r:gz") as archive:
                names = set(archive.getnames())
            self.assertIn("akari-stage2-faithful-pack/PROMPT.md", names)
            self.assertIn("akari-stage2-faithful-pack/MANIFEST.json", names)
            self.assertIn("akari-stage2-faithful-pack/references/000-base.png", names)
            self.assertIn("akari-stage2-faithful-pack/state_bases/sleeping.png", names)
            self.assertIn("akari-stage2-faithful-pack/contact-sheets/state-bases.png", names)

    def test_write_contact_sheet_renders_state_bases(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_dir = self.write_include_hat_source(root)
            pack_dir = root / "pack"
            copied = faithful_pack.copy_pack_assets(source_dir, pack_dir)

            contact_sheet = faithful_pack.write_state_base_contact_sheet(
                pack_dir / "contact-sheets" / "state-bases.png",
                copied["stateBases"],
                preview_size=64,
            )

            self.assertTrue(contact_sheet.is_file())
            with Image.open(contact_sheet) as image:
                self.assertEqual((64 * 4, (64 + 22) * 2), image.size)
                self.assertEqual("RGB", image.mode)
