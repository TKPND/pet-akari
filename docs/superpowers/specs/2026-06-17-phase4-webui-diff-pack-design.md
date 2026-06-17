# Phase 4 WebUI Diff Pack Design

## Goal

Build a deterministic review-diff pack for comparing the current Akari theme against the imported ChatGPT WebUI base images, one state at a time. The first milestone is human selection, not automatic acceptance or theme replacement.

The workflow is intentionally A then B:

1. Generate a state-by-state review diff pack so a human can choose `adopt`, `hold`, or `reject`.
2. In a later step, consume the approved selections to build a static candidate theme.

This spec covers step 1 only.

## Context

The repository now has a WebUI base import path that produces normalized transparent PNGs under:

```text
work/akari-hq-apng/phase4-webui-base-images/webui-base-001/
```

That import output has `qa/webui-base-import-validation.json` with `status: review` and `humanReview.visualAcceptance: pending`. Pending human review is acceptable input for this diff pack, because the diff pack exists to perform that review. A validation `status: fail` is not acceptable input.

Existing Phase 4 candidate-batch and gap-repair paths remain separate. This tool does not modify the current theme and does not add WebUI images to candidate batch yet.

## Scope

In scope:

- Compare the current theme APNG first display frame with the WebUI normalized PNG for each `hq.CORE_STATES` state.
- Produce state-specific `current vs webui` comparison images.
- Produce low-resolution contact sheets for fast human review at 128px and 160px.
- Produce a selection template where a human can set each state to `adopt`, `hold`, or `reject`, with notes.
- Produce a manifest containing inputs, outputs, state order, and simple non-authoritative metrics.

Out of scope:

- Replacing theme assets.
- Building a static candidate theme from selections.
- Setting `visualAcceptance` to true.
- Running or interpreting the human recognition gate.
- Adding WebUI candidates into `akari_phase4_candidate_batch.py`.
- Generating new WebUI images.

## Inputs

The build command takes:

- `--theme-dir`: current theme directory containing `assets/akari-<state>.apng`.
- `--webui-import-dir`: WebUI import run directory containing:
  - `normalized/<state>.png`
  - `qa/webui-base-import-validation.json`
- `--pack-id`: output run id.
- `--output-root`: default ignored work root, `work/akari-hq-apng/phase4-webui-diff-packs`.
- `--preview-sizes`: comma-separated list, default `128,160`.

Input validation:

- `theme-dir/assets/akari-<state>.apng` must exist for every state in `hq.CORE_STATES`.
- `webui-import-dir/normalized/<state>.png` must exist for every state in `hq.CORE_STATES`.
- WebUI validation JSON must exist.
- WebUI validation `status` must not be `fail`.
- WebUI validation `stateOrder`, when present, must match `hq.CORE_STATES`.

`humanReview.visualAcceptance: pending` is allowed and expected.

## Outputs

The command writes ignored work artifacts under:

```text
work/akari-hq-apng/phase4-webui-diff-packs/<pack-id>/
```

Output layout:

```text
state-diffs/
  idle.png
  thinking.png
  working.png
  notification.png
  attention.png
  error.png
  sleeping.png
qa/
  diff-contact-sheet-128.png
  diff-contact-sheet-160.png
diff-pack-manifest.json
selection-template.json
```

`state-diffs/<state>.png` shows the current theme frame and WebUI normalized image side by side with minimal labels: state name, `current`, and `webui`.

The contact sheets show all states in `hq.CORE_STATES` order and are designed for quick visual triage. They are not hidden-label recognition sheets; state names are visible because this is a selection workflow.

## Selection Template

`selection-template.json` is the human-editable bridge to the next step. It contains one entry per state:

```json
{
  "state": "notification",
  "decision": "",
  "allowedDecisions": ["adopt", "hold", "reject"],
  "notes": "",
  "currentPreview": "state-diffs/notification.png",
  "webuiPreview": "normalized/notification.png",
  "diffPreview": "state-diffs/notification.png"
}
```

Rules:

- Empty `decision` means not reviewed yet.
- `adopt` means the WebUI version is a candidate to use in the later static-theme step.
- `hold` means do not use yet, but keep it for follow-up review or repair.
- `reject` means do not use this WebUI state.
- Notes are free-form and optional.

The diff-pack builder only creates the template. It does not consume decisions.

## Metrics

`diff-pack-manifest.json` includes simple metrics per state:

- current source size
- WebUI source size
- current alpha bbox
- WebUI alpha bbox
- current opaque ratio
- WebUI opaque ratio
- resized pixel-diff summary at each preview size

These metrics are informational only. They must not auto-adopt, auto-reject, or change visual acceptance.

## Architecture

Create a focused module:

```text
src/pet_akari/akari_phase4_webui_diff_pack.py
```

Responsibilities:

- load and validate WebUI import metadata
- load current APNG first display frames
- load WebUI normalized PNGs
- render state comparison images
- render contact sheets
- write selection template and manifest
- expose a small `build` CLI

The module may reuse patterns from:

- `akari_phase4_webui_base_import.py` for `ensure_dir`, JSON writing, preview-size parsing, and contact-sheet conventions.
- `akari_phase4_visual_recognition.py` for display-frame handling of APNGs.
- `clawd_hq_theme.py` for `hq.CORE_STATES` and resampling.

No existing Phase 4 builder should call this module in this first step.

## Data Flow

1. Read WebUI validation JSON.
2. Validate WebUI import status and state coverage.
3. For each state in `hq.CORE_STATES`:
   - read current APNG first display frame
   - read WebUI normalized PNG
   - render a side-by-side state diff PNG
   - compute lightweight metrics
4. Render contact sheets for configured preview sizes.
5. Write `selection-template.json`.
6. Write `diff-pack-manifest.json` with `status: review`.

The final manifest status is `review` unless a structural failure aborts the command. A structurally invalid input should raise an exception and not pretend to be a usable pack.

## Error Handling

Fail closed for structural problems:

- missing current APNG for any required state
- missing WebUI normalized PNG for any required state
- unreadable image
- missing WebUI validation JSON
- WebUI validation `status: fail`
- state order mismatch
- empty foreground alpha bbox after loading a supposedly transparent source

Do not fail for:

- WebUI validation `status: review`
- `humanReview.visualAcceptance: pending`
- large visual differences between current and WebUI sources

Large visual differences are the point of the review pack and should be recorded, not treated as build failure.

## Testing

Use synthetic images and small APNG fixtures where possible.

Required tests:

- WebUI validation `review` is accepted.
- WebUI validation `fail` is rejected.
- Missing required current APNG fails.
- Missing required WebUI normalized PNG fails.
- APNG first display frame loading handles display frames consistently.
- State diff image is written at the expected size and mode.
- Contact sheet is written at the expected size and mode.
- Selection template contains every state, empty decisions, allowed decisions `adopt`, `hold`, `reject`, and notes fields.
- Manifest has `status: review`, `stateOrder`, output paths, and metrics.
- CLI parser accepts the `build` command and key options.

Verification after implementation:

```bash
rtk uv run pytest tests/test_akari_phase4_webui_diff_pack.py -v
rtk uv run pytest
rtk uv run ruff check .
rtk uv run ruff format --check .
```

Real smoke command after implementation:

```bash
rtk uv run python -m pet_akari.akari_phase4_webui_diff_pack build \
  --theme-dir work/akari-hq-apng/phase3-staging/theme \
  --webui-import-dir work/akari-hq-apng/phase4-webui-base-images/webui-base-001 \
  --pack-id webui-diff-001
```

## Human Review Contract

This tool improves the selection loop, not the final quality gate.

The generated pack is considered ready when:

- all state comparison images exist,
- contact sheets exist,
- selection template exists with all decisions blank,
- manifest reports `status: review`,
- WebUI visual acceptance remains pending.

Human review then fills `selection-template.json`. A later static-theme step consumes only explicit `adopt` decisions.
