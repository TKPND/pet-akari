"""Build batches of Phase 4 repair candidates for human visual selection."""

from __future__ import annotations

import itertools
import json
from dataclasses import dataclass
from pathlib import Path

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
