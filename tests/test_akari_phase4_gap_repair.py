import json
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

from PIL import Image, ImageChops, ImageDraw, ImageSequence

from pet_akari import akari_phase4_visual_recognition as vr
from pet_akari import clawd_hq_theme as hq

_CLAWD_VALIDATOR = Path(__file__).resolve().parents[1] / "work" / "clawd-on-desk" / "scripts" / "validate-theme.js"
_HAS_CLAWD = _CLAWD_VALIDATOR.exists()


@contextmanager
def temporary_theme_sizes(master_size=(64, 80), runtime_size=(32, 40), reference_runtime_size=(128, 160)):
    old_master = hq.MASTER_SIZE
    old_runtime = hq.RUNTIME_SIZE
    old_reference = hq.REFERENCE_RUNTIME_SIZE
    hq.MASTER_SIZE = master_size
    hq.RUNTIME_SIZE = runtime_size
    hq.REFERENCE_RUNTIME_SIZE = reference_runtime_size
    try:
        yield
    finally:
        hq.MASTER_SIZE = old_master
        hq.RUNTIME_SIZE = old_runtime
        hq.REFERENCE_RUNTIME_SIZE = old_reference


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def apng_frames(path):
    with Image.open(path) as image:
        frames = [frame.copy().convert("RGBA") for frame in ImageSequence.Iterator(image)]
        if image.info.get("default_image") and len(frames) > 1:
            frames = frames[1:]
        return frames


def render_pet_size(image, target_height=128):
    scale = target_height / image.height
    target_width = max(1, round(image.width * scale))
    return image.resize((target_width, target_height), Image.Resampling.LANCZOS)


def changed_bbox(before, after, threshold=20):
    diff = ImageChops.difference(before, after).convert("RGBA")
    mask = Image.new("L", diff.size, 0)
    pixels = []
    for red, green, blue, alpha in diff.getdata():
        pixels.append(255 if alpha or max(red, green, blue) > threshold else 0)
    mask.putdata(pixels)
    return mask.getbbox()


def changed_pixel_ratio(left, right, threshold=20):
    diff = ImageChops.difference(left, right).convert("RGBA")
    changed = sum(1 for red, green, blue, alpha in diff.getdata() if alpha or max(red, green, blue) > threshold)
    return changed / (diff.width * diff.height)


def protected_face_box(frame):
    alpha = frame.getchannel("A").getbbox()
    if alpha is None:
        return None
    left, top, right, bottom = alpha
    face_bottom = top + int((bottom - top) * 0.45)
    return (left, top, right, face_bottom)


def count_changed_pixels_in_box(before, after, box, threshold=20):
    if box is None:
        return 0
    left, top, right, bottom = box
    changed = 0
    diff = ImageChops.difference(before, after).convert("RGBA")
    for y in range(top, bottom):
        for x in range(left, right):
            red, green, blue, alpha = diff.getpixel((x, y))
            if alpha or max(red, green, blue) > threshold:
                changed += 1
    return changed


class AkariPhase4GapRepairTests(unittest.TestCase):
    def make_fixture(self, root):
        root = Path(root)
        masters = root / "masters"
        theme_dir = root / "phase3-staging" / "theme"
        phase3_validation = root / "phase3-staging" / "qa" / "phase3-validation.json"
        qa_dir = root / "phase4-visual-recognition" / "qa"
        run_dir = root / "phase4-gap-repair"
        motion_contract = {"states": {state: {"durationMs": 80, "inbetweens": 0} for state in hq.CORE_STATES}}

        for state_index, state in enumerate(hq.CORE_STATES):
            state_dir = masters / state
            state_dir.mkdir(parents=True, exist_ok=True)
            for frame_index in range(2):
                image = Image.new("RGBA", hq.MASTER_SIZE, (0, 0, 0, 0))
                draw = ImageDraw.Draw(image)
                offset = frame_index * 2
                face_color = (80 + state_index * 18, 90 + frame_index * 34, 190 - state_index * 11, 255)
                body_color = (45 + state_index * 19, 120 + state_index * 9, 145 + frame_index * 20, 255)
                draw.ellipse((18 + offset, 14, 46 + offset, 45), fill=face_color)
                draw.rectangle((21, 45, 43, 72), fill=body_color)
                draw.line((26, 31 + state_index % 5, 38, 31 + state_index % 5), fill=(24, 18, 28, 255), width=2)
                if state == "attention":
                    draw.line((43, 45, 55, 25), fill=(60, 50, 110, 255), width=3)
                if state == "notification":
                    draw.rectangle((8, 10, 17, 22), fill=(255, 70, 42, 255))
                if state == "sleeping":
                    draw.arc((24, 25, 40, 39), 0, 180, fill=(20, 20, 40, 255), width=2)
                image.save(state_dir / f"{frame_index + 1:02d}.png")

        hq.export_theme(masters, theme_dir, motion_contract=motion_contract)
        write_json(
            phase3_validation,
            {
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
            },
        )
        vr.build_phase4_visual_recognition(
            theme_dir=theme_dir,
            phase3_validation=phase3_validation,
            qa_dir=qa_dir,
        )
        evidence = json.loads((qa_dir / "phase4-visual-recognition.json").read_text(encoding="utf-8"))
        evidence["recognition"] = {
            "failedChecks": [
                {
                    "check": "recognition-matches-answer-key",
                    "details": [
                        {"tileId": "A04", "expectedState": "notification", "guessedState": "attention"},
                        {"tileId": "A05", "expectedState": "attention", "guessedState": "notification"},
                    ],
                    "status": "fail",
                },
                {
                    "check": "recognition-confidence",
                    "details": [{"tileId": "A05", "confidence": "low"}],
                    "status": "fail",
                },
            ],
            "status": "rejected",
        }
        evidence["validationChecks"] = {"failed": evidence["recognition"]["failedChecks"], "status": "fail"}
        evidence["visualAcceptance"] = False
        write_json(qa_dir / "phase4-visual-recognition.json", evidence)
        return {
            "theme_dir": theme_dir,
            "phase3_validation": phase3_validation,
            "source_evidence": qa_dir / "phase4-visual-recognition.json",
            "run_dir": run_dir,
        }

    def test_rejects_non_rejected_source_evidence(self):
        with temporary_theme_sizes(), tempfile.TemporaryDirectory() as tmp:
            paths = self.make_fixture(tmp)
            data = json.loads(paths["source_evidence"].read_text(encoding="utf-8"))
            data["visualAcceptance"] = True
            write_json(paths["source_evidence"], data)

            from pet_akari import akari_phase4_gap_repair as repair

            with self.assertRaisesRegex(ValueError, "visualAcceptance false"):
                repair.build_phase4_gap_repair(
                    source_theme=paths["theme_dir"],
                    source_phase4_evidence=paths["source_evidence"],
                    run_dir=paths["run_dir"],
                )

    def test_rejects_source_evidence_without_attention_notification_gap(self):
        with temporary_theme_sizes(), tempfile.TemporaryDirectory() as tmp:
            paths = self.make_fixture(tmp)
            data = json.loads(paths["source_evidence"].read_text(encoding="utf-8"))
            data["recognition"]["failedChecks"] = [{"check": "review-disposition", "status": "fail"}]
            write_json(paths["source_evidence"], data)

            from pet_akari import akari_phase4_gap_repair as repair

            with self.assertRaisesRegex(ValueError, "A04/A05"):
                repair.build_phase4_gap_repair(
                    source_theme=paths["theme_dir"],
                    source_phase4_evidence=paths["source_evidence"],
                    run_dir=paths["run_dir"],
                )

    @unittest.skipUnless(_HAS_CLAWD, "clawd-on-desk validator not available")
    def test_repairs_only_target_states_and_builds_pending_recognition_artifacts(self):
        with temporary_theme_sizes(), tempfile.TemporaryDirectory() as tmp:
            paths = self.make_fixture(tmp)

            from pet_akari import akari_phase4_gap_repair as repair

            result = repair.build_phase4_gap_repair(
                source_theme=paths["theme_dir"],
                source_phase4_evidence=paths["source_evidence"],
                run_dir=paths["run_dir"],
            )

            self.assertEqual(result.run_dir, paths["run_dir"])
            self.assertEqual(result.theme_dir, paths["run_dir"] / "theme")
            self.assertTrue((result.theme_dir / "qa" / "build-manifest.json").is_file())
            self.assertFalse((paths["run_dir"] / "akari-pet.zip").exists())
            self.assertFalse((paths["run_dir"] / "phase5").exists())

            validation = json.loads(result.validation_json.read_text(encoding="utf-8"))
            self.assertFalse(validation["visualAcceptance"])
            self.assertEqual(validation["sourcePhase4Evidence"]["path"], paths["source_evidence"].as_posix())
            self.assertEqual(set(validation["repairTargets"]), {"attention", "error", "notification", "sleeping"})
            self.assertEqual(validation["clawdValidator"]["evidenceRole"], "compatibility-only")

            source_evidence = json.loads(paths["source_evidence"].read_text(encoding="utf-8"))
            self.assertEqual(source_evidence["recognition"]["status"], "rejected")
            self.assertFalse(source_evidence["visualAcceptance"])

            unchanged = set(hq.CORE_STATES) - {"attention", "error", "notification", "sleeping"}
            for state in unchanged:
                self.assertEqual(validation["states"][state]["repairRole"], "copied-unchanged")
                before = apng_frames(paths["theme_dir"] / "assets" / f"akari-{state}.apng")[0]
                after = apng_frames(result.theme_dir / "assets" / f"akari-{state}.apng")[0]
                self.assertIsNone(ImageChops.difference(before, after).getbbox())

            for state in ("attention", "error", "notification", "sleeping"):
                self.assertEqual(validation["states"][state]["repairRole"], "state-local-repair")
                self.assertNotEqual(
                    validation["states"][state]["beforeRuntimeSha256"],
                    validation["states"][state]["afterRuntimeSha256"],
                )
                self.assertTrue(validation["states"][state]["repairRationale"])

            evidence = json.loads(result.visual_recognition_json.read_text(encoding="utf-8"))
            self.assertFalse(evidence["visualAcceptance"])
            self.assertEqual(evidence["recognition"]["status"], "pending")
            self.assertEqual(
                Path(evidence["inputs"]["phase3Validation"]["path"]),
                result.validation_json,
            )
            for name in (
                "preview-128-light.png",
                "preview-128-dark.png",
                "preview-160-light.png",
                "preview-160-dark.png",
                vr.FACE_CROP_SHEET_NAME,
                "answer-key.json",
                "recognition-results.template.json",
                "support-contact-sheet.png",
            ):
                self.assertTrue((result.visual_qa_dir / name).is_file(), name)

    def test_repair_cues_do_not_modify_protected_face_zone(self):
        with temporary_theme_sizes(), tempfile.TemporaryDirectory() as tmp:
            paths = self.make_fixture(tmp)

            from pet_akari import akari_phase3_staging as phase3
            from pet_akari import akari_phase4_gap_repair as repair

            clawd_result = phase3.ValidatorResult(
                command=["node", "stub"], exit_code=0, stdout="", stderr="", status="pass"
            )
            with mock.patch("pet_akari.akari_phase3_staging.run_clawd_validator", return_value=clawd_result):
                result = repair.build_phase4_gap_repair(
                    source_theme=paths["theme_dir"],
                    source_phase4_evidence=paths["source_evidence"],
                    run_dir=paths["run_dir"],
                )

            for state in ("attention", "notification", "error"):
                before = apng_frames(paths["theme_dir"] / "assets" / f"akari-{state}.apng")[0]
                after = apng_frames(result.theme_dir / "assets" / f"akari-{state}.apng")[0]
                self.assertEqual(
                    0,
                    count_changed_pixels_in_box(before, after, protected_face_box(before)),
                    f"{state} repair modified the protected face zone",
                )

    def test_repair_cues_are_readable_at_128px(self):
        with temporary_theme_sizes(), tempfile.TemporaryDirectory() as tmp:
            paths = self.make_fixture(tmp)

            from pet_akari import akari_phase3_staging as phase3
            from pet_akari import akari_phase4_gap_repair as repair

            clawd_result = phase3.ValidatorResult(
                command=["node", "stub"], exit_code=0, stdout="", stderr="", status="pass"
            )
            with mock.patch("pet_akari.akari_phase3_staging.run_clawd_validator", return_value=clawd_result):
                result = repair.build_phase4_gap_repair(
                    source_theme=paths["theme_dir"],
                    source_phase4_evidence=paths["source_evidence"],
                    run_dir=paths["run_dir"],
                )

            for state in ("attention", "notification", "error"):
                before = render_pet_size(apng_frames(paths["theme_dir"] / "assets" / f"akari-{state}.apng")[0])
                after = render_pet_size(apng_frames(result.theme_dir / "assets" / f"akari-{state}.apng")[0])
                bbox = changed_bbox(before, after)
                self.assertIsNotNone(bbox, f"{state} has no visible repair cue at 128px")
                cue_width = bbox[2] - bbox[0]
                cue_height = bbox[3] - bbox[1]
                self.assertGreaterEqual(min(cue_width, cue_height), 15, state)

    def test_attention_and_notification_are_distinct_at_pet_sizes(self):
        with temporary_theme_sizes(), tempfile.TemporaryDirectory() as tmp:
            paths = self.make_fixture(tmp)

            from pet_akari import akari_phase3_staging as phase3
            from pet_akari import akari_phase4_gap_repair as repair

            clawd_result = phase3.ValidatorResult(
                command=["node", "stub"], exit_code=0, stdout="", stderr="", status="pass"
            )
            with mock.patch("pet_akari.akari_phase3_staging.run_clawd_validator", return_value=clawd_result):
                result = repair.build_phase4_gap_repair(
                    source_theme=paths["theme_dir"],
                    source_phase4_evidence=paths["source_evidence"],
                    run_dir=paths["run_dir"],
                )

            attention = apng_frames(result.theme_dir / "assets" / "akari-attention.apng")[0]
            notification = apng_frames(result.theme_dir / "assets" / "akari-notification.apng")[0]
            for height in (128, 160):
                attention_pet = render_pet_size(attention, target_height=height)
                notification_pet = render_pet_size(notification, target_height=height)
                ratio = changed_pixel_ratio(attention_pet, notification_pet)
                self.assertGreaterEqual(
                    ratio,
                    0.08,
                    f"attention/notification differ by only {ratio:.3f} at {height}px",
                )

    def test_sleeping_repair_keeps_smaller_visible_footprint(self):
        with temporary_theme_sizes(), tempfile.TemporaryDirectory() as tmp:
            paths = self.make_fixture(tmp)

            from pet_akari import akari_phase3_staging as phase3
            from pet_akari import akari_phase4_gap_repair as repair

            clawd_result = phase3.ValidatorResult(
                command=["node", "stub"], exit_code=0, stdout="", stderr="", status="pass"
            )
            with mock.patch("pet_akari.akari_phase3_staging.run_clawd_validator", return_value=clawd_result):
                result = repair.build_phase4_gap_repair(
                    source_theme=paths["theme_dir"],
                    source_phase4_evidence=paths["source_evidence"],
                    run_dir=paths["run_dir"],
                )

            sleeping_before = apng_frames(paths["theme_dir"] / "assets" / "akari-sleeping.apng")[0]
            sleeping_after = apng_frames(result.theme_dir / "assets" / "akari-sleeping.apng")[0]
            before_box = sleeping_before.getchannel("A").getbbox()
            after_box = sleeping_after.getchannel("A").getbbox()
            self.assertIsNotNone(before_box)
            self.assertIsNotNone(after_box)
            before_area = (before_box[2] - before_box[0]) * (before_box[3] - before_box[1])
            after_area = (after_box[2] - after_box[0]) * (after_box[3] - after_box[1])
            self.assertLess(after_area, before_area)


if __name__ == "__main__":
    unittest.main()
