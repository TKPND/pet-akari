"""Build batches of Phase 4 repair candidates for human visual selection."""

from __future__ import annotations

import argparse
import itertools
import json
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw

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


def _tile_box(tile_id, tile_size=128, label_height=22, columns=4):
    index = int(tile_id[1:]) - 1
    column = index % columns
    row = index // columns
    left = column * tile_size
    top = row * (tile_size + label_height)
    return (left, top, left + tile_size, top + tile_size)


def _focus_tile_ids(include_all_states):
    if include_all_states:
        return tuple(f"A{index:02d}" for index in range(1, 8))
    return FOCUS_TILE_IDS


def write_batch_contact_sheet(path, candidate_records, include_all_states=False):
    path = Path(path)
    ensure_dir(path.parent)
    tile_ids = _focus_tile_ids(include_all_states)
    tile_size = 128
    padding = 12
    label_width = 72
    row_height = tile_size + padding * 2
    width = label_width + len(tile_ids) * (tile_size + padding)
    height = max(1, len(candidate_records)) * row_height
    sheet = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(sheet)
    for row_index, record in enumerate(candidate_records):
        row_top = row_index * row_height
        draw.text((padding, row_top + padding), record.candidate_id, fill=(20, 24, 32))
        preview = Image.open(record.preview_paths["128-light"]).convert("RGB")
        for tile_index, tile_id in enumerate(tile_ids):
            crop = preview.crop(_tile_box(tile_id))
            left = label_width + tile_index * (tile_size + padding)
            sheet.paste(crop, (left, row_top + padding))
    sheet.save(path)
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
        contact_sheet = write_batch_contact_sheet(
            batch_dir / "batch-contact-sheet.png", built_records, include_all_states
        )
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


def _build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build", help="build a Phase 4 repair candidate batch")
    build.add_argument("--batch-id", default=DEFAULT_BATCH_ID)
    build.add_argument("--output-root", type=Path, default=DEFAULT_BATCH_ROOT)
    build.add_argument("--source-theme", type=Path, default=repair.DEFAULT_SOURCE_THEME)
    build.add_argument("--source-phase4-evidence", type=Path, default=repair.DEFAULT_SOURCE_PHASE4_EVIDENCE)
    build.add_argument("--clawd-validator", type=Path, default=repair.phase3.DEFAULT_CLAWD_VALIDATOR)
    build.add_argument("--attention-recipes", default=",".join(repair.REPAIR_RECIPES["attention"]))
    build.add_argument("--notification-recipes", default=",".join(repair.REPAIR_RECIPES["notification"]))
    build.add_argument("--error-recipes", default=",".join(repair.REPAIR_RECIPES["error"]))
    build.add_argument("--max-candidates", type=int, default=DEFAULT_MAX_CANDIDATES)
    build.add_argument("--include-all-states", action="store_true")
    return parser


def main(argv=None):
    args = _build_parser().parse_args(argv)
    if args.command == "build":
        result = build_candidate_batch(
            batch_id=args.batch_id,
            output_root=args.output_root,
            source_theme=args.source_theme,
            source_phase4_evidence=args.source_phase4_evidence,
            clawd_validator=args.clawd_validator,
            attention_recipes=parse_recipe_csv("attention", args.attention_recipes),
            notification_recipes=parse_recipe_csv("notification", args.notification_recipes),
            error_recipes=parse_recipe_csv("error", args.error_recipes),
            max_candidates=args.max_candidates,
            include_all_states=args.include_all_states,
        )
        print(f"wrote {result['manifest']}")


if __name__ == "__main__":
    main()
