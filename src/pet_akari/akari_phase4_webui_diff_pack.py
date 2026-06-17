"""Build Phase 4 review diff packs for WebUI-imported Akari base images."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageSequence

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
