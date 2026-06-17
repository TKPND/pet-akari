"""Build batches of Phase 4 repair candidates for human visual selection."""

from __future__ import annotations

import itertools
import json
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from pet_akari import akari_phase4_gap_repair as repair

DEFAULT_BATCH_ROOT = Path("work/akari-hq-apng/phase4-candidate-batch")
DEFAULT_BATCH_ID = "default"
DEFAULT_MAX_CANDIDATES = 27
FOCUS_TILE_IDS = ("A04", "A05", "A06")


@dataclass(frozen=True)
class CandidateSpec:
    candidate_id: str
    recipes: dict[str, str]


@dataclass(frozen=True)
class CandidateRecord:
    candidate_id: str
    recipes: dict[str, str]
    run_dir: Path
    status: str
    theme_dir: Path | None = None
    validation_json: Path | None = None
    visual_recognition_json: Path | None = None
    preview_paths: dict[str, str] | None = None
    notes: str = ""


def ensure_dir(path):
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_json(path, data):
    path = Path(path)
    ensure_dir(path.parent)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def parse_recipe_csv(state, value):
    allowed = repair.REPAIR_RECIPES[state]
    recipes = [item.strip() for item in value.split(",") if item.strip()]
    for recipe in recipes:
        if recipe not in allowed:
            raise ValueError(f"unknown {state} recipe: {recipe}")
    return recipes


def expand_recipe_grid(*, attention_recipes, notification_recipes, error_recipes, max_candidates):
    specs = []
    grid = itertools.product(attention_recipes, notification_recipes, error_recipes)
    for index, (attention, notification, error) in enumerate(grid, start=1):
        if len(specs) >= max_candidates:
            break
        specs.append(
            CandidateSpec(
                candidate_id=f"C{index:03d}",
                recipes={
                    "attention": attention,
                    "notification": notification,
                    "error": error,
                },
            )
        )
    return specs


def _record_to_json(record):
    return {
        "candidateId": record.candidate_id,
        "notes": record.notes,
        "previewPaths": record.preview_paths or {},
        "recipes": record.recipes,
        "runDir": record.run_dir.as_posix(),
        "status": record.status,
        "themeDir": record.theme_dir.as_posix() if record.theme_dir else None,
        "validationJson": record.validation_json.as_posix() if record.validation_json else None,
        "visualRecognitionJson": record.visual_recognition_json.as_posix() if record.visual_recognition_json else None,
    }


def write_selection_template(path, candidate_records):
    return write_json(
        path,
        {
            "candidateIds": [record.candidate_id for record in candidate_records if record.status == "built"],
            "recognitionFields": {
                "confidence": ["high", "medium", "low"],
                "guessedState": ["idle", "thinking", "working", "attention", "error", "notification", "sleeping"],
                "requiredCueNoteStates": ["sleeping", "error", "attention", "notification"],
            },
            "reviewDisposition": "",
            "schemaVersion": 1,
            "selectedCandidateId": "",
            "status": "template",
        },
    )


def write_batch_contact_sheet(path, candidate_records, include_all_states=False):
    path = Path(path)
    ensure_dir(path.parent)
    Image.new("RGB", (320, max(1, len(candidate_records)) * 80), "white").save(path)
    return path


def build_candidate_batch(
    *,
    batch_id=DEFAULT_BATCH_ID,
    output_root=DEFAULT_BATCH_ROOT,
    source_theme=repair.DEFAULT_SOURCE_THEME,
    source_phase4_evidence=repair.DEFAULT_SOURCE_PHASE4_EVIDENCE,
    clawd_validator=repair.phase3.DEFAULT_CLAWD_VALIDATOR,
    attention_recipes=None,
    notification_recipes=None,
    error_recipes=None,
    max_candidates=DEFAULT_MAX_CANDIDATES,
    include_all_states=False,
    candidate_builder=repair.build_phase4_gap_repair,
):
    attention_recipes = attention_recipes or list(repair.REPAIR_RECIPES["attention"])
    notification_recipes = notification_recipes or list(repair.REPAIR_RECIPES["notification"])
    error_recipes = error_recipes or list(repair.REPAIR_RECIPES["error"])
    specs = expand_recipe_grid(
        attention_recipes=attention_recipes,
        notification_recipes=notification_recipes,
        error_recipes=error_recipes,
        max_candidates=max_candidates,
    )
    batch_dir = ensure_dir(Path(output_root) / batch_id)
    records = []
    for spec in specs:
        run_dir = batch_dir / f"candidate-{spec.candidate_id}"
        try:
            result = candidate_builder(
                source_theme=source_theme,
                source_phase4_evidence=source_phase4_evidence,
                run_dir=run_dir,
                clawd_validator=clawd_validator,
                repair_recipes=spec.recipes,
            )
            records.append(
                CandidateRecord(
                    candidate_id=spec.candidate_id,
                    recipes=spec.recipes,
                    run_dir=run_dir,
                    status="built",
                    theme_dir=result.theme_dir,
                    validation_json=result.validation_json,
                    visual_recognition_json=result.visual_recognition_json,
                    preview_paths={"128-light": (result.visual_qa_dir / "preview-128-light.png").as_posix()},
                )
            )
        except Exception as exc:
            records.append(
                CandidateRecord(
                    candidate_id=spec.candidate_id,
                    recipes=spec.recipes,
                    run_dir=run_dir,
                    status="invalid",
                    notes=str(exc),
                )
            )
    built_records = [record for record in records if record.status == "built"]
    if built_records:
        contact_sheet = write_batch_contact_sheet(batch_dir / "batch-contact-sheet.png", built_records, include_all_states)
    else:
        contact_sheet = batch_dir / "batch-contact-sheet.png"
    manifest = write_json(
        batch_dir / "batch-manifest.json",
        {
            "batchId": batch_id,
            "candidates": [_record_to_json(record) for record in records],
            "contactSheet": contact_sheet.as_posix(),
            "includeAllStates": include_all_states,
            "schemaVersion": 1,
        },
    )
    selection_template = write_selection_template(batch_dir / "selection-template.json", records)
    if not built_records:
        raise ValueError(f"no valid candidates in batch {batch_id}")
    return {
        "batchDir": batch_dir,
        "contactSheet": contact_sheet,
        "manifest": manifest,
        "selectionTemplate": selection_template,
    }
