"""Build a candidate theme from reviewed Phase 4 WebUI selections."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from PIL import Image, ImageSequence

from pet_akari import akari_phase4_webui_diff_pack as diff_pack
from pet_akari import clawd_hq_theme as hq

DEFAULT_OUTPUT_DIR = Path("work/akari-hq-apng/phase4-webui-selection-theme/theme")
DEFAULT_PACKAGE_PATH = Path("work/akari-hq-apng/phase4-webui-selection-theme/akari-hq-apng-webui-selection.zip")
DEFAULT_MANIFEST_NAME = "webui-selection-theme-manifest.json"
STATIC_FRAME_DURATION_MS = 100
STATIC_APNG_PADDING_PX = 12
ALLOWED_DECISIONS = {"adopt", "hold", "reject"}


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
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _resolve_asset_path(value, *, selection_path):
    path = Path(value)
    if path.is_absolute():
        return path
    cwd_candidate = Path.cwd() / path
    if cwd_candidate.exists():
        return cwd_candidate
    return Path(selection_path).parent / path


def load_reviewed_selection(selection_path):
    selection_path = Path(selection_path)
    selection = load_json(selection_path)
    entries = {entry.get("state"): entry for entry in selection.get("selections", [])}
    reviewed = {}
    for state in diff_pack.REQUIRED_STATES:
        entry = entries.get(state)
        if entry is None:
            raise ValueError(f"selection missing state {state}")
        decision = entry.get("decision", "")
        if not decision:
            raise ValueError(f"selection for {state} is not decided")
        if decision not in ALLOWED_DECISIONS:
            raise ValueError(f"selection for {state} has invalid decision {decision}")
        reviewed[state] = {
            **entry,
            "decision": decision,
            "webuiPreviewPath": _resolve_asset_path(entry["webuiPreview"], selection_path=selection_path),
        }
    return reviewed


def _find_transparent_marker_pixel(image):
    rgba = image.convert("RGBA")
    for point in ((1, 1), (rgba.width - 2, 1), (1, rgba.height - 2), (rgba.width - 2, rgba.height - 2)):
        if rgba.getpixel(point)[3] == 0:
            return point
    alpha = rgba.getchannel("A")
    bbox = alpha.getbbox()
    if bbox is None:
        raise ValueError("static APNG source has no visible pixels")
    for y in range(rgba.height):
        for x in range(rgba.width):
            if rgba.getpixel((x, y))[3] == 0:
                return (x, y)
    raise ValueError("static APNG source needs at least one transparent pixel")


def _fit_foreground_preserving_aspect(image, size):
    frame = image.convert("RGBA")
    if frame.size == size:
        return frame
    bbox = frame.getchannel("A").getbbox()
    if bbox is None:
        raise ValueError("static APNG source has no visible pixels")
    foreground = frame.crop(bbox)
    fit_size = (
        max(1, size[0] - STATIC_APNG_PADDING_PX * 2),
        max(1, size[1] - STATIC_APNG_PADDING_PX * 2),
    )
    foreground.thumbnail(fit_size, hq._resample_filter())
    canvas = Image.new("RGBA", size, (0, 0, 0, 0))
    left = (size[0] - foreground.width) // 2
    top = (size[1] - foreground.height) // 2
    canvas.alpha_composite(foreground, (left, top))
    return canvas


def write_static_apng(source_path, output_path):
    source_path = Path(source_path)
    output_path = Path(output_path)
    ensure_dir(output_path.parent)
    with Image.open(source_path) as image:
        first = _fit_foreground_preserving_aspect(image, hq.RUNTIME_SIZE)
    marker = _find_transparent_marker_pixel(first)
    second = first.copy()
    second.putpixel(marker, (1, 1, 1, 0))
    first.save(
        output_path,
        format="PNG",
        save_all=True,
        append_images=[second],
        duration=[STATIC_FRAME_DURATION_MS, STATIC_FRAME_DURATION_MS],
        loop=0,
    )
    return output_path


def _first_frame(path):
    with Image.open(path) as image:
        frames = [frame.copy().convert("RGBA") for frame in ImageSequence.Iterator(image)]
        if image.info.get("default_image") and len(frames) > 1:
            frames = frames[1:]
    if not frames:
        raise ValueError(f"{path} has no display frames")
    return frames[0]


def write_selection_diffs(theme_dir, output_dir, preview_size=160):
    theme_dir = Path(theme_dir)
    output_dir = Path(output_dir)
    diff_dir = ensure_dir(output_dir / "qa" / "selection-diffs")
    current_frames = diff_pack.collect_current_theme_frames(theme_dir)
    diff_paths = {}
    for state in diff_pack.REQUIRED_STATES:
        candidate = _first_frame(output_dir / "assets" / f"akari-{state}.apng")
        diff_paths[state] = diff_pack.write_state_diff(
            diff_dir / f"{state}.png",
            state,
            current_frames[state],
            candidate,
            preview_size,
        )
    contact_sheet = diff_pack.write_contact_sheet(
        output_dir / "qa" / "webui-selection-diff-contact-sheet.png",
        diff_paths,
        preview_size,
    )
    return diff_paths, contact_sheet


def _copy_theme(theme_dir, output_dir):
    theme_dir = Path(theme_dir)
    output_dir = Path(output_dir)
    if output_dir.resolve() == theme_dir.resolve():
        raise ValueError("output_dir must be different from theme_dir")
    if output_dir.exists():
        shutil.rmtree(output_dir)
    shutil.copytree(theme_dir, output_dir)
    return output_dir


def build_selection_theme(
    *, theme_dir, selection_path, output_dir=DEFAULT_OUTPUT_DIR, package_path=DEFAULT_PACKAGE_PATH
):
    theme_dir = Path(theme_dir)
    output_dir = _copy_theme(theme_dir, output_dir)
    reviewed = load_reviewed_selection(selection_path)

    states = {}
    for state in diff_pack.REQUIRED_STATES:
        entry = reviewed[state]
        asset_path = output_dir / "assets" / f"akari-{state}.apng"
        if entry["decision"] == "adopt":
            write_static_apng(entry["webuiPreviewPath"], asset_path)
            source = "webui-static-apng"
            source_asset = entry["webuiPreviewPath"].as_posix()
        else:
            source = "current-theme"
            source_asset = (theme_dir / "assets" / f"akari-{state}.apng").as_posix()
        states[state] = {
            "asset": asset_path.as_posix(),
            "decision": entry["decision"],
            "notes": entry.get("notes", ""),
            "source": source,
            "sourceAsset": source_asset,
        }

    qa_dir = ensure_dir(output_dir / "qa")
    contact_sheet = hq.write_contact_sheet(output_dir, qa_dir / "webui-selection-contact-sheet.png")
    diff_paths, diff_contact_sheet = write_selection_diffs(theme_dir, output_dir)
    for state, diff_path in diff_paths.items():
        states[state]["diffPreview"] = diff_path.as_posix()
    package = hq.package_theme(output_dir, package_path)
    manifest = write_json(
        qa_dir / DEFAULT_MANIFEST_NAME,
        {
            "contactSheet": contact_sheet.as_posix(),
            "diffContactSheet": diff_contact_sheet.as_posix(),
            "package": package.as_posix(),
            "schemaVersion": 1,
            "selectionPath": Path(selection_path).as_posix(),
            "stateOrder": list(diff_pack.REQUIRED_STATES),
            "states": states,
            "status": "review",
            "themeDir": output_dir.as_posix(),
        },
    )
    return {
        "contactSheet": contact_sheet,
        "diffContactSheet": diff_contact_sheet,
        "manifest": manifest,
        "package": package,
        "themeDir": output_dir,
    }


def _build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build", help="build a candidate theme from reviewed WebUI selections")
    build.add_argument("--theme-dir", type=Path, required=True)
    build.add_argument("--selection", type=Path, required=True, dest="selection_path")
    build.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    build.add_argument("--package", type=Path, default=DEFAULT_PACKAGE_PATH, dest="package_path")
    return parser


def main(argv=None):
    args = _build_parser().parse_args(argv)
    if args.command == "build":
        result = build_selection_theme(
            theme_dir=args.theme_dir,
            selection_path=args.selection_path,
            output_dir=args.output_dir,
            package_path=args.package_path,
        )
        print(f"wrote {result['manifest']}")


if __name__ == "__main__":
    main()
