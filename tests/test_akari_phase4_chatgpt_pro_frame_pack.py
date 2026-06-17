import json
import tarfile
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from pet_akari import akari_phase4_chatgpt_pro_frame_pack as frame_pack


class Phase4ChatgptProFramePackTests(unittest.TestCase):
    def write_keypose_source(self, root, *, omit=None):
        source_dir = root / "pro-faithful-raw"
        source_dir.mkdir()
        colors = {
            "idle": (255, 120, 80),
            "thinking": (40, 80, 120),
            "working": (60, 100, 140),
            "notification": (100, 140, 180),
            "attention": (80, 120, 160),
            "error": (120, 160, 200),
            "sleeping": (140, 180, 220),
        }
        for state, color in colors.items():
            if state == omit:
                continue
            image = Image.new("RGB", (48, 72), "white")
            for x in range(12, 36):
                for y in range(14, 58):
                    image.putpixel((x, y), color)
            image.save(source_dir / f"{state}.png")
        return source_dir

    def write_base_reference(self, root):
        base = root / "000-base.png"
        image = Image.new("RGB", (48, 72), "white")
        for x in range(10, 38):
            for y in range(12, 60):
                image.putpixel((x, y), (255, 120, 80))
        image.save(base)
        return base

    def write_preview_run(self, root):
        preview = root / "preview" / "qa"
        preview.mkdir(parents=True)
        Image.new("RGB", (64, 64), "black").save(preview / "contact-sheet.png")
        (preview / "keypose-motion-summary.json").write_text('{"ok": true}\n', encoding="utf-8")
        return root / "preview"

    def test_collect_keypose_images_finds_all_states(self):
        with tempfile.TemporaryDirectory() as tmp:
            source_dir = self.write_keypose_source(Path(tmp))

            images = frame_pack.collect_keypose_images(source_dir)

            self.assertEqual(list(frame_pack.REQUIRED_STATES), list(images))
            self.assertEqual(source_dir / "working.png", images["working"])

    def test_collect_keypose_images_rejects_missing_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            source_dir = self.write_keypose_source(Path(tmp), omit="sleeping")

            with self.assertRaisesRegex(FileNotFoundError, "sleeping"):
                frame_pack.collect_keypose_images(source_dir)

    def test_write_manifest_describes_inbetween_output_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            pack_dir = Path(tmp) / "akari-pro-inbetween-frame-pack"

            manifest_path = frame_pack.write_manifest(pack_dir)

            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(1, manifest["schemaVersion"])
            self.assertEqual("akari-pro-inbetween-frame-pack", manifest["packId"])
            self.assertEqual(8, manifest["outputContract"]["frameCountPerState"])
            self.assertEqual("clawd-on-desk/CONTRACT.md", manifest["clawdContract"])
            self.assertEqual(
                list(frame_pack.REQUIRED_STATES),
                [entry["state"] for entry in manifest["states"]],
            )
            self.assertEqual("keyposes/working.png", manifest["states"][2]["input"])
            self.assertEqual("outputs/strips/working-8f.png", manifest["states"][2]["preferredStripOutput"])
            self.assertIn("desk", manifest["states"][2]["motionBrief"])

    def test_write_prompt_uses_two_step_pro_flow_and_clawd_constraints(self):
        with tempfile.TemporaryDirectory() as tmp:
            pack_dir = Path(tmp) / "akari-pro-inbetween-frame-pack"

            prompt_path = frame_pack.write_prompt(pack_dir)

            prompt = prompt_path.read_text(encoding="utf-8")
            self.assertIn("最初の応答では画像生成しない", prompt)
            self.assertIn("8コマ", prompt)
            self.assertIn("clawd-on-desk", prompt)
            self.assertIn("384x480", prompt)
            self.assertIn("outputs/strips/working-8f.png", prompt)
            self.assertIn("単なる複製ではなく", prompt)
            self.assertIn("akari-pro-inbetween-frames.tar.gz", prompt)

    def test_build_frame_pack_copies_assets_docs_preview_and_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_dir = self.write_keypose_source(root)
            base = self.write_base_reference(root)
            preview = self.write_preview_run(root)

            result = frame_pack.build_frame_pack(
                source_dir=source_dir,
                output_root=root / "out",
                pack_id="akari-pro-inbetween-frame-pack",
                base_reference=base,
                preview_run_dir=preview,
                preview_size=64,
            )

            pack_dir = result["packDir"]
            self.assertTrue((pack_dir / "PROMPT.md").is_file())
            self.assertTrue((pack_dir / "MANIFEST.json").is_file())
            self.assertTrue((pack_dir / "clawd-on-desk" / "CONTRACT.md").is_file())
            self.assertTrue((pack_dir / "outputs-expected" / "README.md").is_file())
            self.assertTrue((pack_dir / "references" / "pro-idle-reference.png").is_file())
            self.assertTrue((pack_dir / "references" / "stage2-base.png").is_file())
            self.assertTrue((pack_dir / "keyposes" / "idle.png").is_file())
            self.assertTrue((pack_dir / "keyposes" / "working.png").is_file())
            self.assertTrue((pack_dir / "local-preview" / "current-local-motion-contact-sheet.png").is_file())
            self.assertTrue((pack_dir / "local-preview" / "keypose-motion-summary.json").is_file())
            self.assertTrue((pack_dir / "contact-sheets" / "keyposes.png").is_file())
            self.assertTrue((pack_dir / "tree.txt").is_file())
            self.assertTrue(result["archive"].is_file())

            with tarfile.open(result["archive"], "r:gz") as archive:
                names = set(archive.getnames())
            self.assertIn("akari-pro-inbetween-frame-pack/PROMPT.md", names)
            self.assertIn("akari-pro-inbetween-frame-pack/MANIFEST.json", names)
            self.assertIn("akari-pro-inbetween-frame-pack/clawd-on-desk/CONTRACT.md", names)
            self.assertIn("akari-pro-inbetween-frame-pack/keyposes/sleeping.png", names)
            self.assertIn("akari-pro-inbetween-frame-pack/references/stage2-base.png", names)
            self.assertIn("akari-pro-inbetween-frame-pack/contact-sheets/keyposes.png", names)

    def test_write_keypose_contact_sheet_renders_keyposes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_dir = self.write_keypose_source(root)
            pack_dir = root / "pack"
            copied = frame_pack.copy_pack_assets(source_dir, pack_dir, base_reference=None, preview_run_dir=None)

            contact_sheet = frame_pack.write_keypose_contact_sheet(
                pack_dir / "contact-sheets" / "keyposes.png",
                copied["keyposes"],
                preview_size=64,
            )

            self.assertTrue(contact_sheet.is_file())
            with Image.open(contact_sheet) as image:
                self.assertEqual((64 * 4, (64 + 22) * 2), image.size)
                self.assertEqual("RGB", image.mode)

    def test_build_parser_accepts_build_command(self):
        args = frame_pack._build_parser().parse_args(
            [
                "build",
                "--source-dir",
                "pro-faithful-raw",
                "--output-root",
                "out",
                "--pack-id",
                "frame-pack",
                "--base-reference",
                "base.png",
                "--preview-run-dir",
                "preview",
                "--preview-size",
                "96",
                "--no-local-preview",
            ]
        )

        self.assertEqual("build", args.command)
        self.assertEqual(Path("pro-faithful-raw"), args.source_dir)
        self.assertEqual(Path("out"), args.output_root)
        self.assertEqual("frame-pack", args.pack_id)
        self.assertEqual(Path("base.png"), args.base_reference)
        self.assertEqual(Path("preview"), args.preview_run_dir)
        self.assertEqual(96, args.preview_size)
        self.assertTrue(args.no_local_preview)


if __name__ == "__main__":
    unittest.main()
