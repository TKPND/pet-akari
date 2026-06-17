"""Build a repaired Phase 4 candidate for the visual-recognition gap."""

from __future__ import annotations

import argparse
import json
import shutil
from dataclasses import dataclass
from pathlib import Path

import akari_phase3_staging as phase3
import akari_phase4_visual_recognition as vr
import clawd_hq_theme as hq
from PIL import Image, ImageDraw, ImageSequence

DEFAULT_SOURCE_THEME = Path("work/akari-hq-apng/phase3-staging/theme")
DEFAULT_SOURCE_PHASE4_EVIDENCE = Path("work/akari-hq-apng/phase4-visual-recognition/qa/phase4-visual-recognition.json")
DEFAULT_RUN_DIR = Path("work/akari-hq-apng/phase4-gap-repair")
REPAIR_TARGETS = ("attention", "error", "notification", "sleeping")


@dataclass(frozen=True)
class GapRepairResult:
    run_dir: Path
    masters_dir: Path
    theme_dir: Path
    validation_json: Path
    visual_qa_dir: Path
    visual_recognition_json: Path


def ensure_dir(path):
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_json(path, data):
    path = Path(path)
    ensure_dir(path.parent)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def load_json(path):
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def _display_frames(path):
    with Image.open(path) as image:
        frames = [frame.copy().convert("RGBA") for frame in ImageSequence.Iterator(image)]
        if image.info.get("default_image") and len(frames) > 1:
            frames = frames[1:]
    if not frames:
        raise ValueError(f"{path} has no APNG display frames")
    return frames


def _source_phase3_validation(source_evidence):
    phase3_path = source_evidence.get("inputs", {}).get("phase3Validation", {}).get("path")
    if not phase3_path:
        raise ValueError("source Phase 4 evidence must record inputs.phase3Validation.path")
    return Path(phase3_path)


def _validate_source_evidence(path):
    evidence = load_json(path)
    if evidence.get("visualAcceptance") is not False:
        raise ValueError("source Phase 4 evidence must have visualAcceptance false")
    recognition = evidence.get("recognition", {})
    if recognition.get("status") != "rejected":
        raise ValueError("source Phase 4 evidence must have rejected recognition status")
    failed = recognition.get("failedChecks") or evidence.get("validationChecks", {}).get("failed") or []
    failed_text = json.dumps(failed, sort_keys=True)
    has_a04_a05 = "A04" in failed_text and "A05" in failed_text
    has_attention_notification = "attention" in failed_text and "notification" in failed_text
    if not (has_a04_a05 and has_attention_notification):
        raise ValueError("source Phase 4 evidence must include the A04/A05 attention/notification gap")
    return evidence


def _motion_contract_from_manifest(manifest):
    return {
        "states": {
            state: {
                "durationMs": int(manifest["states"][state]["durationMs"]),
                "inbetweens": int(manifest["states"][state].get("inbetweens", 0)),
            }
            for state in hq.CORE_STATES
        }
    }


def _save_frames(frames, output_dir):
    ensure_dir(output_dir)
    for index, frame in enumerate(frames, start=1):
        frame.save(output_dir / f"{index:02d}.png")


def _draw_face_cue(frame, *, mouth="smile", blush=False):
    image = frame.copy()
    draw = ImageDraw.Draw(image)
    width, height = image.size
    face = image.getchannel("A").getbbox()
    if not face:
        return image
    left, top, right, bottom = face
    cx = (left + right) // 2
    head_top = top + max(4, height // 16)
    eye_y = head_top + max(8, height // 10)
    mouth_y = eye_y + max(7, height // 14)
    draw.ellipse((cx - 13, eye_y - 2, cx - 9, eye_y + 2), fill=(22, 18, 26, 255))
    draw.ellipse((cx + 9, eye_y - 2, cx + 13, eye_y + 2), fill=(22, 18, 26, 255))
    if mouth == "open":
        draw.ellipse((cx - 5, mouth_y - 3, cx + 5, mouth_y + 6), fill=(35, 16, 30, 255))
        draw.arc((cx - 7, mouth_y - 5, cx + 7, mouth_y + 7), 180, 360, fill=(255, 135, 150, 255), width=2)
    elif mouth == "alert":
        draw.line((cx - 8, mouth_y, cx + 8, mouth_y - 3), fill=(28, 18, 28, 255), width=2)
    else:
        draw.arc((cx - 9, mouth_y - 5, cx + 9, mouth_y + 7), 10, 170, fill=(28, 18, 28, 255), width=2)
    if blush:
        draw.ellipse((cx - 24, mouth_y - 4, cx - 16, mouth_y + 3), fill=(246, 112, 134, 210))
        draw.ellipse((cx + 16, mouth_y - 4, cx + 24, mouth_y + 3), fill=(246, 112, 134, 210))
    return image


def _repair_attention(frame, frame_index):
    image = _draw_face_cue(frame, mouth="alert")
    draw = ImageDraw.Draw(image)
    width, height = image.size
    alpha = image.getchannel("A").getbbox()
    if not alpha:
        return image
    left, top, right, bottom = alpha
    hand_x = right - max(4, width // 12)
    shoulder_y = top + int((bottom - top) * 0.48)
    hand_y = top + max(4, height // 12) + (frame_index % 2)
    arm_width = max(2, width // 24)
    draw.line((hand_x - 7, shoulder_y, hand_x + 2, hand_y), fill=(62, 48, 108, 255), width=arm_width)
    draw.ellipse((hand_x - 2, hand_y - 3, hand_x + 5, hand_y + 4), fill=(245, 190, 178, 255))
    mark_height = max(12, height // 8)
    mark_x = max(3, min(width - 6, right - max(8, width // 7)))
    mark_top = max(1, top + max(1, height // 24))
    mark_width = max(3, width // 42)
    draw.line((mark_x, mark_top, mark_x, mark_top + mark_height), fill=(42, 94, 238, 255), width=mark_width)
    dot_radius = max(2, width // 48)
    dot_y = min(height - dot_radius - 1, mark_top + mark_height + dot_radius + 2)
    draw.ellipse(
        (mark_x - dot_radius, dot_y - dot_radius, mark_x + dot_radius, dot_y + dot_radius),
        fill=(42, 94, 238, 255),
    )
    ray_top = mark_top + max(2, mark_height // 4)
    draw.line((mark_x - 8, ray_top + 3, mark_x - 3, ray_top), fill=(42, 94, 238, 255), width=mark_width)
    draw.line((mark_x + 3, ray_top, mark_x + 8, ray_top - 4), fill=(42, 94, 238, 255), width=mark_width)
    draw.line((mark_x - 7, ray_top + 11, mark_x - 3, ray_top + 8), fill=(42, 94, 238, 255), width=mark_width)
    return image


def _repair_notification(frame, frame_index):
    image = _draw_face_cue(frame, mouth="open", blush=True)
    draw = ImageDraw.Draw(image)
    width, height = image.size
    alpha = image.getchannel("A").getbbox()
    if not alpha:
        return image
    left, top, right, bottom = alpha
    cue_width = max(18, width // 2)
    cue_height = max(8, height // 7)
    center_x = (left + right) // 2
    cue_left = max(0, min(width - cue_width, center_x - cue_width // 2))
    cue_top = top + int((bottom - top) * 0.42) + (frame_index % 2)
    cue_right = cue_left + cue_width
    cue_bottom = min(height - 1, cue_top + cue_height)
    draw.rounded_rectangle(
        (cue_left, cue_top, cue_right, cue_bottom),
        radius=max(2, width // 24),
        fill=(255, 202, 84, 255),
        outline=(255, 252, 224, 255),
        width=2,
    )
    mid_y = (cue_top + cue_bottom) // 2
    draw.line((cue_left + 3, cue_top + 3, center_x, mid_y), fill=(58, 94, 142, 255), width=1)
    draw.line((cue_right - 3, cue_top + 3, center_x, mid_y), fill=(58, 94, 142, 255), width=1)
    draw.line((cue_left + 4, cue_bottom - 3, cue_right - 4, cue_bottom - 3), fill=(255, 252, 224, 255), width=1)
    return image


def _repair_error(frame, frame_index):
    image = _draw_face_cue(frame, mouth="alert")
    draw = ImageDraw.Draw(image)
    width, height = image.size
    alpha = image.getchannel("A").getbbox()
    if not alpha:
        return image
    left, top, right, bottom = alpha
    x_left = max(1, left + width // 20)
    x_top = top + max(3, height // 12) + (frame_index % 2)
    x_size = max(8, width // 4)
    draw.line((x_left, x_top, x_left + x_size, x_top + x_size), fill=(218, 54, 64, 255), width=2)
    draw.line((x_left + x_size, x_top, x_left, x_top + x_size), fill=(218, 54, 64, 255), width=2)
    cloud_top = max(0, top - 1)
    cloud_left = max(0, left + width // 5)
    cloud_right = min(width - 1, right - width // 6)
    if cloud_right > cloud_left + 4:
        draw.arc(
            (cloud_left, cloud_top, cloud_right, cloud_top + max(8, height // 5)),
            180,
            360,
            fill=(75, 78, 96, 255),
            width=2,
        )
    return image


def _scale_visible_content(frame, factor):
    alpha_bbox = frame.getchannel("A").getbbox()
    if not alpha_bbox:
        return frame.copy()
    content = frame.crop(alpha_bbox)
    new_size = (
        max(1, min(frame.width, int(round(content.width * factor)))),
        max(1, min(frame.height, int(round(content.height * factor)))),
    )
    scaled = content.resize(new_size, hq._resample_filter())
    output = Image.new("RGBA", frame.size, (0, 0, 0, 0))
    center_x = (alpha_bbox[0] + alpha_bbox[2]) // 2
    bottom = alpha_bbox[3]
    left = max(0, min(frame.width - scaled.width, center_x - scaled.width // 2))
    top = max(0, min(frame.height - scaled.height, bottom - scaled.height))
    output.alpha_composite(scaled, (left, top))
    return output


def _repair_sleeping(frame, frame_index):
    image = _scale_visible_content(frame, 0.86)
    draw = ImageDraw.Draw(image)
    alpha = image.getchannel("A").getbbox()
    if not alpha:
        return image
    left, top, right, bottom = alpha
    z_left = max(left + 1, right - max(10, image.width // 3))
    z_top = max(0, top + 2 + frame_index % 2)
    draw.line(
        (z_left, z_top, z_left + 7, z_top, z_left, z_top + 7, z_left + 7, z_top + 7), fill=(80, 84, 190, 255), width=2
    )
    z2_left = max(left, z_left - 6)
    z2_top = min(bottom - 8, z_top + 7)
    draw.line(
        (z2_left, z2_top, z2_left + 5, z2_top, z2_left, z2_top + 5, z2_left + 5, z2_top + 5),
        fill=(80, 84, 190, 230),
        width=1,
    )
    return image


def _repair_frames(state, frames):
    if state == "attention":
        return [_repair_attention(frame, index) for index, frame in enumerate(frames)]
    if state == "error":
        return [_repair_error(frame, index) for index, frame in enumerate(frames)]
    if state == "notification":
        return [_repair_notification(frame, index) for index, frame in enumerate(frames)]
    if state == "sleeping":
        return [_repair_sleeping(frame, index) for index, frame in enumerate(frames)]
    return [frame.copy() for frame in frames]


def _write_repaired_masters(source_theme, masters_dir):
    source_theme = Path(source_theme)
    masters_dir = Path(masters_dir)
    states = {}
    for state in hq.CORE_STATES:
        source_runtime = source_theme / "assets" / f"akari-{state}.apng"
        frames = _display_frames(source_runtime)
        repaired = _repair_frames(state, frames)
        _save_frames(repaired, masters_dir / state)
        states[state] = {
            "repairRole": "state-local-repair" if state in REPAIR_TARGETS else "copied-unchanged",
            "sourceRuntime": source_runtime.as_posix(),
            "sourceRuntimeSha256": hq.sha256_file(source_runtime),
        }
    return states


def _runtime_hashes(theme_dir):
    return {state: hq.sha256_file(Path(theme_dir) / "assets" / f"akari-{state}.apng") for state in hq.CORE_STATES}


def _build_state_validation(source_theme, repaired_theme, master_states):
    before = _runtime_hashes(source_theme)
    after = _runtime_hashes(repaired_theme)
    rationales = {
        "attention": "Raised-hand pose plus large blue attention mark keep attention distinct without red artifact noise.",
        "error": "Red X and gloom cue add a non-face error signal while preserving Akari identity.",
        "notification": "Horizontal message bubble plus open expression creates inspectable notification cue without a vertical side artifact.",
        "sleeping": "Sleeping footprint is visibly resized with stronger Z cues while preserving sleeping pose and identity.",
    }
    states = {}
    for state in hq.CORE_STATES:
        role = master_states[state]["repairRole"]
        data = {
            "afterRuntimeSha256": after[state],
            "beforeRuntimeSha256": before[state],
            "repairRole": role,
        }
        if role == "copied-unchanged":
            data["copiedFromRuntimeSha256"] = before[state]
        else:
            data["repairRationale"] = rationales[state]
        states[state] = data
    return states


def _write_validation(
    *,
    validation_json,
    source_theme,
    source_evidence_path,
    source_evidence,
    repaired_theme,
    clawd_result,
    states,
):
    build_manifest = Path(repaired_theme) / "qa" / "build-manifest.json"
    data = {
        "boundaryStatement": "Compatibility-only repaired candidate evidence; visual acceptance remains Phase 4 recognition gated.",
        "buildManifest": build_manifest.as_posix(),
        "clawdValidator": {
            "command": clawd_result.command,
            "evidenceRole": "compatibility-only",
            "exitCode": clawd_result.exit_code,
            "status": clawd_result.status,
            "stderr": clawd_result.stderr,
            "stdout": clawd_result.stdout,
        },
        "phase": "04-pet-size-visual-recognition-gate",
        "phase4Required": True,
        "releasePackageAccepted": False,
        "repairTargets": list(REPAIR_TARGETS),
        "requirementsCovered": ["VQA-01", "VQA-02", "VQA-03", "VQA-04"],
        "schemaVersion": 1,
        "sourcePhase4Evidence": {
            "path": Path(source_evidence_path).as_posix(),
            "sha256": hq.sha256_file(source_evidence_path),
            "status": source_evidence.get("recognition", {}).get("status"),
            "visualAcceptance": source_evidence.get("visualAcceptance"),
        },
        "sourceTheme": {
            "path": Path(source_theme).as_posix(),
            "buildManifestSha256": hq.sha256_file(Path(source_theme) / "qa" / "build-manifest.json"),
        },
        "states": states,
        "themeDir": Path(repaired_theme).as_posix(),
        "validationRole": "compatibility-only",
        "visualAcceptance": False,
    }
    return write_json(validation_json, data)


def build_phase4_gap_repair(
    *,
    source_theme=DEFAULT_SOURCE_THEME,
    source_phase4_evidence=DEFAULT_SOURCE_PHASE4_EVIDENCE,
    run_dir=DEFAULT_RUN_DIR,
    clawd_validator=phase3.DEFAULT_CLAWD_VALIDATOR,
):
    source_theme = Path(source_theme)
    source_phase4_evidence = Path(source_phase4_evidence)
    run_dir = Path(run_dir)
    masters_dir = run_dir / "masters"
    theme_dir = run_dir / "theme"
    qa_dir = ensure_dir(run_dir / "qa")
    visual_qa_dir = run_dir / "phase4-visual-recognition" / "qa"
    validation_json = qa_dir / "phase4-gap-repair-validation.json"

    source_evidence = _validate_source_evidence(source_phase4_evidence)
    phase3_validation = _source_phase3_validation(source_evidence)
    source_paths = vr.validate_phase3_inputs(source_theme, phase3_validation)
    motion_contract = _motion_contract_from_manifest(source_paths["manifest"])

    if masters_dir.exists():
        shutil.rmtree(masters_dir)
    if theme_dir.exists():
        shutil.rmtree(theme_dir)
    if visual_qa_dir.exists():
        shutil.rmtree(visual_qa_dir)

    master_states = _write_repaired_masters(source_theme, masters_dir)
    hq.export_theme(masters_dir, theme_dir, include_ultra=False, motion_contract=motion_contract)
    hq.validate_lineage(theme_dir)
    hq.validate_theme_assets(theme_dir, motion_contract=motion_contract)
    clawd_result = phase3.run_clawd_validator(theme_dir, clawd_validator)
    states = _build_state_validation(source_theme, theme_dir, master_states)
    _write_validation(
        validation_json=validation_json,
        source_theme=source_theme,
        source_evidence_path=source_phase4_evidence,
        source_evidence=source_evidence,
        repaired_theme=theme_dir,
        clawd_result=clawd_result,
        states=states,
    )
    if clawd_result.exit_code != 0:
        raise ValueError("Clawd validator failed")

    visual = vr.build_phase4_visual_recognition(
        theme_dir=theme_dir,
        phase3_validation=validation_json,
        qa_dir=visual_qa_dir,
    )
    return GapRepairResult(
        run_dir=run_dir,
        masters_dir=masters_dir,
        theme_dir=theme_dir,
        validation_json=validation_json,
        visual_qa_dir=visual_qa_dir,
        visual_recognition_json=visual.evidence_json,
    )


def _build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build", help="build repaired Phase 4 candidate")
    build.add_argument("--source-theme", type=Path, default=DEFAULT_SOURCE_THEME)
    build.add_argument("--source-phase4-evidence", type=Path, default=DEFAULT_SOURCE_PHASE4_EVIDENCE)
    build.add_argument("--run-dir", type=Path, default=DEFAULT_RUN_DIR)
    build.add_argument("--clawd-validator", type=Path, default=phase3.DEFAULT_CLAWD_VALIDATOR)
    return parser


def main(argv=None):
    args = _build_parser().parse_args(argv)
    if args.command == "build":
        result = build_phase4_gap_repair(
            source_theme=args.source_theme,
            source_phase4_evidence=args.source_phase4_evidence,
            run_dir=args.run_dir,
            clawd_validator=args.clawd_validator,
        )
        print(f"wrote {result.validation_json}")


if __name__ == "__main__":
    main()
