import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from pet_akari import akari_phase4_candidate_batch as batch


class Phase4CandidateBatchTests(unittest.TestCase):
    def test_expand_recipe_grid_is_deterministic_and_capped(self):
        candidates = batch.expand_recipe_grid(
            attention_recipes=["a1", "a2"],
            notification_recipes=["n1", "n2"],
            error_recipes=["e1", "e2"],
            max_candidates=5,
        )

        self.assertEqual([candidate.candidate_id for candidate in candidates], ["C001", "C002", "C003", "C004", "C005"])
        self.assertEqual(
            candidates[0].recipes,
            {"attention": "a1", "notification": "n1", "error": "e1"},
        )
        self.assertEqual(
            candidates[4].recipes,
            {"attention": "a2", "notification": "n1", "error": "e1"},
        )

    def test_parse_recipe_csv_rejects_unknown_values(self):
        with self.assertRaisesRegex(ValueError, "unknown attention recipe"):
            batch.parse_recipe_csv("attention", "raised-hand-only,nope")

    def test_build_candidate_batch_records_valid_and_invalid_candidates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_theme = root / "source-theme"
            source_evidence = root / "source-evidence.json"
            source_theme.mkdir()
            source_evidence.write_text("{}", encoding="utf-8")

            from pet_akari import akari_phase4_gap_repair as repair

            def fake_builder(*, source_theme, source_phase4_evidence, run_dir, clawd_validator, repair_recipes):
                if repair_recipes["error"] == "broken-card-lower":
                    raise ValueError("synthetic broken recipe")
                qa_dir = run_dir / "phase4-visual-recognition" / "qa"
                qa_dir.mkdir(parents=True)
                Image.new("RGB", (512, 300), "white").save(qa_dir / "preview-128-light.png")
                evidence = qa_dir / "phase4-visual-recognition.json"
                evidence.write_text("{}", encoding="utf-8")
                validation = run_dir / "qa" / "phase4-gap-repair-validation.json"
                validation.parent.mkdir(parents=True)
                validation.write_text("{}", encoding="utf-8")
                return repair.GapRepairResult(
                    run_dir=run_dir,
                    masters_dir=run_dir / "masters",
                    theme_dir=run_dir / "theme",
                    validation_json=validation,
                    visual_qa_dir=qa_dir,
                    visual_recognition_json=evidence,
                )

            result = batch.build_candidate_batch(
                batch_id="unit",
                output_root=root / "batch",
                source_theme=source_theme,
                source_phase4_evidence=source_evidence,
                clawd_validator=Path("validator.js"),
                attention_recipes=["raised-hand-only"],
                notification_recipes=["permission-card"],
                error_recipes=["lower-x-only", "broken-card-lower"],
                max_candidates=2,
                candidate_builder=fake_builder,
            )

            manifest = json.loads(result["manifest"].read_text(encoding="utf-8"))
            self.assertEqual("unit", manifest["batchId"])
            self.assertEqual(["built", "invalid"], [candidate["status"] for candidate in manifest["candidates"]])
            self.assertIn("synthetic broken recipe", manifest["candidates"][1]["notes"])
            self.assertTrue(result["selectionTemplate"].is_file())

    def test_write_batch_contact_sheet_extracts_focus_tiles(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            preview = root / "preview-128-light.png"
            image = Image.new("RGB", (512, 300), "white")
            colors = {
                "A04": (255, 0, 0),
                "A05": (0, 255, 0),
                "A06": (0, 0, 255),
            }
            # A04 is column 3 row 0, A05 is column 0 row 1, A06 is column 1 row 1.
            for box, color in [
                ((384, 0, 512, 128), colors["A04"]),
                ((0, 150, 128, 278), colors["A05"]),
                ((128, 150, 256, 278), colors["A06"]),
            ]:
                tile = Image.new("RGB", (box[2] - box[0], box[3] - box[1]), color)
                image.paste(tile, box)
            image.save(preview)

            record = batch.CandidateRecord(
                candidate_id="C001",
                recipes={"attention": "raised-hand-only", "notification": "permission-card", "error": "lower-x-only"},
                run_dir=root / "candidate-C001",
                status="built",
                preview_paths={"128-light": preview.as_posix()},
            )
            output = batch.write_batch_contact_sheet(root / "batch-contact-sheet.png", [record], include_all_states=False)

            sheet = Image.open(output).convert("RGB")
            self.assertEqual((492, 152), sheet.size)
            self.assertEqual((255, 0, 0), sheet.getpixel((84, 12)))
            self.assertEqual((0, 255, 0), sheet.getpixel((224, 12)))
            self.assertEqual((0, 0, 255), sheet.getpixel((364, 12)))
