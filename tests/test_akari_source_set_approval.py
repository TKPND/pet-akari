import json
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path

from PIL import Image, ImageDraw

from pet_akari import akari_source_set_approval as approval
from pet_akari import clawd_hq_theme as hq


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


class SourceSetApprovalTest(unittest.TestCase):
    def make_fixture(self, root):
        root = Path(root)
        masters = root / "work" / "rendered" / "masters"
        upstream = root / "work" / "upstream" / "masters-stabilized"
        theme = root / "outputs" / "akari-hq-apng-theme-seamsafe"
        state_quality = {}
        source_manifest = {}
        run_summary = {
            "ok": True,
            "promoted": True,
            "visualApproved": True,
            "paths": {
                "outputsDir": theme.as_posix(),
                "runDir": (root / "work" / "rendered").as_posix(),
            },
        }

        for state_index, state in enumerate(hq.CORE_STATES):
            state_master_dir = masters / state
            state_upstream_dir = upstream / state
            state_master_dir.mkdir(parents=True, exist_ok=True)
            state_upstream_dir.mkdir(parents=True, exist_ok=True)
            source_manifest[state] = []
            for frame_index in range(2):
                color = (
                    40 + state_index * 20,
                    60 + frame_index * 50,
                    120 + state_index * 7,
                    255,
                )
                image = Image.new("RGBA", hq.RUNTIME_SIZE, (0, 0, 0, 0))
                draw = ImageDraw.Draw(image)
                draw.ellipse((6, 6, 26, 30), fill=color)
                draw.rectangle((12 + frame_index, 24, 22 + frame_index, 36), fill=color)
                image.save(state_master_dir / f"{frame_index + 1:03d}.png")

                upstream_image = Image.new("RGBA", hq.RUNTIME_SIZE, (0, 0, 0, 0))
                upstream_draw = ImageDraw.Draw(upstream_image)
                upstream_draw.rectangle((8, 8, 24, 34), fill=color)
                upstream_path = state_upstream_dir / f"{frame_index + 1:02d}.png"
                upstream_image.save(upstream_path)
                source_manifest[state].append(upstream_path.as_posix())

            state_quality[state] = {
                "state": state,
                "status": "pass",
                "metrics": {
                    "motion": {"ok": True, "uniqueFrames": 2},
                    "scale": {"ok": True, "frameCount": 2},
                    "semantics": {
                        "ok": True,
                        "approval": {
                            "approved": True,
                            "notes": f"{state} has source-level face, pose, and motion support",
                        },
                    },
                },
            }

        with temporary_theme_sizes():
            hq.export_theme(
                masters,
                theme,
                motion_contract={"states": {state: {"durationMs": 80, "inbetweens": 0} for state in hq.CORE_STATES}},
            )

        source_manifest_path = write_json(root / "work" / "rendered" / "source-manifest.json", source_manifest)
        state_quality_path = write_json(
            root / "work" / "rendered" / "qa" / "metrics" / "state-quality.json", state_quality
        )
        run_summary_path = write_json(root / "work" / "rendered" / "qa" / "run-summary.json", run_summary)
        return {
            "theme": theme,
            "build_manifest": theme / "qa" / "build-manifest.json",
            "rendered_masters": masters,
            "upstream_masters": upstream,
            "source_manifest": source_manifest_path,
            "state_quality": state_quality_path,
            "run_summary": run_summary_path,
            "approval": theme / "qa" / "source-set-approval.json",
            "contact_sheet": theme / "qa" / "source-set-identity-contact-sheet.png",
            "distinctness": theme / "qa" / "metrics" / "source-distinctness.json",
        }

    def build(self, paths):
        return approval.build_source_set_approval(
            candidate_theme=paths["theme"],
            build_manifest=paths["build_manifest"],
            rendered_masters_root=paths["rendered_masters"],
            upstream_masters_root=paths["upstream_masters"],
            source_manifest=paths["source_manifest"],
            state_quality=paths["state_quality"],
            run_summary=paths["run_summary"],
            output=paths["approval"],
            contact_sheet=paths["contact_sheet"],
            distinctness_output=paths["distinctness"],
        )

    def test_builder_writes_exact_seven_state_phase_2_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = self.make_fixture(tmp)

            output = self.build(paths)

            self.assertEqual(paths["approval"], output)
            data = json.loads(paths["approval"].read_text(encoding="utf-8"))
            self.assertEqual(set(hq.CORE_STATES), set(data["states"]))
            self.assertEqual("seamsafe-promoted", data["sourceSetId"])
            self.assertTrue(data["approved"])
            self.assertTrue(data["approvedForPhase3"])
            self.assertEqual("04", data["deferredToPhase"]["petSizeBlindRecognition"])
            self.assertEqual("03", data["deferredToPhase"]["apngContractExport"])
            self.assertEqual("05", data["deferredToPhase"]["allowlistedPackageCloseout"])
            self.assertEqual(paths["approval"].as_posix(), data["canonicalApprovalArtifact"])
            self.assertTrue(paths["contact_sheet"].is_file())
            self.assertTrue(paths["distinctness"].is_file())
            self.assertTrue(approval.validate_source_set_approval(paths["approval"]))

    def test_missing_state_or_duplicate_runtime_asset_rejects_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = self.make_fixture(tmp)
            manifest = json.loads(paths["build_manifest"].read_text(encoding="utf-8"))
            manifest["states"].pop("sleeping")
            write_json(paths["build_manifest"], manifest)

            with self.assertRaisesRegex(ValueError, "missing state sleeping"):
                self.build(paths)

        with tempfile.TemporaryDirectory() as tmp:
            paths = self.make_fixture(tmp)
            manifest = json.loads(paths["build_manifest"].read_text(encoding="utf-8"))
            manifest["states"]["thinking"]["runtimeAsset"] = manifest["states"]["idle"]["runtimeAsset"]
            manifest["states"]["thinking"]["runtimeSha256"] = manifest["states"]["idle"]["runtimeSha256"]
            write_json(paths["build_manifest"], manifest)

            with self.assertRaisesRegex(ValueError, "duplicate runtime asset"):
                self.build(paths)

    def test_identity_checks_are_required_for_every_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = self.make_fixture(tmp)
            self.build(paths)
            data = json.loads(paths["approval"].read_text(encoding="utf-8"))
            for state in hq.CORE_STATES:
                checks = data["states"][state]["identityReview"]["checks"]
                self.assertEqual(
                    {
                        "hairShapeAndColor",
                        "bangs",
                        "faceProportions",
                        "outfitCues",
                        "palette",
                        "silhouette",
                    },
                    set(checks),
                )

            data["states"]["idle"]["identityReview"]["checks"].pop("bangs")
            write_json(paths["approval"], data)
            with self.assertRaisesRegex(ValueError, "idle identity check missing bangs"):
                approval.validate_source_set_approval(paths["approval"])

    def test_cli_build_records_roots_and_phase_deferrals(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = self.make_fixture(tmp)

            approval.main(
                [
                    "build",
                    "--candidate-theme",
                    paths["theme"].as_posix(),
                    "--build-manifest",
                    paths["build_manifest"].as_posix(),
                    "--rendered-masters-root",
                    paths["rendered_masters"].as_posix(),
                    "--upstream-masters-root",
                    paths["upstream_masters"].as_posix(),
                    "--source-manifest",
                    paths["source_manifest"].as_posix(),
                    "--state-quality",
                    paths["state_quality"].as_posix(),
                    "--run-summary",
                    paths["run_summary"].as_posix(),
                    "--output",
                    paths["approval"].as_posix(),
                    "--contact-sheet",
                    paths["contact_sheet"].as_posix(),
                    "--distinctness-output",
                    paths["distinctness"].as_posix(),
                ]
            )

            data = json.loads(paths["approval"].read_text(encoding="utf-8"))
            self.assertEqual(paths["theme"].as_posix(), data["sourceRoots"]["promotedTheme"])
            self.assertEqual(paths["rendered_masters"].as_posix(), data["sourceRoots"]["renderedMasters"])
            self.assertEqual(paths["upstream_masters"].as_posix(), data["sourceRoots"]["upstreamStabilizedMasters"])
            self.assertIn("Phase 4 owns label-hidden pet-size recognition", " ".join(data["evidenceNotes"]))
            self.assertIn("D-08", " ".join(data["decisionCoverage"]))
            for state in hq.CORE_STATES:
                state_data = data["states"][state]
                self.assertFalse(state_data["fallbackUsed"])
                self.assertIn(state, state_data["renderedMasterDir"])
                self.assertIn(state, state_data["upstreamSourceDir"])


if __name__ == "__main__":
    unittest.main()
