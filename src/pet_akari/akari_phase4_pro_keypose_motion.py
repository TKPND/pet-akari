#!/usr/bin/env python3
"""Build local motion previews from ChatGPT Pro Akari keypose images."""

from __future__ import annotations

import argparse
import json
import shutil
from collections import deque
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw

from pet_akari import akari_full_motion_quality as fq
from pet_akari import clawd_hq_theme as hq

DEFAULT_SOURCE_DIR = Path("work/akari-hq-apng/phase4-chatgpt-pro-faithful-pack/pro-faithful-raw")
DEFAULT_RUN_DIR = Path("work/akari-hq-apng/phase4-chatgpt-pro-faithful-pack/keypose-motion-run")
DEFAULT_FRAME_COUNT = 64
DEFAULT_BACKGROUND_TOLERANCE = 34
DEFAULT_PADDING_RATIO = 0.08


@dataclass(frozen=True)
class KeyposeMotionResult:
    run_dir: Path
    normalized_dir: Path
    masters_dir: Path
    qa_dir: Path
    summary_path: Path


def ensure_dir(path: Path) -> Path:
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_json(path: Path, data: object) -> Path:
    ensure_dir(path.parent)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _rgb_distance(first: tuple[int, int, int], second: tuple[int, int, int]) -> int:
    return max(abs(first[index] - second[index]) for index in range(3))


def _corner_background_color(image: Image.Image, sample_size: int = 12) -> tuple[int, int, int]:
    rgb = image.convert("RGB")
    sample_size = max(1, min(sample_size, rgb.width, rgb.height))
    boxes = (
        (0, 0, sample_size, sample_size),
        (rgb.width - sample_size, 0, rgb.width, sample_size),
        (0, rgb.height - sample_size, sample_size, rgb.height),
        (rgb.width - sample_size, rgb.height - sample_size, rgb.width, rgb.height),
    )
    channels = [[], [], []]
    for box in boxes:
        for red, green, blue in rgb.crop(box).getdata():
            channels[0].append(red)
            channels[1].append(green)
            channels[2].append(blue)
    return tuple(sorted(channel)[len(channel) // 2] for channel in channels)


def remove_boundary_background(image: Image.Image, tolerance: int = DEFAULT_BACKGROUND_TOLERANCE) -> Image.Image:
    rgba = image.convert("RGBA")
    rgb = rgba.convert("RGB")
    background = _corner_background_color(rgb)
    pixels = rgb.load()
    alpha = rgba.getchannel("A")
    visited = set()
    queue: deque[tuple[int, int]] = deque()
    for x in range(rgb.width):
        queue.append((x, 0))
        queue.append((x, rgb.height - 1))
    for y in range(rgb.height):
        queue.append((0, y))
        queue.append((rgb.width - 1, y))

    while queue:
        x, y = queue.popleft()
        if (x, y) in visited:
            continue
        visited.add((x, y))
        if _rgb_distance(pixels[x, y], background) > tolerance:
            continue
        alpha.putpixel((x, y), 0)
        if x > 0:
            queue.append((x - 1, y))
        if x + 1 < rgb.width:
            queue.append((x + 1, y))
        if y > 0:
            queue.append((x, y - 1))
        if y + 1 < rgb.height:
            queue.append((x, y + 1))

    rgba.putalpha(alpha)
    return rgba


@contextmanager
def temporary_theme_sizes(master_size: tuple[int, int], runtime_size: tuple[int, int]):
    original_master = hq.MASTER_SIZE
    original_runtime = hq.RUNTIME_SIZE
    hq.MASTER_SIZE = master_size
    hq.RUNTIME_SIZE = runtime_size
    try:
        yield
    finally:
        hq.MASTER_SIZE = original_master
        hq.RUNTIME_SIZE = original_runtime


def normalize_keypose(
    image: Image.Image,
    *,
    master_size: tuple[int, int] | None = None,
    padding_ratio: float = DEFAULT_PADDING_RATIO,
) -> Image.Image:
    master_size = master_size or hq.MASTER_SIZE
    rgba = image.convert("RGBA")
    bbox = rgba.getchannel("A").getbbox()
    if bbox is None:
        raise ValueError("keypose has no visible pixels after background removal")
    cropped = rgba.crop(bbox)
    pad_x = round(master_size[0] * padding_ratio)
    pad_y = round(master_size[1] * padding_ratio)
    max_width = max(1, master_size[0] - pad_x * 2)
    max_height = max(1, master_size[1] - pad_y * 2)
    scale = min(max_width / cropped.width, max_height / cropped.height)
    size = (max(1, round(cropped.width * scale)), max(1, round(cropped.height * scale)))
    resized = cropped.resize(size, hq._resample_filter())
    canvas = Image.new("RGBA", master_size, (0, 0, 0, 0))
    left = (master_size[0] - resized.width) // 2
    top = master_size[1] - pad_y - resized.height
    canvas.alpha_composite(resized, (left, top))
    return canvas


def collect_keypose_sources(source_dir: Path) -> dict[str, Path]:
    source_dir = Path(source_dir)
    sources = {}
    for state in hq.CORE_STATES:
        matches = sorted(source_dir.glob(f"*{state}*.png"))
        if not matches:
            raise FileNotFoundError(f"missing keypose image for {state} under {source_dir}")
        sources[state] = matches[0]
    return sources


def write_preview_gif(frame_paths: list[Path], output_path: Path, duration_ms: int = fq.FRAME_DURATION_MS) -> Path:
    frames = []
    for path in frame_paths:
        with Image.open(path) as image:
            frame = image.convert("RGBA").resize(hq.RUNTIME_SIZE, hq._resample_filter())
        frames.append(frame)
    ensure_dir(output_path.parent)
    frames[0].save(output_path, save_all=True, append_images=frames[1:], duration=duration_ms, loop=0, disposal=2)
    return output_path


def write_motion_contact_sheet(masters_dir: Path, output_path: Path, sample_count: int = 8) -> Path:
    tile_size = hq.RUNTIME_SIZE
    label_height = 26
    width = sample_count * tile_size[0]
    height = len(hq.CORE_STATES) * (tile_size[1] + label_height)
    sheet = Image.new("RGBA", (width, height), (24, 24, 24, 255))
    draw = ImageDraw.Draw(sheet)
    for row, state in enumerate(hq.CORE_STATES):
        state_frames = sorted((Path(masters_dir) / state).glob("*.png"))
        if not state_frames:
            raise FileNotFoundError(f"missing rendered frames for {state}")
        y = row * (tile_size[1] + label_height)
        indices = [round(index * (len(state_frames) - 1) / max(1, sample_count - 1)) for index in range(sample_count)]
        for column, frame_index in enumerate(indices):
            with Image.open(state_frames[frame_index]) as image:
                frame = image.convert("RGBA").resize(tile_size, hq._resample_filter())
            x = column * tile_size[0]
            sheet.alpha_composite(frame, (x, y))
        draw.text((8, y + tile_size[1] + 6), state, fill=(240, 240, 240, 255))
    ensure_dir(output_path.parent)
    sheet.save(output_path)
    return output_path


def build_keypose_motion_preview(
    source_dir: Path = DEFAULT_SOURCE_DIR,
    run_dir: Path = DEFAULT_RUN_DIR,
    frame_count: int = DEFAULT_FRAME_COUNT,
    background_tolerance: int = DEFAULT_BACKGROUND_TOLERANCE,
    master_size: tuple[int, int] | None = None,
    runtime_size: tuple[int, int] | None = None,
) -> KeyposeMotionResult:
    run_dir = Path(run_dir)
    master_size = master_size or hq.MASTER_SIZE
    runtime_size = runtime_size or hq.RUNTIME_SIZE
    if run_dir.exists():
        shutil.rmtree(run_dir)
    normalized_dir = ensure_dir(run_dir / "normalized")
    frames_dir = ensure_dir(run_dir / "frames")
    masters_dir = ensure_dir(run_dir / "masters")
    qa_dir = ensure_dir(run_dir / "qa")
    previews_dir = ensure_dir(qa_dir / "previews")
    with temporary_theme_sizes(master_size, runtime_size):
        sources = collect_keypose_sources(source_dir)
        normalized_sources = {}
        for state, source in sources.items():
            with Image.open(source) as image:
                transparent = remove_boundary_background(image, tolerance=background_tolerance)
            normalized = normalize_keypose(transparent, master_size=master_size)
            output = normalized_dir / f"{state}.png"
            normalized.save(output)
            normalized_sources[state] = output

        states = {}
        for state, normalized_source in normalized_sources.items():
            rendered = fq.render_state_frames(state, [normalized_source], frames_dir / state, frame_count=frame_count)
            state_master_dir = ensure_dir(masters_dir / state)
            for frame in rendered:
                frame_output = state_master_dir / frame.name
                frame_output.write_bytes(frame.read_bytes())
            partition = frames_dir / state / "layer-partition.json"
            if partition.is_file():
                (state_master_dir / "layer-partition.json").write_bytes(partition.read_bytes())
            write_preview_gif(rendered, previews_dir / f"{state}.gif")
            states[state] = {
                "source": str(sources[state]),
                "normalized": str(normalized_source),
                "frames": len(rendered),
                "preview": str(previews_dir / f"{state}.gif"),
            }

        contact_sheet = write_motion_contact_sheet(masters_dir, qa_dir / "contact-sheet.png")
    summary_path = write_json(
        qa_dir / "keypose-motion-summary.json",
        {
            "ok": True,
            "sourceDir": str(source_dir),
            "runDir": str(run_dir),
            "frameCount": frame_count,
            "backgroundTolerance": background_tolerance,
            "masterSize": list(master_size),
            "runtimeSize": list(runtime_size),
            "contactSheet": str(contact_sheet),
            "states": states,
        },
    )
    return KeyposeMotionResult(run_dir, normalized_dir, masters_dir, qa_dir, summary_path)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build", help="build local motion previews from Pro keyposes")
    build.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE_DIR)
    build.add_argument("--run-dir", type=Path, default=DEFAULT_RUN_DIR)
    build.add_argument("--frame-count", type=int, default=DEFAULT_FRAME_COUNT)
    build.add_argument("--background-tolerance", type=int, default=DEFAULT_BACKGROUND_TOLERANCE)
    build.add_argument("--master-size", default=f"{hq.MASTER_SIZE[0]}x{hq.MASTER_SIZE[1]}")
    build.add_argument("--runtime-size", default=f"{hq.RUNTIME_SIZE[0]}x{hq.RUNTIME_SIZE[1]}")
    return parser


def _parse_size(value: str) -> tuple[int, int]:
    try:
        width, height = value.lower().split("x", 1)
        return (int(width), int(height))
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"expected WIDTHxHEIGHT, got {value}") from exc


def main(argv=None) -> None:
    args = _build_parser().parse_args(argv)
    if args.command == "build":
        result = build_keypose_motion_preview(
            source_dir=args.source_dir,
            run_dir=args.run_dir,
            frame_count=args.frame_count,
            background_tolerance=args.background_tolerance,
            master_size=_parse_size(args.master_size),
            runtime_size=_parse_size(args.runtime_size),
        )
        print(f"wrote keypose motion summary to {result.summary_path}")


if __name__ == "__main__":
    main()
