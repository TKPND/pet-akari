#!/usr/bin/env python3
"""Reorder a small frame loop for smoothest adjacent transitions (frame 0 stays first).

Brute-forces all cyclic orders that keep frame 0 first (5! = 120 for 6 frames)
and minimizes the summed mean absolute RGBA difference between adjacent frames,
including the wrap-around. Deterministic; no new imagery is drawn.
"""

import argparse
import itertools
import shutil
from pathlib import Path

import numpy as np
from PIL import Image


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("frames_dir", type=Path)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument(
        "--criterion",
        choices=("pixel", "top"),
        default="pixel",
        help="top = minimize max adjacent bbox-top jump first, pixel diff second",
    )
    args = ap.parse_args()
    files = sorted(args.frames_dir.glob("[0-9][0-9].png"))
    imgs = [np.array(Image.open(f).convert("RGBA"), dtype=np.int32) for f in files]
    n = len(imgs)
    tops = [int(np.nonzero(img[..., 3] > 0)[0].min()) for img in imgs]
    diff = np.zeros((n, n))
    for i in range(n):
        for j in range(i + 1, n):
            d = float(np.abs(imgs[i] - imgs[j]).mean())
            diff[i, j] = diff[j, i] = d
    best, best_key = None, None
    for perm in itertools.permutations(range(1, n)):
        order = (0,) + perm
        cost = sum(diff[order[k], order[(k + 1) % n]] for k in range(n))
        max_jump = max(abs(tops[order[k]] - tops[order[(k + 1) % n]]) for k in range(n))
        key = (max_jump, cost) if args.criterion == "top" else (cost,)
        if best_key is None or key < best_key:
            best, best_key = order, key
    identity_cost = sum(diff[k, (k + 1) % n] for k in range(n))
    identity_jump = max(abs(tops[k] - tops[(k + 1) % n]) for k in range(n))
    print(
        "order:",
        best,
        "key:",
        tuple(round(v, 2) for v in best_key),
        "identity: jump",
        identity_jump,
        "cost",
        round(identity_cost, 2),
    )
    if args.apply and best != tuple(range(n)):
        tmp = args.frames_dir / "tmp-reorder"
        tmp.mkdir()
        for new_idx, old_idx in enumerate(best):
            shutil.copy(files[old_idx], tmp / f"{new_idx:02d}.png")
        for f in sorted(tmp.glob("*.png")):
            shutil.move(str(f), args.frames_dir / f.name)
        tmp.rmdir()
        print("applied")


if __name__ == "__main__":
    main()
