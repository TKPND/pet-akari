#!/usr/bin/env python3
"""Horizontally align RGBA frames of one row by their feet centroid (bottom 40 rows)."""

import argparse
from pathlib import Path

import numpy as np
from PIL import Image


def feet_cx(a):
    alpha = a[..., 3] > 0
    ys, xs = np.nonzero(alpha)
    y1 = int(ys.max())
    band = alpha[max(0, y1 - 39) : y1 + 1, :]
    return float(np.nonzero(band)[1].mean())


def shift_x(a, dx):
    out = np.zeros_like(a)
    if dx >= 0:
        out[:, dx:, :] = a[:, : a.shape[1] - dx, :]
    else:
        out[:, : a.shape[1] + dx, :] = a[:, -dx:, :]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("frames_dir", type=Path)
    args = ap.parse_args()
    files = sorted(args.frames_dir.glob("[0-9][0-9].png"))
    frames = [np.array(Image.open(f).convert("RGBA")) for f in files]
    cxs = [feet_cx(a) for a in frames]
    target = float(np.median(cxs))
    for f, arr, cx in zip(files, frames, cxs):
        dx = int(round(target - cx))
        alpha = arr[..., 3] > 0
        xs = np.nonzero(alpha)[1]
        dx = max(dx, -int(xs.min()))
        dx = min(dx, int(arr.shape[1] - 1 - xs.max()))
        if dx != 0:
            Image.fromarray(shift_x(arr, dx)).save(f)
        print(f"{f.name}: feet_cx={cx:.1f} shift={dx}")


if __name__ == "__main__":
    main()
