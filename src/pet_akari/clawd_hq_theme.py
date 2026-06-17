#!/usr/bin/env python3
"""Build deterministic Clawd Akari HQ APNG theme assets."""

import argparse
import hashlib
import json
import math
import os
import zipfile
from collections.abc import Mapping
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

MASTER_SIZE = (2048, 2560)
REFERENCE_RUNTIME_SIZE = (1536, 1920)
RUNTIME_SIZE = (384, 480)
DEFAULT_DURATION_MS = 125
DEFAULT_INBETWEENS = 9
CORE_STATES = ("idle", "thinking", "working", "notification", "attention", "error", "sleeping")


def _resample_filter():
    return getattr(getattr(Image, "Resampling", Image), "LANCZOS")


def _scale_runtime_box(box):
    x_scale = RUNTIME_SIZE[0] / REFERENCE_RUNTIME_SIZE[0]
    y_scale = RUNTIME_SIZE[1] / REFERENCE_RUNTIME_SIZE[1]
    return {
        "x": round(box["x"] * x_scale),
        "y": round(box["y"] * y_scale),
        "w": round(box["w"] * x_scale),
        "h": round(box["h"] * y_scale),
    }


def build_theme_json():
    states = {state: [f"akari-{state}.apng"] for state in CORE_STATES}
    for state in ("juggling", "sweeping", "carrying"):
        states[state] = ["akari-working.apng"]

    return {
        "schemaVersion": 1,
        "name": "Akari HQ APNG",
        "author": "Takahiro and Akari",
        "description": "Transparent APNG Clawd theme for Short Coral Akari.",
        "version": "1.0.0",
        "viewBox": {"x": 0, "y": 0, "width": RUNTIME_SIZE[0], "height": RUNTIME_SIZE[1]},
        "layout": {
            "contentBox": {"x": 0, "y": 0, "width": RUNTIME_SIZE[0], "height": RUNTIME_SIZE[1]},
            "centerX": RUNTIME_SIZE[0] / 2,
            "baselineY": RUNTIME_SIZE[1] * 0.94,
            "visibleHeightRatio": 0.7,
            "baselineBottomRatio": 0.04,
        },
        "eyeTracking": {"enabled": False, "states": []},
        "sleepSequence": {"mode": "direct"},
        "miniMode": {"supported": False},
        "hitBoxes": {
            "default": _scale_runtime_box({"x": 120, "y": 80, "w": 1296, "h": 1760}),
            "sleeping": _scale_runtime_box({"x": 120, "y": 520, "w": 1296, "h": 900}),
        },
        "workingTiers": [{"minSessions": 1, "file": "akari-working.apng"}],
        "jugglingTiers": [{"minSessions": 1, "file": "akari-working.apng"}],
        "objectScale": {"widthRatio": 1.0, "heightRatio": 1.0, "offsetX": 0, "offsetY": 0},
        "states": states,
    }


def ensure_dir(path):
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def sha256_file(path):
    hasher = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def apng_metadata(path):
    with Image.open(path) as image:
        durations = []
        for index in range(image.n_frames):
            image.seek(index)
            durations.append(float(image.info.get("duration", 0) or 0))
        return {
            "size": [image.size[0], image.size[1]],
            "frames": image.n_frames,
            "durationsMs": durations,
            "totalDurationMs": sum(durations),
        }


def list_master_frames(masters_dir, state, require_state_dir=True):
    masters_dir = Path(masters_dir)
    state_dir = masters_dir / state
    if state_dir.is_dir():
        search_dir = state_dir
    elif require_state_dir:
        raise FileNotFoundError(f"missing master frame directory for {state}: {state_dir}")
    else:
        search_dir = masters_dir
    frames = sorted(search_dir.glob("*.png"))
    if not frames:
        raise FileNotFoundError(f"no PNG master frames found for {state} in {search_dir}")
    return frames


def frame_feet_center_x(image, band_height=40):
    rgba = image.convert("RGBA")
    alpha = rgba.getchannel("A")
    bbox = alpha.getbbox()
    if bbox is None:
        raise ValueError("frame has no visible pixels")

    _, _, _, bottom = bbox
    top = max(0, bottom - band_height)
    band = alpha.crop((0, top, rgba.width, bottom))
    pixels = band.load()
    total = 0
    weighted = 0
    for y in range(band.height):
        for x in range(band.width):
            value = pixels[x, y]
            if value:
                total += value
                weighted += x * value
    if total == 0:
        raise ValueError("frame has no visible feet band pixels")
    return weighted / total


def _clamped_shift_x(image, dx):
    rgba = image.convert("RGBA")
    bbox = rgba.getchannel("A").getbbox()
    if bbox is None:
        return rgba, 0

    left, _, right, _ = bbox
    dx = int(round(dx))
    dx = max(dx, -left)
    dx = min(dx, rgba.width - right)
    if dx == 0:
        return rgba, 0

    shifted = Image.new("RGBA", rgba.size, (0, 0, 0, 0))
    shifted.alpha_composite(rgba, (dx, 0))
    return shifted, dx


def stabilize_state_masters(frame_paths, output_dir):
    frame_paths = [Path(path) for path in frame_paths]
    if not frame_paths:
        raise ValueError("at least one frame is required")

    output_dir = ensure_dir(output_dir)
    frames = []
    centers = []
    for path in frame_paths:
        with Image.open(path) as source:
            frame = source.convert("RGBA")
        if frame.size != MASTER_SIZE:
            raise ValueError(f"{path} has size {frame.size}, expected {MASTER_SIZE}")
        if frame.getchannel("A").getbbox() is None:
            raise ValueError(f"{path} has no visible pixels")
        frames.append(frame)
        centers.append(frame_feet_center_x(frame))

    target = sorted(centers)[len(centers) // 2]
    outputs = []
    for index, (source_path, frame, center) in enumerate(zip(frame_paths, frames, centers), start=1):
        stabilized, _ = _clamped_shift_x(frame, target - center)
        output = output_dir / f"{index:02d}.png"
        stabilized.save(output)
        outputs.append(output)
    return outputs


def stabilize_masters(masters_dir, output_dir, states=CORE_STATES):
    masters_dir = Path(masters_dir)
    output_dir = ensure_dir(output_dir)
    outputs = []
    for state in states:
        frames = list_master_frames(masters_dir, state)
        outputs.extend(stabilize_state_masters(frames, output_dir / state))
    return outputs


def remove_chroma_key(image, key=(0, 255, 0), tolerance=28):
    rgba = image.convert("RGBA")
    red, green, blue, alpha = rgba.split()
    masks = []
    for channel, value in ((red, key[0]), (green, key[1]), (blue, key[2])):
        table = [255 if abs(pixel - value) <= tolerance else 0 for pixel in range(256)]
        masks.append(channel.point(table))
    key_mask = ImageChops.multiply(ImageChops.multiply(masks[0], masks[1]), masks[2])

    green_high = green.point(lambda pixel: 255 if pixel >= 170 else 0)
    red_low = red.point(lambda pixel: 255 if pixel <= 80 else 0)
    blue_low = blue.point(lambda pixel: 255 if pixel <= 90 else 0)
    green_over_red = ImageChops.subtract(green, red).point(lambda pixel: 255 if pixel >= 90 else 0)
    green_over_blue = ImageChops.subtract(green, blue).point(lambda pixel: 255 if pixel >= 90 else 0)
    visible = alpha.point(lambda pixel: 255 if pixel > 0 else 0)
    green_dominant_mask = ImageChops.multiply(
        ImageChops.multiply(ImageChops.multiply(green_high, red_low), blue_low),
        ImageChops.multiply(ImageChops.multiply(green_over_red, green_over_blue), visible),
    )

    removal_mask = ImageChops.lighter(key_mask, green_dominant_mask)
    cleaned = rgba.copy()
    cleaned.paste((0, 0, 0, 0), mask=removal_mask)
    return cleaned


def normalize_to_master(image):
    cleaned = remove_chroma_key(image)
    bbox = cleaned.getchannel("A").getbbox()
    canvas = Image.new("RGBA", MASTER_SIZE, (0, 0, 0, 0))
    if bbox is None:
        return canvas

    cropped = cleaned.crop(bbox)
    max_width = int(MASTER_SIZE[0] * 0.88)
    max_height = int(MASTER_SIZE[1] * 0.9)
    scale = min(max_width / cropped.width, max_height / cropped.height)
    size = (max(1, round(cropped.width * scale)), max(1, round(cropped.height * scale)))
    sprite = cropped.resize(size, _resample_filter())
    left = (MASTER_SIZE[0] - sprite.width) // 2
    top = max(0, int(MASTER_SIZE[1] * 0.94) - sprite.height)
    canvas.alpha_composite(sprite, (left, top))
    return canvas


def _visible_x_runs(alpha, min_column_pixels, max_gap):
    width, height = alpha.size
    data = alpha.tobytes()
    runs = []
    start = None
    for x in range(width):
        count = 0
        for y in range(height):
            if data[y * width + x]:
                count += 1
        if count >= min_column_pixels:
            if start is None:
                start = x
        elif start is not None:
            runs.append((start, x))
            start = None
    if start is not None:
        runs.append((start, width))

    merged = []
    for left, right in runs:
        if merged and left - merged[-1][1] <= max_gap:
            merged[-1] = (merged[-1][0], right)
        else:
            merged.append((left, right))
    return merged


def _alpha_column_has_pixels(alpha_data, width, height, x):
    for y in range(height):
        if alpha_data[y * width + x]:
            return True
    return False


def _expand_run_to_sparse_edges(alpha, left, right):
    width, height = alpha.size
    data = alpha.tobytes()
    while left > 0 and _alpha_column_has_pixels(data, width, height, left - 1):
        left -= 1
    while right < width and _alpha_column_has_pixels(data, width, height, right):
        right += 1
    return left, right


def split_strip_by_components(strip, frames):
    cleaned = remove_chroma_key(strip)
    alpha = cleaned.getchannel("A")
    width, height = alpha.size
    min_column_pixels = max(2, round(height * 0.02))
    max_gap = max(2, round(width / (frames * 10)))
    min_width = max(2, round(width / (frames * 5)))
    min_height = max(2, round(height * 0.2))

    boxes = []
    for left, right in _visible_x_runs(alpha, min_column_pixels, max_gap):
        left, right = _expand_run_to_sparse_edges(alpha, left, right)
        bbox = alpha.crop((left, 0, right, height)).getbbox()
        if bbox is None:
            continue
        top, bottom = bbox[1], bbox[3]
        box = (left + bbox[0], top, left + bbox[2], bottom)
        if box[2] - box[0] < min_width or box[3] - box[1] < min_height:
            continue
        boxes.append(box)

    if len(boxes) != frames:
        raise ValueError(f"component split found {len(boxes)} components, expected {frames}")

    return [cleaned.crop(box) for box in sorted(boxes)]


def split_strip_to_masters(strip_path, output_dir, frames, split_mode="grid"):
    if frames <= 0:
        raise ValueError("frames must be greater than zero")
    if split_mode not in {"grid", "components"}:
        raise ValueError("split_mode must be grid or components")

    output_dir = ensure_dir(output_dir)
    with Image.open(strip_path) as strip:
        strip = strip.convert("RGBA")
        outputs = []
        if split_mode == "components":
            crops = split_strip_by_components(strip, frames)
        else:
            crops = []
            for index in range(frames):
                left = round(index * strip.width / frames)
                right = round((index + 1) * strip.width / frames)
                if right <= left:
                    raise ValueError(f"frame {index + 1} has zero width in strip {strip.width}x{strip.height}")
                crops.append(strip.crop((left, 0, right, strip.height)))

        for index, crop in enumerate(crops):
            frame = normalize_to_master(crop)
            output = output_dir / f"{index + 1:02d}.png"
            frame.save(output)
            outputs.append(output)
    return outputs


def _synthetic_colors(state):
    colors = {
        "idle": ((255, 139, 84, 255), (42, 50, 84, 255)),
        "thinking": ((255, 174, 120, 255), (48, 70, 112, 255)),
        "working": ((255, 128, 96, 255), (35, 58, 104, 255)),
        "notification": ((255, 191, 94, 255), (74, 72, 122, 255)),
        "attention": ((255, 151, 118, 255), (36, 94, 116, 255)),
        "error": ((255, 104, 112, 255), (96, 42, 70, 255)),
        "sleeping": ((238, 147, 120, 255), (36, 44, 78, 255)),
    }
    return colors[state]


def _draw_synthetic_frame(state, index, frame_count):
    image = Image.new("RGBA", MASTER_SIZE, (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    x_scale = MASTER_SIZE[0] / 2048
    y_scale = MASTER_SIZE[1] / 2560
    line_scale = min(x_scale, y_scale)

    def x(value):
        return round(value * x_scale)

    def y(value):
        return round(value * y_scale)

    def xy_box(left, top, right, bottom):
        return (x(left), y(top), x(right), y(bottom))

    def xy_points(points):
        return [(x(px), y(py)) for px, py in points]

    def width(value):
        return max(1, round(value * line_scale))

    def radius(value):
        return max(1, round(value * line_scale))

    phase = (index / max(1, frame_count)) * math.tau
    bob = round(math.sin(phase) * 28 * y_scale)
    wave = round(math.cos(phase) * 18 * x_scale)
    skin, navy = _synthetic_colors(state)
    line = (28, 25, 34, 255)
    blush = (255, 194, 164, 255)

    body_box = xy_box(610, 1030, 1438, 2220)
    head_box = xy_box(560, 360, 1488, 1250)
    cap_box = xy_box(560, 275, 1488, 665)

    def shift_box(box):
        left, top, right, bottom = box
        return (left + wave, top + bob, right + wave, bottom + bob)

    def shift_points(points):
        return [(px + wave, py + bob) for px, py in points]

    draw.rounded_rectangle(shift_box(body_box), radius=radius(220), fill=skin, outline=line, width=width(24))
    draw.ellipse(shift_box(head_box), fill=(255, 207, 181, 255), outline=line, width=width(24))
    draw.pieslice(shift_box(cap_box), 180, 360, fill=navy, outline=line, width=width(24))
    draw.rectangle(shift_box(xy_box(760, 500, 1338, 640)), fill=navy)

    if state == "sleeping":
        draw.arc(shift_box(xy_box(800, 730, 950, 820)), 10, 170, fill=line, width=width(18))
        draw.arc(shift_box(xy_box(1100, 730, 1250, 820)), 10, 170, fill=line, width=width(18))
        draw.text((x(1320) + wave, y(435) + bob), "Z", fill=navy)
    elif state == "error":
        draw.line(shift_points(xy_points([(820, 760), (930, 850)])), fill=line, width=width(20))
        draw.line(shift_points(xy_points([(930, 760), (820, 850)])), fill=line, width=width(20))
        draw.line(shift_points(xy_points([(1120, 760), (1230, 850)])), fill=line, width=width(20))
        draw.line(shift_points(xy_points([(1230, 760), (1120, 850)])), fill=line, width=width(20))
    else:
        eye_shift = x(18) if state in ("thinking", "attention") else 0
        left_eye = shift_box(xy_box(830, 760, 900, 830))
        right_eye = shift_box(xy_box(1140, 760, 1210, 830))
        draw.ellipse((left_eye[0] + eye_shift, left_eye[1], left_eye[2] + eye_shift, left_eye[3]), fill=line)
        draw.ellipse((right_eye[0] + eye_shift, right_eye[1], right_eye[2] + eye_shift, right_eye[3]), fill=line)

    draw.arc(shift_box(xy_box(900, 880, 1148, 1025)), 20, 160, fill=line, width=width(18))
    draw.ellipse(shift_box(xy_box(760, 900, 860, 980)), fill=blush)
    draw.ellipse(shift_box(xy_box(1188, 900, 1288, 980)), fill=blush)

    if state in ("working", "juggling"):
        draw.rounded_rectangle(
            shift_box(xy_box(770, 1510, 1278, 1825)),
            radius=radius(42),
            fill=(248, 248, 244, 255),
            outline=line,
            width=width(16),
        )
        draw.line(shift_points(xy_points([(835, 1590), (1210, 1590)])), fill=navy, width=width(14))
        draw.line(shift_points(xy_points([(835, 1680), (1140, 1680)])), fill=navy, width=width(14))
    elif state == "notification":
        draw.ellipse(shift_box(xy_box(1320, 780, 1470, 930)), fill=(255, 226, 82, 255), outline=line, width=width(16))
    elif state == "attention":
        draw.polygon(
            shift_points(xy_points([(1024, 1280), (1120, 1510), (930, 1510)])),
            fill=(255, 226, 82, 255),
            outline=line,
        )
    elif state == "thinking":
        draw.ellipse(shift_box(xy_box(1310, 520, 1450, 660)), fill=(255, 255, 255, 255), outline=line, width=width(14))
        draw.ellipse(shift_box(xy_box(1460, 410, 1530, 480)), fill=(255, 255, 255, 255), outline=line, width=width(10))

    return image


def write_synthetic_masters(masters_dir, frame_count=4):
    if frame_count <= 0:
        raise ValueError("frame_count must be greater than zero")
    masters_dir = ensure_dir(masters_dir)
    outputs = []
    for state in CORE_STATES:
        state_dir = ensure_dir(masters_dir / state)
        for index in range(frame_count):
            frame = _draw_synthetic_frame(state, index, frame_count)
            output = state_dir / f"{index + 1:02d}.png"
            frame.save(output)
            outputs.append(output)
    return outputs


def interpolate_rgba(first, second, t):
    if first.size != second.size:
        raise ValueError("interpolated frames must have the same size")
    if not 0 < t < 1:
        raise ValueError("interpolation t must be between 0 and 1")

    return Image.blend(first.convert("RGBA"), second.convert("RGBA"), t)


def expand_loop_frames(frames, inbetweens=0):
    if inbetweens < 0:
        raise ValueError("inbetweens must be zero or greater")
    if not frames:
        raise ValueError("at least one frame is required")
    if inbetweens == 0 or len(frames) == 1:
        return list(frames)

    expanded = []
    for index, frame in enumerate(frames):
        next_frame = frames[(index + 1) % len(frames)]
        expanded.append(frame)
        for step in range(1, inbetweens + 1):
            expanded.append(interpolate_rgba(frame, next_frame, step / (inbetweens + 1)))
    return expanded


def encode_apng(frame_paths, output_path, size, duration_ms=DEFAULT_DURATION_MS, inbetweens=DEFAULT_INBETWEENS):
    frame_paths = [Path(path) for path in frame_paths]
    if not frame_paths:
        raise ValueError("at least one frame is required")
    if duration_ms <= 0:
        raise ValueError("duration_ms must be greater than zero")

    output_path = Path(output_path)
    ensure_dir(output_path.parent)
    frames = []
    for path in frame_paths:
        with Image.open(path) as source:
            frame = source.convert("RGBA")
        if frame.size != size:
            frame = frame.resize(size, _resample_filter())
        frames.append(frame)

    frames = expand_loop_frames(frames, inbetweens)
    first, rest = frames[0], frames[1:]
    first.save(
        output_path,
        format="PNG",
        save_all=True,
        append_images=rest,
        duration=[duration_ms] * len(frames),
        loop=0,
    )
    return output_path


def _manifest_keyframe_indices(source_frame_count, inbetweens):
    if source_frame_count <= 0:
        raise ValueError("source_frame_count must be greater than zero")
    if inbetweens < 0:
        raise ValueError("inbetweens must be zero or greater")
    return [index * (inbetweens + 1) for index in range(source_frame_count)]


def default_motion_contract():
    return {
        "states": {
            state: {
                "durationMs": DEFAULT_DURATION_MS,
                "inbetweens": DEFAULT_INBETWEENS,
            }
            for state in CORE_STATES
        }
    }


def load_motion_contract(path):
    if path is None:
        return None
    path = Path(path)
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_motion_contract(
    motion_contract=None,
    duration_ms=DEFAULT_DURATION_MS,
    inbetweens=DEFAULT_INBETWEENS,
):
    if motion_contract is None:
        motion_contract = {
            "states": {state: {"durationMs": duration_ms, "inbetweens": inbetweens} for state in CORE_STATES}
        }
    elif isinstance(motion_contract, (str, Path)):
        motion_contract = load_motion_contract(motion_contract)

    if not isinstance(motion_contract, Mapping):
        raise ValueError("motion contract must be a JSON object")

    states = motion_contract.get("states")
    if not isinstance(states, Mapping):
        raise ValueError("motion contract states must be a JSON object")

    normalized = {"states": {}}
    for state in CORE_STATES:
        settings = states.get(state)
        if settings is None:
            raise ValueError(f"motion contract missing state {state}")
        if not isinstance(settings, Mapping):
            raise ValueError(f"motion contract {state} settings must be a JSON object")
        if "durationMs" not in settings:
            raise ValueError(f"motion contract {state} missing durationMs")
        if "inbetweens" not in settings:
            raise ValueError(f"motion contract {state} missing inbetweens")
        state_duration = settings["durationMs"]
        state_inbetweens = settings["inbetweens"]
        if type(state_duration) is not int:
            raise ValueError(f"motion contract {state} durationMs must be an integer")
        if type(state_inbetweens) is not int:
            raise ValueError(f"motion contract {state} inbetweens must be an integer")
        if state_duration <= 0:
            raise ValueError(f"motion contract {state} durationMs must be greater than zero")
        if state_inbetweens < 0:
            raise ValueError(f"motion contract {state} inbetweens must be zero or greater")
        normalized["states"][state] = {
            "durationMs": state_duration,
            "inbetweens": state_inbetweens,
        }
    return normalized


def motion_settings_for_state(motion_contract, state):
    settings = motion_contract["states"][state]
    return settings["durationMs"], settings["inbetweens"]


def assert_no_exporter_inbetweens(motion_contract):
    normalized = normalize_motion_contract(motion_contract)
    offenders = [state for state in CORE_STATES if normalized["states"][state]["inbetweens"] != 0]
    if offenders:
        raise ValueError(f"production motion contract uses exporter inbetweens: {', '.join(offenders)}")
    return True


def _manifest_relative_path(path, base_dir):
    return Path(os.path.relpath(Path(path).resolve(), Path(base_dir).resolve())).as_posix()


def build_export_manifest(masters_dir, theme_dir, state_frames, state_outputs, motion_contract):
    masters_dir = Path(masters_dir)
    theme_dir = Path(theme_dir)
    manifest = {
        "manifestVersion": 1,
        "exporter": {
            "tool": "python -m pet_akari.clawd_hq_theme",
            "runtimeSize": [RUNTIME_SIZE[0], RUNTIME_SIZE[1]],
            "sourceMasterRoot": str(masters_dir.resolve()),
        },
        "states": {},
    }

    for state in CORE_STATES:
        duration_ms, inbetweens = motion_settings_for_state(motion_contract, state)
        frames = [Path(path) for path in state_frames[state]]
        runtime_asset = Path(state_outputs[state])
        metadata = apng_metadata(runtime_asset)
        manifest["states"][state] = {
            "sourceMasterDir": _manifest_relative_path(masters_dir / state, theme_dir),
            "sourceMasterFiles": [
                {
                    "path": _manifest_relative_path(path, theme_dir),
                    "sha256": sha256_file(path),
                }
                for path in frames
            ],
            "trueSourceFrames": len(frames),
            "encodedFrames": metadata["frames"],
            "durationMs": duration_ms,
            "inbetweens": inbetweens,
            "keyframeIndices": _manifest_keyframe_indices(len(frames), inbetweens),
            "runtimeAsset": str(runtime_asset.relative_to(theme_dir)),
            "runtimeSha256": sha256_file(runtime_asset),
            "runtimeSize": metadata["size"],
            "durationsMs": metadata["durationsMs"],
            "totalDurationMs": metadata["totalDurationMs"],
        }

    output = ensure_dir(theme_dir / "qa") / "build-manifest.json"
    output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output


def _resolve_manifest_file(path, theme_dir, source_root=None, state=None):
    path = Path(path)
    if path.is_absolute():
        return path
    theme_relative = Path(theme_dir) / path
    if theme_relative.is_file():
        return theme_relative
    if path.is_file():
        return path
    if source_root is not None:
        source_root = Path(source_root)
        if state is not None:
            state_relative = source_root / state / path.name
            if state_relative.is_file():
                return state_relative
        root_relative = source_root / path.name
        if root_relative.is_file():
            return root_relative
    return path


def lineage_frames_match(first, second, invisible_alpha=3):
    first = first.convert("RGBA")
    second = second.convert("RGBA")
    if first.size != second.size:
        return False

    first_pixels = first.tobytes()
    second_pixels = second.tobytes()
    for index in range(0, len(first_pixels), 4):
        first_pixel = first_pixels[index : index + 4]
        second_pixel = second_pixels[index : index + 4]
        if first_pixel == second_pixel:
            continue
        if first_pixel[3] <= invisible_alpha and second_pixel[3] <= invisible_alpha:
            continue
        return False
    return True


def validate_lineage(theme_dir, manifest_path=None):
    theme_dir = Path(theme_dir)
    manifest_path = Path(manifest_path) if manifest_path else theme_dir / "qa" / "build-manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(manifest_path)

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("manifestVersion") != 1:
        raise ValueError("build manifest version mismatch")

    exporter = manifest.get("exporter", {})
    runtime_size = tuple(exporter.get("runtimeSize", RUNTIME_SIZE))
    if len(runtime_size) != 2:
        raise ValueError("build manifest runtimeSize mismatch")
    expected_duration = exporter.get("durationMs")
    expected_inbetweens = exporter.get("inbetweens")
    source_root = exporter.get("sourceMasterRoot")

    for state in CORE_STATES:
        state_manifest = manifest.get("states", {}).get(state)
        if not state_manifest:
            raise ValueError(f"build manifest missing state {state}")

        source_files = state_manifest.get("sourceMasterFiles", [])
        if len(source_files) != state_manifest.get("trueSourceFrames"):
            raise ValueError(f"{state} source frame count mismatch")

        for source in source_files:
            source_path = _resolve_manifest_file(source["path"], theme_dir, source_root=source_root, state=state)
            if not source_path.is_file():
                raise FileNotFoundError(source_path)
            actual_source_sha = sha256_file(source_path)
            if actual_source_sha != source["sha256"]:
                raise ValueError(f"{state} source master sha256 mismatch: {source_path}")

        runtime_path = theme_dir / state_manifest["runtimeAsset"]
        if not runtime_path.is_file():
            raise FileNotFoundError(runtime_path)
        actual_runtime_sha = sha256_file(runtime_path)
        if actual_runtime_sha != state_manifest["runtimeSha256"]:
            raise ValueError(f"{state} runtime asset sha256 mismatch: {runtime_path}")

        metadata = apng_metadata(runtime_path)
        if metadata["size"] != [runtime_size[0], runtime_size[1]]:
            raise ValueError(f"{state} runtime size mismatch")
        if metadata["frames"] != state_manifest["encodedFrames"]:
            raise ValueError(f"{state} runtime frame count mismatch")
        if abs(metadata["totalDurationMs"] - state_manifest["totalDurationMs"]) > 0.001:
            raise ValueError(f"{state} runtime total duration mismatch")
        state_duration = state_manifest.get("durationMs", expected_duration)
        state_inbetweens = state_manifest.get("inbetweens", expected_inbetweens)
        if state_duration is not None and any(
            duration != float(state_duration) for duration in metadata["durationsMs"]
        ):
            raise ValueError(f"{state} runtime frame duration mismatch")
        if state_inbetweens is not None:
            expected_keyframes = _manifest_keyframe_indices(len(source_files), int(state_inbetweens))
            if state_manifest["keyframeIndices"] != expected_keyframes:
                raise ValueError(f"{state} keyframe indices mismatch")

        with Image.open(runtime_path) as runtime:
            for source, keyframe_index in zip(source_files, state_manifest["keyframeIndices"]):
                if keyframe_index >= runtime.n_frames:
                    raise ValueError(f"{state} keyframe {keyframe_index} is outside runtime frame range")
                source_path = _resolve_manifest_file(source["path"], theme_dir, source_root=source_root, state=state)
                with Image.open(source_path) as source_image:
                    expected_frame = source_image.convert("RGBA")
                    if expected_frame.size != runtime_size:
                        expected_frame = expected_frame.resize(runtime_size, _resample_filter())
                runtime.seek(keyframe_index)
                runtime_frame = runtime.convert("RGBA")
                if not lineage_frames_match(runtime_frame, expected_frame):
                    raise ValueError(f"{state} keyframe {keyframe_index} does not match source master")
    return True


def write_theme_json(theme_dir):
    theme_dir = ensure_dir(theme_dir)
    output = theme_dir / "theme.json"
    output.write_text(json.dumps(build_theme_json(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output


def export_theme(
    masters_dir,
    theme_dir,
    include_ultra=False,
    duration_ms=DEFAULT_DURATION_MS,
    inbetweens=DEFAULT_INBETWEENS,
    motion_contract=None,
):
    masters_dir = Path(masters_dir)
    theme_dir = ensure_dir(theme_dir)
    assets_dir = ensure_dir(theme_dir / "assets")
    motion_contract = normalize_motion_contract(motion_contract, duration_ms, inbetweens)
    write_theme_json(theme_dir)

    outputs = []
    state_frames = {}
    state_outputs = {}
    for state in CORE_STATES:
        state_duration_ms, state_inbetweens = motion_settings_for_state(motion_contract, state)
        frames = list_master_frames(masters_dir, state)
        state_frames[state] = frames
        output = encode_apng(
            frames,
            assets_dir / f"akari-{state}.apng",
            RUNTIME_SIZE,
            duration_ms=state_duration_ms,
            inbetweens=state_inbetweens,
        )
        state_outputs[state] = output
        outputs.append(output)

    build_export_manifest(masters_dir, theme_dir, state_frames, state_outputs, motion_contract)

    if include_ultra:
        ultra_dir = ensure_dir(theme_dir / "assets-ultra")
        for state in CORE_STATES:
            state_duration_ms, state_inbetweens = motion_settings_for_state(motion_contract, state)
            frames = list_master_frames(masters_dir, state)
            output = encode_apng(
                frames,
                ultra_dir / f"akari-{state}.apng",
                MASTER_SIZE,
                duration_ms=state_duration_ms,
                inbetweens=state_inbetweens,
            )
            outputs.append(output)
    return outputs


def validate_apng(
    path,
    size,
    expected_frames=None,
    expected_total_duration_ms=None,
    expected_duration_ms=None,
):
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(path)

    with Image.open(path) as image:
        if image.size != size:
            raise ValueError(f"{path} has size {image.size}, expected {size}")
        if not getattr(image, "is_animated", False):
            raise ValueError(f"{path} is not animated")
        if getattr(image, "n_frames", 1) < 2:
            raise ValueError(f"{path} must contain at least two frames")
        if expected_frames is not None and image.n_frames != expected_frames:
            raise ValueError(f"{path} has frame count {image.n_frames}, expected {expected_frames}")

        corners = ((0, 0), (size[0] - 1, 0), (0, size[1] - 1), (size[0] - 1, size[1] - 1))
        durations = []
        for index in range(image.n_frames):
            image.seek(index)
            duration = float(image.info.get("duration", 0) or 0)
            durations.append(duration)
            if expected_duration_ms is not None and abs(duration - float(expected_duration_ms)) > 0.001:
                raise ValueError(
                    f"{path} frame duration mismatch at frame {index}: {duration}ms, expected {expected_duration_ms}ms"
                )
            frame = image.convert("RGBA")
            if frame.size != size:
                raise ValueError(f"{path} frame {index} has size {frame.size}, expected {size}")
            alpha = frame.getchannel("A")
            if alpha.getbbox() is None:
                raise ValueError(f"{path} frame {index} has no visible pixels")
            visible_pixels = sum(alpha.histogram()[1:])
            min_visible_pixels = max(1, int(size[0] * size[1] * 0.000001))
            if visible_pixels < min_visible_pixels:
                raise ValueError(
                    f"{path} frame {index} has {visible_pixels} visible pixels, expected at least {min_visible_pixels}"
                )
            for corner in corners:
                if frame.getpixel(corner)[3] != 0:
                    raise ValueError(f"{path} frame {index} corner {corner} is not transparent")
        if expected_total_duration_ms is not None:
            total_duration_ms = sum(durations)
            if abs(total_duration_ms - expected_total_duration_ms) > 0.001:
                raise ValueError(
                    f"{path} has total duration {total_duration_ms}ms, expected {expected_total_duration_ms}ms"
                )
    return True


def source_frame_count_from_manifest(theme_dir, state):
    manifest_path = Path(theme_dir) / "qa" / "build-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return int(manifest["states"][state]["trueSourceFrames"])


def validate_theme_assets(
    theme_dir,
    require_ultra=False,
    expected_frames=None,
    expected_total_duration_ms=None,
    motion_contract=None,
):
    theme_dir = Path(theme_dir)
    theme_path = theme_dir / "theme.json"
    if not theme_path.is_file():
        raise FileNotFoundError(theme_path)

    theme = json.loads(theme_path.read_text(encoding="utf-8"))
    expected = build_theme_json()
    contract_keys = (
        "schemaVersion",
        "name",
        "author",
        "description",
        "version",
        "viewBox",
        "eyeTracking",
        "sleepSequence",
        "miniMode",
        "layout",
        "hitBoxes",
        "workingTiers",
        "jugglingTiers",
        "objectScale",
        "states",
    )
    for key in contract_keys:
        if theme.get(key) != expected[key]:
            raise ValueError(f"theme.json {key} mismatch")

    motion_contract = normalize_motion_contract(motion_contract) if motion_contract is not None else None
    for state in CORE_STATES:
        asset = f"akari-{state}.apng"
        state_expected_frames = expected_frames
        state_expected_total = expected_total_duration_ms
        if motion_contract:
            state_duration_ms, state_inbetweens = motion_settings_for_state(motion_contract, state)
            true_source_frames = source_frame_count_from_manifest(theme_dir, state)
            state_expected_frames = true_source_frames * (state_inbetweens + 1)
            state_expected_total = state_expected_frames * state_duration_ms
        validate_apng(
            theme_dir / "assets" / asset,
            RUNTIME_SIZE,
            expected_frames=state_expected_frames,
            expected_total_duration_ms=state_expected_total,
            expected_duration_ms=state_duration_ms if motion_contract else None,
        )
        if require_ultra:
            validate_apng(
                theme_dir / "assets-ultra" / asset,
                MASTER_SIZE,
                expected_frames=state_expected_frames,
                expected_total_duration_ms=state_expected_total,
                expected_duration_ms=state_duration_ms if motion_contract else None,
            )
    return True


def write_contact_sheet(theme_dir, output_path):
    theme_dir = Path(theme_dir)
    output_path = Path(output_path)
    ensure_dir(output_path.parent)
    thumb_size = (192, 240)
    label_height = 28
    columns = 4
    rows = math.ceil(len(CORE_STATES) / columns)
    sheet = Image.new("RGBA", (columns * thumb_size[0], rows * (thumb_size[1] + label_height)), (250, 250, 250, 255))
    draw = ImageDraw.Draw(sheet)

    for index, state in enumerate(CORE_STATES):
        path = theme_dir / "assets" / f"akari-{state}.apng"
        with Image.open(path) as image:
            image.seek(0)
            frame = image.convert("RGBA")
        frame.thumbnail(thumb_size, _resample_filter())
        column = index % columns
        row = index // columns
        left = column * thumb_size[0] + (thumb_size[0] - frame.width) // 2
        top = row * (thumb_size[1] + label_height) + (thumb_size[1] - frame.height) // 2
        sheet.alpha_composite(frame, (left, top))
        draw.text(
            (column * thumb_size[0] + 8, row * (thumb_size[1] + label_height) + thumb_size[1] + 6),
            state,
            fill=(20, 20, 24, 255),
        )

    sheet.convert("RGB").save(output_path)
    return output_path


def package_theme(theme_dir, output_zip):
    theme_dir = Path(theme_dir)
    output_zip = Path(output_zip)
    ensure_dir(output_zip.parent)
    output_resolved = output_zip.resolve()
    with zipfile.ZipFile(output_zip, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(theme_dir.rglob("*")):
            if not path.is_file() or path.resolve() == output_resolved:
                continue
            archive.write(path, Path("akari-hq-apng") / path.relative_to(theme_dir))
    return output_zip


def _build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    synthetic = subparsers.add_parser("synthetic-masters", help="write deterministic synthetic master frames")
    synthetic.add_argument("masters_dir", type=Path, nargs="?")
    synthetic.add_argument("--out", type=Path, dest="out_dir")
    synthetic.add_argument("--frame-count", "--frames", type=int, default=4, dest="frame_count")

    split = subparsers.add_parser("split-strip", help="split a flat chroma-key strip into master frames")
    split.add_argument("strip_path", type=Path, nargs="?")
    split.add_argument("output_dir", type=Path, nargs="?")
    split.add_argument("--strip", type=Path, dest="strip_path_flag")
    split.add_argument("--out", type=Path, dest="out_dir")
    split.add_argument("--frames", type=int, required=True)
    split.add_argument("--split-mode", choices=("grid", "components"), default="grid")

    stabilize = subparsers.add_parser("stabilize-masters", help="write horizontally stabilized master frames")
    stabilize.add_argument("masters_dir", type=Path, nargs="?")
    stabilize.add_argument("output_dir", type=Path, nargs="?")
    stabilize.add_argument("--masters", type=Path, dest="masters_dir_flag")
    stabilize.add_argument("--out", type=Path, dest="out_dir")

    export = subparsers.add_parser("export-theme", help="export runtime and optional ultra APNG theme assets")
    export.add_argument("masters_dir", type=Path, nargs="?")
    export.add_argument("theme_dir", type=Path, nargs="?")
    export.add_argument("--masters", type=Path, dest="masters_dir_flag")
    export.add_argument("--theme-dir", type=Path, dest="theme_dir_flag")
    export.add_argument("--include-ultra", action="store_true")
    export.add_argument("--duration-ms", type=int, default=DEFAULT_DURATION_MS)
    export.add_argument("--inbetweens", type=int, default=DEFAULT_INBETWEENS)
    export.add_argument("--motion-contract", type=Path)

    validate = subparsers.add_parser("validate-assets", help="validate theme.json and APNG assets")
    validate.add_argument("theme_dir", type=Path, nargs="?")
    validate.add_argument("--theme-dir", type=Path, dest="theme_dir_flag")
    validate.add_argument("--require-ultra", action="store_true")
    validate.add_argument("--expected-frames", type=int)
    validate.add_argument("--expected-total-ms", type=float, dest="expected_total_duration_ms")
    validate.add_argument("--motion-contract", type=Path)

    lineage = subparsers.add_parser("validate-lineage", help="validate source-to-runtime APNG lineage")
    lineage.add_argument("theme_dir", type=Path, nargs="?")
    lineage.add_argument("--theme-dir", type=Path, dest="theme_dir_flag")
    lineage.add_argument("--manifest", type=Path, dest="manifest_path")

    contact = subparsers.add_parser("contact-sheet", help="write a contact sheet of first runtime frames")
    contact.add_argument("theme_dir", type=Path, nargs="?")
    contact.add_argument("output_path", type=Path, nargs="?")
    contact.add_argument("--theme-dir", type=Path, dest="theme_dir_flag")
    contact.add_argument("--out", type=Path, dest="out_path")

    package = subparsers.add_parser("package", help="zip a theme directory under akari-hq-apng/")
    package.add_argument("theme_dir", type=Path, nargs="?")
    package.add_argument("output_zip", type=Path, nargs="?")
    package.add_argument("--theme-dir", type=Path, dest="theme_dir_flag")
    package.add_argument("--out", type=Path, dest="out_path")

    return parser


def _resolve_arg(parser, args, positional_name, flag_name, label):
    value = getattr(args, flag_name, None) or getattr(args, positional_name, None)
    if value is None:
        parser.error(f"{args.command} requires {label}")
    return value


def main(argv=None):
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "synthetic-masters":
        masters_dir = _resolve_arg(parser, args, "masters_dir", "out_dir", "a masters directory")
        outputs = write_synthetic_masters(masters_dir, args.frame_count)
        print(f"wrote {len(outputs)} synthetic master frames to {masters_dir}")
    elif args.command == "split-strip":
        strip_path = _resolve_arg(parser, args, "strip_path", "strip_path_flag", "a strip path")
        output_dir = _resolve_arg(parser, args, "output_dir", "out_dir", "an output directory")
        outputs = split_strip_to_masters(strip_path, output_dir, args.frames, split_mode=args.split_mode)
        print(f"wrote {len(outputs)} master frames to {output_dir}")
    elif args.command == "stabilize-masters":
        masters_dir = _resolve_arg(parser, args, "masters_dir", "masters_dir_flag", "a masters directory")
        output_dir = _resolve_arg(parser, args, "output_dir", "out_dir", "an output directory")
        outputs = stabilize_masters(masters_dir, output_dir)
        print(f"wrote {len(outputs)} stabilized master frames to {output_dir}")
    elif args.command == "export-theme":
        masters_dir = _resolve_arg(parser, args, "masters_dir", "masters_dir_flag", "a masters directory")
        theme_dir = _resolve_arg(parser, args, "theme_dir", "theme_dir_flag", "a theme directory")
        if args.duration_ms <= 0:
            parser.error("export-theme requires --duration-ms greater than zero")
        if args.inbetweens < 0:
            parser.error("export-theme requires --inbetweens zero or greater")
        outputs = export_theme(
            masters_dir,
            theme_dir,
            args.include_ultra,
            duration_ms=args.duration_ms,
            inbetweens=args.inbetweens,
            motion_contract=args.motion_contract,
        )
        print(f"wrote {len(outputs)} APNG assets to {theme_dir}")
    elif args.command == "validate-assets":
        theme_dir = _resolve_arg(parser, args, "theme_dir", "theme_dir_flag", "a theme directory")
        if args.expected_frames is not None and args.expected_frames <= 0:
            parser.error("validate-assets requires --expected-frames greater than zero")
        if args.expected_total_duration_ms is not None and args.expected_total_duration_ms <= 0:
            parser.error("validate-assets requires --expected-total-ms greater than zero")
        validate_theme_assets(
            theme_dir,
            args.require_ultra,
            expected_frames=args.expected_frames,
            expected_total_duration_ms=args.expected_total_duration_ms,
            motion_contract=args.motion_contract,
        )
        print(f"validated assets in {theme_dir}")
    elif args.command == "validate-lineage":
        theme_dir = _resolve_arg(parser, args, "theme_dir", "theme_dir_flag", "a theme directory")
        validate_lineage(theme_dir, manifest_path=args.manifest_path)
        print(f"validated lineage in {theme_dir}")
    elif args.command == "contact-sheet":
        theme_dir = _resolve_arg(parser, args, "theme_dir", "theme_dir_flag", "a theme directory")
        output_path = _resolve_arg(parser, args, "output_path", "out_path", "an output path")
        output = write_contact_sheet(theme_dir, output_path)
        print(f"wrote contact sheet to {output}")
    elif args.command == "package":
        theme_dir = _resolve_arg(parser, args, "theme_dir", "theme_dir_flag", "a theme directory")
        output_zip = _resolve_arg(parser, args, "output_zip", "out_path", "an output zip")
        output = package_theme(theme_dir, output_zip)
        print(f"wrote package to {output}")
    else:
        parser.error(f"unknown command {args.command}")


if __name__ == "__main__":
    main()
