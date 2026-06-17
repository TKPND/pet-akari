import json
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path

import akari_phase3_staging as phase3
import akari_source_set_approval as approval
import clawd_hq_theme as hq
from PIL import Image, ImageDraw


@contextmanager
def temporary_theme_sizes(master_size=(64, 80), runtime_size=(32, 40), reference_runtime_size=(128, 160)):
    original = (hq.MASTER_SIZE, hq.RUNTIME_SIZE, hq.REFERENCE_RUNTIME_SIZE)
    hq.MASTER_SIZE = master_size
    hq.RUNTIME_SIZE = runtime_size
    hq.REFERENCE_RUNTIME_SIZE = reference_runtime_size
    try:
        yield
    finally:
        hq.MASTER_SIZE, hq.RUNTIME_SIZE, hq.REFERENCE_RUNTIME_SIZE = original


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


class AkariPhase3StagingTests(unittest.TestCase):
    def make_fixture(self, root):
        root = Path(root)
        masters = root / "masters"
        approval_path = root / "qa" / "source-set-approval.json"
        motion_contract = root / "motion-contract.json"
        run_dir = root / "phase3-staging"
        theme_dir = run_dir / "theme"
        validation_json = run_dir / "qa" / "phase3-validation.json"
        validator_text = run_dir / "qa" / "clawd-validator.txt"
        validator_script = root / "validate-theme.js"

        for state_index, state in enumerate(hq.CORE_STATES):
            state_dir = masters / state
            state_dir.mkdir(parents=True, exist_ok=True)
            for frame_index in range(2):
                image = Image.new("RGBA", hq.MASTER_SIZE, (0, 0, 0, 0))
                draw = ImageDraw.Draw(image)
                color = (
                    40 + state_index * 21,
                    70 + frame_index * 70,
                    140 + state_index * 9,
                    255,
                )
                offset = frame_index * 3
                draw.ellipse((16 + offset, 18, 48 + offset, 58), fill=color)
                draw.rectangle((28, 12 + offset, 36, 22 + offset), fill=(250, 220, 180, 255))
                image.save(state_dir / f"{frame_index + 1:02d}.png")

        states = {}
        for state in hq.CORE_STATES:
            states[state] = {
                "approved": True,
                "fallbackUsed": False,
                "identityReview": {
                    "checks": {check: "pass" for check in approval.IDENTITY_CHECKS},
                    "identityOk": True,
                    "notes": "test identity fixture",
                    "reviewedEvidence": [(masters / state).as_posix()],
                },
                "promotedRuntimeAsset": (root / "runtime" / f"akari-{state}.apng").as_posix(),
                "promotedRuntimeSha256": f"sha-{state}",
                "rejectionReason": None,
                "renderedMasterDir": (masters / state).as_posix(),
                "semanticFallbackReason": None,
                "sourceLevelDistinctness": {
                    "ok": True,
                    "phase4RecognitionDeferred": True,
                    "signals": ["face", "pose", "motion"],
                },
                "sourceMasterFiles": [
                    {
                        "path": (masters / state / "01.png").as_posix(),
                        "sha256": hq.sha256_file(masters / state / "01.png"),
                    },
                    {
                        "path": (masters / state / "02.png").as_posix(),
                        "sha256": hq.sha256_file(masters / state / "02.png"),
                    },
                ],
                "trueSourceFrames": 2,
                "upstreamSourceDir": (root / "upstream" / state).as_posix(),
                "upstreamSourceFiles": [],
            }

        approval_data = {
            "approved": True,
            "approvedForPhase3": True,
            "canonicalApprovalArtifact": approval_path.as_posix(),
            "decisionCoverage": [f"D-{index:02d}" for index in range(1, 9)],
            "deferredToPhase": {
                "allowlistedPackageCloseout": "05",
                "apngContractExport": "03",
                "petSizeBlindRecognition": "04",
            },
            "evidence": {},
            "evidenceNotes": ["test approval fixture"],
            "phase": approval.PHASE,
            "reviewer": "test",
            "schemaVersion": 1,
            "sourceRoots": {
                "promotedTheme": (root / "promoted").as_posix(),
                "renderedMasters": masters.as_posix(),
                "upstreamStabilizedMasters": (root / "upstream").as_posix(),
            },
            "sourceSetId": approval.SOURCE_SET_ID,
            "states": states,
        }
        write_json(approval_path, approval_data)
        write_json(
            motion_contract, {"states": {state: {"durationMs": 80, "inbetweens": 0} for state in hq.CORE_STATES}}
        )
        validator_script.write_text(
            "console.log('fake Clawd validator passed');\nprocess.exit(0);\n",
            encoding="utf-8",
        )
        return {
            "approval": approval_path,
            "masters": masters,
            "motion_contract": motion_contract,
            "run_dir": run_dir,
            "theme_dir": theme_dir,
            "validation_json": validation_json,
            "validator_text": validator_text,
            "validator_script": validator_script,
        }

    def stage(self, paths):
        return phase3.stage_theme(
            approval_path=paths["approval"],
            run_dir=paths["run_dir"],
            theme_dir=paths["theme_dir"],
            motion_contract_path=paths["motion_contract"],
            validation_output=paths["validation_json"],
            validator_output=paths["validator_text"],
            clawd_validator=paths["validator_script"],
        )

    def test_refuses_unapproved_source_set_before_theme_json_is_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            with temporary_theme_sizes():
                paths = self.make_fixture(tmp)
                data = json.loads(paths["approval"].read_text(encoding="utf-8"))
                data["approvedForPhase3"] = False
                write_json(paths["approval"], data)

                with self.assertRaisesRegex(ValueError, "approved for Phase 3"):
                    self.stage(paths)

                self.assertFalse((paths["theme_dir"] / "theme.json").exists())
                self.assertFalse(paths["validation_json"].exists())

    def test_exports_staged_theme_and_phase3_validation_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            with temporary_theme_sizes():
                paths = self.make_fixture(tmp)
                result = self.stage(paths)

                self.assertEqual(paths["theme_dir"], result.theme_dir)
                self.assertEqual(paths["validation_json"], result.validation_json)
                self.assertEqual(paths["validator_text"], result.validator_text)
                self.assertEqual(paths["theme_dir"] / "qa" / "build-manifest.json", result.build_manifest)
                self.assertTrue((paths["theme_dir"] / "theme.json").is_file())
                for state in hq.CORE_STATES:
                    self.assertTrue((paths["theme_dir"] / "assets" / f"akari-{state}.apng").is_file())
                self.assertTrue(result.build_manifest.is_file())
                self.assertTrue(paths["validation_json"].is_file())
                self.assertTrue(paths["validator_text"].is_file())

                evidence = json.loads(paths["validation_json"].read_text(encoding="utf-8"))
                self.assertEqual(["ASSET-03", "VQA-05", "PKG-01", "PKG-02"], evidence["requirementsCovered"])
                self.assertEqual(set(hq.CORE_STATES), set(evidence["states"]))
                self.assertEqual("pass", evidence["clawdValidator"]["status"])

    def test_records_compatibility_only_boundary_not_visual_acceptance(self):
        with tempfile.TemporaryDirectory() as tmp:
            with temporary_theme_sizes():
                paths = self.make_fixture(tmp)
                self.stage(paths)

                evidence = json.loads(paths["validation_json"].read_text(encoding="utf-8"))
                self.assertEqual("compatibility-only", evidence["clawdValidator"]["evidenceRole"])
                self.assertFalse(evidence["visualAcceptance"])
                self.assertTrue(evidence["phase4Required"])
                self.assertFalse(evidence["releasePackageAccepted"])
                self.assertIsNone(evidence["finalAllowlistedPackage"])
                self.assertIn("visual-state acceptance remains Phase 04", evidence["boundaryStatement"])

    def test_missing_state_master_fails_closed_before_evidence_is_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            with temporary_theme_sizes():
                paths = self.make_fixture(tmp)
                for png in (paths["masters"] / "sleeping").glob("*.png"):
                    png.unlink()
                (paths["masters"] / "sleeping").rmdir()

                with self.assertRaisesRegex(FileNotFoundError, "sleeping"):
                    self.stage(paths)

                self.assertFalse(paths["validation_json"].exists())

    def test_missing_png_master_fails_closed_before_evidence_is_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            with temporary_theme_sizes():
                paths = self.make_fixture(tmp)
                for png in (paths["masters"] / "error").glob("*.png"):
                    png.unlink()

                with self.assertRaisesRegex(FileNotFoundError, "no PNG frames"):
                    self.stage(paths)

                self.assertFalse(paths["validation_json"].exists())

    def test_master_hash_drift_fails_closed_before_evidence_is_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            with temporary_theme_sizes():
                paths = self.make_fixture(tmp)
                image = Image.new("RGBA", hq.MASTER_SIZE, (0, 0, 0, 0))
                draw = ImageDraw.Draw(image)
                draw.rectangle((8, 8, 48, 58), fill=(255, 20, 20, 255))
                image.save(paths["masters"] / "idle" / "01.png")

                with self.assertRaisesRegex(ValueError, "approved master hash mismatch"):
                    self.stage(paths)

                self.assertFalse(paths["validation_json"].exists())

    def test_stale_assets_fail_closed_before_evidence_is_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            with temporary_theme_sizes():
                paths = self.make_fixture(tmp)
                assets_dir = paths["theme_dir"] / "assets"
                assets_dir.mkdir(parents=True, exist_ok=True)
                (assets_dir / "akari-stale.apng").write_bytes(b"stale")

                with self.assertRaisesRegex(ValueError, "exactly approved runtime assets"):
                    self.stage(paths)

                self.assertFalse(paths["validation_json"].exists())

    def test_validator_failure_records_raw_output_and_raises_without_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            with temporary_theme_sizes():
                paths = self.make_fixture(tmp)
                paths["validator_script"].write_text(
                    "console.log('validator stdout before failure');\n"
                    "console.error('validator stderr failure');\n"
                    "process.exit(7);\n",
                    encoding="utf-8",
                )

                with self.assertRaisesRegex(ValueError, "Clawd validator failed"):
                    self.stage(paths)

                raw = paths["validator_text"].read_text(encoding="utf-8")
                self.assertIn("validator stdout before failure", raw)
                self.assertIn("validator stderr failure", raw)
                evidence = json.loads(paths["validation_json"].read_text(encoding="utf-8"))
                self.assertEqual("fail", evidence["clawdValidator"]["status"])
                self.assertFalse(evidence["visualAcceptance"])


if __name__ == "__main__":
    unittest.main()
