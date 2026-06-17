# Phase 4 Repair Regression Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move `pet-akari` to a proper `src/pet_akari` Python package and fix the Phase 4 `attention` / `notification` / `error` visual repair gates that allowed the rejected candidate through.

**Architecture:** First make a mechanical package-layout migration that preserves behavior. Then add failing pet-size visual tests for face protection, cue size, and attention/notification distinction. Finally update the repair transforms and visual-recognition coverage while preserving fail-closed human recognition.

**Tech Stack:** Python 3.11, Pillow, pytest, ruff, uv, APNG assets generated under `work/`.

---

## File Structure

- Create `src/pet_akari/__init__.py`: package marker and version export.
- Move `tools/akari_denser_motion.py` to `src/pet_akari/akari_denser_motion.py`.
- Move `tools/akari_full_motion_quality.py` to `src/pet_akari/akari_full_motion_quality.py`.
- Move `tools/akari_phase3_staging.py` to `src/pet_akari/akari_phase3_staging.py`.
- Move `tools/akari_phase4_gap_repair.py` to `src/pet_akari/akari_phase4_gap_repair.py`.
- Move `tools/akari_phase4_visual_recognition.py` to `src/pet_akari/akari_phase4_visual_recognition.py`.
- Move `tools/akari_source_set_approval.py` to `src/pet_akari/akari_source_set_approval.py`.
- Move `tools/align_row.py` to `src/pet_akari/align_row.py`.
- Move `tools/clawd_hq_theme.py` to `src/pet_akari/clawd_hq_theme.py`.
- Move `tools/extract_peeled.py` to `src/pet_akari/extract_peeled.py`.
- Move `tools/measure_edges.py` to `src/pet_akari/measure_edges.py`.
- Move `tools/reorder_loop.py` to `src/pet_akari/reorder_loop.py`.
- Move `tools/strip_outline.py` to `src/pet_akari/strip_outline.py`.
- Move all `tools/test_*.py` files to `tests/test_*.py`.
- Modify `pyproject.toml`: add setuptools `src` layout config, change pytest path to `tests`, and keep dev dependencies.
- Modify `README.md`: replace `PYTHONPATH=tools`-style examples with `uv run pytest` and package module examples.
- Modify `src/pet_akari/akari_phase4_gap_repair.py`: remove `_draw_face_cue()`, change repair transforms.
- Modify `src/pet_akari/akari_phase4_visual_recognition.py`: extend face-crop coverage to `attention` and `notification`.
- Modify `tests/test_akari_phase4_gap_repair.py`: add pet-size visual gate tests.
- Modify `tests/test_akari_phase4_visual_recognition.py`: update face-crop expectations and fail-closed coverage.
- Create `docs/phase4-human-recognition.md`: short runbook for the `request_user_input` recognition gate.

## Task 1: Mechanical Package Migration

**Files:**
- Create: `src/pet_akari/__init__.py`
- Move: `tools/*.py` implementation files to `src/pet_akari/`
- Move: `tools/test_*.py` to `tests/`
- Modify: `pyproject.toml`
- Modify: `README.md`

- [ ] **Step 1: Move implementation and test files**

Run these commands from the repository root:

```bash
rtk mkdir -p src/pet_akari tests
rtk git mv tools/akari_denser_motion.py src/pet_akari/akari_denser_motion.py
rtk git mv tools/akari_full_motion_quality.py src/pet_akari/akari_full_motion_quality.py
rtk git mv tools/akari_phase3_staging.py src/pet_akari/akari_phase3_staging.py
rtk git mv tools/akari_phase4_gap_repair.py src/pet_akari/akari_phase4_gap_repair.py
rtk git mv tools/akari_phase4_visual_recognition.py src/pet_akari/akari_phase4_visual_recognition.py
rtk git mv tools/akari_source_set_approval.py src/pet_akari/akari_source_set_approval.py
rtk git mv tools/align_row.py src/pet_akari/align_row.py
rtk git mv tools/clawd_hq_theme.py src/pet_akari/clawd_hq_theme.py
rtk git mv tools/extract_peeled.py src/pet_akari/extract_peeled.py
rtk git mv tools/measure_edges.py src/pet_akari/measure_edges.py
rtk git mv tools/reorder_loop.py src/pet_akari/reorder_loop.py
rtk git mv tools/strip_outline.py src/pet_akari/strip_outline.py
rtk git mv tools/test_akari_denser_motion.py tests/test_akari_denser_motion.py
rtk git mv tools/test_akari_full_motion_quality.py tests/test_akari_full_motion_quality.py
rtk git mv tools/test_akari_phase3_staging.py tests/test_akari_phase3_staging.py
rtk git mv tools/test_akari_phase4_gap_repair.py tests/test_akari_phase4_gap_repair.py
rtk git mv tools/test_akari_phase4_visual_recognition.py tests/test_akari_phase4_visual_recognition.py
rtk git mv tools/test_akari_source_set_approval.py tests/test_akari_source_set_approval.py
rtk git mv tools/test_clawd_hq_theme.py tests/test_clawd_hq_theme.py
```

Expected: `tools/` is empty or absent, `src/pet_akari/` contains implementation modules, and `tests/` contains test modules.

- [ ] **Step 2: Add the package initializer**

Create `src/pet_akari/__init__.py` with:

```python
"""Akari pet theme asset pipeline."""

__version__ = "0.1.0"
```

- [ ] **Step 3: Update `pyproject.toml`**

Replace the file content with:

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "pet-akari"
version = "0.1.0"
description = "Akari pet theme asset pipeline for Clawd desktop pets"
readme = "README.md"
license = "MIT"
requires-python = ">=3.11"
dependencies = [
    "pillow>=10.0",
    "numpy>=1.24",
    "scipy>=1.11",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "ruff>=0.4",
]

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]
pythonpath = ["src"]

[tool.ruff]
target-version = "py311"
line-length = 120

[tool.ruff.lint]
select = ["E", "F", "W", "I"]
ignore = ["E501"]
```

- [ ] **Step 4: Update imports**

Change implementation imports that referenced sibling modules by bare name to package imports. Use these exact patterns:

```python
from pet_akari import clawd_hq_theme as hq
from pet_akari import akari_phase3_staging as phase3
from pet_akari import akari_phase4_visual_recognition as phase4
```

Change tests that imported implementation modules by bare name to package imports. Example replacements:

```python
from pet_akari import clawd_hq_theme as hq
from pet_akari import akari_phase4_visual_recognition as phase4
from pet_akari import akari_phase4_gap_repair as repair
```

Inside tests, replace dynamic imports such as:

```python
import akari_phase4_gap_repair as repair
```

with:

```python
from pet_akari import akari_phase4_gap_repair as repair
```

- [ ] **Step 5: Update README commands**

In `README.md`, keep setup and lint sections but use package-era commands:

````markdown
## テスト

```bash
uv run pytest
```

## Lint

```bash
uv run ruff check .
uv run ruff format --check .
```
````

- [ ] **Step 6: Run the migrated test suite**

Run:

```bash
rtk uv run pytest
```

Expected: tests are collected from `tests/` and pass with no `ModuleNotFoundError` for moved modules.

- [ ] **Step 7: Run lint**

Run:

```bash
rtk uv run ruff check .
rtk uv run ruff format --check .
```

Expected: both commands pass.

- [ ] **Step 8: Commit mechanical migration**

Run:

```bash
rtk git add pyproject.toml README.md src tests uv.lock
rtk git commit -m "refactor: move pet akari tools into package"
```

Expected: commit contains only package layout, import, README, and lockfile changes. No repair behavior changes.

## Task 2: Expand Visual Recognition Face-Crop Coverage

**Files:**
- Modify: `src/pet_akari/akari_phase4_visual_recognition.py`
- Modify: `tests/test_akari_phase4_visual_recognition.py`

- [ ] **Step 1: Write the failing coverage test**

In `tests/test_akari_phase4_visual_recognition.py`, update `test_face_crop_sheet_and_distinctness_metrics_are_non_noise` so it expects `attention` and `notification` face-crop pairs:

```python
def test_face_crop_sheet_and_distinctness_metrics_are_non_noise(self):
    with tempfile.TemporaryDirectory() as tmp, temporary_theme_sizes():
        paths = self.make_fixture(tmp)
        self.build(paths)

        evidence = json.loads((paths["qa_dir"] / "phase4-visual-recognition.json").read_text(encoding="utf-8"))
        self.assertTrue((paths["qa_dir"] / "face-crops-idle-error-sleeping-attention-notification.png").is_file())
        pairs = evidence["faceCropDistinctness"]["pairs"]
        expected_states = {"idle", "error", "sleeping", "attention", "notification"}
        expected_pairs = {
            "__".join((left, right))
            for index, left in enumerate(sorted(expected_states))
            for right in sorted(expected_states)[index + 1 :]
        }
        self.assertEqual(expected_pairs, set(pairs))
        for metric in pairs.values():
            self.assertGreater(metric["meanAbsDiffRgb"], 5.0)
            self.assertGreater(metric["changedPixelRatio"], 0.05)
```

Also update `test_face_crop_distinctness_fails_closed_on_near_identical_sources`:

```python
def test_face_crop_distinctness_fails_closed_on_near_identical_sources(self):
    with tempfile.TemporaryDirectory() as tmp, temporary_theme_sizes():
        paths = self.make_fixture(
            tmp,
            identical_face_states=("idle", "error", "sleeping", "attention", "notification"),
        )

        with self.assertRaisesRegex(ValueError, "face crop distinctness"):
            self.build(paths)

        self.assertFalse((paths["qa_dir"] / "phase4-visual-recognition.json").exists())
```

- [ ] **Step 2: Run the focused test to verify it fails**

Run:

```bash
rtk uv run pytest tests/test_akari_phase4_visual_recognition.py::AkariPhase4VisualRecognitionTests::test_face_crop_sheet_and_distinctness_metrics_are_non_noise -v
```

Expected: FAIL because `face-crops-idle-error-sleeping-attention-notification.png` is not generated and pairs only cover idle/error/sleeping.

- [ ] **Step 3: Update face-crop constants**

In `src/pet_akari/akari_phase4_visual_recognition.py`, set:

```python
FACE_CROP_STATES = ("idle", "error", "sleeping", "attention", "notification")
FACE_CROP_SHEET_NAME = "face-crops-idle-error-sleeping-attention-notification.png"
```

Use `FACE_CROP_SHEET_NAME` anywhere the old `face-crops-idle-error-sleeping.png` literal was used. The evidence artifact key should also use the new filename.

- [ ] **Step 4: Run the focused tests**

Run:

```bash
rtk uv run pytest tests/test_akari_phase4_visual_recognition.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit visual-recognition coverage**

Run:

```bash
rtk git add src/pet_akari/akari_phase4_visual_recognition.py tests/test_akari_phase4_visual_recognition.py
rtk git commit -m "test: cover attention notification face crops"
```

Expected: commit contains only face-crop coverage and tests.

## Task 3: Add Pet-Size Repair Gate Tests

**Files:**
- Modify: `tests/test_akari_phase4_gap_repair.py`

- [ ] **Step 1: Add visual helper functions to the test file**

Add these helpers below `apng_frames()`:

```python
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
```

- [ ] **Step 2: Add failing face-protection test**

Add this method to `AkariPhase4GapRepairTests`:

```python
def test_repair_cues_do_not_modify_protected_face_zone(self):
    with temporary_theme_sizes(), tempfile.TemporaryDirectory() as tmp:
        paths = self.make_fixture(tmp)

        from pet_akari import akari_phase4_gap_repair as repair

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
```

- [ ] **Step 3: Add failing pet-size cue test**

Add this method:

```python
def test_repair_cues_are_readable_at_128px(self):
    with temporary_theme_sizes(), tempfile.TemporaryDirectory() as tmp:
        paths = self.make_fixture(tmp)

        from pet_akari import akari_phase4_gap_repair as repair

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
```

- [ ] **Step 4: Add failing attention/notification pairwise test**

Add this method:

```python
def test_attention_and_notification_are_distinct_at_pet_sizes(self):
    with temporary_theme_sizes(), tempfile.TemporaryDirectory() as tmp:
        paths = self.make_fixture(tmp)

        from pet_akari import akari_phase4_gap_repair as repair

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
            self.assertGreaterEqual(ratio, 0.08, f"attention/notification differ by only {ratio:.3f} at {height}px")
```

- [ ] **Step 5: Run the focused tests to verify failures**

Run:

```bash
rtk uv run pytest tests/test_akari_phase4_gap_repair.py::AkariPhase4GapRepairTests::test_repair_cues_do_not_modify_protected_face_zone tests/test_akari_phase4_gap_repair.py::AkariPhase4GapRepairTests::test_repair_cues_are_readable_at_128px tests/test_akari_phase4_gap_repair.py::AkariPhase4GapRepairTests::test_attention_and_notification_are_distinct_at_pet_sizes -v
```

Expected: at least `test_repair_cues_do_not_modify_protected_face_zone` fails against the current `_draw_face_cue()` and face-overlapping error X.

- [ ] **Step 6: Commit failing tests**

Run:

```bash
rtk git add tests/test_akari_phase4_gap_repair.py
rtk git commit -m "test: add pet size repair gates"
```

Expected: commit contains failing tests only. The next task makes them pass.

## Task 4: Repair Attention, Notification, And Error Cues

**Files:**
- Modify: `src/pet_akari/akari_phase4_gap_repair.py`
- Modify: `tests/test_akari_phase4_gap_repair.py`

- [ ] **Step 1: Remove `_draw_face_cue()` calls and helper**

In `src/pet_akari/akari_phase4_gap_repair.py`, delete `_draw_face_cue()` and ensure `_repair_attention()`, `_repair_notification()`, and `_repair_error()` start from:

```python
image = frame.copy()
draw = ImageDraw.Draw(image)
width, height = image.size
alpha = image.getchannel("A").getbbox()
if not alpha:
    return image
left, top, right, bottom = alpha
```

- [ ] **Step 2: Add small drawing helpers**

Add these helpers above `_repair_attention()`:

```python
def _protected_face_bottom(alpha):
    left, top, right, bottom = alpha
    return top + int((bottom - top) * 0.45)


def _side_prop_rect(alpha, image_size, *, width_ratio, height_ratio, y_ratio):
    image_width, image_height = image_size
    left, top, right, bottom = alpha
    prop_width = max(10, int(image_width * width_ratio))
    prop_height = max(8, int(image_height * height_ratio))
    gap = max(2, image_width // 48)
    if right + gap + prop_width <= image_width:
        prop_left = right + gap
    elif left - gap - prop_width >= 0:
        prop_left = left - gap - prop_width
    else:
        prop_left = max(0, min(image_width - prop_width, right - prop_width))
    prop_top = max(0, min(image_height - prop_height, top + int((bottom - top) * y_ratio)))
    return (prop_left, prop_top, prop_left + prop_width, prop_top + prop_height)


def _draw_star(draw, center, radius, *, fill, outline):
    cx, cy = center
    points = [
        (cx, cy - radius),
        (cx + radius // 3, cy - radius // 3),
        (cx + radius, cy - radius // 4),
        (cx + radius // 2, cy + radius // 5),
        (cx + radius * 2 // 3, cy + radius),
        (cx, cy + radius // 2),
        (cx - radius * 2 // 3, cy + radius),
        (cx - radius // 2, cy + radius // 5),
        (cx - radius, cy - radius // 4),
        (cx - radius // 3, cy - radius // 3),
    ]
    draw.polygon(points, fill=fill, outline=outline)
```

- [ ] **Step 3: Replace `_repair_attention()`**

Use this implementation:

```python
def _repair_attention(frame, frame_index):
    image = frame.copy()
    draw = ImageDraw.Draw(image)
    width, height = image.size
    alpha = image.getchannel("A").getbbox()
    if not alpha:
        return image
    left, top, right, bottom = alpha

    arm_width = max(2, width // 24)
    shoulder_y = top + int((bottom - top) * 0.52)
    hand_x = right - max(4, width // 14)
    hand_y = max(0, top + int((bottom - top) * 0.18) + (frame_index % 2))
    draw.line((hand_x - 8, shoulder_y, hand_x + 3, hand_y), fill=(62, 48, 108, 255), width=arm_width)
    draw.ellipse((hand_x - 2, hand_y - 3, hand_x + 6, hand_y + 5), fill=(245, 190, 178, 255))

    prop = _side_prop_rect(alpha, image.size, width_ratio=0.18, height_ratio=0.16, y_ratio=0.06)
    prop_left, prop_top, prop_right, prop_bottom = prop
    radius = max(5, min(prop_right - prop_left, prop_bottom - prop_top) // 2)
    center = ((prop_left + prop_right) // 2, (prop_top + prop_bottom) // 2 + (frame_index % 2))
    _draw_star(draw, center, radius, fill=(255, 220, 86, 255), outline=(64, 76, 145, 255))
    inner_radius = max(2, radius // 2)
    _draw_star(draw, center, inner_radius, fill=(255, 255, 236, 255), outline=(255, 220, 86, 255))
    return image
```

- [ ] **Step 4: Replace `_repair_notification()`**

Use this implementation:

```python
def _repair_notification(frame, frame_index):
    image = frame.copy()
    draw = ImageDraw.Draw(image)
    width, height = image.size
    alpha = image.getchannel("A").getbbox()
    if not alpha:
        return image
    left, top, right, bottom = alpha

    card = _side_prop_rect(alpha, image.size, width_ratio=0.28, height_ratio=0.2, y_ratio=0.26)
    card_left, card_top, card_right, card_bottom = card
    card_top += frame_index % 2
    card_bottom += frame_index % 2
    draw.rounded_rectangle(
        (card_left, card_top, card_right, card_bottom),
        radius=max(3, width // 32),
        fill=(250, 236, 174, 255),
        outline=(70, 105, 168, 255),
        width=max(2, width // 96),
    )

    button_y = card_top + int((card_bottom - card_top) * 0.68)
    button_radius = max(2, (card_bottom - card_top) // 8)
    left_button_x = card_left + int((card_right - card_left) * 0.35)
    right_button_x = card_left + int((card_right - card_left) * 0.65)
    draw.ellipse(
        (left_button_x - button_radius, button_y - button_radius, left_button_x + button_radius, button_y + button_radius),
        fill=(78, 174, 110, 255),
    )
    draw.ellipse(
        (right_button_x - button_radius, button_y - button_radius, right_button_x + button_radius, button_y + button_radius),
        fill=(214, 86, 96, 255),
    )

    bubble_tail = [
        (card_left + max(2, width // 64), card_bottom - max(2, height // 80)),
        (max(0, right - max(2, width // 64)), min(bottom, card_bottom + max(4, height // 32))),
        (card_left + max(6, width // 24), card_bottom - max(2, height // 80)),
    ]
    draw.polygon(bubble_tail, fill=(250, 236, 174, 255), outline=(70, 105, 168, 255))
    return image
```

- [ ] **Step 5: Replace `_repair_error()`**

Use this implementation:

```python
def _repair_error(frame, frame_index):
    image = frame.copy()
    draw = ImageDraw.Draw(image)
    width, height = image.size
    alpha = image.getchannel("A").getbbox()
    if not alpha:
        return image
    left, top, right, bottom = alpha
    face_bottom = _protected_face_bottom(alpha)

    x_size = max(10, width // 5)
    x_left = max(0, min(width - x_size - 1, left + max(2, width // 16)))
    x_top = max(face_bottom + max(2, height // 32), top + int((bottom - top) * 0.58) + (frame_index % 2))
    x_top = min(height - x_size - 1, x_top)
    stroke = max(2, width // 96)
    draw.line((x_left, x_top, x_left + x_size, x_top + x_size), fill=(218, 54, 64, 255), width=stroke)
    draw.line((x_left + x_size, x_top, x_left, x_top + x_size), fill=(218, 54, 64, 255), width=stroke)

    prop = _side_prop_rect(alpha, image.size, width_ratio=0.22, height_ratio=0.16, y_ratio=0.58)
    prop_left, prop_top, prop_right, prop_bottom = prop
    prop_top = max(prop_top, face_bottom + max(2, height // 32))
    draw.rounded_rectangle(
        (prop_left, prop_top, prop_right, prop_bottom),
        radius=max(2, width // 48),
        fill=(70, 74, 92, 255),
        outline=(218, 54, 64, 255),
        width=stroke,
    )
    crack_x = (prop_left + prop_right) // 2
    draw.line(
        (crack_x, prop_top + 2, crack_x - 3, prop_top + 7, crack_x + 2, prop_top + 12),
        fill=(245, 226, 170, 255),
        width=max(1, stroke - 1),
    )
    return image
```

- [ ] **Step 6: Remove obsolete blue/red pixel assertions**

In `tests/test_akari_phase4_gap_repair.py`, replace `test_second_pass_repairs_are_large_cues_without_attention_or_notification_artifacts` with assertions that call the new helper tests or remove the method if it duplicates them. Keep the sleeping footprint assertion by moving it into a focused test:

```python
def test_sleeping_repair_keeps_smaller_visible_footprint(self):
    with temporary_theme_sizes(), tempfile.TemporaryDirectory() as tmp:
        paths = self.make_fixture(tmp)

        from pet_akari import akari_phase4_gap_repair as repair

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
```

- [ ] **Step 7: Run focused repair tests**

Run:

```bash
rtk uv run pytest tests/test_akari_phase4_gap_repair.py -v
```

Expected: PASS.

- [ ] **Step 8: Run combined Phase 4 tests**

Run:

```bash
rtk uv run pytest tests/test_akari_phase4_gap_repair.py tests/test_akari_phase4_visual_recognition.py -v
```

Expected: PASS.

- [ ] **Step 9: Commit repair behavior**

Run:

```bash
rtk git add src/pet_akari/akari_phase4_gap_repair.py tests/test_akari_phase4_gap_repair.py
rtk git commit -m "fix: protect akari face in phase4 repairs"
```

Expected: commit contains repair behavior and matching tests.

## Task 5: Document Human Recognition Gate

**Files:**
- Create: `docs/phase4-human-recognition.md`
- Modify: `README.md`

- [ ] **Step 1: Add recognition runbook**

Create `docs/phase4-human-recognition.md`:

```markdown
# Phase 4 Human Recognition Gate

Fresh Phase 4 visual acceptance requires label-hidden human recognition. Automated compatibility checks are not enough to set `visualAcceptance: true`.

Before asking for recognition answers, show the generated label-hidden previews from the active candidate QA directory:

- `work/akari-hq-apng/phase4-gap-repair/phase4-visual-recognition/qa/preview-128-light.png`
- `work/akari-hq-apng/phase4-gap-repair/phase4-visual-recognition/qa/preview-128-dark.png`
- `work/akari-hq-apng/phase4-gap-repair/phase4-visual-recognition/qa/preview-160-light.png`
- `work/akari-hq-apng/phase4-gap-repair/phase4-visual-recognition/qa/preview-160-dark.png`

Use `request_user_input` choices for each tile. Send a short normal message immediately before the question UI appears.

Collect:

- `guessedState`: `idle`, `thinking`, `working`, `attention`, `error`, `notification`, or `sleeping`
- `confidence`: `high`, `medium`, or `low`
- cue notes for `sleeping`, `error`, `attention`, and `notification`

Preserve the human answers verbatim before comparing them to `answer-key.json`. Keep `visualAcceptance: false` when any required state is wrong, low confidence, missing cue notes, or explicitly rejected.
```

- [ ] **Step 2: Link runbook from README**

Add this line to `README.md` under the tools or test section:

```markdown
Phase 4 の label-hidden human recognition gate は [docs/phase4-human-recognition.md](docs/phase4-human-recognition.md) を参照。
```

- [ ] **Step 3: Commit documentation**

Run:

```bash
rtk git add README.md docs/phase4-human-recognition.md
rtk git commit -m "docs: document phase4 human recognition gate"
```

Expected: commit contains only recognition-gate docs.

## Task 6: Final Verification

**Files:**
- Verify: all moved package modules, tests, docs, and `uv.lock`

- [ ] **Step 1: Run full test suite**

Run:

```bash
rtk uv run pytest
```

Expected: PASS for all tests under `tests/`.

- [ ] **Step 2: Run lint**

Run:

```bash
rtk uv run ruff check .
rtk uv run ruff format --check .
```

Expected: PASS.

- [ ] **Step 3: Inspect git status**

Run:

```bash
rtk git status --short
```

Expected: no untracked implementation files. Generated `work/` artifacts are absent or ignored.

- [ ] **Step 4: Record final commit if needed**

If Task 6 produced doc or lockfile-only updates, run:

```bash
rtk git add README.md pyproject.toml uv.lock
rtk git commit -m "chore: finalize phase4 repair project config"
```

Expected: commit is skipped if there are no staged changes.

## Self-Review

- Spec coverage: package layout is covered by Task 1; repair behavior is covered by Task 4; validation gates are covered by Tasks 2 and 3; human recognition flow is covered by Task 5; verification is covered by Task 6.
- Placeholder scan: no task uses unresolved placeholders, open work markers, or deferred implementation steps.
- Type consistency: package imports consistently use `from pet_akari import module_name as alias`; test helper names are defined before use; face-crop filename is consistently `face-crops-idle-error-sleeping-attention-notification.png`.
