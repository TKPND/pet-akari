# Phase 4 WebUI Base Import Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a deterministic Pillow-based importer that turns ChatGPT WebUI-generated Akari state PNGs with baked checker backgrounds into transparent normalized review assets.

**Architecture:** Add one focused module, `pet_akari.akari_phase4_webui_base_import`, with pure helpers first, then orchestration and CLI. The importer remains separate from the existing gap-repair and candidate-batch routes; it produces ignored `work/` artifacts plus validation JSON and contact sheets for human review.

**Tech Stack:** Python 3, Pillow, `unittest`, existing `pet_akari.clawd_hq_theme` constants/helpers, `argparse`, JSON artifacts.

---

## File Structure

- Create: `src/pet_akari/akari_phase4_webui_base_import.py`
  - Owns WebUI base import only: state discovery, archive extraction/copy, checker-background removal, bbox/canvas normalization, QA contact sheets, validation JSON, CLI.
- Create: `tests/test_akari_phase4_webui_base_import.py`
  - Uses small synthetic images to verify deterministic behavior and fail-closed paths.
- Modify: `README.md`
  - Add a short tool row or usage note for the new importer after the module works.
- Do not modify:
  - `src/pet_akari/akari_phase4_gap_repair.py`
  - `src/pet_akari/akari_phase4_candidate_batch.py`
  - Existing Phase 4 visual recognition behavior.

The `work/akari-hq-apng/phase4-webui-base-images/raw/` input artifacts are intentionally ignored and should not be staged.

---

### Task 1: State Discovery And JSON Helpers

**Files:**
- Create: `src/pet_akari/akari_phase4_webui_base_import.py`
- Create: `tests/test_akari_phase4_webui_base_import.py`

- [ ] **Step 1: Write failing tests for state filename discovery and JSON writing**

Create `tests/test_akari_phase4_webui_base_import.py` with:

```python
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from pet_akari import akari_phase4_webui_base_import as importer


class Phase4WebuiBaseImportTests(unittest.TestCase):
    def write_state_inputs(self, root):
        input_dir = root / "akari_clawd_base_images"
        input_dir.mkdir()
        for name in [
            "1-idle.png",
            "2-thinking.png",
            "3-working.png",
            "4-attention.png",
            "5-notification.png",
            "6-error.png",
            "7-sleeping.png",
            "000-base.png",
            "states_overview.png",
        ]:
            Image.new("RGB", (16, 16), "white").save(input_dir / name)
        return input_dir

    def test_collect_state_images_resolves_required_states(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_dir = self.write_state_inputs(root)

            states = importer.collect_state_images(input_dir)

            self.assertEqual(list(states), list(importer.REQUIRED_STATES))
            self.assertEqual("1-idle.png", states["idle"].name)
            self.assertEqual("5-notification.png", states["notification"].name)
            self.assertNotIn("base", states)

    def test_collect_state_images_fails_when_required_state_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_dir = self.write_state_inputs(root)
            (input_dir / "5-notification.png").unlink()

            with self.assertRaisesRegex(ValueError, "missing required state image: notification"):
                importer.collect_state_images(input_dir)

    def test_write_json_creates_parent_and_sorts_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "qa" / "validation.json"

            importer.write_json(output, {"b": 2, "a": 1})

            self.assertEqual({"a": 1, "b": 2}, json.loads(output.read_text(encoding="utf-8")))
            self.assertTrue(output.read_text(encoding="utf-8").endswith("\n"))
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
rtk uv run pytest tests/test_akari_phase4_webui_base_import.py -v
```

Expected: FAIL with `ImportError` or `AttributeError` because `akari_phase4_webui_base_import` does not exist yet.

- [ ] **Step 3: Add minimal module with state discovery helpers**

Create `src/pet_akari/akari_phase4_webui_base_import.py`:

```python
"""Import ChatGPT WebUI-generated Akari base PNGs for Phase 4 review."""

from __future__ import annotations

import json
import re
from pathlib import Path

from pet_akari import clawd_hq_theme as hq

DEFAULT_OUTPUT_ROOT = Path("work/akari-hq-apng/phase4-webui-base-images")
DEFAULT_RUN_ID = "webui-base-001"
DEFAULT_CANVAS_SIZE = 1024
DEFAULT_PREVIEW_SIZES = (128, 160)
DEFAULT_BACKGROUND_TOLERANCE = 18
DEFAULT_PADDING_RATIO = 0.06
REQUIRED_STATES = hq.CORE_STATES


def ensure_dir(path):
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_json(path, data):
    path = Path(path)
    ensure_dir(path.parent)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _state_from_filename(path):
    stem = Path(path).stem.lower()
    for state in REQUIRED_STATES:
        if re.search(rf"(^|[-_]){re.escape(state)}($|[-_])", stem):
            return state
    return None


def collect_state_images(input_dir):
    input_dir = Path(input_dir)
    if not input_dir.is_dir():
        raise FileNotFoundError(input_dir)
    states = {}
    for path in sorted(input_dir.glob("*.png")):
        state = _state_from_filename(path)
        if state and state not in states:
            states[state] = path
    missing = [state for state in REQUIRED_STATES if state not in states]
    if missing:
        raise ValueError(f"missing required state image: {missing[0]}")
    return {state: states[state] for state in REQUIRED_STATES}
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
rtk uv run pytest tests/test_akari_phase4_webui_base_import.py -v
```

Expected: PASS for 3 tests.

- [ ] **Step 5: Commit Task 1**

```bash
rtk git add src/pet_akari/akari_phase4_webui_base_import.py tests/test_akari_phase4_webui_base_import.py
rtk git commit -m "feat: add webui base import state discovery"
```

---

### Task 2: Edge-Connected Checker Background Removal

**Files:**
- Modify: `src/pet_akari/akari_phase4_webui_base_import.py`
- Modify: `tests/test_akari_phase4_webui_base_import.py`

- [ ] **Step 1: Add failing tests for background removal**

Append these helpers and tests inside `Phase4WebuiBaseImportTests` in `tests/test_akari_phase4_webui_base_import.py`:

```python
    def checker_image(self, size=(24, 24)):
        image = Image.new("RGBA", size, (255, 255, 255, 255))
        pixels = image.load()
        colors = [(255, 255, 255, 255), (236, 238, 242, 255)]
        for y in range(size[1]):
            for x in range(size[0]):
                pixels[x, y] = colors[((x // 4) + (y // 4)) % 2]
        return image

    def test_remove_checker_background_removes_only_edge_connected_background(self):
        image = self.checker_image()
        pixels = image.load()
        for y in range(6, 18):
            for x in range(8, 16):
                pixels[x, y] = (255, 245, 230, 255)
        pixels[12, 12] = (236, 238, 242, 255)

        result, metrics = importer.remove_checker_background(image, tolerance=18)

        self.assertEqual(0, result.getpixel((0, 0))[3])
        self.assertEqual(255, result.getpixel((10, 10))[3])
        self.assertEqual(255, result.getpixel((12, 12))[3])
        self.assertEqual([8, 6, 16, 18], metrics["alphaBBox"])
        self.assertGreater(metrics["removedPixels"], 0)
        self.assertGreater(metrics["retainedOpaqueRatio"], 0)

    def test_alpha_bbox_fails_for_empty_foreground(self):
        image = self.checker_image()
        result, _metrics = importer.remove_checker_background(image, tolerance=18)

        with self.assertRaisesRegex(ValueError, "foreground bbox is empty"):
            importer.alpha_bbox(result)
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
rtk uv run pytest tests/test_akari_phase4_webui_base_import.py::Phase4WebuiBaseImportTests::test_remove_checker_background_removes_only_edge_connected_background tests/test_akari_phase4_webui_base_import.py::Phase4WebuiBaseImportTests::test_alpha_bbox_fails_for_empty_foreground -v
```

Expected: FAIL with `AttributeError` for `remove_checker_background` or `alpha_bbox`.

- [ ] **Step 3: Implement background removal**

Add imports near the top of `src/pet_akari/akari_phase4_webui_base_import.py`:

```python
from collections import deque
```

Add these functions after `collect_state_images`:

```python
def _is_low_chroma_light(pixel):
    red, green, blue = pixel[:3]
    return min(red, green, blue) >= 220 and max(red, green, blue) - min(red, green, blue) <= 24


def _edge_points(width, height):
    for x in range(width):
        yield x, 0
        yield x, height - 1
    for y in range(1, height - 1):
        yield 0, y
        yield width - 1, y


def _within_tolerance(pixel, palette, tolerance):
    red, green, blue = pixel[:3]
    for target in palette:
        if max(abs(red - target[0]), abs(green - target[1]), abs(blue - target[2])) <= tolerance:
            return True
    return False


def _checker_palette(image):
    rgba = image.convert("RGBA")
    pixels = rgba.load()
    palette = []
    seen = set()
    for point in _edge_points(rgba.width, rgba.height):
        rgb = pixels[point][:3]
        if rgb not in seen and _is_low_chroma_light(rgb):
            seen.add(rgb)
            palette.append(rgb)
    if not palette:
        raise ValueError("could not infer checker background palette")
    return palette


def alpha_bbox(image):
    bbox = image.convert("RGBA").getchannel("A").getbbox()
    if bbox is None:
        raise ValueError("foreground bbox is empty")
    return bbox


def remove_checker_background(image, tolerance=DEFAULT_BACKGROUND_TOLERANCE):
    rgba = image.convert("RGBA")
    palette = _checker_palette(rgba)
    pixels = rgba.load()
    queue = deque()
    visited = set()
    for point in _edge_points(rgba.width, rgba.height):
        if point not in visited and _within_tolerance(pixels[point], palette, tolerance):
            visited.add(point)
            queue.append(point)

    while queue:
        x, y = queue.popleft()
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if nx < 0 or ny < 0 or nx >= rgba.width or ny >= rgba.height:
                continue
            point = (nx, ny)
            if point in visited:
                continue
            if _within_tolerance(pixels[point], palette, tolerance):
                visited.add(point)
                queue.append(point)

    for x, y in visited:
        red, green, blue, _alpha = pixels[x, y]
        pixels[x, y] = (red, green, blue, 0)

    bbox = alpha_bbox(rgba)
    opaque_pixels = sum(1 for pixel in rgba.getdata() if pixel[3] > 0)
    edge_opaque = sum(1 for point in _edge_points(rgba.width, rgba.height) if pixels[point][3] > 0)
    edge_total = (rgba.width * 2) + max(0, rgba.height - 2) * 2
    metrics = {
        "alphaBBox": list(bbox),
        "edgeOpaqueRatio": edge_opaque / edge_total if edge_total else 0,
        "palette": [list(color) for color in palette],
        "removedPixels": len(visited),
        "retainedOpaqueRatio": opaque_pixels / (rgba.width * rgba.height),
        "sourceSize": [rgba.width, rgba.height],
        "tolerance": tolerance,
    }
    return rgba, metrics
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
rtk uv run pytest tests/test_akari_phase4_webui_base_import.py -v
```

Expected: PASS for 5 tests.

- [ ] **Step 5: Commit Task 2**

```bash
rtk git add src/pet_akari/akari_phase4_webui_base_import.py tests/test_akari_phase4_webui_base_import.py
rtk git commit -m "feat: remove webui checker backgrounds"
```

---

### Task 3: Normalize Images And Render Contact Sheets

**Files:**
- Modify: `src/pet_akari/akari_phase4_webui_base_import.py`
- Modify: `tests/test_akari_phase4_webui_base_import.py`

- [ ] **Step 1: Add failing tests for normalize and contact sheet output**

Append these tests inside `Phase4WebuiBaseImportTests`:

```python
    def test_normalize_foreground_fits_square_canvas_with_transparency(self):
        image = Image.new("RGBA", (30, 40), (0, 0, 0, 0))
        for y in range(10, 35):
            for x in range(8, 22):
                image.putpixel((x, y), (255, 120, 80, 255))

        normalized, metrics = importer.normalize_foreground(image, canvas_size=64, padding_ratio=0.1)

        self.assertEqual((64, 64), normalized.size)
        self.assertEqual(0, normalized.getpixel((0, 0))[3])
        self.assertIsNotNone(normalized.getchannel("A").getbbox())
        self.assertEqual([8, 10, 22, 35], metrics["sourceBBox"])
        self.assertEqual([64, 64], metrics["canvasSize"])

    def test_write_contact_sheet_writes_labeled_preview(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            normalized_dir = root / "normalized"
            normalized_dir.mkdir()
            normalized = {}
            for index, state in enumerate(importer.REQUIRED_STATES):
                path = normalized_dir / f"{state}.png"
                image = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
                image.putpixel((8 + index, 8), (255, 80, 40, 255))
                image.save(path)
                normalized[state] = path

            output = importer.write_contact_sheet(root / "qa" / "contact-sheet-32.png", normalized, preview_size=32)

            self.assertTrue(output.is_file())
            with Image.open(output) as sheet:
                self.assertEqual((32 * 4, (32 + 22) * 2), sheet.size)
                self.assertEqual("RGB", sheet.mode)

    def test_write_background_removal_preview_writes_checker_backed_sheet(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cleaned = {}
            for index, state in enumerate(importer.REQUIRED_STATES):
                image = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
                image.putpixel((8 + index, 8), (255, 80, 40, 255))
                cleaned[state] = image

            output = importer.write_background_removal_preview(
                root / "qa" / "background-removal-preview.png", cleaned, preview_size=32
            )

            self.assertTrue(output.is_file())
            with Image.open(output) as sheet:
                self.assertEqual((32 * 4, (32 + 22) * 2), sheet.size)
                self.assertEqual("RGB", sheet.mode)
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
rtk uv run pytest tests/test_akari_phase4_webui_base_import.py::Phase4WebuiBaseImportTests::test_normalize_foreground_fits_square_canvas_with_transparency tests/test_akari_phase4_webui_base_import.py::Phase4WebuiBaseImportTests::test_write_contact_sheet_writes_labeled_preview tests/test_akari_phase4_webui_base_import.py::Phase4WebuiBaseImportTests::test_write_background_removal_preview_writes_checker_backed_sheet -v
```

Expected: FAIL with `AttributeError` for `normalize_foreground`, `write_contact_sheet`, or `write_background_removal_preview`.

- [ ] **Step 3: Implement normalize and contact sheet helpers**

Add import:

```python
from PIL import Image, ImageDraw
```

If `PIL` is not imported yet, place it after the standard library imports and before `pet_akari` imports.

Add these functions after `remove_checker_background`:

```python
def normalize_foreground(image, canvas_size=DEFAULT_CANVAS_SIZE, padding_ratio=DEFAULT_PADDING_RATIO):
    rgba = image.convert("RGBA")
    bbox = alpha_bbox(rgba)
    crop = rgba.crop(bbox)
    padding = max(0, int(canvas_size * padding_ratio))
    max_size = max(1, canvas_size - padding * 2)
    crop.thumbnail((max_size, max_size), hq._resample_filter())
    canvas = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
    left = (canvas_size - crop.width) // 2
    top = (canvas_size - crop.height) // 2
    canvas.alpha_composite(crop, (left, top))
    metrics = {
        "canvasSize": [canvas_size, canvas_size],
        "normalizedBBox": list(alpha_bbox(canvas)),
        "outputPasteBox": [left, top, left + crop.width, top + crop.height],
        "padding": padding,
        "sourceBBox": list(bbox),
    }
    return canvas, metrics


def _render_preview_tile(path, preview_size):
    with Image.open(path) as image:
        frame = image.convert("RGBA")
    frame.thumbnail((preview_size, preview_size), hq._resample_filter())
    tile = Image.new("RGBA", (preview_size, preview_size), (255, 255, 255, 0))
    left = (preview_size - frame.width) // 2
    top = (preview_size - frame.height) // 2
    tile.alpha_composite(frame, (left, top))
    return tile


def write_contact_sheet(path, normalized_paths, preview_size):
    path = Path(path)
    ensure_dir(path.parent)
    columns = 4
    label_height = 22
    rows = (len(REQUIRED_STATES) + columns - 1) // columns
    sheet = Image.new("RGBA", (columns * preview_size, rows * (preview_size + label_height)), (245, 247, 250, 255))
    draw = ImageDraw.Draw(sheet)
    for index, state in enumerate(REQUIRED_STATES):
        tile = _render_preview_tile(normalized_paths[state], preview_size)
        column = index % columns
        row = index // columns
        left = column * preview_size
        top = row * (preview_size + label_height)
        sheet.alpha_composite(tile, (left, top))
        draw.text((left + 6, top + preview_size + 4), state, fill=(20, 24, 32, 255))
    sheet.convert("RGB").save(path)
    return path


def _checker_tile(size):
    tile = Image.new("RGBA", (size, size), (255, 255, 255, 255))
    draw = ImageDraw.Draw(tile)
    cell = max(4, size // 8)
    for y in range(0, size, cell):
        for x in range(0, size, cell):
            if ((x // cell) + (y // cell)) % 2:
                draw.rectangle((x, y, x + cell - 1, y + cell - 1), fill=(232, 236, 242, 255))
    return tile


def write_background_removal_preview(path, cleaned_images, preview_size):
    path = Path(path)
    ensure_dir(path.parent)
    columns = 4
    label_height = 22
    rows = (len(REQUIRED_STATES) + columns - 1) // columns
    sheet = Image.new("RGBA", (columns * preview_size, rows * (preview_size + label_height)), (245, 247, 250, 255))
    draw = ImageDraw.Draw(sheet)
    for index, state in enumerate(REQUIRED_STATES):
        frame = cleaned_images[state].copy().convert("RGBA")
        frame.thumbnail((preview_size, preview_size), hq._resample_filter())
        tile = _checker_tile(preview_size)
        left = (preview_size - frame.width) // 2
        top = (preview_size - frame.height) // 2
        tile.alpha_composite(frame, (left, top))
        column = index % columns
        row = index // columns
        sheet_left = column * preview_size
        sheet_top = row * (preview_size + label_height)
        sheet.alpha_composite(tile, (sheet_left, sheet_top))
        draw.text((sheet_left + 6, sheet_top + preview_size + 4), state, fill=(20, 24, 32, 255))
    sheet.convert("RGB").save(path)
    return path
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
rtk uv run pytest tests/test_akari_phase4_webui_base_import.py -v
```

Expected: PASS for 8 tests.

- [ ] **Step 5: Commit Task 3**

```bash
rtk git add src/pet_akari/akari_phase4_webui_base_import.py tests/test_akari_phase4_webui_base_import.py
rtk git commit -m "feat: normalize webui base images"
```

---

### Task 4: Build Orchestration, Archive Handling, Validation, And CLI

**Files:**
- Modify: `src/pet_akari/akari_phase4_webui_base_import.py`
- Modify: `tests/test_akari_phase4_webui_base_import.py`

- [ ] **Step 1: Add failing tests for build orchestration and CLI parser**

Append imports at the top of `tests/test_akari_phase4_webui_base_import.py`:

```python
import tarfile
```

Append these tests inside `Phase4WebuiBaseImportTests`:

```python
    def make_import_archive(self, root):
        input_dir = self.write_state_inputs(root)
        for path in input_dir.glob("*.png"):
            image = self.checker_image((32, 32))
            for y in range(8, 24):
                for x in range(10, 22):
                    image.putpixel((x, y), (255, 120, 80, 255))
            image.save(path)
        archive = root / "akari_clawd_base_images.tar.gz"
        with tarfile.open(archive, "w:gz") as tar:
            tar.add(input_dir, arcname=input_dir.name)
        return archive

    def test_build_webui_base_import_writes_outputs_and_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = self.make_import_archive(root)

            result = importer.build_webui_base_import(
                input_archive=archive,
                output_root=root / "out",
                run_id="unit",
                canvas_size=64,
                preview_sizes=(32,),
                background_tolerance=18,
                padding_ratio=0.1,
            )

            self.assertTrue((result["normalizedDir"] / "idle.png").is_file())
            self.assertTrue((result["qaDir"] / "contact-sheet-32.png").is_file())
            self.assertTrue((result["qaDir"] / "background-removal-preview.png").is_file())
            validation = json.loads(result["validationJson"].read_text(encoding="utf-8"))
            self.assertEqual("review", validation["status"])
            self.assertEqual("unit", validation["runId"])
            self.assertEqual(list(importer.REQUIRED_STATES), validation["stateOrder"])
            self.assertEqual(set(importer.REQUIRED_STATES), set(validation["states"]))
            self.assertEqual(
                "working-notification visual distinction requires human review",
                validation["humanReview"]["requiredChecks"][0],
            )

    def test_build_webui_base_import_rejects_archive_and_dir_together(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = self.make_import_archive(root)
            input_dir = root / "akari_clawd_base_images"

            with self.assertRaisesRegex(ValueError, "specify exactly one of input_archive or input_dir"):
                importer.build_webui_base_import(input_archive=archive, input_dir=input_dir, output_root=root / "out")

    def test_build_parser_accepts_build_command(self):
        args = importer._build_parser().parse_args(
            [
                "build",
                "--input-archive",
                "raw.tar.gz",
                "--run-id",
                "trial",
                "--canvas-size",
                "512",
                "--preview-sizes",
                "128,160",
                "--background-tolerance",
                "20",
                "--padding-ratio",
                "0.08",
            ]
        )

        self.assertEqual("build", args.command)
        self.assertEqual(Path("raw.tar.gz"), args.input_archive)
        self.assertEqual("trial", args.run_id)
        self.assertEqual(512, args.canvas_size)
        self.assertEqual("128,160", args.preview_sizes)
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
rtk uv run pytest tests/test_akari_phase4_webui_base_import.py::Phase4WebuiBaseImportTests::test_build_webui_base_import_writes_outputs_and_validation tests/test_akari_phase4_webui_base_import.py::Phase4WebuiBaseImportTests::test_build_webui_base_import_rejects_archive_and_dir_together tests/test_akari_phase4_webui_base_import.py::Phase4WebuiBaseImportTests::test_build_parser_accepts_build_command -v
```

Expected: FAIL with `AttributeError` for `build_webui_base_import` or `_build_parser`.

- [ ] **Step 3: Implement archive handling, build orchestration, validation, and CLI**

Add imports near the top of `src/pet_akari/akari_phase4_webui_base_import.py`:

```python
import argparse
import shutil
import tarfile
```

Add these functions after `write_contact_sheet`:

```python
def parse_preview_sizes(value):
    sizes = tuple(int(item.strip()) for item in value.split(",") if item.strip())
    if not sizes:
        raise ValueError("at least one preview size is required")
    if any(size <= 0 for size in sizes):
        raise ValueError("preview sizes must be positive")
    return sizes


def _copy_input(input_archive, input_dir, raw_dir):
    ensure_dir(raw_dir)
    if (input_archive is None) == (input_dir is None):
        raise ValueError("specify exactly one of input_archive or input_dir")
    if input_archive is not None:
        input_archive = Path(input_archive)
        if not input_archive.is_file():
            raise FileNotFoundError(input_archive)
        copied = raw_dir / input_archive.name
        shutil.copy2(input_archive, copied)
        extract_dir = raw_dir / "extracted"
        ensure_dir(extract_dir)
        with tarfile.open(copied, "r:gz") as archive:
            archive.extractall(extract_dir)
        candidates = [path for path in extract_dir.iterdir() if path.is_dir()]
        return candidates[0] if candidates else extract_dir
    input_dir = Path(input_dir)
    if not input_dir.is_dir():
        raise FileNotFoundError(input_dir)
    copied_dir = raw_dir / input_dir.name
    if copied_dir.exists():
        shutil.rmtree(copied_dir)
    shutil.copytree(input_dir, copied_dir)
    return copied_dir


def _validate_state_metrics(states, contact_sheets):
    status = "review"
    problems = []
    for state, metrics in states.items():
        background = metrics["background"]
        normalize = metrics["normalize"]
        if background["edgeOpaqueRatio"] > 0.05:
            problems.append(f"{state} edge opaque ratio remains high")
        if background["retainedOpaqueRatio"] < 0.01:
            problems.append(f"{state} retained opaque ratio is too low")
        if normalize["normalizedBBox"][2] <= normalize["normalizedBBox"][0]:
            problems.append(f"{state} normalized bbox is empty")
    if problems:
        status = "fail"
    return {
        "contactSheets": [path.as_posix() for path in contact_sheets],
        "humanReview": {
            "requiredChecks": [
                "working-notification visual distinction requires human review",
                "attention error sleeping cues remain readable at low resolution",
            ],
            "visualAcceptance": "pending",
        },
        "problems": problems,
        "schemaVersion": 1,
        "status": status,
    }


def build_webui_base_import(
    *,
    input_archive=None,
    input_dir=None,
    output_root=DEFAULT_OUTPUT_ROOT,
    run_id=DEFAULT_RUN_ID,
    canvas_size=DEFAULT_CANVAS_SIZE,
    preview_sizes=DEFAULT_PREVIEW_SIZES,
    background_tolerance=DEFAULT_BACKGROUND_TOLERANCE,
    padding_ratio=DEFAULT_PADDING_RATIO,
):
    run_dir = ensure_dir(Path(output_root) / run_id)
    raw_dir = ensure_dir(run_dir / "raw")
    normalized_dir = ensure_dir(run_dir / "normalized")
    qa_dir = ensure_dir(run_dir / "qa")
    source_dir = _copy_input(input_archive, input_dir, raw_dir)
    state_images = collect_state_images(source_dir)
    cleaned_images = {}
    normalized_paths = {}
    state_metrics = {}
    for state, source_path in state_images.items():
        with Image.open(source_path) as image:
            cleaned, background_metrics = remove_checker_background(image, tolerance=background_tolerance)
        cleaned_images[state] = cleaned.copy()
        normalized, normalize_metrics = normalize_foreground(cleaned, canvas_size=canvas_size, padding_ratio=padding_ratio)
        output_path = normalized_dir / f"{state}.png"
        normalized.save(output_path)
        normalized_paths[state] = output_path
        state_metrics[state] = {
            "background": background_metrics,
            "inputPath": source_path.as_posix(),
            "normalize": normalize_metrics,
            "outputPath": output_path.as_posix(),
        }

    contact_sheets = [write_contact_sheet(qa_dir / f"contact-sheet-{size}.png", normalized_paths, size) for size in preview_sizes]
    background_preview = write_background_removal_preview(
        qa_dir / "background-removal-preview.png", cleaned_images, preview_sizes[0]
    )
    validation = _validate_state_metrics(state_metrics, contact_sheets)
    validation.update(
        {
            "backgroundRemovalPreview": background_preview.as_posix(),
            "canvasSize": canvas_size,
            "normalizedDir": normalized_dir.as_posix(),
            "previewSizes": list(preview_sizes),
            "rawDir": raw_dir.as_posix(),
            "runDir": run_dir.as_posix(),
            "runId": run_id,
            "stateOrder": list(REQUIRED_STATES),
            "states": state_metrics,
        }
    )
    validation_json = write_json(qa_dir / "webui-base-import-validation.json", validation)
    return {
        "normalizedDir": normalized_dir,
        "qaDir": qa_dir,
        "runDir": run_dir,
        "validationJson": validation_json,
    }


def _build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build", help="import WebUI-generated Phase 4 base PNGs")
    build.add_argument("--input-archive", type=Path)
    build.add_argument("--input-dir", type=Path)
    build.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    build.add_argument("--run-id", default=DEFAULT_RUN_ID)
    build.add_argument("--canvas-size", type=int, default=DEFAULT_CANVAS_SIZE)
    build.add_argument("--preview-sizes", default=",".join(str(size) for size in DEFAULT_PREVIEW_SIZES))
    build.add_argument("--background-tolerance", type=int, default=DEFAULT_BACKGROUND_TOLERANCE)
    build.add_argument("--padding-ratio", type=float, default=DEFAULT_PADDING_RATIO)
    return parser


def main(argv=None):
    args = _build_parser().parse_args(argv)
    if args.command == "build":
        result = build_webui_base_import(
            input_archive=args.input_archive,
            input_dir=args.input_dir,
            output_root=args.output_root,
            run_id=args.run_id,
            canvas_size=args.canvas_size,
            preview_sizes=parse_preview_sizes(args.preview_sizes),
            background_tolerance=args.background_tolerance,
            padding_ratio=args.padding_ratio,
        )
        print(f"wrote {result['validationJson']}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
rtk uv run pytest tests/test_akari_phase4_webui_base_import.py -v
```

Expected: PASS for 11 tests.

- [ ] **Step 5: Commit Task 4**

```bash
rtk git add src/pet_akari/akari_phase4_webui_base_import.py tests/test_akari_phase4_webui_base_import.py
rtk git commit -m "feat: build webui base import artifacts"
```

---

### Task 5: Documentation, Full Verification, And Real Image Smoke

**Files:**
- Modify: `README.md`
- Runtime output only: `work/akari-hq-apng/phase4-webui-base-images/webui-base-001/`

- [ ] **Step 1: Add README usage**

In `README.md`, add this short usage block near the other pet-akari tool commands:

````markdown
### Phase 4 WebUI Base Import

Import ChatGPT WebUI-generated state PNGs with baked checker backgrounds into transparent normalized review assets:

```bash
rtk uv run python -m pet_akari.akari_phase4_webui_base_import build \
  --input-archive work/akari-hq-apng/phase4-webui-base-images/raw/akari_clawd_base_images.tar.gz \
  --run-id webui-base-001
```

The importer writes ignored `work/` artifacts, including normalized RGBA PNGs, contact sheets, and `qa/webui-base-import-validation.json`. Human review is still required before any visual acceptance decision.
````

- [ ] **Step 2: Run focused tests**

Run:

```bash
rtk uv run pytest tests/test_akari_phase4_webui_base_import.py -v
```

Expected: PASS for all WebUI base import tests.

- [ ] **Step 3: Run full verification**

Run:

```bash
rtk uv run pytest && rtk uv run ruff check . && rtk uv run ruff format --check .
```

Expected: all pytest tests pass, ruff reports no lint failures, formatting check passes.

- [ ] **Step 4: Run real image smoke against the saved WebUI archive**

Run:

```bash
rtk uv run python -m pet_akari.akari_phase4_webui_base_import build \
  --input-archive work/akari-hq-apng/phase4-webui-base-images/raw/akari_clawd_base_images.tar.gz \
  --run-id webui-base-001
```

Expected:

- Command exits 0.
- Output includes `wrote work/akari-hq-apng/phase4-webui-base-images/webui-base-001/qa/webui-base-import-validation.json`.
- These files exist:

```text
work/akari-hq-apng/phase4-webui-base-images/webui-base-001/normalized/idle.png
work/akari-hq-apng/phase4-webui-base-images/webui-base-001/normalized/notification.png
work/akari-hq-apng/phase4-webui-base-images/webui-base-001/qa/contact-sheet-128.png
work/akari-hq-apng/phase4-webui-base-images/webui-base-001/qa/contact-sheet-160.png
work/akari-hq-apng/phase4-webui-base-images/webui-base-001/qa/webui-base-import-validation.json
```

Then inspect validation status:

```bash
rtk json work/akari-hq-apng/phase4-webui-base-images/webui-base-001/qa/webui-base-import-validation.json
```

Expected: `status` is `review` unless metrics indicate an actual structural failure. `humanReview.visualAcceptance` remains `pending`.

- [ ] **Step 5: Commit Task 5**

```bash
rtk git add README.md
rtk git commit -m "docs: document webui base import"
```

Generated `work/` files remain ignored and unstaged.

---

## Final Completion Checklist

- [ ] `rtk git status --short` shows no tracked or untracked source/doc changes.
- [ ] `rtk uv run pytest` passes.
- [ ] `rtk uv run ruff check .` passes.
- [ ] `rtk uv run ruff format --check .` passes.
- [ ] Real image smoke produced `webui-base-001` artifacts from the saved raw archive.
- [ ] The final response reports that human visual acceptance is still pending, not auto-approved.
