"""Build Phase 4 review diff packs for WebUI-imported Akari base images."""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageChops, ImageSequence

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
