# Phase 4 Candidate Batch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Phase 4 の attention / notification / error 修復候補をコード生成バッチで量産し、人間が label-hidden contact sheet から選べるようにする。

**Architecture:** `akari_phase4_gap_repair` に recipe 選択 interface を追加し、既存の theme/export/recognition pipeline は再利用する。新規 `akari_phase4_candidate_batch` が recipe grid を展開し、candidate ごとに build して batch manifest、batch contact sheet、selection template を生成する。

**Tech Stack:** Python 3.11+, Pillow, pytest, ruff, uv, existing APNG/theme pipeline.

---

## File Structure

- Modify: `src/pet_akari/akari_phase4_gap_repair.py`
  - repair recipe constants
  - recipe-aware `_repair_frames()` / `_write_repaired_masters()` / `build_phase4_gap_repair()`
  - CLI `--attention-recipe`, `--notification-recipe`, `--error-recipe`
- Create: `src/pet_akari/akari_phase4_candidate_batch.py`
  - recipe grid expansion
  - candidate build orchestration
  - batch manifest and selection template writing
  - batch contact sheet generation
  - CLI
- Modify: `tests/test_akari_phase4_gap_repair.py`
  - recipe override tests
- Create: `tests/test_akari_phase4_candidate_batch.py`
  - pure helper tests and fake-builder orchestration tests
- Modify: `README.md`
  - add candidate batch command under tool notes

## Task 1: Make Gap Repair Recipe-Aware

**Files:**
- Modify: `src/pet_akari/akari_phase4_gap_repair.py`
- Modify: `tests/test_akari_phase4_gap_repair.py`

- [ ] **Step 1: Write failing tests for recipe override plumbing**

Add these tests to `tests/test_akari_phase4_gap_repair.py` inside `AkariPhase4GapRepairTests`:

```python
def test_recipe_overrides_are_recorded_in_validation(self):
    with temporary_theme_sizes(), tempfile.TemporaryDirectory() as tmp:
        paths = self.make_fixture(tmp)

        from pet_akari import akari_phase4_gap_repair as repair

        recipes = {
            "attention": "raised-hand-only",
            "notification": "message-bubble",
            "error": "lower-x-only",
        }
        result = repair.build_phase4_gap_repair(
            source_theme=paths["theme_dir"],
            source_phase4_evidence=paths["source_evidence"],
            run_dir=paths["run_dir"],
            repair_recipes=recipes,
        )

        validation = json.loads(result.validation_json.read_text(encoding="utf-8"))
        self.assertEqual(recipes, validation["repairRecipes"])
        self.assertEqual("raised-hand-only", validation["states"]["attention"]["repairRecipe"])
        self.assertEqual("message-bubble", validation["states"]["notification"]["repairRecipe"])
        self.assertEqual("lower-x-only", validation["states"]["error"]["repairRecipe"])


def test_invalid_repair_recipe_fails_closed(self):
    with temporary_theme_sizes(), tempfile.TemporaryDirectory() as tmp:
        paths = self.make_fixture(tmp)

        from pet_akari import akari_phase4_gap_repair as repair

        with self.assertRaisesRegex(ValueError, "unknown attention repair recipe"):
            repair.build_phase4_gap_repair(
                source_theme=paths["theme_dir"],
                source_phase4_evidence=paths["source_evidence"],
                run_dir=paths["run_dir"],
                repair_recipes={"attention": "not-a-recipe"},
            )
```

- [ ] **Step 2: Run the focused tests and verify they fail**

Run:

```bash
rtk uv run pytest tests/test_akari_phase4_gap_repair.py::AkariPhase4GapRepairTests::test_recipe_overrides_are_recorded_in_validation tests/test_akari_phase4_gap_repair.py::AkariPhase4GapRepairTests::test_invalid_repair_recipe_fails_closed -v
```

Expected: FAIL because `build_phase4_gap_repair()` does not accept `repair_recipes`.

- [ ] **Step 3: Add recipe constants and resolver**

In `src/pet_akari/akari_phase4_gap_repair.py`, add below `REPAIR_TARGETS`:

```python
DEFAULT_REPAIR_RECIPES = {
    "attention": "small-star-side",
    "notification": "permission-card",
    "error": "broken-card-lower",
}

REPAIR_RECIPES = {
    "attention": ("raised-hand-only", "check-badge", "small-star-side"),
    "notification": ("permission-card", "message-bubble", "bell-side"),
    "error": ("lower-x-only", "broken-card-lower", "alert-panel-lower"),
}
```

Add this resolver near the JSON helpers:

```python
def resolve_repair_recipes(overrides=None):
    recipes = dict(DEFAULT_REPAIR_RECIPES)
    if overrides:
        recipes.update({key: value for key, value in overrides.items() if value is not None})
    for state, recipe in recipes.items():
        allowed = REPAIR_RECIPES.get(state)
        if allowed is None:
            raise ValueError(f"unknown repair recipe state: {state}")
        if recipe not in allowed:
            raise ValueError(f"unknown {state} repair recipe: {recipe}")
    return recipes
```

- [ ] **Step 4: Split repair functions by recipe**

Keep the current visual behavior as the default recipe. Add recipe-aware wrappers:

```python
def _repair_attention(frame, frame_index, recipe="small-star-side"):
    image = _repair_attention_base_pose(frame, frame_index)
    if recipe == "raised-hand-only":
        return image
    if recipe == "check-badge":
        return _draw_attention_check_badge(image, frame_index)
    if recipe == "small-star-side":
        return _draw_attention_star(image, frame_index)
    raise ValueError(f"unknown attention repair recipe: {recipe}")
```

Implement the helper split by moving the current arm drawing into `_repair_attention_base_pose()` and the current star drawing into `_draw_attention_star()`. Add `_draw_attention_check_badge()` using a lower-side check mark:

```python
def _draw_attention_check_badge(image, frame_index):
    draw = ImageDraw.Draw(image)
    width, height = image.size
    alpha = image.getchannel("A").getbbox()
    if not alpha or not _can_draw_repair_cue(alpha, image.size):
        return image
    face_bottom = _protected_face_bottom(alpha)
    prop_left, prop_top, prop_right, prop_bottom = _side_prop_rect(
        alpha, image.size, width_ratio=0.2, height_ratio=0.16, y_ratio=0.54
    )
    prop_top = max(prop_top + frame_index % 2, face_bottom + max(2, height // 32))
    prop_bottom = min(height - 1, prop_top + max(8, prop_bottom - prop_top))
    draw.rounded_rectangle(
        (prop_left, prop_top, prop_right, prop_bottom),
        radius=max(3, width // 40),
        fill=(238, 248, 220, 255),
        outline=(64, 124, 88, 255),
        width=max(2, width // 96),
    )
    mid_y = (prop_top + prop_bottom) // 2
    draw.line(
        (prop_left + 4, mid_y, prop_left + 9, mid_y + 5, prop_right - 4, prop_top + 5),
        fill=(64, 124, 88, 255),
        width=max(2, width // 96),
    )
    return image
```

Apply the same pattern to notification and error:

```python
def _repair_notification(frame, frame_index, recipe="permission-card"):
    if recipe == "permission-card":
        return _repair_notification_permission_card(frame, frame_index)
    if recipe == "message-bubble":
        return _repair_notification_message_bubble(frame, frame_index)
    if recipe == "bell-side":
        return _repair_notification_bell_side(frame, frame_index)
    raise ValueError(f"unknown notification repair recipe: {recipe}")


def _repair_error(frame, frame_index, recipe="broken-card-lower"):
    if recipe == "lower-x-only":
        return _repair_error_lower_x_only(frame, frame_index)
    if recipe == "broken-card-lower":
        return _repair_error_broken_card_lower(frame, frame_index)
    if recipe == "alert-panel-lower":
        return _repair_error_alert_panel_lower(frame, frame_index)
    raise ValueError(f"unknown error repair recipe: {recipe}")
```

Use the current notification implementation as `_repair_notification_permission_card()`. Use the current error implementation as `_repair_error_broken_card_lower()`.

- [ ] **Step 5: Thread recipes through the build pipeline**

Change signatures:

```python
def _repair_frames(state, frames, repair_recipes=None):
    repair_recipes = resolve_repair_recipes(repair_recipes)
    if state == "attention":
        return [_repair_attention(frame, index, repair_recipes["attention"]) for index, frame in enumerate(frames)]
    if state == "error":
        return [_repair_error(frame, index, repair_recipes["error"]) for index, frame in enumerate(frames)]
    if state == "notification":
        return [_repair_notification(frame, index, repair_recipes["notification"]) for index, frame in enumerate(frames)]
    if state == "sleeping":
        return [_repair_sleeping(frame, index) for index, frame in enumerate(frames)]
    return [frame.copy() for frame in frames]
```

Change `_write_repaired_masters()`:

```python
def _write_repaired_masters(source_theme, masters_dir, repair_recipes=None):
    repair_recipes = resolve_repair_recipes(repair_recipes)
    source_theme = Path(source_theme)
    masters_dir = Path(masters_dir)
    states = {}
    for state in hq.CORE_STATES:
        source_runtime = source_theme / "assets" / f"akari-{state}.apng"
        frames = _display_frames(source_runtime)
        repaired = _repair_frames(state, frames, repair_recipes)
        _save_frames(repaired, masters_dir / state)
        states[state] = {
            "repairRecipe": repair_recipes.get(state),
            "repairRole": "state-local-repair" if state in REPAIR_TARGETS else "copied-unchanged",
            "sourceRuntime": source_runtime.as_posix(),
            "sourceRuntimeSha256": hq.sha256_file(source_runtime),
        }
    return states
```

Change the `build_phase4_gap_repair()` signature to add `repair_recipes`:

```python
def build_phase4_gap_repair(
    *,
    source_theme=DEFAULT_SOURCE_THEME,
    source_phase4_evidence=DEFAULT_SOURCE_PHASE4_EVIDENCE,
    run_dir=DEFAULT_RUN_DIR,
    clawd_validator=phase3.DEFAULT_CLAWD_VALIDATOR,
    repair_recipes=None,
):
```

Then add recipe resolution after `validation_json` is assigned:

```python
    repair_recipes = resolve_repair_recipes(repair_recipes)
```

Replace the existing master write call:

```python
    master_states = _write_repaired_masters(source_theme, masters_dir, repair_recipes)
```

Change `_write_validation()` to accept `repair_recipes`, and include it in JSON:

```python
"repairRecipes": repair_recipes,
```

Change `_build_state_validation()` so repaired states include:

```python
if role == "copied-unchanged":
    data["copiedFromRuntimeSha256"] = before[state]
else:
    data["repairRecipe"] = master_states[state].get("repairRecipe")
    data["repairRationale"] = rationales[state]
```

- [ ] **Step 6: Add CLI flags**

In `_build_parser()`, add:

```python
    build.add_argument("--attention-recipe", choices=REPAIR_RECIPES["attention"], default=None)
    build.add_argument("--notification-recipe", choices=REPAIR_RECIPES["notification"], default=None)
    build.add_argument("--error-recipe", choices=REPAIR_RECIPES["error"], default=None)
```

In `main()`:

```python
        repair_recipes = {
            "attention": args.attention_recipe,
            "notification": args.notification_recipe,
            "error": args.error_recipe,
        }
        result = build_phase4_gap_repair(
            source_theme=args.source_theme,
            source_phase4_evidence=args.source_phase4_evidence,
            run_dir=args.run_dir,
            clawd_validator=args.clawd_validator,
            repair_recipes=repair_recipes,
        )
```

- [ ] **Step 7: Run focused tests**

Run:

```bash
rtk uv run pytest tests/test_akari_phase4_gap_repair.py -v
```

Expected: PASS.

- [ ] **Step 8: Commit recipe-aware repair**

Run:

```bash
rtk git add src/pet_akari/akari_phase4_gap_repair.py tests/test_akari_phase4_gap_repair.py
rtk git commit -m "feat: support phase4 repair recipes"
```

## Task 2: Add Candidate Batch Pure Helpers

**Files:**
- Create: `src/pet_akari/akari_phase4_candidate_batch.py`
- Create: `tests/test_akari_phase4_candidate_batch.py`

- [ ] **Step 1: Write failing tests for recipe grid and ids**

Create `tests/test_akari_phase4_candidate_batch.py`:

```python
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from pet_akari import akari_phase4_candidate_batch as batch


class Phase4CandidateBatchTests(unittest.TestCase):
    def test_expand_recipe_grid_is_deterministic_and_capped(self):
        candidates = batch.expand_recipe_grid(
            attention_recipes=["a1", "a2"],
            notification_recipes=["n1", "n2"],
            error_recipes=["e1", "e2"],
            max_candidates=5,
        )

        self.assertEqual([candidate.candidate_id for candidate in candidates], ["C001", "C002", "C003", "C004", "C005"])
        self.assertEqual(
            candidates[0].recipes,
            {"attention": "a1", "notification": "n1", "error": "e1"},
        )
        self.assertEqual(
            candidates[4].recipes,
            {"attention": "a2", "notification": "n1", "error": "e1"},
        )

    def test_parse_recipe_csv_rejects_unknown_values(self):
        with self.assertRaisesRegex(ValueError, "unknown attention recipe"):
            batch.parse_recipe_csv("attention", "raised-hand-only,nope")
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
rtk uv run pytest tests/test_akari_phase4_candidate_batch.py -v
```

Expected: FAIL because `akari_phase4_candidate_batch` does not exist.

- [ ] **Step 3: Create module with dataclasses and pure helpers**

Create `src/pet_akari/akari_phase4_candidate_batch.py`:

```python
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
```

- [ ] **Step 4: Run pure helper tests**

Run:

```bash
rtk uv run pytest tests/test_akari_phase4_candidate_batch.py::Phase4CandidateBatchTests::test_expand_recipe_grid_is_deterministic_and_capped tests/test_akari_phase4_candidate_batch.py::Phase4CandidateBatchTests::test_parse_recipe_csv_rejects_unknown_values -v
```

Expected: PASS.

- [ ] **Step 5: Commit pure helper module**

Run:

```bash
rtk git add src/pet_akari/akari_phase4_candidate_batch.py tests/test_akari_phase4_candidate_batch.py
rtk git commit -m "feat: add phase4 candidate batch helpers"
```

## Task 3: Build Batch Orchestration With Fakeable Builder

**Files:**
- Modify: `src/pet_akari/akari_phase4_candidate_batch.py`
- Modify: `tests/test_akari_phase4_candidate_batch.py`

- [ ] **Step 1: Add failing orchestration tests**

Append to `Phase4CandidateBatchTests`:

```python
    def test_build_candidate_batch_records_valid_and_invalid_candidates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_theme = root / "source-theme"
            source_evidence = root / "source-evidence.json"
            source_theme.mkdir()
            source_evidence.write_text("{}", encoding="utf-8")

            def fake_builder(*, source_theme, source_phase4_evidence, run_dir, clawd_validator, repair_recipes):
                if repair_recipes["error"] == "broken-card-lower":
                    raise ValueError("synthetic broken recipe")
                qa_dir = run_dir / "phase4-visual-recognition" / "qa"
                qa_dir.mkdir(parents=True)
                Image.new("RGB", (512, 300), "white").save(qa_dir / "preview-128-light.png")
                evidence = qa_dir / "phase4-visual-recognition.json"
                evidence.write_text("{}", encoding="utf-8")
                validation = run_dir / "qa" / "phase4-gap-repair-validation.json"
                validation.parent.mkdir(parents=True)
                validation.write_text("{}", encoding="utf-8")
                return repair.GapRepairResult(
                    run_dir=run_dir,
                    masters_dir=run_dir / "masters",
                    theme_dir=run_dir / "theme",
                    validation_json=validation,
                    visual_qa_dir=qa_dir,
                    visual_recognition_json=evidence,
                )

            result = batch.build_candidate_batch(
                batch_id="unit",
                output_root=root / "batch",
                source_theme=source_theme,
                source_phase4_evidence=source_evidence,
                clawd_validator=Path("validator.js"),
                attention_recipes=["raised-hand-only"],
                notification_recipes=["permission-card"],
                error_recipes=["lower-x-only", "broken-card-lower"],
                max_candidates=2,
                candidate_builder=fake_builder,
            )

            manifest = json.loads(result["manifest"].read_text(encoding="utf-8"))
            self.assertEqual("unit", manifest["batchId"])
            self.assertEqual(["built", "invalid"], [candidate["status"] for candidate in manifest["candidates"]])
            self.assertIn("synthetic broken recipe", manifest["candidates"][1]["notes"])
            self.assertTrue(result["selectionTemplate"].is_file())
```

- [ ] **Step 2: Run orchestration test and verify it fails**

Run:

```bash
rtk uv run pytest tests/test_akari_phase4_candidate_batch.py::Phase4CandidateBatchTests::test_build_candidate_batch_records_valid_and_invalid_candidates -v
```

Expected: FAIL because `build_candidate_batch()` is missing.

- [ ] **Step 3: Implement orchestration**

Add to `src/pet_akari/akari_phase4_candidate_batch.py`:

```python
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
            "schemaVersion": 1,
            "status": "template",
            "selectedCandidateId": "",
            "reviewDisposition": "",
            "candidateIds": [record.candidate_id for record in candidate_records if record.status == "built"],
            "recognitionFields": {
                "guessedState": ["idle", "thinking", "working", "attention", "error", "notification", "sleeping"],
                "confidence": ["high", "medium", "low"],
                "requiredCueNoteStates": ["sleeping", "error", "attention", "notification"],
            },
        },
    )


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
            "contactSheet": contact_sheet.as_posix(),
            "includeAllStates": include_all_states,
            "schemaVersion": 1,
            "candidates": [_record_to_json(record) for record in records],
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
```

This references `write_batch_contact_sheet()`, which is implemented in Task 4.

- [ ] **Step 4: Temporarily add contact sheet placeholder for this task**

Add a minimal implementation so orchestration tests can pass before Task 4:

```python
def write_batch_contact_sheet(path, candidate_records, include_all_states=False):
    path = Path(path)
    ensure_dir(path.parent)
    Image.new("RGB", (320, max(1, len(candidate_records)) * 80), "white").save(path)
    return path
```

Task 4 replaces this with real preview slicing.

- [ ] **Step 5: Run orchestration tests**

Run:

```bash
rtk uv run pytest tests/test_akari_phase4_candidate_batch.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit orchestration**

Run:

```bash
rtk git add src/pet_akari/akari_phase4_candidate_batch.py tests/test_akari_phase4_candidate_batch.py
rtk git commit -m "feat: orchestrate phase4 candidate batch"
```

## Task 4: Generate Real Batch Contact Sheet

**Files:**
- Modify: `src/pet_akari/akari_phase4_candidate_batch.py`
- Modify: `tests/test_akari_phase4_candidate_batch.py`

- [ ] **Step 1: Add failing contact sheet test**

Append:

```python
    def test_write_batch_contact_sheet_extracts_focus_tiles(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            preview = root / "preview-128-light.png"
            image = Image.new("RGB", (512, 300), "white")
            colors = {
                "A04": (255, 0, 0),
                "A05": (0, 255, 0),
                "A06": (0, 0, 255),
            }
            # A04 is column 3 row 0, A05 is column 0 row 1, A06 is column 1 row 1.
            for box, color in [
                ((384, 0, 512, 128), colors["A04"]),
                ((0, 150, 128, 278), colors["A05"]),
                ((128, 150, 256, 278), colors["A06"]),
            ]:
                tile = Image.new("RGB", (box[2] - box[0], box[3] - box[1]), color)
                image.paste(tile, box)
            image.save(preview)

            record = batch.CandidateRecord(
                candidate_id="C001",
                recipes={"attention": "raised-hand-only", "notification": "permission-card", "error": "lower-x-only"},
                run_dir=root / "candidate-C001",
                status="built",
                preview_paths={"128-light": preview.as_posix()},
            )
            output = batch.write_batch_contact_sheet(root / "batch-contact-sheet.png", [record], include_all_states=False)

            sheet = Image.open(output).convert("RGB")
            self.assertEqual((428, 152), sheet.size)
            self.assertEqual((255, 0, 0), sheet.getpixel((36, 12)))
            self.assertEqual((0, 255, 0), sheet.getpixel((176, 12)))
            self.assertEqual((0, 0, 255), sheet.getpixel((316, 12)))
```

- [ ] **Step 2: Run contact sheet test and verify it fails against placeholder**

Run:

```bash
rtk uv run pytest tests/test_akari_phase4_candidate_batch.py::Phase4CandidateBatchTests::test_write_batch_contact_sheet_extracts_focus_tiles -v
```

Expected: FAIL because placeholder does not crop tiles.

- [ ] **Step 3: Implement focus tile cropping**

Replace `write_batch_contact_sheet()` with:

```python
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
```

- [ ] **Step 4: Run batch tests**

Run:

```bash
rtk uv run pytest tests/test_akari_phase4_candidate_batch.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit contact sheet**

Run:

```bash
rtk git add src/pet_akari/akari_phase4_candidate_batch.py tests/test_akari_phase4_candidate_batch.py
rtk git commit -m "feat: render phase4 candidate contact sheet"
```

## Task 5: Add CLI And README Usage

**Files:**
- Modify: `src/pet_akari/akari_phase4_candidate_batch.py`
- Modify: `README.md`
- Modify: `tests/test_akari_phase4_candidate_batch.py`

- [ ] **Step 1: Add CLI parser test**

Append:

```python
    def test_build_parser_accepts_default_batch_command(self):
        args = batch._build_parser().parse_args(
            [
                "build",
                "--batch-id",
                "trial",
                "--max-candidates",
                "3",
                "--attention-recipes",
                "raised-hand-only,check-badge",
                "--include-all-states",
            ]
        )

        self.assertEqual("build", args.command)
        self.assertEqual("trial", args.batch_id)
        self.assertEqual(3, args.max_candidates)
        self.assertEqual("raised-hand-only,check-badge", args.attention_recipes)
        self.assertTrue(args.include_all_states)
```

- [ ] **Step 2: Run parser test and verify it fails**

Run:

```bash
rtk uv run pytest tests/test_akari_phase4_candidate_batch.py::Phase4CandidateBatchTests::test_build_parser_accepts_default_batch_command -v
```

Expected: FAIL because `_build_parser()` is missing.

- [ ] **Step 3: Implement parser and main**

Add:

```python
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
```

- [ ] **Step 4: Update README**

Add under the tools section:

````markdown
Phase 4 の修復候補をまとめて探索する場合:

```bash
uv run python -m pet_akari.akari_phase4_candidate_batch build \
  --batch-id trial-001 \
  --max-candidates 27 \
  --clawd-validator /absolute/path/to/validate-theme.js
```

生成結果は `work/akari-hq-apng/phase4-candidate-batch/<batch-id>/` に出力される。`batch-contact-sheet.png` を見て候補を選び、選んだ candidate を既存の human recognition gate に通す。
````

- [ ] **Step 5: Run tests and lint**

Run:

```bash
rtk uv run pytest tests/test_akari_phase4_candidate_batch.py -v
rtk uv run ruff check .
rtk uv run ruff format --check .
```

Expected: all PASS.

- [ ] **Step 6: Commit CLI and docs**

Run:

```bash
rtk git add src/pet_akari/akari_phase4_candidate_batch.py tests/test_akari_phase4_candidate_batch.py README.md
rtk git commit -m "docs: document phase4 candidate batch"
```

## Task 6: Full Verification And Trial Batch Smoke Test

**Files:**
- Verify only; no source changes expected.

- [ ] **Step 1: Run full test suite**

Run:

```bash
rtk uv run pytest
```

Expected: PASS.

- [ ] **Step 2: Run lint**

Run:

```bash
rtk uv run ruff check .
rtk uv run ruff format --check .
```

Expected: PASS.

- [ ] **Step 3: Run a small fake-data-free smoke command when work artifacts are available**

If these paths exist:

```text
work/akari-hq-apng/phase3-staging/theme
work/akari-hq-apng/phase4-visual-recognition/qa/phase4-visual-recognition.json
```

Run a small real batch:

```bash
rtk uv run python -m pet_akari.akari_phase4_candidate_batch build \
  --batch-id smoke \
  --max-candidates 3 \
  --clawd-validator /data_ssd_nvme2/vibe_workspace/create-a-pet-based-on-what/work/clawd-on-desk/scripts/validate-theme.js
```

Expected:

```text
wrote work/akari-hq-apng/phase4-candidate-batch/smoke/batch-manifest.json
```

Then verify:

```bash
rtk ls work/akari-hq-apng/phase4-candidate-batch/smoke
```

Expected: `batch-manifest.json`, `batch-contact-sheet.png`, `selection-template.json`, and at least one `candidate-C00x/`.

If the work artifacts are absent, skip this step and state that the source test/lint verification passed but real batch smoke was skipped because ignored `work/` inputs were missing.

- [ ] **Step 4: Inspect git status**

Run:

```bash
rtk git status --short
```

Expected: clean except ignored `work/` artifacts.

## Self-Review

- Spec coverage: recipe grid, batch manifest, contact sheet, selection template, fail-closed recognition handoff, and validation boundaries are covered.
- Placeholder scan: no task uses unresolved placeholders; all code-facing steps include concrete snippets and commands.
- Type consistency: `CandidateSpec`, `CandidateRecord`, `build_candidate_batch()`, `write_batch_contact_sheet()`, and CLI option names are defined before use and reused consistently.
