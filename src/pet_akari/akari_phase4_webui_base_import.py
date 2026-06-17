"""Import ChatGPT WebUI-generated Akari base PNGs for Phase 4 review."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import tarfile
from collections import deque
from pathlib import Path

from PIL import Image, ImageDraw

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

    bbox = rgba.getchannel("A").getbbox()
    data = rgba.get_flattened_data() if hasattr(rgba, "get_flattened_data") else rgba.getdata()
    opaque_pixels = sum(1 for pixel in data if pixel[3] > 0)
    edge_opaque = sum(1 for point in _edge_points(rgba.width, rgba.height) if pixels[point][3] > 0)
    edge_total = (rgba.width * 2) + max(0, rgba.height - 2) * 2
    metrics = {
        "alphaBBox": list(bbox) if bbox is not None else None,
        "edgeOpaqueRatio": edge_opaque / edge_total if edge_total else 0,
        "palette": [list(color) for color in palette],
        "removedPixels": len(visited),
        "retainedOpaqueRatio": opaque_pixels / (rgba.width * rgba.height),
        "sourceSize": [rgba.width, rgba.height],
        "tolerance": tolerance,
    }
    return rgba, metrics


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
            archive.extractall(extract_dir, filter="data")
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
