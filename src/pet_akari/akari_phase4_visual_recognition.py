"""Build and validate Phase 4 pet-size visual recognition evidence."""

import argparse
import json
import math
import shutil
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageSequence, ImageStat

from pet_akari import clawd_hq_theme as hq

PHASE = "04"
DEFAULT_THEME_DIR = Path("work/akari-hq-apng/phase3-staging/theme")
DEFAULT_PHASE3_VALIDATION = Path("work/akari-hq-apng/phase3-staging/qa/phase3-validation.json")
DEFAULT_QA_DIR = Path("work/akari-hq-apng/phase4-visual-recognition/qa")
PREVIEW_SIZES = (128, 160)
BACKGROUND_VARIANTS = {
    "light": (246, 246, 242, 255),
    "dark": (24, 26, 34, 255),
}
REQUIRED_RECOGNITION_STATES = ("sleeping", "error", "attention", "notification")
FACE_CROP_STATES = ("idle", "error", "sleeping", "attention", "notification")
FACE_CROP_SHEET_NAME = "face-crops-idle-error-sleeping-attention-notification.png"
REQUIREMENTS_COVERED = ["VQA-01", "VQA-03", "VQA-04"]
DECISION_COVERAGE = [
    "D-01: Consume work/akari-hq-apng/phase3-staging/theme as the default candidate.",
    "D-02: Bind Phase 3 validation and build-manifest evidence before rendering.",
    "D-03: Reject stale runtime assets through manifest and SHA-256 validation.",
    "D-04: Keep Phase 4 logic in a focused tools helper.",
    "D-05: Generate label-hidden 128px and 160px previews for all core states.",
    "D-06: Generate face crops, dark/light previews, recognition template, and seam/motion notes.",
    "D-07: Keep visualAcceptance false until recognition validation passes.",
    "D-08: Require explicit recognition evidence for sleeping/error/attention/notification.",
    "D-09: Measure idle/error/sleeping face crop distinctness after pet-size normalization.",
    "D-10: Record Phase 3 input and Phase 4 artifact hashes for Phase 5 drift rejection.",
]
BOUNDARY_STATEMENT = (
    "Phase 4 build artifacts are pending review; visual acceptance requires filled recognition results."
)
MIN_FACE_MEAN_ABS_DIFF_RGB = 5.0
MIN_FACE_CHANGED_PIXEL_RATIO = 0.05


@dataclass(frozen=True)
class VisualRecognitionResult:
    qa_dir: Path
    evidence_json: Path
    preview_paths: dict[str, Path]
    face_crop_sheet: Path
    support_contact_sheet: Path
    answer_key: Path
    recognition_template: Path
    recognition_results: Path | None = None


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


def _manifest_path(theme_dir, build_manifest=None):
    return Path(build_manifest) if build_manifest is not None else Path(theme_dir) / "qa" / "build-manifest.json"


def _motion_contract_from_manifest(manifest):
    states = {}
    for state in hq.CORE_STATES:
        state_manifest = manifest["states"][state]
        states[state] = {
            "durationMs": int(state_manifest["durationMs"]),
            "inbetweens": int(state_manifest.get("inbetweens", 0)),
        }
    return {"states": states}


def _validate_runtime_asset_set(theme_dir, manifest):
    theme_dir = Path(theme_dir)
    assets_dir = theme_dir / "assets"
    if not assets_dir.is_dir():
        raise FileNotFoundError(assets_dir)
    expected_assets = {f"akari-{state}.apng" for state in hq.CORE_STATES}
    actual_assets = {path.name for path in assets_dir.glob("*.apng")}
    if actual_assets != expected_assets:
        raise ValueError("Phase 4 candidate must contain exactly hq.CORE_STATES runtime APNG assets")
    if set(manifest.get("states", {})) != set(hq.CORE_STATES):
        raise ValueError("build manifest states must exactly match hq.CORE_STATES")
    for state in hq.CORE_STATES:
        runtime_asset = manifest["states"][state]["runtimeAsset"]
        runtime_path = theme_dir / runtime_asset
        if not runtime_path.is_file():
            raise FileNotFoundError(runtime_path)
        if hq.sha256_file(runtime_path) != manifest["states"][state]["runtimeSha256"]:
            raise ValueError(f"{state} runtime APNG hash mismatch")
    return True


def validate_phase3_inputs(
    theme_dir=DEFAULT_THEME_DIR, phase3_validation=DEFAULT_PHASE3_VALIDATION, build_manifest=None
):
    theme_dir = Path(theme_dir)
    if not theme_dir.is_dir():
        raise FileNotFoundError(theme_dir)
    phase3_validation = Path(phase3_validation)
    phase3_data = load_json(phase3_validation)
    if phase3_data.get("phase4Required") is not True:
        raise ValueError("Phase 3 validation must have phase4Required true")
    if phase3_data.get("visualAcceptance") is not False:
        raise ValueError("Phase 3 validation must not already claim visualAcceptance")
    if phase3_data.get("clawdValidator", {}).get("status") != "pass":
        raise ValueError("Phase 3 Clawd validator status must be pass")

    build_manifest = _manifest_path(theme_dir, build_manifest)
    manifest = load_json(build_manifest)
    _validate_runtime_asset_set(theme_dir, manifest)
    motion_contract = _motion_contract_from_manifest(manifest)
    hq.validate_lineage(theme_dir, build_manifest)
    hq.validate_theme_assets(theme_dir, motion_contract=motion_contract)
    return {
        "build_manifest": build_manifest,
        "manifest": manifest,
        "motion_contract": motion_contract,
        "phase3_data": phase3_data,
        "phase3_validation": phase3_validation,
        "theme_dir": theme_dir,
    }


def _display_frames(path):
    path = Path(path)
    with Image.open(path) as image:
        frames = [frame.copy().convert("RGBA") for frame in ImageSequence.Iterator(image)]
        if image.info.get("default_image") and len(frames) > 1:
            frames = frames[1:]
    if not frames:
        raise ValueError(f"{path} has no APNG display frames")
    return frames


def _first_frame(theme_dir, state):
    frames = _display_frames(Path(theme_dir) / "assets" / f"akari-{state}.apng")
    return frames[0]


def _tile_id(index):
    return f"A{index + 1:02d}"


def build_answer_key(output_path, manifest):
    tiles = [
        {
            "state": state,
            "tileId": _tile_id(index),
            "runtimeAsset": manifest["states"][state]["runtimeAsset"],
        }
        for index, state in enumerate(hq.CORE_STATES)
    ]
    return write_json(
        output_path,
        {
            "schemaVersion": 1,
            "tileOrder": "hq.CORE_STATES",
            "tiles": tiles,
        },
    )


def _render_pet_tile(frame, tile_size, background):
    tile = Image.new("RGBA", (tile_size, tile_size), background)
    sprite = frame.copy()
    sprite.thumbnail((tile_size, tile_size), hq._resample_filter())
    left = (tile_size - sprite.width) // 2
    top = (tile_size - sprite.height) // 2
    tile.alpha_composite(sprite, (left, top))
    return tile


def render_label_hidden_previews(theme_dir, qa_dir, answer_key):
    theme_dir = Path(theme_dir)
    qa_dir = ensure_dir(qa_dir)
    answer = load_json(answer_key)
    preview_paths = {}
    label_height = 22
    columns = 4
    rows = math.ceil(len(hq.CORE_STATES) / columns)
    for size in PREVIEW_SIZES:
        for variant, background in BACKGROUND_VARIANTS.items():
            sheet = Image.new(
                "RGBA",
                (columns * size, rows * (size + label_height)),
                background,
            )
            draw = ImageDraw.Draw(sheet)
            label_fill = (28, 30, 38, 255) if variant == "light" else (235, 235, 230, 255)
            for index, tile in enumerate(answer["tiles"]):
                state = tile["state"]
                frame = _first_frame(theme_dir, state)
                pet_tile = _render_pet_tile(frame, size, background)
                column = index % columns
                row = index // columns
                left = column * size
                top = row * (size + label_height)
                sheet.alpha_composite(pet_tile, (left, top))
                draw.text((left + 8, top + size + 4), tile["tileId"], fill=label_fill)
            output = qa_dir / f"preview-{size}-{variant}.png"
            sheet.convert("RGB").save(output)
            preview_paths[f"{size}-{variant}"] = output
    return preview_paths


def _normalized_face_crop(frame, output_size=(96, 96)):
    rgba = frame.convert("RGBA")
    bbox = rgba.getchannel("A").getbbox()
    if bbox is None:
        raise ValueError("cannot crop a blank frame")
    left, top, right, bottom = bbox
    width = right - left
    height = bottom - top
    crop_box = (
        max(0, left + round(width * 0.14)),
        max(0, top),
        min(rgba.width, right - round(width * 0.14)),
        min(rgba.height, top + round(height * 0.58)),
    )
    crop = rgba.crop(crop_box).resize(output_size, hq._resample_filter())
    canvas = Image.new("RGBA", output_size, (0, 0, 0, 0))
    canvas.alpha_composite(crop)
    background = Image.new("RGBA", output_size, (246, 246, 242, 255))
    background.alpha_composite(canvas)
    return background.convert("RGB")


def _face_crops(theme_dir):
    return {state: _normalized_face_crop(_first_frame(theme_dir, state)) for state in FACE_CROP_STATES}


def render_face_crops(theme_dir, output_path):
    crops = _face_crops(theme_dir)
    crop_width, crop_height = next(iter(crops.values())).size
    label_height = 22
    sheet = Image.new("RGB", (len(FACE_CROP_STATES) * crop_width, crop_height + label_height), (246, 246, 242))
    draw = ImageDraw.Draw(sheet)
    for index, state in enumerate(FACE_CROP_STATES):
        left = index * crop_width
        sheet.paste(crops[state], (left, 0))
        draw.text((left + 6, crop_height + 4), state, fill=(28, 30, 38))
    output_path = Path(output_path)
    ensure_dir(output_path.parent)
    sheet.save(output_path)
    return output_path


def compute_face_crop_metrics(theme_dir):
    crops = _face_crops(theme_dir)
    pairs = {}
    for first, second in combinations(FACE_CROP_STATES, 2):
        diff = ImageChops.difference(crops[first], crops[second])
        stat = ImageStat.Stat(diff)
        mean_abs = sum(stat.mean) / len(stat.mean)
        pixels = list(diff.getdata())
        changed = sum(1 for pixel in pixels if max(pixel) > 10)
        changed_ratio = changed / len(pixels)
        key = f"{first}__{second}"
        pairs[key] = {
            "changedPixelRatio": round(changed_ratio, 6),
            "meanAbsDiffRgb": round(mean_abs, 4),
        }
        if mean_abs < MIN_FACE_MEAN_ABS_DIFF_RGB or changed_ratio < MIN_FACE_CHANGED_PIXEL_RATIO:
            raise ValueError(f"face crop distinctness below threshold for {first}/{second}")
    return {
        "metricRole": "fail-closed-sanity-check",
        "pairs": pairs,
        "status": "pass",
        "thresholds": {
            "changedPixelRatio": MIN_FACE_CHANGED_PIXEL_RATIO,
            "meanAbsDiffRgb": MIN_FACE_MEAN_ABS_DIFF_RGB,
        },
    }


def build_recognition_template(output_path, answer_key):
    answer = load_json(answer_key)
    entries = {
        tile["tileId"]: {
            "confidence": "",
            "cueNotes": "",
            "guessedState": "",
        }
        for tile in answer["tiles"]
    }
    return write_json(
        output_path,
        {
            "entries": entries,
            "requiredCueNoteStates": list(REQUIRED_RECOGNITION_STATES),
            "requiredStates": list(hq.CORE_STATES),
            "schemaVersion": 1,
            "status": "template",
        },
    )


def build_seam_motion_notes(theme_dir, manifest):
    notes = {}
    for state in hq.CORE_STATES:
        runtime_path = Path(theme_dir) / manifest["states"][state]["runtimeAsset"]
        frames = _display_frames(runtime_path)
        sample_indices = sorted({0, len(frames) // 2, len(frames) - 1})
        samples = []
        for index in sample_indices:
            frame = frames[index]
            bbox = frame.getchannel("A").getbbox()
            samples.append(
                {
                    "alphaBbox": list(bbox) if bbox else None,
                    "frameIndex": index,
                    "hasVisiblePixels": bbox is not None,
                }
            )
        notes[state] = {
            "encodedFrames": manifest["states"][state]["encodedFrames"],
            "runtimeAsset": manifest["states"][state]["runtimeAsset"],
            "samples": samples,
            "status": "sampled",
        }
    return notes


def _state_evidence(manifest):
    states = {}
    for state in hq.CORE_STATES:
        state_manifest = manifest["states"][state]
        states[state] = {
            "durationMs": state_manifest["durationMs"],
            "encodedFrames": state_manifest["encodedFrames"],
            "inbetweens": state_manifest["inbetweens"],
            "runtimeAsset": state_manifest["runtimeAsset"],
            "runtimeSha256": state_manifest["runtimeSha256"],
            "trueSourceFrames": state_manifest["trueSourceFrames"],
        }
    return states


def _artifact_hashes(paths):
    return {
        name: {
            "path": Path(path).as_posix(),
            "sha256": hq.sha256_file(path),
        }
        for name, path in sorted(paths.items())
    }


def _runtime_asset_hashes(theme_dir, manifest):
    runtime_assets = {}
    for state in hq.CORE_STATES:
        runtime_asset = manifest["states"][state]["runtimeAsset"]
        runtime_path = Path(theme_dir) / runtime_asset
        runtime_assets[state] = {
            "path": runtime_asset,
            "sha256": hq.sha256_file(runtime_path),
        }
    return runtime_assets


def build_pending_evidence(*, paths, artifacts, preview_paths, face_metrics, seam_motion_notes):
    manifest = paths["manifest"]
    artifact_hashes = _artifact_hashes(artifacts)
    input_hashes = {
        "buildManifest": {
            "path": paths["build_manifest"].as_posix(),
            "sha256": hq.sha256_file(paths["build_manifest"]),
        },
        "phase3Validation": {
            "path": paths["phase3_validation"].as_posix(),
            "sha256": hq.sha256_file(paths["phase3_validation"]),
        },
        "runtimeAssets": _runtime_asset_hashes(paths["theme_dir"], manifest),
    }
    return {
        "artifacts": artifact_hashes,
        "boundaryStatement": BOUNDARY_STATEMENT,
        "clawdValidator": {
            "evidenceRole": paths["phase3_data"].get("clawdValidator", {}).get("evidenceRole", "compatibility-only"),
            "status": paths["phase3_data"].get("clawdValidator", {}).get("status"),
        },
        "decisionCoverage": list(DECISION_COVERAGE),
        "faceCropDistinctness": face_metrics,
        "inputs": input_hashes,
        "labelHiddenPreviews": {
            key: {
                "file": path.name,
                "sha256": hq.sha256_file(path),
                "visibleLabels": "tile-id-only",
            }
            for key, path in sorted(preview_paths.items())
        },
        "phase": PHASE,
        "phase5DriftBinding": {
            "artifactSha256": {name: data["sha256"] for name, data in artifact_hashes.items()},
            "inputSha256": {
                "buildManifest": input_hashes["buildManifest"]["sha256"],
                "phase3Validation": input_hashes["phase3Validation"]["sha256"],
                "runtimeAssets": {state: data["sha256"] for state, data in input_hashes["runtimeAssets"].items()},
            },
        },
        "recognition": {
            "requiredCueNoteStates": list(REQUIRED_RECOGNITION_STATES),
            "requiredStates": list(hq.CORE_STATES),
            "status": "pending",
        },
        "requirementsCovered": list(REQUIREMENTS_COVERED),
        "schemaVersion": 1,
        "seamMotionNotes": seam_motion_notes,
        "states": _state_evidence(manifest),
        "themeDir": paths["theme_dir"].as_posix(),
        "visualAcceptance": False,
    }


def build_phase4_visual_recognition(
    *,
    theme_dir=DEFAULT_THEME_DIR,
    phase3_validation=DEFAULT_PHASE3_VALIDATION,
    qa_dir=DEFAULT_QA_DIR,
    build_manifest=None,
):
    paths = validate_phase3_inputs(theme_dir, phase3_validation, build_manifest)
    qa_dir = ensure_dir(qa_dir)
    evidence_json = qa_dir / "phase4-visual-recognition.json"
    answer_key = build_answer_key(qa_dir / "answer-key.json", paths["manifest"])
    preview_paths = render_label_hidden_previews(paths["theme_dir"], qa_dir, answer_key)
    face_crop_sheet = render_face_crops(paths["theme_dir"], qa_dir / FACE_CROP_SHEET_NAME)
    face_metrics = compute_face_crop_metrics(paths["theme_dir"])
    support_contact_sheet = hq.write_contact_sheet(paths["theme_dir"], qa_dir / "support-contact-sheet.png")
    recognition_template = build_recognition_template(qa_dir / "recognition-results.template.json", answer_key)
    seam_motion_notes = build_seam_motion_notes(paths["theme_dir"], paths["manifest"])
    artifacts = {
        path.name: path
        for path in [
            *preview_paths.values(),
            face_crop_sheet,
            support_contact_sheet,
            answer_key,
            recognition_template,
        ]
    }
    evidence = build_pending_evidence(
        paths=paths,
        artifacts=artifacts,
        preview_paths=preview_paths,
        face_metrics=face_metrics,
        seam_motion_notes=seam_motion_notes,
    )
    write_json(evidence_json, evidence)
    return VisualRecognitionResult(
        qa_dir=qa_dir,
        evidence_json=evidence_json,
        preview_paths=preview_paths,
        face_crop_sheet=face_crop_sheet,
        support_contact_sheet=support_contact_sheet,
        answer_key=answer_key,
        recognition_template=recognition_template,
    )


def _load_entries_by_state(recognition_data, answer_key):
    entries = recognition_data.get("entries")
    if not isinstance(entries, dict):
        raise ValueError("recognition results entries must be a JSON object")
    answer = load_json(answer_key)
    tile_to_state = {tile["tileId"]: tile["state"] for tile in answer["tiles"]}
    by_state = {}
    for key, entry in entries.items():
        if not isinstance(entry, dict):
            raise ValueError(f"recognition entry {key} must be a JSON object")
        state = key if key in hq.CORE_STATES else tile_to_state.get(key)
        if state is None:
            raise ValueError(f"unknown recognition entry {key}")
        by_state[state] = entry
    return by_state


def _build_recognition_records(recognition_data, answer_key):
    entries = recognition_data.get("entries")
    if not isinstance(entries, dict):
        raise ValueError("recognition results entries must be a JSON object")
    answer = load_json(answer_key)
    records = []
    for tile in answer["tiles"]:
        tile_id = tile["tileId"]
        expected_state = tile["state"]
        entry = entries.get(tile_id, entries.get(expected_state))
        if not isinstance(entry, dict):
            raise ValueError(f"recognition results missing states: {expected_state}")
        guessed = entry.get("guessedState")
        confidence = entry.get("confidence")
        records.append(
            {
                "confidence": confidence,
                "cueNotes": entry.get("cueNotes", ""),
                "expectedState": expected_state,
                "guessedState": guessed,
                "matchedExpectedState": guessed == expected_state,
                "notes": entry.get("notes", ""),
                "tileId": tile_id,
            }
        )
    return records


def _failed_recognition_checks(recognition_data, records):
    failures = []
    mismatches = [record for record in records if record["matchedExpectedState"] is not True]
    if mismatches:
        failures.append(
            {
                "check": "recognition-matches-answer-key",
                "details": [
                    {
                        "expectedState": record["expectedState"],
                        "guessedState": record["guessedState"],
                        "tileId": record["tileId"],
                    }
                    for record in mismatches
                ],
                "status": "fail",
            }
        )
    low_confidence = [record for record in records if str(record.get("confidence", "")).lower() == "low"]
    if low_confidence:
        failures.append(
            {
                "check": "recognition-confidence",
                "details": [
                    {
                        "confidence": record["confidence"],
                        "expectedState": record["expectedState"],
                        "guessedState": record["guessedState"],
                        "tileId": record["tileId"],
                    }
                    for record in low_confidence
                ],
                "status": "fail",
            }
        )
    status = recognition_data.get("status")
    if status and status not in ("accepted", "approved", "pass"):
        failures.append(
            {
                "check": "review-disposition",
                "details": status,
                "status": "fail",
            }
        )
    return failures


def _validate_recorded_hashes(evidence, *, theme_dir, phase3_validation, build_manifest):
    failures = []
    current_inputs = {
        "buildManifest": hq.sha256_file(build_manifest),
        "phase3Validation": hq.sha256_file(phase3_validation),
    }
    for key, current_sha in current_inputs.items():
        recorded_sha = evidence.get("inputs", {}).get(key, {}).get("sha256")
        if recorded_sha != current_sha:
            failures.append(
                {
                    "check": f"{key}-hash",
                    "currentSha256": current_sha,
                    "recordedSha256": recorded_sha,
                    "status": "fail",
                }
            )
    runtime_assets = evidence.get("inputs", {}).get("runtimeAssets", {})
    for state in hq.CORE_STATES:
        runtime = runtime_assets.get(state, {})
        runtime_path = Path(theme_dir) / runtime.get("path", "")
        current_sha = hq.sha256_file(runtime_path)
        if runtime.get("sha256") != current_sha:
            failures.append(
                {
                    "check": "runtime-asset-hash",
                    "currentSha256": current_sha,
                    "recordedSha256": runtime.get("sha256"),
                    "state": state,
                    "status": "fail",
                }
            )
    for name, artifact in evidence.get("artifacts", {}).items():
        path = Path(artifact.get("path", ""))
        if not path.is_file():
            failures.append(
                {
                    "check": "artifact-exists",
                    "path": path.as_posix(),
                    "status": "fail",
                }
            )
            continue
        current_sha = hq.sha256_file(path)
        if artifact.get("sha256") != current_sha:
            failures.append(
                {
                    "check": "artifact-hash",
                    "currentSha256": current_sha,
                    "name": name,
                    "recordedSha256": artifact.get("sha256"),
                    "status": "fail",
                }
            )
    return failures


def validate_phase4_visual_recognition(
    *,
    theme_dir=DEFAULT_THEME_DIR,
    phase3_validation=DEFAULT_PHASE3_VALIDATION,
    qa_dir=DEFAULT_QA_DIR,
    build_manifest=None,
    recognition_results=None,
    evidence_json=None,
):
    qa_dir = Path(qa_dir)
    evidence_json = Path(evidence_json) if evidence_json is not None else qa_dir / "phase4-visual-recognition.json"
    recognition_results = (
        Path(recognition_results) if recognition_results is not None else qa_dir / "recognition-results.json"
    )
    evidence = load_json(evidence_json)
    if Path(theme_dir) == DEFAULT_THEME_DIR and evidence.get("themeDir"):
        theme_dir = Path(evidence["themeDir"])
    phase3_path = evidence.get("inputs", {}).get("phase3Validation", {}).get("path")
    if Path(phase3_validation) == DEFAULT_PHASE3_VALIDATION and phase3_path:
        phase3_validation = Path(phase3_path)
    paths = validate_phase3_inputs(theme_dir, phase3_validation, build_manifest)
    if evidence.get("visualAcceptance") is not False:
        raise ValueError("Phase 4 evidence must start from pending visualAcceptance false")
    if evidence.get("recognition", {}).get("status") not in ("pending", "rejected"):
        raise ValueError("Phase 4 recognition evidence must be pending or rejected before validation")
    recognition_data = load_json(recognition_results)
    by_state = _load_entries_by_state(recognition_data, qa_dir / "answer-key.json")
    records = _build_recognition_records(recognition_data, qa_dir / "answer-key.json")
    missing = [state for state in hq.CORE_STATES if state not in by_state]
    if missing:
        raise ValueError(f"recognition results missing states: {', '.join(missing)}")
    for state in REQUIRED_RECOGNITION_STATES:
        notes = by_state[state].get("cueNotes")
        if not isinstance(notes, str) or not notes.strip():
            raise ValueError(f"{state} recognition cueNotes are required")

    stored_results = qa_dir / "recognition-results.json"
    if recognition_results.resolve() != stored_results.resolve():
        shutil.copyfile(recognition_results, stored_results)
    evidence["artifacts"][stored_results.name] = {
        "path": stored_results.as_posix(),
        "sha256": hq.sha256_file(stored_results),
    }
    evidence["phase5DriftBinding"]["artifactSha256"][stored_results.name] = hq.sha256_file(stored_results)
    failed_checks = _validate_recorded_hashes(
        evidence,
        theme_dir=paths["theme_dir"],
        phase3_validation=paths["phase3_validation"],
        build_manifest=paths["build_manifest"],
    ) + _failed_recognition_checks(recognition_data, records)
    evidence["recognition"] = {
        "distinguishabilityNotes": recognition_data.get("distinguishabilityNotes", {}),
        "entries": records,
        "failedChecks": failed_checks,
        "requiredCueNoteStates": list(REQUIRED_RECOGNITION_STATES),
        "requiredStates": list(hq.CORE_STATES),
        "results": stored_results.as_posix(),
        "status": "accepted" if not failed_checks else "rejected",
    }
    evidence["recognition"]["seamMotionNotes"] = recognition_data.get("seamMotionNotes", {})
    evidence["requirementsCovered"] = sorted(set(evidence["requirementsCovered"]) | {"VQA-02"})
    evidence["phase5DriftBinding"]["selfHashExcluded"] = True
    evidence["validationChecks"] = {
        "failed": failed_checks,
        "status": "pass" if not failed_checks else "fail",
    }
    evidence["visualAcceptance"] = not failed_checks
    write_json(evidence_json, evidence)
    return VisualRecognitionResult(
        qa_dir=qa_dir,
        evidence_json=evidence_json,
        preview_paths={},
        face_crop_sheet=qa_dir / FACE_CROP_SHEET_NAME,
        support_contact_sheet=qa_dir / "support-contact-sheet.png",
        answer_key=qa_dir / "answer-key.json",
        recognition_template=qa_dir / "recognition-results.template.json",
        recognition_results=stored_results,
    )


def _build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser("build", help="build pending Phase 4 visual recognition artifacts")
    build.add_argument("--theme-dir", type=Path, default=DEFAULT_THEME_DIR)
    build.add_argument("--phase3-validation", type=Path, default=DEFAULT_PHASE3_VALIDATION)
    build.add_argument("--build-manifest", type=Path, default=None)
    build.add_argument("--qa-dir", type=Path, default=DEFAULT_QA_DIR)

    validate = subparsers.add_parser("validate", help="validate filled Phase 4 recognition results")
    validate.add_argument("--theme-dir", type=Path, default=DEFAULT_THEME_DIR)
    validate.add_argument("--phase3-validation", type=Path, default=DEFAULT_PHASE3_VALIDATION)
    validate.add_argument("--build-manifest", type=Path, default=None)
    validate.add_argument("--qa-dir", type=Path, default=DEFAULT_QA_DIR)
    validate.add_argument("--recognition-results", type=Path, default=None)
    validate.add_argument("--evidence-json", type=Path, default=None)
    return parser


def main(argv=None):
    args = _build_parser().parse_args(argv)
    if args.command == "build":
        result = build_phase4_visual_recognition(
            theme_dir=args.theme_dir,
            phase3_validation=args.phase3_validation,
            qa_dir=args.qa_dir,
            build_manifest=args.build_manifest,
        )
        print(f"wrote {result.evidence_json}")
    elif args.command == "validate":
        result = validate_phase4_visual_recognition(
            theme_dir=args.theme_dir,
            phase3_validation=args.phase3_validation,
            build_manifest=args.build_manifest,
            qa_dir=args.qa_dir,
            recognition_results=args.recognition_results,
            evidence_json=args.evidence_json,
        )
        print(f"validated {result.evidence_json}")


if __name__ == "__main__":
    main()
