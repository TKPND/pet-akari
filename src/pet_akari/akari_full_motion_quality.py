#!/usr/bin/env python3
"""Build non-blur full-state Akari HQ APNG motion assets."""

from __future__ import annotations

import argparse
import json
import math
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageChops

from pet_akari import clawd_hq_theme as hq

RUN_DIR = Path("work/akari-hq-apng/full-motion-quality-run")
SOURCE_ROOT = Path("work/akari-hq-apng/denser-source-run/masters-stabilized")
CLAWD_ROOT = Path("work/clawd-on-desk")
OUTPUTS_DIR = Path("outputs/akari-hq-apng-theme")
PACKAGE_PATH = Path("outputs/akari-hq-apng-theme.zip")

RENDERED_FRAMES = 64
FRAME_DURATION_MS = 63
MASTER_SIZE = hq.MASTER_SIZE
RUNTIME_SIZE = hq.RUNTIME_SIZE


@dataclass(frozen=True)
class RunPaths:
    run_dir: Path
    outputs_dir: Path
    frames_dir: Path
    masters_dir: Path
    staging_theme_dir: Path
    qa_dir: Path
    metrics_dir: Path


@dataclass(frozen=True)
class PreflightResult:
    ok: bool
    missing: tuple[str, ...]
    checked: dict[str, str]
    recovery: tuple[str, ...]


@dataclass(frozen=True)
class FrameMetrics:
    bbox: tuple[int, int, int, int]
    visible_width: int
    visible_height: int
    alpha_area: int
    upper_alpha_area: int
    upper_visible_width: int
    baseline_y: int
    center_x: float
    center_y: float


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def build_motion_contract() -> dict[str, object]:
    return {
        "states": {
            state: {
                "durationMs": FRAME_DURATION_MS,
                "inbetweens": 0,
                "renderedFrames": RENDERED_FRAMES,
            }
            for state in hq.CORE_STATES
        }
    }


def write_json(path: Path, data: object) -> Path:
    ensure_dir(path.parent)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def run_preflight(
    source_root: Path = SOURCE_ROOT,
    clawd_root: Path = CLAWD_ROOT,
    outputs_dir: Path = OUTPUTS_DIR,
) -> PreflightResult:
    source_root = Path(source_root)
    clawd_root = Path(clawd_root)
    outputs_dir = Path(outputs_dir)
    checked = {
        "source_root": str(source_root),
        "clawd_validator": str(clawd_root / "scripts" / "validate-theme.js"),
        "clawd_svg_samples": str(clawd_root / "assets" / "svg"),
        "outputs_dir": str(outputs_dir),
    }
    missing = []
    if not source_root.is_dir():
        missing.append("source_root")
    for state in hq.CORE_STATES:
        state_dir = source_root / state
        if not state_dir.is_dir():
            missing.append(f"source_state:{state}")
        elif not sorted(state_dir.glob("*.png")):
            missing.append(f"source_frames:{state}")
    if not (clawd_root / "scripts" / "validate-theme.js").is_file():
        missing.append("clawd_validator")
    if not (clawd_root / "assets" / "svg").is_dir():
        missing.append("clawd_svg_samples")
    if outputs_dir.exists() and not outputs_dir.is_dir():
        missing.append("outputs_dir")
    recovery = []
    if any(item.startswith("source_") for item in missing):
        recovery.append(
            "source recovery: expected stabilized PNG anchors under "
            "work/akari-hq-apng/denser-source-run/masters-stabilized/<state>/; "
            "if missing, rebuild/split the denser source run before continuing."
        )
    return PreflightResult(ok=not missing, missing=tuple(missing), checked=checked, recovery=tuple(recovery))


def prepare_run(run_dir: Path = RUN_DIR, outputs_dir: Path = OUTPUTS_DIR) -> RunPaths:
    run_dir = Path(run_dir)
    paths = RunPaths(
        run_dir=run_dir,
        outputs_dir=Path(outputs_dir),
        frames_dir=ensure_dir(run_dir / "frames"),
        masters_dir=ensure_dir(run_dir / "masters"),
        staging_theme_dir=ensure_dir(run_dir / "staging-theme"),
        qa_dir=ensure_dir(run_dir / "qa"),
        metrics_dir=ensure_dir(run_dir / "qa" / "metrics"),
    )
    ensure_dir(paths.qa_dir / "previews")
    write_json(run_dir / "motion-contract.json", build_motion_contract())
    return paths


def _nonzero_alpha_area(alpha: Image.Image) -> int:
    binary = alpha.point(lambda value: 255 if value else 0)
    return int(sum(binary.histogram()[1:]))


def measure_frame_metrics(image: Image.Image) -> FrameMetrics:
    rgba = image.convert("RGBA")
    alpha = rgba.getchannel("A")
    bbox = alpha.getbbox()
    if bbox is None:
        return FrameMetrics((0, 0, 0, 0), 0, 0, 0, 0, 0, 0, 0.0, 0.0)
    left, top, right, bottom = bbox
    cropped_alpha = alpha.crop(bbox)
    alpha_area = _nonzero_alpha_area(cropped_alpha)
    upper_bottom = top + max(1, int((bottom - top) * 0.38))
    upper_alpha = alpha.crop((left, top, right, upper_bottom))
    upper_bbox = upper_alpha.getbbox()
    upper_alpha_area = _nonzero_alpha_area(upper_alpha)
    upper_visible_width = upper_bbox[2] - upper_bbox[0] if upper_bbox else 0
    return FrameMetrics(
        bbox=bbox,
        visible_width=right - left,
        visible_height=bottom - top,
        alpha_area=alpha_area,
        upper_alpha_area=upper_alpha_area,
        upper_visible_width=upper_visible_width,
        baseline_y=bottom - 1,
        center_x=(left + right) / 2,
        center_y=(top + bottom) / 2,
    )


def _mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def evaluate_sleeping_size_gate(
    *,
    sleeping: FrameMetrics,
    standing_reference: list[FrameMetrics],
    min_area_ratio: float,
    min_head_readability_ratio: float,
) -> dict[str, object]:
    reference_area = _mean([float(item.alpha_area) for item in standing_reference])
    reference_head = _mean([float(item.upper_alpha_area) for item in standing_reference])
    area_ratio = float(sleeping.alpha_area) / reference_area if reference_area else 0.0
    head_ratio = float(sleeping.upper_alpha_area) / reference_head if reference_head else 0.0
    return {
        "ok": area_ratio >= min_area_ratio and head_ratio >= min_head_readability_ratio,
        "areaRatio": area_ratio,
        "headReadabilityRatio": head_ratio,
        "minAreaRatio": min_area_ratio,
        "minHeadReadabilityRatio": min_head_readability_ratio,
    }


@dataclass(frozen=True)
class Transform:
    dx: float = 0.0
    dy: float = 0.0
    scale_x: float = 1.0
    scale_y: float = 1.0


OWNERSHIP_LEGACY = "legacy"
OWNERSHIP_EXACT = "exact"
OWNERSHIP_MODES = (OWNERSHIP_LEGACY, OWNERSHIP_EXACT)


def _owned_alpha_mask(image: Image.Image) -> Image.Image:
    alpha = image if image.mode == "L" else image.convert("RGBA").getchannel("A")
    return alpha.point(lambda value: 255 if value else 0)


def _alpha_overlap_pixels(first: Image.Image, second: Image.Image, *, threshold: int = 1) -> int:
    first_alpha = first.convert("RGBA").getchannel("A")
    second_alpha = second.convert("RGBA").getchannel("A")
    first_bbox = first_alpha.getbbox()
    second_bbox = second_alpha.getbbox()
    if first_bbox is None or second_bbox is None:
        return 0
    left = max(first_bbox[0], second_bbox[0])
    top = max(first_bbox[1], second_bbox[1])
    right = min(first_bbox[2], second_bbox[2])
    bottom = min(first_bbox[3], second_bbox[3])
    if right <= left or bottom <= top:
        return 0
    box = (left, top, right, bottom)
    first_alpha = first_alpha.crop(box).point(lambda value: 255 if value >= threshold else 0)
    second_alpha = second_alpha.crop(box).point(lambda value: 255 if value >= threshold else 0)
    overlap = ImageChops.multiply(first_alpha, second_alpha)
    return int(overlap.histogram()[255])


def _binary_alpha(image: Image.Image) -> Image.Image:
    return image.convert("RGBA").getchannel("A").point(lambda value: 255 if value else 0)


def layer_overlap_pixels(first: Image.Image, second: Image.Image) -> int:
    return _alpha_overlap_pixels(first, second, threshold=1)


def build_layer_partition_report(layers: dict[str, Image.Image]) -> dict[str, object]:
    moving = ["torso_base", "left_side", "right_side", "head"]
    all_names = ["body_base", *moving]
    overlaps = {}
    body_overlaps = {}
    opaque_overlaps = {}
    unexpected_overlaps = {}
    for name in moving:
        if "body_base" in layers and name in layers:
            body_overlaps[name] = layer_overlap_pixels(layers["body_base"], layers[name])
    for index, first_name in enumerate(moving):
        for second_name in moving[index + 1 :]:
            if first_name in layers and second_name in layers:
                key = f"{first_name}:{second_name}"
                overlaps[key] = layer_overlap_pixels(layers[first_name], layers[second_name])
                unexpected_overlaps[key] = overlaps[key]
    for index, first_name in enumerate(all_names):
        for second_name in all_names[index + 1 :]:
            if first_name in layers and second_name in layers:
                opaque_overlaps[f"{first_name}:{second_name}"] = _alpha_overlap_pixels(
                    layers[first_name],
                    layers[second_name],
                    threshold=220,
                )
    body_residual = sum(body_overlaps.values())
    opaque_overlap = sum(opaque_overlaps.values())
    unexpected_overlap = sum(unexpected_overlaps.values())
    max_overlap = max(body_residual, opaque_overlap, unexpected_overlap)
    return {
        "ok": body_residual == 0 and opaque_overlap == 0 and unexpected_overlap == 0,
        "maxOverlapPixels": max_overlap,
        "bodyResidualOverlapPixels": body_residual,
        "opaqueOverlapPixels": opaque_overlap,
        "allowedFeatherOverlapPixels": 0,
        "unexpectedOverlapPixels": unexpected_overlap,
        "overlaps": overlaps,
        "bodyOverlaps": body_overlaps,
        "opaqueOverlaps": opaque_overlaps,
    }


def _partition_report_allowed(partition: dict[str, object], ownership_mode: str) -> bool:
    if partition["ok"]:
        return True
    return (
        ownership_mode == OWNERSHIP_LEGACY
        and partition["opaqueOverlapPixels"] == 0
        and partition["unexpectedOverlapPixels"] == 0
    )


def extract_basic_layers(image: Image.Image, ownership_mode: str = OWNERSHIP_EXACT) -> dict[str, Image.Image]:
    if ownership_mode not in OWNERSHIP_MODES:
        raise ValueError(f"unknown ownership mode {ownership_mode}")
    rgba = image.convert("RGBA")
    metrics = measure_frame_metrics(rgba)
    if metrics.alpha_area == 0:
        return {"body_base": rgba}
    left, top, right, bottom = metrics.bbox
    height = bottom - top
    width = right - left
    head_bottom = top + int(height * 0.38)
    torso_top = head_bottom
    side_width = max(1, int(width * 0.38))
    left_side_right = min(right, left + side_width)
    right_side_left = max(left, right - side_width)

    alpha = rgba.getchannel("A")
    part_mask = Image.new("L", rgba.size, 0)

    def layer_from_box(box: tuple[int, int, int, int]) -> Image.Image:
        clipped = (
            max(0, box[0]),
            max(0, box[1]),
            min(rgba.width, box[2]),
            min(rgba.height, box[3]),
        )
        if clipped[2] <= clipped[0] or clipped[3] <= clipped[1]:
            return Image.new("RGBA", rgba.size, (0, 0, 0, 0))
        source_crop = rgba.crop(clipped)
        alpha_crop = alpha.crop(clipped)
        if ownership_mode == OWNERSHIP_LEGACY:
            part_mask.paste(255, clipped, mask=alpha_crop)
            layer_mask = alpha_crop
        else:
            owned = _owned_alpha_mask(alpha_crop)
            part_mask.paste(owned, clipped)
            layer_mask = owned
        layer = Image.new("RGBA", rgba.size, (0, 0, 0, 0))
        layer.paste(source_crop, clipped, mask=layer_mask)
        return layer

    head = layer_from_box((left, top, right, head_bottom))
    left_side = layer_from_box((left, torso_top, left_side_right, bottom))
    right_side = layer_from_box((right_side_left, torso_top, right, bottom))
    torso_base = layer_from_box((left_side_right, torso_top, right_side_left, bottom))
    body_base = rgba.copy()
    erased_alpha = alpha.copy()
    erased_alpha.paste(0, mask=part_mask)
    body_base.putalpha(erased_alpha)
    return {
        "body_base": body_base,
        "torso_base": torso_base,
        "left_side": left_side,
        "right_side": right_side,
        "head": head,
    }


def ease_in_out(phase: float) -> float:
    return 0.5 - 0.5 * math.cos(math.tau * phase)


def motion_wave(phase: float) -> float:
    return math.sin(math.tau * phase) + 0.18 * math.sin(2.0 * math.tau * phase)


def recipe_transform(state: str, layer_name: str, frame_index: int, frame_count: int) -> Transform:
    phase = frame_index / frame_count
    wave = motion_wave(phase)
    soft = ease_in_out(phase)
    if state == "sleeping":
        if layer_name in {"torso_base", "left_side", "right_side"}:
            return Transform(scale_x=1.015, scale_y=1.0 + 0.025 * soft)
        if layer_name == "head":
            return Transform(dy=-4.0 * soft)
    if state == "working":
        if layer_name in {"torso_base", "head"}:
            return Transform(dy=-10.0 * max(0.0, wave))
        if layer_name in {"left_side", "right_side"}:
            return Transform(dy=8.0 * wave)
    if state == "notification":
        if layer_name == "right_side":
            return Transform(dy=-38.0 * soft)
        return Transform(dy=-4.0 * soft)
    if state == "attention":
        return Transform(dy=-12.0 * wave)
    if state == "error":
        return Transform(dy=8.0 * soft, scale_x=1.0 + 0.015 * soft, scale_y=1.0 - 0.035 * soft)
    if state == "thinking":
        if layer_name == "head":
            return Transform(dx=10.0 * wave, dy=-3.0 * soft)
        return Transform(dx=3.0 * wave)
    return Transform(dy=-5.0 * soft, scale_x=1.0 + 0.006 * soft, scale_y=1.0 - 0.006 * soft)


def _transform_layer(layer: Image.Image, transform: Transform) -> Image.Image:
    bbox = layer.getchannel("A").getbbox()
    if bbox is None:
        return layer.copy()
    cropped = layer.crop(bbox)
    width = max(1, round(cropped.width * transform.scale_x))
    height = max(1, round(cropped.height * transform.scale_y))
    resized = cropped.resize((width, height), hq._resample_filter())
    canvas = Image.new("RGBA", layer.size, (0, 0, 0, 0))
    left = round(bbox[0] + transform.dx - (width - cropped.width) / 2)
    top = round(bbox[1] + transform.dy - (height - cropped.height))
    paste_left = max(0, left)
    paste_top = max(0, top)
    crop_left = max(0, -left)
    crop_top = max(0, -top)
    crop_right = min(resized.width, layer.width - left)
    crop_bottom = min(resized.height, layer.height - top)
    if crop_right > crop_left and crop_bottom > crop_top:
        canvas.alpha_composite(resized.crop((crop_left, crop_top, crop_right, crop_bottom)), (paste_left, paste_top))
    return canvas


def _render_puppet_layers(
    layers: dict[str, Image.Image],
    state: str,
    frame_index: int,
    frame_count: int,
) -> Image.Image:
    base_layer = layers.get("body_base")
    if base_layer is None:
        first_layer = next(iter(layers.values()))
        canvas = Image.new("RGBA", first_layer.size, (0, 0, 0, 0))
    else:
        canvas = Image.new("RGBA", base_layer.size, (0, 0, 0, 0))
        canvas.alpha_composite(base_layer)
    for name in ("torso_base", "left_side", "right_side", "head"):
        layer = layers.get(name)
        if layer is None:
            continue
        canvas.alpha_composite(_transform_layer(layer, recipe_transform(state, name, frame_index, frame_count)))
    return canvas


def render_puppet_frame(
    base: Image.Image,
    state: str,
    frame_index: int,
    frame_count: int,
    ownership_mode: str = OWNERSHIP_EXACT,
    validate_partition: bool = True,
) -> Image.Image:
    layers = extract_basic_layers(base, ownership_mode=ownership_mode)
    if validate_partition:
        partition = build_layer_partition_report(layers)
        if not _partition_report_allowed(partition, ownership_mode):
            raise ValueError(f"overlapping motion layers would cause opaque duplicates: {partition}")
    return _render_puppet_layers(layers, state, frame_index, frame_count)


def _load_anchor(path: Path) -> Image.Image:
    with Image.open(path) as source:
        base = source.convert("RGBA")
    if base.size != hq.MASTER_SIZE:
        base = base.resize(hq.MASTER_SIZE, hq._resample_filter())
    return base


def render_state_frames(
    state: str,
    source_paths: list[Path],
    output_dir: Path,
    frame_count: int = RENDERED_FRAMES,
    ownership_mode: str = OWNERSHIP_EXACT,
) -> list[Path]:
    if state not in hq.CORE_STATES:
        raise ValueError(f"unknown state {state}")
    if not source_paths:
        raise ValueError(f"no source anchors for {state}")
    if frame_count < len(source_paths):
        raise ValueError("frame_count must be at least the number of source anchors")
    output_dir = ensure_dir(Path(output_dir))
    anchors = [_load_anchor(path) for path in source_paths]
    anchor_layers = [extract_basic_layers(anchor, ownership_mode=ownership_mode) for anchor in anchors]
    partition_reports = [
        {"source": str(path), **build_layer_partition_report(layers)}
        for path, layers in zip(source_paths, anchor_layers)
    ]
    write_json(output_dir / "layer-partition.json", partition_reports)
    for partition in partition_reports:
        if not _partition_report_allowed(partition, ownership_mode):
            raise ValueError(f"overlapping motion layers would cause opaque duplicates: {partition}")
    outputs = []
    boundaries = [round(index * frame_count / len(anchors)) for index in range(len(anchors) + 1)]
    for index in range(frame_count):
        anchor_index = next(
            candidate for candidate in range(len(anchors)) if boundaries[candidate] <= index < boundaries[candidate + 1]
        )
        anchor_start = boundaries[anchor_index]
        anchor_end = boundaries[anchor_index + 1]
        local_count = max(1, anchor_end - anchor_start)
        local_frame = index - anchor_start
        frame = _render_puppet_layers(
            anchor_layers[anchor_index],
            state,
            local_frame,
            local_count,
        )
        output = output_dir / f"{index + 1:03d}.png"
        frame.save(output)
        outputs.append(output)
    return outputs


def ghosting_score(image: Image.Image) -> float:
    rgba = image.convert("RGBA")
    alpha = rgba.getchannel("A")
    bbox = alpha.getbbox()
    if bbox is None:
        return 0.0
    histogram = alpha.histogram()
    semi_transparent = sum(histogram[20:220])
    opaque = sum(histogram[220:256])
    if opaque == 0:
        return float(semi_transparent)
    return semi_transparent / opaque


def _runtime_image(image: Image.Image) -> Image.Image:
    return image.convert("RGBA").resize(hq.RUNTIME_SIZE, hq._resample_filter())


def _dark_background(image: Image.Image) -> Image.Image:
    background = Image.new("RGBA", image.size, (24, 24, 24, 255))
    background.alpha_composite(image.convert("RGBA"))
    return background


def _mean_abs_diff(first: Image.Image, second: Image.Image, box: tuple[int, int, int, int]) -> float:
    diff = ImageChops.difference(first.convert("RGBA").crop(box), second.convert("RGBA").crop(box))
    total_pixels = diff.width * diff.height * 4
    if total_pixels == 0:
        return 0.0
    histogram = diff.histogram()
    total = 0
    for channel in range(4):
        offset = channel * 256
        total += sum(value * histogram[offset + value] for value in range(256))
    return total / total_pixels


def _max_diff(first: Image.Image, second: Image.Image, box: tuple[int, int, int, int]) -> int:
    diff = ImageChops.difference(first.convert("RGBA").crop(box), second.convert("RGBA").crop(box))
    return max(channel[1] for channel in diff.getextrema())


def _runtime_split_y(source: Image.Image) -> int:
    metrics = measure_frame_metrics(source)
    if metrics.alpha_area == 0:
        return 0
    top = metrics.bbox[1]
    height = metrics.bbox[3] - metrics.bbox[1]
    source_y = top + int(height * 0.38)
    return round(source_y * hq.RUNTIME_SIZE[1] / source.height)


def _seam_band_box(image: Image.Image, split_y: int, radius: int = 3) -> tuple[int, int, int, int]:
    top = max(0, split_y - radius)
    bottom = min(image.height, split_y + radius + 1)
    return (0, top, image.width, bottom)


def _motion_proxy_runtime_pixels(base: Image.Image, state: str, frame_index: int, frame_count: int) -> float:
    transforms = [
        recipe_transform(state, layer_name, frame_index, frame_count)
        for layer_name in ("torso_base", "left_side", "right_side", "head")
    ]
    runtime_displacements = [
        (
            transform.dx * hq.RUNTIME_SIZE[0] / base.width,
            transform.dy * hq.RUNTIME_SIZE[1] / base.height,
        )
        for transform in transforms
    ]
    absolute = max((abs(dx) + abs(dy) for dx, dy in runtime_displacements), default=0.0)
    relative = 0.0
    for index, first in enumerate(runtime_displacements):
        for second in runtime_displacements[index + 1 :]:
            relative = max(relative, abs(first[0] - second[0]) + abs(first[1] - second[1]))
    return max(absolute, relative)


def write_seam_probe(
    source_root: Path = SOURCE_ROOT,
    output_dir: Path = Path("work/akari-hq-apng/line-investigation/seam-probe"),
    samples: tuple[tuple[str, int, int], ...] = (
        ("idle", 0, 8),
        ("working", 2, 8),
        ("notification", 2, 8),
        ("attention", 2, 8),
    ),
) -> Path:
    output_dir = ensure_dir(Path(output_dir))
    report = {"samples": []}
    for state, frame_index, frame_count in samples:
        source_paths = sorted((Path(source_root) / state).glob("*.png"))
        if not source_paths:
            raise FileNotFoundError(f"no source anchors for {state} under {source_root}")
        source_path = source_paths[0]
        base = _load_anchor(source_path)
        source_runtime = _runtime_image(base)
        legacy_runtime = _runtime_image(
            render_puppet_frame(base, state, frame_index, frame_count, ownership_mode=OWNERSHIP_LEGACY)
        )
        exact_runtime = _runtime_image(
            render_puppet_frame(base, state, frame_index, frame_count, ownership_mode=OWNERSHIP_EXACT)
        )
        split_y = _runtime_split_y(base)
        seam_box = _seam_band_box(source_runtime, split_y)
        prefix = f"{state}-{frame_index:02d}"
        source_runtime.save(output_dir / f"{prefix}-source.png")
        legacy_runtime.save(output_dir / f"{prefix}-legacy.png")
        exact_runtime.save(output_dir / f"{prefix}-exact.png")
        ImageChops.difference(source_runtime, legacy_runtime).save(output_dir / f"{prefix}-legacy-diff.png")
        ImageChops.difference(source_runtime, exact_runtime).save(output_dir / f"{prefix}-exact-diff.png")
        source_dark = _dark_background(source_runtime)
        legacy_dark = _dark_background(legacy_runtime)
        exact_dark = _dark_background(exact_runtime)
        source_dark.save(output_dir / f"{prefix}-source-dark.png")
        legacy_dark.save(output_dir / f"{prefix}-legacy-dark.png")
        exact_dark.save(output_dir / f"{prefix}-exact-dark.png")
        layers = extract_basic_layers(base, ownership_mode=OWNERSHIP_EXACT)
        report["samples"].append(
            {
                "state": state,
                "frameIndex": frame_index,
                "frameCount": frame_count,
                "source": str(source_path),
                "runtimeSplitY": split_y,
                "seamBox": seam_box,
                "legacyMeanAbsDiff": _mean_abs_diff(source_runtime, legacy_runtime, seam_box),
                "exactMeanAbsDiff": _mean_abs_diff(source_runtime, exact_runtime, seam_box),
                "legacyDarkMeanAbsDiff": _mean_abs_diff(source_dark, legacy_dark, seam_box),
                "exactDarkMeanAbsDiff": _mean_abs_diff(source_dark, exact_dark, seam_box),
                "legacyMaxDiff": _max_diff(source_runtime, legacy_runtime, seam_box),
                "exactMaxDiff": _max_diff(source_runtime, exact_runtime, seam_box),
                "partition": build_layer_partition_report(layers),
                "motionProxyRuntimePixels": _motion_proxy_runtime_pixels(base, state, frame_index, frame_count),
            }
        )
    return write_json(output_dir / "seam-probe-report.json", report)


def build_state_quality_report(state: str, metrics: dict[str, dict[str, object]]) -> dict[str, object]:
    statuses = [gate.get("ok") for gate in metrics.values()]
    if any(status is False for status in statuses):
        status = "fail"
    elif any(status is None for status in statuses):
        status = "needs-human-review"
    else:
        status = "pass"
    return {"state": state, "status": status, "metrics": metrics}


def evaluate_rendered_state(
    state: str,
    frame_paths: list[Path],
    standing_reference: list[FrameMetrics],
    visual_approval: dict[str, object] | None = None,
) -> dict[str, object]:
    frames = []
    metrics = []
    for path in frame_paths:
        with Image.open(path) as image:
            frame = image.convert("RGBA")
        frames.append(frame)
        metrics.append(measure_frame_metrics(frame))
    ghosting = max((ghosting_score(frame) for frame in frames), default=0.0)
    unique_frames = len({hq.sha256_file(path) for path in frame_paths})
    partition_path = frame_paths[0].parent / "layer-partition.json" if frame_paths else None
    partition_reports = (
        json.loads(partition_path.read_text(encoding="utf-8")) if partition_path and partition_path.is_file() else []
    )
    max_layer_overlap = max((int(report.get("maxOverlapPixels", 0)) for report in partition_reports), default=0)
    approval = visual_approval if isinstance(visual_approval, dict) else {}
    approval_states = approval.get("states") if isinstance(approval.get("states"), dict) else {}
    raw_state_approval = approval_states.get(state, {})
    state_approval = raw_state_approval if isinstance(raw_state_approval, dict) else {}
    semantic_ok = True if state_approval.get("approved") is True else None
    gates = {
        "scale": {"ok": all(item.alpha_area > 0 for item in metrics), "frameCount": len(metrics)},
        "ghosting": {"ok": ghosting < 0.12, "maxScore": ghosting, "maxAllowed": 0.12},
        "motion": {"ok": unique_frames >= 8, "uniqueFrames": unique_frames},
        "layerPartition": {
            "ok": bool(partition_reports) and max_layer_overlap == 0,
            "maxOverlapPixels": max_layer_overlap,
            "partitionReport": str(partition_path) if partition_path else None,
        },
    }
    if state == "sleeping" and metrics:
        gates["sleepingSize"] = evaluate_sleeping_size_gate(
            sleeping=metrics[0],
            standing_reference=standing_reference,
            min_area_ratio=0.55,
            min_head_readability_ratio=0.45,
        )
        gates["semantics"] = {
            "ok": semantic_ok,
            "rubric": "closed or relaxed eyes, resting posture, slow breathing",
            "approval": state_approval,
        }
    else:
        gates["semantics"] = {
            "ok": semantic_ok,
            "rubric": f"{state} state semantics require visual QA",
            "approval": state_approval,
        }
    return build_state_quality_report(state, gates)


def build_zero_inbetween_contract(frame_count: int = RENDERED_FRAMES) -> dict[str, object]:
    return {
        "states": {state: {"durationMs": FRAME_DURATION_MS, "inbetweens": 0} for state in hq.CORE_STATES},
        "renderedFrames": frame_count,
    }


def export_staging_theme(paths: RunPaths, frame_count: int = RENDERED_FRAMES) -> Path:
    contract = build_zero_inbetween_contract(frame_count)
    hq.assert_no_exporter_inbetweens(contract)
    hq.export_theme(
        paths.masters_dir,
        paths.staging_theme_dir,
        include_ultra=False,
        motion_contract=contract,
    )
    hq.write_contact_sheet(paths.staging_theme_dir, paths.staging_theme_dir / "contact-sheet.png")
    return paths.staging_theme_dir


def all_states_visually_approved(visual_approval: dict[str, object] | None) -> bool:
    approval = visual_approval if isinstance(visual_approval, dict) else {}
    states = approval.get("states") or {}
    return (
        isinstance(states, dict)
        and set(states) == set(hq.CORE_STATES)
        and all(isinstance(states[state], dict) and states[state].get("approved") is True for state in hq.CORE_STATES)
    )


def load_visual_approval(path: Path) -> dict[str, object] | None:
    path = Path(path)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid visual approval JSON: {path}") from exc


def write_visual_approval(paths: RunPaths, approvals: dict[str, dict[str, object]], reviewer: str = "codex") -> Path:
    data = {
        "reviewer": reviewer,
        "states": approvals,
    }
    return write_json(paths.qa_dir / "visual-approval.json", data)


def write_source_manifest(paths: RunPaths, source_root: Path) -> Path:
    manifest = {
        state: [str(path) for path in sorted((Path(source_root) / state).glob("*.png"))] for state in hq.CORE_STATES
    }
    return write_json(paths.run_dir / "source-manifest.json", manifest)


def write_run_summary(
    paths: RunPaths,
    *,
    states: dict[str, object],
    promoted: bool,
    visual_approval: dict[str, object] | None = None,
) -> Path:
    visual_approved = all_states_visually_approved(visual_approval)
    states_pass = _all_states_pass({"states": states})
    data = {
        "ok": visual_approved and states_pass,
        "promoted": promoted,
        "visualApproved": visual_approved,
        "states": states,
        "paths": {
            "runDir": str(paths.run_dir),
            "stagingTheme": str(paths.staging_theme_dir),
            "outputsDir": str(paths.outputs_dir),
            "summary": str(paths.qa_dir / "run-summary.json"),
            "visualApproval": str(paths.qa_dir / "visual-approval.json"),
        },
        "contract": build_motion_contract(),
    }
    return write_json(paths.qa_dir / "run-summary.json", data)


def _all_states_pass(summary: dict[str, object]) -> bool:
    states = summary.get("states", {})
    return (
        isinstance(states, dict)
        and set(states) == set(hq.CORE_STATES)
        and all(isinstance(states[state], dict) and states[state].get("status") == "pass" for state in hq.CORE_STATES)
    )


def promote_staging_theme(
    paths: RunPaths,
    summary: dict[str, object],
    visual_approval: dict[str, object] | None,
) -> Path:
    if not _all_states_pass(summary):
        raise ValueError("not all states passed; refusing to promote staging theme")
    if not all_states_visually_approved(visual_approval):
        raise ValueError("visual approval is required for every state before promotion")
    ensure_dir(paths.outputs_dir.parent)
    if paths.outputs_dir.exists():
        backup = paths.qa_dir / "previous-output-backup"
        if backup.exists():
            shutil.rmtree(backup)
        shutil.copytree(paths.outputs_dir, backup)
        shutil.rmtree(paths.outputs_dir)
    shutil.copytree(paths.staging_theme_dir, paths.outputs_dir)
    return paths.outputs_dir


def package_outputs(outputs_dir: Path = OUTPUTS_DIR, package_path: Path = PACKAGE_PATH) -> Path:
    outputs_dir = Path(outputs_dir)
    package_path = Path(package_path)
    ensure_dir(package_path.parent)
    if package_path.exists():
        package_path.unlink()
    with zipfile.ZipFile(package_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(outputs_dir.rglob("*")):
            if path.is_file():
                archive.write(path, Path("akari-hq-apng") / path.relative_to(outputs_dir))
    return package_path


def _default_package_path(outputs_dir: Path) -> Path:
    outputs_dir = Path(outputs_dir)
    return outputs_dir.parent / f"{outputs_dir.name}.zip"


def render_all_states(
    paths: RunPaths,
    source_root: Path = SOURCE_ROOT,
    frame_count: int = RENDERED_FRAMES,
    ownership_mode: str = OWNERSHIP_EXACT,
) -> dict[str, list[Path]]:
    rendered = {}
    for state in hq.CORE_STATES:
        sources = sorted((Path(source_root) / state).glob("*.png"))
        if not sources:
            raise FileNotFoundError(f"no source anchors for {state} under {source_root}")
        frames = render_state_frames(
            state,
            sources,
            paths.frames_dir / state,
            frame_count=frame_count,
            ownership_mode=ownership_mode,
        )
        master_dir = ensure_dir(paths.masters_dir / state)
        for frame in frames:
            shutil.copy2(frame, master_dir / frame.name)
        partition_report = paths.frames_dir / state / "layer-partition.json"
        if not partition_report.is_file():
            raise FileNotFoundError(f"missing layer partition report for {state}: {partition_report}")
        shutil.copy2(partition_report, master_dir / "layer-partition.json")
        rendered[state] = sorted(master_dir.glob("*.png"))
    return rendered


def run_pipeline(
    run_dir: Path = RUN_DIR,
    source_root: Path = SOURCE_ROOT,
    clawd_root: Path = CLAWD_ROOT,
    outputs_dir: Path = OUTPUTS_DIR,
    promote: bool = False,
    visual_approval_path: Path | None = None,
    package_path: Path | None = None,
) -> Path:
    preflight = run_preflight(source_root=source_root, clawd_root=clawd_root, outputs_dir=outputs_dir)
    paths = prepare_run(run_dir, outputs_dir=outputs_dir)
    write_json(
        paths.qa_dir / "preflight.json",
        {
            "ok": preflight.ok,
            "missing": list(preflight.missing),
            "checked": preflight.checked,
            "recovery": list(preflight.recovery),
        },
    )
    if not preflight.ok:
        raise FileNotFoundError(f"preflight failed: {', '.join(preflight.missing)}")
    write_source_manifest(paths, source_root)
    visual_approval = load_visual_approval(visual_approval_path or (paths.qa_dir / "visual-approval.json"))
    rendered = render_all_states(paths, source_root=source_root)
    standing_reference = []
    for state in [item for item in hq.CORE_STATES if item != "sleeping"]:
        with Image.open(rendered[state][0]) as image:
            standing_reference.append(measure_frame_metrics(image.convert("RGBA")))
    state_reports = {}
    for state, frames in rendered.items():
        state_reports[state] = evaluate_rendered_state(
            state, frames, standing_reference, visual_approval=visual_approval
        )
    write_json(paths.metrics_dir / "state-quality.json", state_reports)
    export_staging_theme(paths)
    hq.validate_lineage(paths.staging_theme_dir)
    hq.validate_theme_assets(paths.staging_theme_dir, motion_contract=build_zero_inbetween_contract())
    summary_path = write_run_summary(paths, states=state_reports, promoted=False, visual_approval=visual_approval)
    if promote:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        promote_staging_theme(paths, summary, visual_approval=visual_approval)
        resolved_package_path = (
            Path(package_path) if package_path is not None else _default_package_path(paths.outputs_dir)
        )
        package_outputs(outputs_dir=paths.outputs_dir, package_path=resolved_package_path)
        write_run_summary(paths, states=state_reports, promoted=True, visual_approval=visual_approval)
    return paths.qa_dir / "run-summary.json"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    run = subparsers.add_parser("run", help="render and validate the full-state Akari motion theme")
    run.add_argument("--run-dir", type=Path, default=RUN_DIR)
    run.add_argument("--source-root", type=Path, default=SOURCE_ROOT)
    run.add_argument("--clawd-root", type=Path, default=CLAWD_ROOT)
    run.add_argument("--outputs-dir", type=Path, default=OUTPUTS_DIR)
    run.add_argument("--visual-approval", type=Path)
    run.add_argument("--package-path", type=Path)
    run.add_argument("--promote", action="store_true")
    probe = subparsers.add_parser("probe-seam", help="write runtime-scale seam comparison diagnostics")
    probe.add_argument("--source-root", type=Path, default=SOURCE_ROOT)
    probe.add_argument("--out", type=Path, default=Path("work/akari-hq-apng/line-investigation/seam-probe"))
    return parser


def main(argv=None) -> None:
    args = _build_parser().parse_args(argv)
    if args.command == "run":
        summary = run_pipeline(
            run_dir=args.run_dir,
            source_root=args.source_root,
            clawd_root=args.clawd_root,
            outputs_dir=args.outputs_dir,
            visual_approval_path=args.visual_approval,
            package_path=args.package_path,
            promote=args.promote,
        )
        print(f"wrote run summary to {summary}")
    elif args.command == "probe-seam":
        report = write_seam_probe(source_root=args.source_root, output_dir=args.out)
        print(f"wrote seam probe report to {report}")


if __name__ == "__main__":
    main()
