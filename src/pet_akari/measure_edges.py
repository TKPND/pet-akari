#!/usr/bin/env python3
"""Report edge whiteness, green residue, bbox tops, and feet-centroid spread per row."""

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage


def frame_stats(path):
    a = np.array(Image.open(path).convert("RGBA"))
    alpha = a[..., 3] > 0
    r, g, b = (a[..., i].astype(np.int16) for i in range(3))
    dist = ndimage.distance_transform_edt(alpha)
    edge = (dist > 0) & (dist <= 2)
    mn = np.minimum(np.minimum(r, g), b)
    mx = np.maximum(np.maximum(r, g), b)
    white_edge = int((edge & (mn >= 200) & ((mx - mn) < 60)).sum())
    green = int((alpha & ((g - np.maximum(r, b)) > 25) & (g > 140)).sum())
    green_edge = int((edge & ((g - np.maximum(r, b)) > 25) & (g > 140)).sum())
    ys, xs = np.nonzero(alpha)
    y1 = int(ys.max())
    band = alpha[max(0, y1 - 39) : y1 + 1, :]
    feet_cx = float(np.nonzero(band)[1].mean())
    return {
        "white_edge": white_edge,
        "green_px": green,
        "green_edge": green_edge,
        "top": int(ys.min()),
        "feet_cx": round(feet_cx, 1),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("frames_root", type=Path)
    args = ap.parse_args()
    report = {}
    for state_dir in sorted(p for p in args.frames_root.iterdir() if p.is_dir()):
        files = sorted(state_dir.glob("[0-9][0-9].png"))
        if not files:
            continue
        frames = [frame_stats(f) for f in files]
        cxs = [f["feet_cx"] for f in frames]
        tops = [f["top"] for f in frames]
        jumps = [abs(tops[i] - tops[(i + 1) % len(tops)]) for i in range(len(tops))]
        report[state_dir.name] = {
            "frames": frames,
            "feet_cx_spread": round(max(cxs) - min(cxs), 1),
            "max_top_jump": max(jumps),
            "max_white_edge": max(f["white_edge"] for f in frames),
            "max_green_px": max(f["green_px"] for f in frames),
            "max_green_edge": max(f["green_edge"] for f in frames),
        }
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
