import contextlib
import io
import json
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path

import akari_phase4_visual_recognition as phase4
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


class AkariPhase4VisualRecognitionTests(unittest.TestCase):
    def make_fixture(self, root, *, identical_face_states=()):
        root = Path(root)
        masters = root / "masters"
        theme_dir = root / "phase3-staging" / "theme"
        phase3_validation = root / "phase3-staging" / "qa" / "phase3-validation.json"
        qa_dir = root / "phase4-visual-recognition" / "qa"
        motion_contract = {"states": {state: {"durationMs": 80, "inbetweens": 0} for state in hq.CORE_STATES}}

        for state_index, state in enumerate(hq.CORE_STATES):
            state_dir = masters / state
            state_dir.mkdir(parents=True, exist_ok=True)
            for frame_index in range(2):
                image = Image.new("RGBA", hq.MASTER_SIZE, (0, 0, 0, 0))
                draw = ImageDraw.Draw(image)
                if state in identical_face_states:
                    face_color = (190, 120, 140, 255)
                    body_color = (70, 90, 150, 255)
                    mouth_y = 32
                else:
                    face_color = (
                        80 + state_index * 19,
                        80 + frame_index * 45,
                        180 - state_index * 12,
                        255,
                    )
                    body_color = (
                        40 + state_index * 22,
                        100 + state_index * 11,
                        140 + frame_index * 30,
                        255,
                    )
                    mouth_y = 30 + (state_index % 4) * 3
                offset = frame_index * 2
                draw.ellipse((18 + offset, 14, 46 + offset, 45), fill=face_color)
                draw.rectangle((21, 45, 43, 72), fill=body_color)
                draw.line((26, mouth_y, 38, mouth_y), fill=(30, 20, 28, 255), width=2)
                if state in ("error", "attention", "notification") and state not in identical_face_states:
                    draw.rectangle((8, 10, 17, 22), fill=(255, 60, 40, 255))
                if state == "sleeping" and state not in identical_face_states:
                    draw.arc((24, 25, 40, 39), 0, 180, fill=(20, 20, 40, 255), width=2)
                    draw.line((48, 18, 56, 18), fill=(80, 80, 170, 255), width=2)
                image.save(state_dir / f"{frame_index + 1:02d}.png")

        hq.export_theme(masters, theme_dir, motion_contract=motion_contract)
        phase3_data = {
            "boundaryStatement": "Clawd validator success is compatibility evidence only; visual-state acceptance remains Phase 04.",
            "buildManifest": (theme_dir / "qa" / "build-manifest.json").as_posix(),
            "clawdValidator": {
                "evidenceRole": "compatibility-only",
                "exitCode": 0,
                "status": "pass",
            },
            "phase": "03-apng-export-and-clawd-contract-validation",
            "phase4Required": True,
            "releasePackageAccepted": False,
            "requirementsCovered": ["ASSET-03", "VQA-05", "PKG-01", "PKG-02"],
            "schemaVersion": 1,
            "themeDir": theme_dir.as_posix(),
            "validationRole": "compatibility-only",
            "visualAcceptance": False,
        }
        write_json(phase3_validation, phase3_data)
        return {
            "masters": masters,
            "theme_dir": theme_dir,
            "phase3_validation": phase3_validation,
            "build_manifest": theme_dir / "qa" / "build-manifest.json",
            "qa_dir": qa_dir,
        }

    def build(self, paths):
        return phase4.build_phase4_visual_recognition(
            theme_dir=paths["theme_dir"],
            phase3_validation=paths["phase3_validation"],
            qa_dir=paths["qa_dir"],
        )

    def test_rejects_malformed_phase3_inputs_before_evidence_is_written(self):
        with tempfile.TemporaryDirectory() as tmp, temporary_theme_sizes():
            paths = self.make_fixture(tmp)
            data = json.loads(paths["phase3_validation"].read_text(encoding="utf-8"))
            data["phase4Required"] = False
            write_json(paths["phase3_validation"], data)

            with self.assertRaisesRegex(ValueError, "phase4Required"):
                self.build(paths)

            self.assertFalse((paths["qa_dir"] / "phase4-visual-recognition.json").exists())

    def test_generates_label_hidden_preview_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp, temporary_theme_sizes():
            paths = self.make_fixture(tmp)
            result = self.build(paths)

            self.assertEqual(paths["qa_dir"], result.qa_dir)
            expected_files = [
                "preview-128-light.png",
                "preview-128-dark.png",
                "preview-160-light.png",
                "preview-160-dark.png",
                "face-crops-idle-error-sleeping.png",
                "support-contact-sheet.png",
                "answer-key.json",
                "recognition-results.template.json",
                "phase4-visual-recognition.json",
            ]
            for name in expected_files:
                self.assertTrue((paths["qa_dir"] / name).is_file(), name)

            answer_key = json.loads((paths["qa_dir"] / "answer-key.json").read_text(encoding="utf-8"))
            self.assertEqual(set(hq.CORE_STATES), {tile["state"] for tile in answer_key["tiles"]})
            self.assertEqual(len(hq.CORE_STATES), len({tile["tileId"] for tile in answer_key["tiles"]}))

            evidence = json.loads(result.evidence_json.read_text(encoding="utf-8"))
            self.assertFalse(evidence["visualAcceptance"])
            self.assertEqual("04", evidence["phase"])
            self.assertTrue({"VQA-01", "VQA-03", "VQA-04"}.issubset(evidence["requirementsCovered"]))
            self.assertEqual("pending", evidence["recognition"]["status"])
            self.assertEqual(
                {"128-light", "128-dark", "160-light", "160-dark"},
                set(evidence["labelHiddenPreviews"]),
            )

    def test_face_crop_sheet_and_distinctness_metrics_are_non_noise(self):
        with tempfile.TemporaryDirectory() as tmp, temporary_theme_sizes():
            paths = self.make_fixture(tmp)
            self.build(paths)

            evidence = json.loads((paths["qa_dir"] / "phase4-visual-recognition.json").read_text(encoding="utf-8"))
            self.assertTrue((paths["qa_dir"] / "face-crops-idle-error-sleeping.png").is_file())
            pairs = evidence["faceCropDistinctness"]["pairs"]
            self.assertEqual({"idle__error", "idle__sleeping", "error__sleeping"}, set(pairs))
            for metric in pairs.values():
                self.assertGreater(metric["meanAbsDiffRgb"], 5.0)
                self.assertGreater(metric["changedPixelRatio"], 0.05)

    def test_face_crop_distinctness_fails_closed_on_near_identical_sources(self):
        with tempfile.TemporaryDirectory() as tmp, temporary_theme_sizes():
            paths = self.make_fixture(tmp, identical_face_states=("idle", "error", "sleeping"))

            with self.assertRaisesRegex(ValueError, "face crop distinctness"):
                self.build(paths)

            self.assertFalse((paths["qa_dir"] / "phase4-visual-recognition.json").exists())

    def test_required_states_need_recognition_results(self):
        with tempfile.TemporaryDirectory() as tmp, temporary_theme_sizes():
            paths = self.make_fixture(tmp)
            self.build(paths)
            recognition = {
                "schemaVersion": 1,
                "reviewer": "test",
                "entries": {
                    state: {
                        "guessedState": state,
                        "confidence": "high",
                        "cueNotes": "visible face and pose cue",
                    }
                    for state in hq.CORE_STATES
                    if state != "sleeping"
                },
            }
            recognition_path = paths["qa_dir"] / "recognition-results.json"
            write_json(recognition_path, recognition)

            with self.assertRaisesRegex(ValueError, "sleeping"):
                phase4.validate_phase4_visual_recognition(
                    qa_dir=paths["qa_dir"],
                    recognition_results=recognition_path,
                )

    def test_mismatched_recognition_records_fail_closed_evidence(self):
        with tempfile.TemporaryDirectory() as tmp, temporary_theme_sizes():
            paths = self.make_fixture(tmp)
            self.build(paths)
            answer = json.loads((paths["qa_dir"] / "answer-key.json").read_text(encoding="utf-8"))
            entries = {}
            for tile in answer["tiles"]:
                guessed = tile["state"]
                confidence = "high"
                if tile["state"] == "notification":
                    guessed = "attention"
                if tile["state"] == "attention":
                    guessed = "notification"
                    confidence = "low"
                entries[tile["tileId"]] = {
                    "confidence": confidence,
                    "cueNotes": "visible face or pose cue",
                    "guessedState": guessed,
                }
            recognition_path = paths["qa_dir"] / "recognition-results.json"
            write_json(
                recognition_path,
                {
                    "distinguishabilityNotes": {
                        state: {"notes": "cue", "status": "recorded"}
                        for state in ("sleeping", "error", "attention", "notification")
                    },
                    "entries": entries,
                    "schemaVersion": 1,
                    "status": "partial-approval-improvement-required",
                },
            )

            phase4.validate_phase4_visual_recognition(
                theme_dir=paths["theme_dir"],
                phase3_validation=paths["phase3_validation"],
                qa_dir=paths["qa_dir"],
                recognition_results=recognition_path,
            )
            phase4.validate_phase4_visual_recognition(
                theme_dir=paths["theme_dir"],
                phase3_validation=paths["phase3_validation"],
                qa_dir=paths["qa_dir"],
                recognition_results=recognition_path,
            )

            evidence = json.loads((paths["qa_dir"] / "phase4-visual-recognition.json").read_text(encoding="utf-8"))
            self.assertFalse(evidence["visualAcceptance"])
            self.assertEqual(evidence["recognition"]["status"], "rejected")
            self.assertIn("VQA-02", evidence["requirementsCovered"])
            failed_checks = {item["check"] for item in evidence["recognition"]["failedChecks"]}
            self.assertIn("recognition-matches-answer-key", failed_checks)
            self.assertIn("recognition-confidence", failed_checks)
            self.assertIn("review-disposition", failed_checks)

    def test_evidence_json_binds_all_inputs_and_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp, temporary_theme_sizes():
            paths = self.make_fixture(tmp)
            self.build(paths)

            evidence = json.loads((paths["qa_dir"] / "phase4-visual-recognition.json").read_text(encoding="utf-8"))
            self.assertEqual(hq.sha256_file(paths["build_manifest"]), evidence["inputs"]["buildManifest"]["sha256"])
            self.assertEqual(
                hq.sha256_file(paths["phase3_validation"]),
                evidence["inputs"]["phase3Validation"]["sha256"],
            )
            self.assertEqual(set(hq.CORE_STATES), set(evidence["inputs"]["runtimeAssets"]))
            for state, runtime in evidence["inputs"]["runtimeAssets"].items():
                self.assertEqual(
                    hq.sha256_file(paths["theme_dir"] / runtime["path"]),
                    runtime["sha256"],
                    state,
                )
            artifact_names = {
                "preview-128-light.png",
                "preview-128-dark.png",
                "preview-160-light.png",
                "preview-160-dark.png",
                "face-crops-idle-error-sleeping.png",
                "support-contact-sheet.png",
                "answer-key.json",
                "recognition-results.template.json",
            }
            self.assertTrue(artifact_names.issubset(evidence["artifacts"]))
            for name in artifact_names:
                artifact = evidence["artifacts"][name]
                self.assertEqual(hq.sha256_file(paths["qa_dir"] / name), artifact["sha256"])
            self.assertIn("phase5DriftBinding", evidence)

    def test_cli_build_prints_evidence_path(self):
        with tempfile.TemporaryDirectory() as tmp, temporary_theme_sizes():
            paths = self.make_fixture(tmp)
            stdout = io.StringIO()

            with contextlib.redirect_stdout(stdout):
                phase4.main(
                    [
                        "build",
                        "--theme-dir",
                        str(paths["theme_dir"]),
                        "--phase3-validation",
                        str(paths["phase3_validation"]),
                        "--qa-dir",
                        str(paths["qa_dir"]),
                    ]
                )

            self.assertEqual(stdout.getvalue(), f"wrote {paths['qa_dir'] / 'phase4-visual-recognition.json'}\n")


if __name__ == "__main__":
    unittest.main()
