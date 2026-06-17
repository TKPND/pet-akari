#!/usr/bin/env python3
"""Extract stable-slot frames from peeled strips using the ORIGINAL strips' geometry.

The hatch-pet stable-slots extractor detects poses via alpha connected
components. Peeling the white sticker outline fragments those components and
breaks slot assignment. This tool reuses the skill's own functions to compute
component groups and the shared viewport from the ORIGINAL (un-peeled) strip,
then samples pixels at those exact positions from the PEELED strip. Geometry
(scale, baseline, slot order) is therefore identical to the original
extraction; only the outline pixels disappear.
"""

import argparse
import importlib.util
from pathlib import Path

from PIL import Image

SKILL_SCRIPT = Path.home() / ".codex/skills/hatch-pet/scripts/extract_strip_frames.py"


def load_skill_module():
    spec = importlib.util.spec_from_file_location("esf", SKILL_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def extract_state(esf, orig_path, peeled_path, state, output_root, chroma_key, threshold):
    frame_count = esf.ROW_FRAME_COUNTS[state]
    with Image.open(orig_path) as opened:
        orig = esf.remove_chroma_background(opened, chroma_key, threshold)
    with Image.open(peeled_path) as opened:
        peeled = esf.remove_chroma_background(opened, chroma_key, threshold)
    if orig.size != peeled.size:
        raise SystemExit(f"{state}: size mismatch orig {orig.size} vs peeled {peeled.size}")

    state_dir = output_root / state
    state_dir.mkdir(parents=True, exist_ok=True)
    padding = 4
    groups = esf.component_frame_groups(orig, frame_count)
    if groups is None:
        # Mirror extract_stable_slot_frames' uniform-slot fallback, with the
        # shared viewport band computed from the ORIGINAL strip's bbox.
        bbox = orig.getbbox()
        if bbox is None:
            raise SystemExit(f"{state}: original strip is empty")
        shared_top = max(0, bbox[1] - padding)
        shared_bottom = min(orig.height, bbox[3] + padding)
        slot_width = orig.width / frame_count
        outputs = []
        for index in range(frame_count):
            left = round(index * slot_width)
            right = round((index + 1) * slot_width)
            crop = peeled.crop((left, shared_top, right, shared_bottom))
            frame = esf.fit_viewport_to_cell(crop)
            output = state_dir / f"{index:02d}.png"
            frame.save(output)
            outputs.append(output.name)
        return outputs

    # Mirror extract_stable_slot_frames, but sample pixels from the peeled strip.
    bboxes = [esf.component_bounds(group) for group in groups]
    shared_top = max(0, min(bbox[1] for bbox in bboxes) - padding)
    shared_bottom = min(orig.height, max(bbox[3] for bbox in bboxes) + padding)
    viewport_width = max(bbox[2] - bbox[0] for bbox in bboxes) + padding * 2
    viewport_height = max(1, shared_bottom - shared_top)

    outputs = []
    for index, (group, bbox) in enumerate(zip(groups, bboxes)):
        grouped = esf.component_group_image(peeled, group, padding=padding)
        grouped_top = max(0, bbox[1] - padding)
        viewport = Image.new("RGBA", (viewport_width, viewport_height), (0, 0, 0, 0))
        left = (viewport_width - grouped.width) // 2
        viewport.alpha_composite(grouped, (left, grouped_top - shared_top))
        frame = esf.fit_viewport_to_cell(viewport)
        output = state_dir / f"{index:02d}.png"
        frame.save(output)
        outputs.append(output.name)
    return outputs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--orig-dir", type=Path, required=True)
    ap.add_argument("--peeled-dir", type=Path, required=True)
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--states", default="all")
    ap.add_argument("--key-threshold", type=float, default=96.0)
    args = ap.parse_args()

    esf = load_skill_module()
    chroma_key = esf.load_chroma_key(args.orig_dir, None)
    states = esf.parse_states(args.states)
    for state in states:
        orig_path = args.orig_dir / f"{state}.png"
        peeled_path = args.peeled_dir / f"{state}.png"
        for p in (orig_path, peeled_path):
            if not p.is_file():
                raise SystemExit(f"missing strip: {p}")
        outputs = extract_state(
            esf,
            orig_path,
            peeled_path,
            state,
            args.output_dir,
            chroma_key,
            args.key_threshold,
        )
        print(f"{state}: {len(outputs)} frames")


if __name__ == "__main__":
    main()
