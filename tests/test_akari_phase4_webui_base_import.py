import json
import tarfile
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

    def checker_image(self, size=(24, 24)):
        image = Image.new("RGBA", size, (255, 255, 255, 255))
        pixels = image.load()
        colors = [(255, 255, 255, 255), (236, 238, 242, 255)]
        for y in range(size[1]):
            for x in range(size[0]):
                pixels[x, y] = colors[((x // 4) + (y // 4)) % 2]
        return image

    def test_remove_checker_background_removes_only_edge_connected_background(self):
        image = self.checker_image()
        pixels = image.load()
        for y in range(6, 18):
            for x in range(8, 16):
                pixels[x, y] = (255, 245, 230, 255)
        pixels[12, 12] = (236, 238, 242, 255)

        result, metrics = importer.remove_checker_background(image, tolerance=18)

        self.assertEqual(0, result.getpixel((0, 0))[3])
        self.assertEqual(255, result.getpixel((10, 10))[3])
        self.assertEqual(255, result.getpixel((12, 12))[3])
        self.assertEqual([8, 6, 16, 18], metrics["alphaBBox"])
        self.assertGreater(metrics["removedPixels"], 0)
        self.assertGreater(metrics["retainedOpaqueRatio"], 0)

    def test_alpha_bbox_fails_for_empty_foreground(self):
        image = self.checker_image()
        result, _metrics = importer.remove_checker_background(image, tolerance=18)

        with self.assertRaisesRegex(ValueError, "foreground bbox is empty"):
            importer.alpha_bbox(result)

    def test_normalize_foreground_fits_square_canvas_with_transparency(self):
        image = Image.new("RGBA", (30, 40), (0, 0, 0, 0))
        for y in range(10, 35):
            for x in range(8, 22):
                image.putpixel((x, y), (255, 120, 80, 255))

        normalized, metrics = importer.normalize_foreground(image, canvas_size=64, padding_ratio=0.1)

        self.assertEqual((64, 64), normalized.size)
        self.assertEqual(0, normalized.getpixel((0, 0))[3])
        self.assertIsNotNone(normalized.getchannel("A").getbbox())
        self.assertEqual([8, 10, 22, 35], metrics["sourceBBox"])
        self.assertEqual([64, 64], metrics["canvasSize"])

    def test_write_contact_sheet_writes_labeled_preview(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            normalized_dir = root / "normalized"
            normalized_dir.mkdir()
            normalized = {}
            for index, state in enumerate(importer.REQUIRED_STATES):
                path = normalized_dir / f"{state}.png"
                image = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
                image.putpixel((8 + index, 8), (255, 80, 40, 255))
                image.save(path)
                normalized[state] = path

            output = importer.write_contact_sheet(root / "qa" / "contact-sheet-32.png", normalized, preview_size=32)

            self.assertTrue(output.is_file())
            with Image.open(output) as sheet:
                self.assertEqual((32 * 4, (32 + 22) * 2), sheet.size)
                self.assertEqual("RGB", sheet.mode)

    def test_write_background_removal_preview_writes_checker_backed_sheet(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cleaned = {}
            for index, state in enumerate(importer.REQUIRED_STATES):
                image = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
                image.putpixel((8 + index, 8), (255, 80, 40, 255))
                cleaned[state] = image

            output = importer.write_background_removal_preview(
                root / "qa" / "background-removal-preview.png", cleaned, preview_size=32
            )

            self.assertTrue(output.is_file())
            with Image.open(output) as sheet:
                self.assertEqual((32 * 4, (32 + 22) * 2), sheet.size)
                self.assertEqual("RGB", sheet.mode)

    def make_import_archive(self, root):
        input_dir = self.write_state_inputs(root)
        for path in input_dir.glob("*.png"):
            image = self.checker_image((32, 32))
            for y in range(8, 24):
                for x in range(10, 22):
                    image.putpixel((x, y), (255, 120, 80, 255))
            image.save(path)
        archive = root / "akari_clawd_base_images.tar.gz"
        with tarfile.open(archive, "w:gz") as tar:
            tar.add(input_dir, arcname=input_dir.name)
        return archive

    def test_build_webui_base_import_writes_outputs_and_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = self.make_import_archive(root)

            result = importer.build_webui_base_import(
                input_archive=archive,
                output_root=root / "out",
                run_id="unit",
                canvas_size=64,
                preview_sizes=(32,),
                background_tolerance=18,
                padding_ratio=0.1,
            )

            self.assertTrue((result["normalizedDir"] / "idle.png").is_file())
            self.assertTrue((result["qaDir"] / "contact-sheet-32.png").is_file())
            self.assertTrue((result["qaDir"] / "background-removal-preview.png").is_file())
            validation = json.loads(result["validationJson"].read_text(encoding="utf-8"))
            self.assertEqual("review", validation["status"])
            self.assertEqual("unit", validation["runId"])
            self.assertEqual(list(importer.REQUIRED_STATES), validation["stateOrder"])
            self.assertEqual(set(importer.REQUIRED_STATES), set(validation["states"]))
            self.assertEqual(
                "working-notification visual distinction requires human review",
                validation["humanReview"]["requiredChecks"][0],
            )

    def test_build_webui_base_import_rejects_archive_and_dir_together(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = self.make_import_archive(root)
            input_dir = root / "akari_clawd_base_images"

            with self.assertRaisesRegex(ValueError, "specify exactly one of input_archive or input_dir"):
                importer.build_webui_base_import(input_archive=archive, input_dir=input_dir, output_root=root / "out")

    def test_build_parser_accepts_build_command(self):
        args = importer._build_parser().parse_args(
            [
                "build",
                "--input-archive",
                "raw.tar.gz",
                "--run-id",
                "trial",
                "--canvas-size",
                "512",
                "--preview-sizes",
                "128,160",
                "--background-tolerance",
                "20",
                "--padding-ratio",
                "0.08",
            ]
        )

        self.assertEqual("build", args.command)
        self.assertEqual(Path("raw.tar.gz"), args.input_archive)
        self.assertEqual("trial", args.run_id)
        self.assertEqual(512, args.canvas_size)
        self.assertEqual("128,160", args.preview_sizes)
