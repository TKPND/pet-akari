# Phase 4 Repair Regression Design

Date: 2026-06-17
Status: approved for planning
Repository: pet-akari

## Goal

Fix the Phase 4 visual repair regression in the current `pet-akari` repository while cleaning up the Python project layout enough for continued work here.

The implementation must make the `attention`, `notification`, and `error` states more recognizable at 128-160 px pet size, strengthen the visual gates that allowed the rejected candidate through, and move the project from `tools/`-as-package to a proper `src/pet_akari/` package with tests under `tests/`.

## Non-Goals

- Do not change the sleeping repair unless relocation requires mechanical import updates.
- Do not package or release the Clawd theme.
- Do not migrate the old review bundle into repository docs in this change.
- Do not add console scripts yet; module execution and `uv run pytest` are enough.
- Do not treat automated compatibility validation as visual acceptance.

## Architecture

The repository becomes a normal Python `src` layout project:

- `src/pet_akari/` contains implementation modules currently stored as non-test files under `tools/`.
- `tests/` contains the existing `tools/test_*.py` tests after import updates.
- `pyproject.toml` defines the package layout and keeps `uv run pytest` as the standard verification path.
- `uv.lock` is a tracked reproducibility artifact for this repo going forward.

The main modules for this change are:

- `pet_akari.phase4_gap_repair`: state-local APNG repair transforms and repaired-candidate staging.
- `pet_akari.phase4_visual_recognition`: label-hidden preview generation, recognition-result validation, and visual-gate evidence.
- `pet_akari.clawd_hq_theme`: shared APNG/theme contract and export helpers.

Existing command examples should stop relying on ad hoc `PYTHONPATH=tools` invocation once the package layout is in place.

## Repair Behavior

The next repair pass changes strategy from drawing small primitives on Akari to creating pet-size-readable silhouette and prop differences.

### Sleeping

Keep the current sleeping improvement. The rejected second-pass evidence says sleeping became recognizable at high confidence, so this state should remain unchanged except for mechanical package migration.

### Error

The error state must preserve Akari's face. Any red X, broken-object cue, cloud, or failure prop must be placed below the face zone or outside the character silhouette. The face exclusion zone is the upper head/face portion of the alpha bounding box, with the exact threshold enforced by tests.

The result should read as tool failure or error state, not as damage drawn onto the character.

### Attention

Attention should not use the same card, envelope, or permission prop category as notification. It should read as completion, call-back, or happy attention at pet size. Candidate directions include a large star/check/spark signal, a clear raised-body silhouette, or another non-alert cue that is visually separate from notification.

This design intentionally does not adopt a red warning exclamation mark as the primary attention cue, because that overlaps with permission/alert semantics.

### Notification

Notification should read as permission or alert. It should use a large side or upper-side prop such as a permission bubble, bell, or approval-card shape. It must not rely on text labels, filenames, tiny badges, or microscopic corner icons.

The prop should be positioned so it is visually separate from both the working pose and the attention cue.

### Face Drawing

Remove `_draw_face_cue()` as part of the repair. State distinction should come from pose, silhouette, and surrounding props, not from overwriting existing facial artwork.

## Validation

The visual gates must test for the failure modes shown by the rejected candidate, not only for color counts or changed hashes.

Required gates:

- Face exclusion: repair diffs for `attention`, `notification`, and especially `error` must not alter the protected head/face zone.
- Pet-size minimum cue: repaired cues for `attention`, `notification`, and `error` must remain large enough after 128 px preview normalization.
- Pairwise distinction: `attention` and `notification` must differ meaningfully at 128 px and 160 px, including enough changed area and non-identical cue placement/category.
- Visual recognition coverage: `FACE_CROP_STATES` must include `attention` and `notification`, while face crops remain an identity-preservation sanity check rather than an incentive to alter faces.

Existing fail-closed behavior remains:

- `visualAcceptance` stays `false` until fresh label-hidden human recognition passes.
- Hash binding, label-hidden previews, support contact sheets, and recognition evidence remain part of the Phase 4 evidence path.
- Low confidence, swapped attention/notification guesses, missing cue notes, or rejected disposition keep the result blocked.

## Human Recognition Flow

Fresh human recognition must use the enabled `default_mode_request_user_input` path rather than unstructured chat.

Before calling `request_user_input`, the assistant must send a short normal message saying it is about to show the question UI. The recognition UI should collect, for each tile:

- `guessedState`: one of `idle`, `thinking`, `working`, `attention`, `error`, `notification`, or `sleeping`.
- `confidence`: `high`, `medium`, or `low`.
- Cue notes for the required states: `sleeping`, `error`, `attention`, and `notification`.

The assistant must preserve the user's answers verbatim before comparing them to the answer key.

## Data Flow

1. Move implementation modules from `tools/` to `src/pet_akari/`.
2. Move tests from `tools/test_*.py` to `tests/`.
3. Update imports and `pyproject.toml` for `src` layout.
4. Make `uv run pytest` the standard verification command.
5. Add failing tests for face exclusion, pet-size cue size, attention/notification distinction, and expanded visual-recognition coverage.
6. Update `phase4_gap_repair` to remove face drawing and repair `attention`, `notification`, and `error` using the approved prop/silhouette strategy.
7. Update `phase4_visual_recognition` coverage for attention/notification.
8. Verify with tests and lint.

Generated candidate assets and QA outputs stay under `work/`. The repository change should include code, tests, docs, and lockfile updates, but not generated `work/` artifacts unless a later release/package task explicitly asks for them.

## Verification

Minimum commands:

```bash
rtk uv run pytest
rtk uv run ruff check .
rtk uv run ruff format --check .
```

If module-level commands are needed during implementation, use package module paths rather than `PYTHONPATH=tools` once the migration is complete.

## Risks

- Package migration and visual repair touch the same files; the implementation should keep the migration mechanical before changing behavior.
- Pairwise pixel thresholds can still be gamed by large irrelevant noise, so the tests should combine size, location, and protected-zone checks.
- Face crop distinctness can accidentally encourage face edits. Tests must pair expanded face-crop coverage with explicit face-protection assertions.
- The final human gate remains necessary. Automated gates reduce obvious failures but do not replace label-hidden recognition.

## Approval Record

The user approved:

- Package-first repair.
- `src/pet_akari/` package layout with tests in `tests/`.
- Repair strategy for `attention`, `notification`, and `error`.
- Strengthened pet-size, pairwise, and face-exclusion validation.
- Fresh human recognition through `request_user_input` choices when the candidate is ready.
