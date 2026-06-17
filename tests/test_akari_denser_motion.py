import contextlib
import io
import json
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path

from PIL import Image

from pet_akari import akari_denser_motion as denser
from pet_akari import clawd_hq_theme as hq


@contextmanager
def temporary_theme_sizes(master_size=(128, 160), runtime_size=(32, 40), reference_runtime_size=(1536, 1920)):
    original = (hq.MASTER_SIZE, hq.RUNTIME_SIZE, hq.REFERENCE_RUNTIME_SIZE)
    hq.MASTER_SIZE = master_size
    hq.RUNTIME_SIZE = runtime_size
    hq.REFERENCE_RUNTIME_SIZE = reference_runtime_size
    try:
        yield
    finally:
        hq.MASTER_SIZE, hq.RUNTIME_SIZE, hq.REFERENCE_RUNTIME_SIZE = original


class AkariDenserMotionTests(unittest.TestCase):
    def test_temporary_theme_sizes_restores_globals(self):
        original = (hq.MASTER_SIZE, hq.RUNTIME_SIZE, hq.REFERENCE_RUNTIME_SIZE)

        with temporary_theme_sizes(master_size=(64, 80), runtime_size=(16, 20)):
            self.assertEqual(hq.MASTER_SIZE, (64, 80))
            self.assertEqual(hq.RUNTIME_SIZE, (16, 20))

        self.assertEqual((hq.MASTER_SIZE, hq.RUNTIME_SIZE, hq.REFERENCE_RUNTIME_SIZE), original)

    def test_build_motion_contract_matches_spec(self):
        contract = denser.build_motion_contract()

        self.assertEqual(set(contract["states"]), set(hq.CORE_STATES))
        for state in ("idle", "thinking", "notification", "error", "sleeping"):
            self.assertEqual(contract["states"][state], {"durationMs": 125, "inbetweens": 4})
        self.assertEqual(contract["states"]["working"], {"durationMs": 100, "inbetweens": 3})
        self.assertEqual(contract["states"]["attention"], {"durationMs": 100, "inbetweens": 3})

    def test_prepare_run_writes_contract_prompts_and_anchor_sheets(self):
        with tempfile.TemporaryDirectory() as tmp, temporary_theme_sizes():
            root = Path(tmp)
            anchors_dir = root / "anchors"
            run_dir = root / "run"
            hq.write_synthetic_masters(anchors_dir, frame_count=4)

            denser.prepare_run(anchors_dir, run_dir)

            contract = json.loads((run_dir / "motion-contract.json").read_text(encoding="utf-8"))
            self.assertEqual(contract, denser.build_motion_contract())
            self.assertTrue((run_dir / "qa" / "anchor-contact-sheet.png").is_file())
            for state in hq.CORE_STATES:
                self.assertTrue((run_dir / "prompts" / f"{state}-denser.md").is_file())
                self.assertTrue((run_dir / "references" / f"{state}-anchors.png").is_file())

            idle_prompt = (run_dir / "prompts" / "idle-denser.md").read_text(encoding="utf-8")
            self.assertIn("8 full-body frames", idle_prompt)
            self.assertIn("dark navy cadet/newsboy cap", idle_prompt)
            self.assertIn("No ahoge", idle_prompt)
            self.assertIn("flat pure #00ff00", idle_prompt)

            working_prompt = (run_dir / "prompts" / "working-denser.md").read_text(encoding="utf-8")
            self.assertIn("12 full-body frames", working_prompt)
            self.assertIn("focused task-work energy", working_prompt)

            with Image.open(run_dir / "references" / "idle-anchors.png") as sheet:
                self.assertGreater(sheet.width, sheet.height)

    def test_prepare_run_cli_prints_run_directory(self):
        with tempfile.TemporaryDirectory() as tmp, temporary_theme_sizes():
            root = Path(tmp)
            anchors_dir = root / "anchors"
            run_dir = root / "run"
            hq.write_synthetic_masters(anchors_dir, frame_count=4)

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                denser.main(["prepare-run", "--anchors", str(anchors_dir), "--run-dir", str(run_dir)])

            self.assertEqual(stdout.getvalue(), f"prepared denser motion run in {run_dir}\n")
            self.assertTrue((run_dir / "motion-contract.json").is_file())

    def test_prepare_run_rejects_non_four_anchor_count_before_writing_outputs(self):
        with tempfile.TemporaryDirectory() as tmp, temporary_theme_sizes():
            root = Path(tmp)
            anchors_dir = root / "anchors"
            run_dir = root / "run"
            hq.write_synthetic_masters(anchors_dir, frame_count=4)
            (anchors_dir / "working" / "04.png").unlink()

            with self.assertRaisesRegex(ValueError, r"(working.*4 anchor|4 anchor.*working)"):
                denser.prepare_run(anchors_dir, run_dir)

            self.assertFalse(run_dir.exists())

    def test_prepare_run_rejects_missing_anchor_state_before_writing_outputs(self):
        with tempfile.TemporaryDirectory() as tmp, temporary_theme_sizes():
            root = Path(tmp)
            anchors_dir = root / "anchors"
            run_dir = root / "run"
            hq.write_synthetic_masters(anchors_dir, frame_count=4)
            for path in (anchors_dir / "error").glob("*.png"):
                path.unlink()
            (anchors_dir / "error").rmdir()

            with self.assertRaisesRegex(ValueError, r"(error.*4 anchor|4 anchor.*error)"):
                denser.prepare_run(anchors_dir, run_dir)

            self.assertFalse(run_dir.exists())

    def test_prepare_run_rejects_corrupt_anchor_before_writing_outputs(self):
        with tempfile.TemporaryDirectory() as tmp, temporary_theme_sizes():
            root = Path(tmp)
            anchors_dir = root / "anchors"
            run_dir = root / "run"
            hq.write_synthetic_masters(anchors_dir, frame_count=4)
            (anchors_dir / "thinking" / "03.png").write_text("not a png", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "thinking"):
                denser.prepare_run(anchors_dir, run_dir)

            self.assertFalse(run_dir.exists())


if __name__ == "__main__":
    unittest.main()
