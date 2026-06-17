"""Import ChatGPT WebUI-generated Akari base PNGs for Phase 4 review."""

from __future__ import annotations

import json
import re
from collections import deque
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
    opaque_pixels = sum(1 for pixel in rgba.getdata() if pixel[3] > 0)
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
