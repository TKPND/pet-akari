#!/usr/bin/env python3
"""Prepare and QA denser true-frame Akari motion sources."""

import argparse
import json
from pathlib import Path

import clawd_hq_theme as hq
from PIL import Image, ImageDraw

TARGET_TRUE_FRAMES = {
    "idle": 8,
    "thinking": 8,
    "working": 12,
    "notification": 8,
    "attention": 12,
    "error": 8,
    "sleeping": 8,
}

STATE_NOTES = {
    "idle": "calm breathing, slow blink, tiny hoodie and hair sway",
    "thinking": "curious focused thinking with small head and eye movement",
    "working": "focused task-work energy, attentive forward lean, small hand movement near hoodie or bag strap",
    "notification": "approval or help-needed attention cue, expectant but calm",
    "attention": "task-complete bright bounce or happy expression",
    "error": "soft disappointed failed pose, readable but not dramatic",
    "sleeping": "quiet sleeping breathing loop",
}

IDENTITY_LOCK = """Identity lock:
- Keep the dark navy cadet/newsboy cap: low on the head, rounded crown, seam panels, short curved front brim.
- No ahoge, antenna hair, or loose hair tuft through the top of the cap.
- Keep short coral-orange bob hair tucked under the cap.
- Keep magenta eyes, teal jacket, cream hoodie, navy pleated skirt, black crossbody bag, white socks, and mismatched teal/orange shoe accents.
- Keep the viewer-right cap accent and silver button separate from the viewer-right cyan hairpin.
- Do not turn either sneaker into a mostly teal shoe or mostly orange shoe.
"""


def ensure_dir(path):
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def resample_filter():
    return getattr(getattr(Image, "Resampling", Image), "LANCZOS")


def build_motion_contract():
    contract = {"states": {}}
    for state in hq.CORE_STATES:
        if state in ("working", "attention"):
            contract["states"][state] = {"durationMs": 100, "inbetweens": 3}
        else:
            contract["states"][state] = {"durationMs": 125, "inbetweens": 4}
    return contract


def write_json(path, data):
    path = Path(path)
    ensure_dir(path.parent)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def collect_anchor_frames(anchors_dir):
    anchors_dir = Path(anchors_dir)
    frames_by_state = {}
    for state in hq.CORE_STATES:
        state_dir = anchors_dir / state
        frames = sorted(state_dir.glob("*.png")) if state_dir.is_dir() else []
        if len(frames) != 4:
            raise ValueError(f"{state} requires exactly 4 anchor PNGs, found {len(frames)}")
        for frame in frames:
            try:
                with Image.open(frame) as image:
                    image.verify()
            except OSError as error:
                raise ValueError(f"{state} anchor PNG is unreadable: {frame}") from error
        frames_by_state[state] = frames
    return frames_by_state


def write_anchor_sheet(anchor_paths, output_path):
    output_path = Path(output_path)
    ensure_dir(output_path.parent)
    thumb_size = (256, 320)
    label_height = 28
    frames = []
    for path in anchor_paths:
        path = Path(path)
        with Image.open(path) as image:
            frame = image.convert("RGBA")
        frame.thumbnail(thumb_size, resample_filter())
        frames.append((path, frame.copy()))

    sheet = Image.new(
        "RGBA",
        (len(frames) * thumb_size[0], thumb_size[1] + label_height),
        (0, 255, 0, 255),
    )
    draw = ImageDraw.Draw(sheet)
    for index, (path, frame) in enumerate(frames):
        left = index * thumb_size[0] + (thumb_size[0] - frame.width) // 2
        top = (thumb_size[1] - frame.height) // 2
        sheet.alpha_composite(frame, (left, top))
        draw.text((index * thumb_size[0] + 8, thumb_size[1] + 6), path.stem, fill=(20, 20, 24, 255))
    sheet.convert("RGB").save(output_path)
    return output_path


def build_prompt(state):
    target_frames = TARGET_TRUE_FRAMES[state]
    note = STATE_NOTES[state]
    return f"""# Akari {state} Denser Motion Prompt

Generate one horizontal {target_frames}-frame sprite strip for Clawd Akari `{state}`.

Use the attached `{state}-anchors.png` image as the exact 4-keyframe pose anchor. Preserve the same character in every frame and add intermediate poses between those anchors.

{IDENTITY_LOCK}
Animation:
- {target_frames} full-body frames arranged left to right in one strip.
- Motion: {note}.
- Keep frame 1, the middle anchors, and the final-to-first loop consistent with the attached 4 keyframes.
- Feet stay planted on one baseline unless the state note explicitly implies a tiny bounce.
- Body scale stays constant across the strip.
- No literal running, walking travel, laptop, tools, paper, code, UI, symbols, speed lines, dust, text, scenery, shadows, or detached effects.

Sprite production:
- Perfectly flat pure #00ff00 chroma-key background across the whole strip.
- Keep the character fully inside each frame with generous padding.
- Separate each frame with enough green background so deterministic splitting works.
- No visible grid, labels, frame numbers, borders, checkerboard transparency, white background, black background, shadows, floor patches, glow, or guide marks.
- Do not use #00ff00 or close green-screen colors on the character.

Reject if the hat silhouette, hair, bag, shoe colors, or outfit drift from the anchors.
"""


def write_all_anchor_contact_sheet(references_dir, output_path):
    references_dir = Path(references_dir)
    output_path = Path(output_path)
    ensure_dir(output_path.parent)
    rows = []
    for state in hq.CORE_STATES:
        path = references_dir / f"{state}-anchors.png"
        with Image.open(path) as image:
            rows.append((state, image.convert("RGBA")))

    width = max(image.width for _, image in rows)
    height = sum(image.height + 28 for _, image in rows)
    sheet = Image.new("RGBA", (width, height), (250, 250, 250, 255))
    draw = ImageDraw.Draw(sheet)
    y = 0
    for state, image in rows:
        sheet.alpha_composite(image, (0, y))
        draw.text((8, y + image.height + 6), state, fill=(20, 20, 24, 255))
        y += image.height + 28
    sheet.convert("RGB").save(output_path)
    return output_path


def prepare_run(anchors_dir, run_dir):
    anchor_frames = collect_anchor_frames(anchors_dir)
    run_dir = Path(run_dir)
    prompts_dir = ensure_dir(run_dir / "prompts")
    references_dir = ensure_dir(run_dir / "references")
    ensure_dir(run_dir / "generated")
    ensure_dir(run_dir / "decoded")
    ensure_dir(run_dir / "masters")
    ensure_dir(run_dir / "masters-stabilized")
    qa_dir = ensure_dir(run_dir / "qa")

    write_json(run_dir / "motion-contract.json", build_motion_contract())
    for state in hq.CORE_STATES:
        anchors = anchor_frames[state]
        write_anchor_sheet(anchors, references_dir / f"{state}-anchors.png")
        (prompts_dir / f"{state}-denser.md").write_text(build_prompt(state), encoding="utf-8")
    write_all_anchor_contact_sheet(references_dir, qa_dir / "anchor-contact-sheet.png")
    return run_dir


def _build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare = subparsers.add_parser("prepare-run", help="write denser source run prompts and references")
    prepare.add_argument("--anchors", type=Path, required=True)
    prepare.add_argument("--run-dir", type=Path, required=True)
    return parser


def main(argv=None):
    args = _build_parser().parse_args(argv)
    if args.command == "prepare-run":
        run_dir = prepare_run(args.anchors, args.run_dir)
        print(f"prepared denser motion run in {run_dir}")


if __name__ == "__main__":
    main()
