# Phase 4 WebUI Diff Pack Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a deterministic Phase 4 review diff pack that compares the current Akari theme with WebUI-imported base PNGs state by state and produces human selection artifacts.

**Architecture:** Add one focused module, `pet_akari.akari_phase4_webui_diff_pack`, that reads an existing theme and an existing WebUI import run, renders comparison artifacts, and writes review JSON. Keep it separate from WebUI base import, gap repair, and candidate batch; this first slice creates review inputs only and never edits theme assets.

**Tech Stack:** Python 3, Pillow, `unittest`, existing `pet_akari.clawd_hq_theme` constants/helpers, JSON artifacts, `argparse`.

---

## File Structure

- Create: `src/pet_akari/akari_phase4_webui_diff_pack.py`
  - Owns WebUI diff-pack generation only: input validation, current APNG display-frame loading, WebUI PNG loading, metrics, state diff rendering, contact sheet rendering, selection template, manifest, CLI.
- Create: `tests/test_akari_phase4_webui_diff_pack.py`
  - Uses small synthetic APNG/PNG fixtures to lock down deterministic behavior and fail-closed paths.
- Modify: `README.md`
  - Add one tool row and short usage block for the diff-pack command.
- Do not modify:
  - `src/pet_akari/akari_phase4_webui_base_import.py`
  - `src/pet_akari/akari_phase4_candidate_batch.py`
  - `src/pet_akari/akari_phase4_gap_repair.py`
  - Existing Phase 4 visual recognition behavior.

The generated `work/akari-hq-apng/phase4-webui-diff-packs/` artifacts are ignored and must not be staged.

---

### Task 1: Validation And JSON Skeleton

**Files:**
- Create: `src/pet_akari/akari_phase4_webui_diff_pack.py`
- Create: `tests/test_akari_phase4_webui_diff_pack.py`

- [ ] **Step 1: Write failing tests for WebUI validation and JSON helpers**

Create `tests/test_akari_phase4_webui_diff_pack.py` with:

```python
import json
import tempfile
import unittest
from pathlib import Path

from pet_akari import akari_phase4_webui_diff_pack as diff_pack


class Phase4WebuiDiffPackTests(unittest.TestCase):
    def write_webui_import(self, root, *, status="review", state_order=None, omit_state=None):
        import_dir = root / "webui-base-001"
        normalized_dir = import_dir / "normalized"
        qa_dir = import_dir / "qa"
        normalized_dir.mkdir(parents=True)
        qa_dir.mkdir()
        state_order = list(diff_pack.REQUIRED_STATES) if state_order is None else state_order
        for state in diff_pack.REQUIRED_STATES:
            if state == omit_state:
                continue
            (normalized_dir / f"{state}.png").write_bytes(b"not-an-image-yet")
        validation = {
            "humanReview": {"visualAcceptance": "pending"},
            "schemaVersion": 1,
            "stateOrder": state_order,
            "status": status,
        }
        (qa_dir / "webui-base-import-validation.json").write_text(
            json.dumps(validation, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return import_dir

    def test_load_webui_import_accepts_review_pending(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            import_dir = self.write_webui_import(root)

            data = diff_pack.load_webui_import(import_dir)

            self.assertEqual("review", data["validation"]["status"])
            self.assertEqual(list(diff_pack.REQUIRED_STATES), list(data["normalizedPaths"]))
            self.assertEqual(import_dir / "normalized" / "idle.png", data["normalizedPaths"]["idle"])

    def test_load_webui_import_rejects_failed_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            import_dir = self.write_webui_import(root, status="fail")

            with self.assertRaisesRegex(ValueError, "WebUI import validation status is fail"):
                diff_pack.load_webui_import(import_dir)

    def test_load_webui_import_rejects_state_order_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bad_order = list(reversed(diff_pack.REQUIRED_STATES))
            import_dir = self.write_webui_import(root, state_order=bad_order)

            with self.assertRaisesRegex(ValueError, "WebUI import stateOrder must match hq.CORE_STATES"):
                diff_pack.load_webui_import(import_dir)

    def test_load_webui_import_rejects_missing_normalized_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            import_dir = self.write_webui_import(root, omit_state="notification")

            with self.assertRaisesRegex(FileNotFoundError, "notification.png"):
                diff_pack.load_webui_import(import_dir)

    def test_write_json_creates_parent_and_sorts_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "qa" / "manifest.json"

            diff_pack.write_json(output, {"b": 2, "a": 1})

            self.assertEqual({"a": 1, "b": 2}, json.loads(output.read_text(encoding="utf-8")))
            self.assertTrue(output.read_text(encoding="utf-8").endswith("\n"))
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
rtk uv run pytest tests/test_akari_phase4_webui_diff_pack.py -v
```

Expected: FAIL during collection with `ImportError` because `akari_phase4_webui_diff_pack` does not exist yet.

- [ ] **Step 3: Add minimal module with validation helpers**

Create `src/pet_akari/akari_phase4_webui_diff_pack.py`:

```python
"""Build Phase 4 review diff packs for WebUI-imported Akari base images."""

from __future__ import annotations

import json
from pathlib import Path

from pet_akari import clawd_hq_theme as hq

DEFAULT_OUTPUT_ROOT = Path("work/akari-hq-apng/phase4-webui-diff-packs")
DEFAULT_PACK_ID = "webui-diff-001"
DEFAULT_PREVIEW_SIZES = (128, 160)
WEBUI_VALIDATION = Path("qa/webui-base-import-validation.json")
REQUIRED_STATES = hq.CORE_STATES
ALLOWED_DECISIONS = ("adopt", "hold", "reject")


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


def _normalized_paths(import_dir):
    import_dir = Path(import_dir)
    normalized_dir = import_dir / "normalized"
    paths = {}
    for state in REQUIRED_STATES:
        path = normalized_dir / f"{state}.png"
        if not path.is_file():
            raise FileNotFoundError(path)
        paths[state] = path
    return paths


def load_webui_import(import_dir):
    import_dir = Path(import_dir)
    validation_path = import_dir / WEBUI_VALIDATION
    validation = load_json(validation_path)
    if validation.get("status") == "fail":
        raise ValueError("WebUI import validation status is fail")
    state_order = validation.get("stateOrder")
    if state_order is not None and list(state_order) != list(REQUIRED_STATES):
        raise ValueError("WebUI import stateOrder must match hq.CORE_STATES")
    return {
        "importDir": import_dir,
        "normalizedPaths": _normalized_paths(import_dir),
        "validation": validation,
        "validationPath": validation_path,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
rtk uv run pytest tests/test_akari_phase4_webui_diff_pack.py -v
```

Expected: PASS for 5 tests.

- [ ] **Step 5: Commit Task 1**

```bash
rtk git add src/pet_akari/akari_phase4_webui_diff_pack.py tests/test_akari_phase4_webui_diff_pack.py
rtk git commit -m "feat: add webui diff pack validation"
```

---

### Task 2: Current Theme Frame Loading And Metrics

**Files:**
- Modify: `src/pet_akari/akari_phase4_webui_diff_pack.py`
- Modify: `tests/test_akari_phase4_webui_diff_pack.py`

- [ ] **Step 1: Add failing tests for APNG display frames, source collection, and metrics**

Append imports at the top of `tests/test_akari_phase4_webui_diff_pack.py`:

```python
from PIL import Image
```

Append these helpers and tests inside `Phase4WebuiDiffPackTests`:

```python
    def write_theme(self, root, *, omit_state=None):
        theme_dir = root / "theme"
        assets_dir = theme_dir / "assets"
        assets_dir.mkdir(parents=True)
        for index, state in enumerate(diff_pack.REQUIRED_STATES):
            if state == omit_state:
                continue
            first = Image.new("RGBA", (24, 32), (0, 0, 0, 0))
            second = Image.new("RGBA", (24, 32), (0, 0, 0, 0))
            first.putpixel((4 + index, 8), (255, 0, 0, 255))
            second.putpixel((10, 12 + index), (0, 128, 255, 255))
            first.save(
                assets_dir / f"akari-{state}.apng",
                format="PNG",
                save_all=True,
                append_images=[second],
                duration=[100, 100],
                loop=0,
            )
        return theme_dir

    def write_real_webui_import(self, root, *, omit_state=None):
        import_dir = root / "webui-base-001"
        normalized_dir = import_dir / "normalized"
        qa_dir = import_dir / "qa"
        normalized_dir.mkdir(parents=True)
        qa_dir.mkdir()
        for index, state in enumerate(diff_pack.REQUIRED_STATES):
            if state == omit_state:
                continue
            image = Image.new("RGBA", (30, 40), (0, 0, 0, 0))
            image.putpixel((12 + index, 16), (255, 120, 80, 255))
            image.save(normalized_dir / f"{state}.png")
        validation = {
            "humanReview": {"visualAcceptance": "pending"},
            "schemaVersion": 1,
            "stateOrder": list(diff_pack.REQUIRED_STATES),
            "status": "review",
        }
        (qa_dir / "webui-base-import-validation.json").write_text(
            json.dumps(validation, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return import_dir

    def test_collect_current_theme_frames_loads_required_apngs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            theme_dir = self.write_theme(root)

            frames = diff_pack.collect_current_theme_frames(theme_dir)

            self.assertEqual(list(diff_pack.REQUIRED_STATES), list(frames))
            self.assertEqual((24, 32), frames["idle"].size)
            self.assertEqual("RGBA", frames["idle"].mode)

    def test_collect_current_theme_frames_rejects_missing_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            theme_dir = self.write_theme(root, omit_state="error")

            with self.assertRaisesRegex(FileNotFoundError, "akari-error.apng"):
                diff_pack.collect_current_theme_frames(theme_dir)

    def test_image_metrics_records_bbox_and_opaque_ratio(self):
        image = Image.new("RGBA", (10, 12), (0, 0, 0, 0))
        image.putpixel((2, 3), (255, 0, 0, 255))
        image.putpixel((4, 6), (255, 0, 0, 255))

        metrics = diff_pack.image_metrics(image)

        self.assertEqual([10, 12], metrics["size"])
        self.assertEqual([2, 3, 5, 7], metrics["alphaBBox"])
        self.assertAlmostEqual(2 / 120, metrics["opaqueRatio"])

    def test_image_metrics_rejects_empty_alpha_bbox(self):
        image = Image.new("RGBA", (10, 12), (0, 0, 0, 0))

        with self.assertRaisesRegex(ValueError, "foreground bbox is empty"):
            diff_pack.image_metrics(image)

    def test_pixel_diff_summary_resizes_before_comparing(self):
        current = Image.new("RGBA", (12, 16), (0, 0, 0, 0))
        webui = Image.new("RGBA", (30, 40), (0, 0, 0, 0))
        current.putpixel((4, 4), (255, 0, 0, 255))
        webui.putpixel((10, 12), (0, 128, 255, 255))

        summary = diff_pack.pixel_diff_summary(current, webui, preview_size=32)

        self.assertEqual(32, summary["previewSize"])
        self.assertGreater(summary["changedPixels"], 0)
        self.assertGreater(summary["meanChannelDelta"], 0)
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
rtk uv run pytest tests/test_akari_phase4_webui_diff_pack.py::Phase4WebuiDiffPackTests::test_collect_current_theme_frames_loads_required_apngs tests/test_akari_phase4_webui_diff_pack.py::Phase4WebuiDiffPackTests::test_collect_current_theme_frames_rejects_missing_state tests/test_akari_phase4_webui_diff_pack.py::Phase4WebuiDiffPackTests::test_image_metrics_records_bbox_and_opaque_ratio tests/test_akari_phase4_webui_diff_pack.py::Phase4WebuiDiffPackTests::test_image_metrics_rejects_empty_alpha_bbox tests/test_akari_phase4_webui_diff_pack.py::Phase4WebuiDiffPackTests::test_pixel_diff_summary_resizes_before_comparing -v
```

Expected: FAIL with `AttributeError` for the new functions.

- [ ] **Step 3: Implement current APNG loading and metrics**

Add imports in `src/pet_akari/akari_phase4_webui_diff_pack.py`:

```python
from PIL import Image, ImageChops, ImageSequence
```

Add these functions after `load_webui_import`:

```python
def _display_frames(path):
    path = Path(path)
    with Image.open(path) as image:
        frames = [frame.copy().convert("RGBA") for frame in ImageSequence.Iterator(image)]
        if image.info.get("default_image") and len(frames) > 1:
            frames = frames[1:]
    if not frames:
        raise ValueError(f"{path} has no APNG display frames")
    return frames


def collect_current_theme_frames(theme_dir):
    theme_dir = Path(theme_dir)
    frames = {}
    for state in REQUIRED_STATES:
        path = theme_dir / "assets" / f"akari-{state}.apng"
        if not path.is_file():
            raise FileNotFoundError(path)
        frames[state] = _display_frames(path)[0]
    return frames


def _alpha_bbox(image):
    bbox = image.convert("RGBA").getchannel("A").getbbox()
    if bbox is None:
        raise ValueError("foreground bbox is empty")
    return bbox


def _opaque_ratio(image):
    rgba = image.convert("RGBA")
    data = rgba.get_flattened_data() if hasattr(rgba, "get_flattened_data") else rgba.getdata()
    opaque = sum(1 for pixel in data if pixel[3] > 0)
    return opaque / (rgba.width * rgba.height)


def image_metrics(image):
    rgba = image.convert("RGBA")
    bbox = _alpha_bbox(rgba)
    return {
        "alphaBBox": list(bbox),
        "opaqueRatio": _opaque_ratio(rgba),
        "size": [rgba.width, rgba.height],
    }


def _preview_tile(image, preview_size):
    frame = image.copy().convert("RGBA")
    frame.thumbnail((preview_size, preview_size), hq._resample_filter())
    tile = Image.new("RGBA", (preview_size, preview_size), (0, 0, 0, 0))
    left = (preview_size - frame.width) // 2
    top = (preview_size - frame.height) // 2
    tile.alpha_composite(frame, (left, top))
    return tile


def pixel_diff_summary(current, webui, preview_size):
    current_tile = _preview_tile(current, preview_size)
    webui_tile = _preview_tile(webui, preview_size)
    diff = ImageChops.difference(current_tile, webui_tile)
    data = diff.get_flattened_data() if hasattr(diff, "get_flattened_data") else diff.getdata()
    changed = 0
    total_delta = 0
    for red, green, blue, alpha in data:
        delta = red + green + blue + alpha
        if delta:
            changed += 1
            total_delta += delta
    pixels = preview_size * preview_size
    return {
        "changedPixels": changed,
        "changedRatio": changed / pixels,
        "meanChannelDelta": total_delta / (pixels * 4),
        "previewSize": preview_size,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
rtk uv run pytest tests/test_akari_phase4_webui_diff_pack.py -v
```

Expected: PASS for 10 tests.

- [ ] **Step 5: Commit Task 2**

```bash
rtk git add src/pet_akari/akari_phase4_webui_diff_pack.py tests/test_akari_phase4_webui_diff_pack.py
rtk git commit -m "feat: load webui diff pack sources"
```

---

### Task 3: State Diff Images And Contact Sheets

**Files:**
- Modify: `src/pet_akari/akari_phase4_webui_diff_pack.py`
- Modify: `tests/test_akari_phase4_webui_diff_pack.py`

- [ ] **Step 1: Add failing tests for state diff and contact sheet rendering**

Append these tests inside `Phase4WebuiDiffPackTests`:

```python
    def test_write_state_diff_writes_side_by_side_preview(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            current = Image.new("RGBA", (24, 32), (0, 0, 0, 0))
            webui = Image.new("RGBA", (30, 40), (0, 0, 0, 0))
            current.putpixel((8, 10), (255, 0, 0, 255))
            webui.putpixel((12, 16), (0, 128, 255, 255))

            output = diff_pack.write_state_diff(root / "state-diffs" / "idle.png", "idle", current, webui, preview_size=64)

            self.assertTrue(output.is_file())
            with Image.open(output) as image:
                self.assertEqual((64 * 2, 64 + 44), image.size)
                self.assertEqual("RGB", image.mode)

    def test_write_contact_sheet_writes_all_state_diffs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state_diff_paths = {}
            for state in diff_pack.REQUIRED_STATES:
                path = root / "state-diffs" / f"{state}.png"
                path.parent.mkdir(parents=True, exist_ok=True)
                Image.new("RGB", (64 * 2, 64 + 44), "white").save(path)
                state_diff_paths[state] = path

            output = diff_pack.write_contact_sheet(root / "qa" / "diff-contact-sheet-64.png", state_diff_paths, preview_size=64)

            self.assertTrue(output.is_file())
            with Image.open(output) as image:
                self.assertEqual((64 * 2 * 4, (64 + 44 + 22) * 2), image.size)
                self.assertEqual("RGB", image.mode)
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
rtk uv run pytest tests/test_akari_phase4_webui_diff_pack.py::Phase4WebuiDiffPackTests::test_write_state_diff_writes_side_by_side_preview tests/test_akari_phase4_webui_diff_pack.py::Phase4WebuiDiffPackTests::test_write_contact_sheet_writes_all_state_diffs -v
```

Expected: FAIL with `AttributeError` for `write_state_diff` and `write_contact_sheet`.

- [ ] **Step 3: Implement state diff and contact sheet rendering**

Update imports in `src/pet_akari/akari_phase4_webui_diff_pack.py`:

```python
from PIL import Image, ImageChops, ImageDraw, ImageSequence
```

Add these functions after `pixel_diff_summary`:

```python
def write_state_diff(path, state, current, webui, preview_size):
    path = Path(path)
    ensure_dir(path.parent)
    label_height = 44
    width = preview_size * 2
    height = preview_size + label_height
    sheet = Image.new("RGBA", (width, height), (245, 247, 250, 255))
    draw = ImageDraw.Draw(sheet)
    current_tile = _preview_tile(current, preview_size)
    webui_tile = _preview_tile(webui, preview_size)
    sheet.alpha_composite(current_tile, (0, 0))
    sheet.alpha_composite(webui_tile, (preview_size, 0))
    draw.text((6, preview_size + 4), f"{state} current", fill=(20, 24, 32, 255))
    draw.text((preview_size + 6, preview_size + 4), f"{state} webui", fill=(20, 24, 32, 255))
    sheet.convert("RGB").save(path)
    return path


def write_contact_sheet(path, state_diff_paths, preview_size):
    path = Path(path)
    ensure_dir(path.parent)
    columns = 4
    label_height = 22
    tile_width = preview_size * 2
    tile_height = preview_size + 44
    rows = (len(REQUIRED_STATES) + columns - 1) // columns
    sheet = Image.new(
        "RGBA",
        (columns * tile_width, rows * (tile_height + label_height)),
        (245, 247, 250, 255),
    )
    draw = ImageDraw.Draw(sheet)
    for index, state in enumerate(REQUIRED_STATES):
        with Image.open(state_diff_paths[state]) as image:
            tile = image.convert("RGBA")
        if tile.size != (tile_width, tile_height):
            tile = tile.resize((tile_width, tile_height), hq._resample_filter())
        column = index % columns
        row = index // columns
        left = column * tile_width
        top = row * (tile_height + label_height)
        sheet.alpha_composite(tile, (left, top))
        draw.text((left + 6, top + tile_height + 4), state, fill=(20, 24, 32, 255))
    sheet.convert("RGB").save(path)
    return path
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
rtk uv run pytest tests/test_akari_phase4_webui_diff_pack.py -v
```

Expected: PASS for 12 tests.

- [ ] **Step 5: Commit Task 3**

```bash
rtk git add src/pet_akari/akari_phase4_webui_diff_pack.py tests/test_akari_phase4_webui_diff_pack.py
rtk git commit -m "feat: render webui diff pack previews"
```

---

### Task 4: Build Orchestration, Selection Template, Manifest, And CLI

**Files:**
- Modify: `src/pet_akari/akari_phase4_webui_diff_pack.py`
- Modify: `tests/test_akari_phase4_webui_diff_pack.py`

- [ ] **Step 1: Add failing tests for build output and CLI parser**

Append these tests inside `Phase4WebuiDiffPackTests`:

```python
    def test_build_webui_diff_pack_writes_review_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            theme_dir = self.write_theme(root)
            import_dir = self.write_real_webui_import(root)

            result = diff_pack.build_webui_diff_pack(
                theme_dir=theme_dir,
                webui_import_dir=import_dir,
                output_root=root / "out",
                pack_id="unit",
                preview_sizes=(64,),
            )

            self.assertTrue((result["stateDiffsDir"] / "idle.png").is_file())
            self.assertTrue((result["qaDir"] / "diff-contact-sheet-64.png").is_file())
            selection = json.loads(result["selectionTemplate"].read_text(encoding="utf-8"))
            manifest = json.loads(result["manifest"].read_text(encoding="utf-8"))
            self.assertEqual("review", manifest["status"])
            self.assertEqual("unit", manifest["packId"])
            self.assertEqual(list(diff_pack.REQUIRED_STATES), manifest["stateOrder"])
            self.assertEqual(set(diff_pack.REQUIRED_STATES), set(manifest["states"]))
            self.assertEqual(list(diff_pack.REQUIRED_STATES), [item["state"] for item in selection["selections"]])
            self.assertEqual("", selection["selections"][0]["decision"])
            self.assertEqual(["adopt", "hold", "reject"], selection["selections"][0]["allowedDecisions"])
            self.assertEqual("", selection["selections"][0]["notes"])

    def test_build_webui_diff_pack_rejects_failed_webui_import(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            theme_dir = self.write_theme(root)
            import_dir = self.write_webui_import(root, status="fail")

            with self.assertRaisesRegex(ValueError, "WebUI import validation status is fail"):
                diff_pack.build_webui_diff_pack(
                    theme_dir=theme_dir,
                    webui_import_dir=import_dir,
                    output_root=root / "out",
                    pack_id="unit",
                )

    def test_parse_preview_sizes_validates_values(self):
        self.assertEqual((128, 160), diff_pack.parse_preview_sizes("128,160"))
        with self.assertRaisesRegex(ValueError, "preview sizes must be positive"):
            diff_pack.parse_preview_sizes("128,0")

    def test_build_parser_accepts_build_command(self):
        args = diff_pack._build_parser().parse_args(
            [
                "build",
                "--theme-dir",
                "theme",
                "--webui-import-dir",
                "webui",
                "--output-root",
                "out",
                "--pack-id",
                "trial",
                "--preview-sizes",
                "128,160",
            ]
        )

        self.assertEqual("build", args.command)
        self.assertEqual(Path("theme"), args.theme_dir)
        self.assertEqual(Path("webui"), args.webui_import_dir)
        self.assertEqual(Path("out"), args.output_root)
        self.assertEqual("trial", args.pack_id)
        self.assertEqual("128,160", args.preview_sizes)
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
rtk uv run pytest tests/test_akari_phase4_webui_diff_pack.py::Phase4WebuiDiffPackTests::test_build_webui_diff_pack_writes_review_artifacts tests/test_akari_phase4_webui_diff_pack.py::Phase4WebuiDiffPackTests::test_build_webui_diff_pack_rejects_failed_webui_import tests/test_akari_phase4_webui_diff_pack.py::Phase4WebuiDiffPackTests::test_parse_preview_sizes_validates_values tests/test_akari_phase4_webui_diff_pack.py::Phase4WebuiDiffPackTests::test_build_parser_accepts_build_command -v
```

Expected: FAIL with `AttributeError` for `build_webui_diff_pack`, `parse_preview_sizes`, or `_build_parser`.

- [ ] **Step 3: Implement orchestration, selection template, manifest, and CLI**

Add import near the top of `src/pet_akari/akari_phase4_webui_diff_pack.py`:

```python
import argparse
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


def _selection_entry(state, current_preview, webui_preview, diff_preview):
    return {
        "allowedDecisions": list(ALLOWED_DECISIONS),
        "currentPreview": current_preview.as_posix(),
        "decision": "",
        "diffPreview": diff_preview.as_posix(),
        "notes": "",
        "state": state,
        "webuiPreview": webui_preview.as_posix(),
    }


def write_selection_template(path, state_diff_paths, webui_paths):
    selections = [
        _selection_entry(state, state_diff_paths[state], webui_paths[state], state_diff_paths[state])
        for state in REQUIRED_STATES
    ]
    return write_json(
        path,
        {
            "allowedDecisions": list(ALLOWED_DECISIONS),
            "schemaVersion": 1,
            "selections": selections,
            "status": "template",
        },
    )


def build_webui_diff_pack(
    *,
    theme_dir,
    webui_import_dir,
    output_root=DEFAULT_OUTPUT_ROOT,
    pack_id=DEFAULT_PACK_ID,
    preview_sizes=DEFAULT_PREVIEW_SIZES,
):
    pack_dir = ensure_dir(Path(output_root) / pack_id)
    state_diffs_dir = ensure_dir(pack_dir / "state-diffs")
    qa_dir = ensure_dir(pack_dir / "qa")
    webui = load_webui_import(webui_import_dir)
    current_frames = collect_current_theme_frames(theme_dir)
    webui_images = {}
    for state, path in webui["normalizedPaths"].items():
        with Image.open(path) as image:
            webui_images[state] = image.convert("RGBA")
        _alpha_bbox(webui_images[state])

    state_diff_paths = {}
    states = {}
    for state in REQUIRED_STATES:
        state_diff = write_state_diff(
            state_diffs_dir / f"{state}.png",
            state,
            current_frames[state],
            webui_images[state],
            max(preview_sizes),
        )
        state_diff_paths[state] = state_diff
        states[state] = {
            "current": image_metrics(current_frames[state]),
            "currentAsset": (Path(theme_dir) / "assets" / f"akari-{state}.apng").as_posix(),
            "diffPreview": state_diff.as_posix(),
            "pixelDiff": {
                str(size): pixel_diff_summary(current_frames[state], webui_images[state], size)
                for size in preview_sizes
            },
            "webui": image_metrics(webui_images[state]),
            "webuiAsset": webui["normalizedPaths"][state].as_posix(),
        }

    contact_sheets = [
        write_contact_sheet(qa_dir / f"diff-contact-sheet-{size}.png", state_diff_paths, size)
        for size in preview_sizes
    ]
    selection_template = write_selection_template(
        pack_dir / "selection-template.json", state_diff_paths, webui["normalizedPaths"]
    )
    manifest = write_json(
        pack_dir / "diff-pack-manifest.json",
        {
            "contactSheets": [path.as_posix() for path in contact_sheets],
            "packDir": pack_dir.as_posix(),
            "packId": pack_id,
            "previewSizes": list(preview_sizes),
            "schemaVersion": 1,
            "selectionTemplate": selection_template.as_posix(),
            "stateOrder": list(REQUIRED_STATES),
            "states": states,
            "status": "review",
            "themeDir": Path(theme_dir).as_posix(),
            "webuiImportDir": Path(webui_import_dir).as_posix(),
            "webuiValidation": webui["validationPath"].as_posix(),
        },
    )
    return {
        "manifest": manifest,
        "packDir": pack_dir,
        "qaDir": qa_dir,
        "selectionTemplate": selection_template,
        "stateDiffsDir": state_diffs_dir,
    }


def _build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build", help="build a Phase 4 WebUI review diff pack")
    build.add_argument("--theme-dir", type=Path, required=True)
    build.add_argument("--webui-import-dir", type=Path, required=True)
    build.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    build.add_argument("--pack-id", default=DEFAULT_PACK_ID)
    build.add_argument("--preview-sizes", default=",".join(str(size) for size in DEFAULT_PREVIEW_SIZES))
    return parser


def main(argv=None):
    args = _build_parser().parse_args(argv)
    if args.command == "build":
        result = build_webui_diff_pack(
            theme_dir=args.theme_dir,
            webui_import_dir=args.webui_import_dir,
            output_root=args.output_root,
            pack_id=args.pack_id,
            preview_sizes=parse_preview_sizes(args.preview_sizes),
        )
        print(f"wrote {result['manifest']}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
rtk uv run pytest tests/test_akari_phase4_webui_diff_pack.py -v
```

Expected: PASS for 16 tests.

- [ ] **Step 5: Commit Task 4**

```bash
rtk git add src/pet_akari/akari_phase4_webui_diff_pack.py tests/test_akari_phase4_webui_diff_pack.py
rtk git commit -m "feat: build webui diff pack artifacts"
```

---

### Task 5: README, Full Verification, And Real Smoke

**Files:**
- Modify: `README.md`
- Runtime output only: `work/akari-hq-apng/phase4-webui-diff-packs/webui-diff-001/`

- [ ] **Step 1: Add README usage**

In `README.md`, add a tool-table row near the other Phase 4 tools:

```markdown
| `akari_phase4_webui_diff_pack.py` | Phase 4 WebUIベース画像の現行theme比較パック |
```

Add this short usage block near the WebUI base import section:

````markdown
### Phase 4 WebUI Diff Pack

Compare the current theme with WebUI-imported base images and produce a human-editable state selection template:

```bash
rtk uv run python -m pet_akari.akari_phase4_webui_diff_pack build \
  --theme-dir work/akari-hq-apng/phase3-staging/theme \
  --webui-import-dir work/akari-hq-apng/phase4-webui-base-images/webui-base-001 \
  --pack-id webui-diff-001
```

The diff pack writes ignored `work/` artifacts, including state-by-state comparison images, contact sheets, `selection-template.json`, and `diff-pack-manifest.json`. Human review fills `adopt`, `hold`, or `reject`; this command does not change theme assets.
````

- [ ] **Step 2: Run focused tests**

Run:

```bash
rtk uv run pytest tests/test_akari_phase4_webui_diff_pack.py -v
```

Expected: PASS for all WebUI diff-pack tests.

- [ ] **Step 3: Run full verification**

Run:

```bash
rtk uv run pytest && rtk uv run ruff check . && rtk uv run ruff format --check .
```

Expected: all pytest tests pass, ruff reports no lint failures, formatting check passes.

- [ ] **Step 4: Run real smoke against current theme and WebUI import**

Run:

```bash
rtk uv run python -m pet_akari.akari_phase4_webui_diff_pack build \
  --theme-dir work/akari-hq-apng/phase3-staging/theme \
  --webui-import-dir work/akari-hq-apng/phase4-webui-base-images/webui-base-001 \
  --pack-id webui-diff-001
```

Expected:

- Command exits 0.
- Output includes `wrote work/akari-hq-apng/phase4-webui-diff-packs/webui-diff-001/diff-pack-manifest.json`.
- These files exist:

```text
work/akari-hq-apng/phase4-webui-diff-packs/webui-diff-001/state-diffs/idle.png
work/akari-hq-apng/phase4-webui-diff-packs/webui-diff-001/state-diffs/notification.png
work/akari-hq-apng/phase4-webui-diff-packs/webui-diff-001/qa/diff-contact-sheet-128.png
work/akari-hq-apng/phase4-webui-diff-packs/webui-diff-001/qa/diff-contact-sheet-160.png
work/akari-hq-apng/phase4-webui-diff-packs/webui-diff-001/selection-template.json
work/akari-hq-apng/phase4-webui-diff-packs/webui-diff-001/diff-pack-manifest.json
```

Inspect manifest and selection template:

```bash
rtk json work/akari-hq-apng/phase4-webui-diff-packs/webui-diff-001/diff-pack-manifest.json
rtk json work/akari-hq-apng/phase4-webui-diff-packs/webui-diff-001/selection-template.json
```

Expected:

- manifest `status` is `review`.
- manifest `stateOrder` is `hq.CORE_STATES`.
- selection template decisions are all empty strings.
- allowed decisions are `adopt`, `hold`, `reject`.

- [ ] **Step 5: Commit Task 5**

```bash
rtk git add README.md
rtk git commit -m "docs: document webui diff pack"
```

Generated `work/` files remain ignored and unstaged.

---

## Final Completion Checklist

- [ ] `rtk git status --short` shows no tracked or untracked source/doc changes.
- [ ] `rtk uv run pytest` passes.
- [ ] `rtk uv run ruff check .` passes.
- [ ] `rtk uv run ruff format --check .` passes.
- [ ] Real smoke produced `webui-diff-001` artifacts from the current theme and WebUI import.
- [ ] `diff-pack-manifest.json` has `status: review`.
- [ ] `selection-template.json` has blank decisions and allowed decisions `adopt`, `hold`, `reject`.
- [ ] The final response reports that this does not change theme assets and does not set visual acceptance.
