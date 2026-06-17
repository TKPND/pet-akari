#!/usr/bin/env python3
"""Peel the baked-in white sticker outline + green halo from a chroma-key strip.

Iteratively converts near-white / green-tinged pixels that touch the chroma
background into pure chroma, stopping when the removal count collapses
(outline fully consumed) or at --max-peel iterations.
"""

import argparse
from pathlib import Path

import numpy as np
from PIL import Image


def masks(rgb, white_min=170):
    r = rgb[..., 0].astype(np.int16)
    g = rgb[..., 1].astype(np.int16)
    b = rgb[..., 2].astype(np.int16)
    bg = (g - np.maximum(r, b)) > 100
    green_tinge = ((g - np.maximum(r, b)) > 25) & (g > 140) & ~bg
    mn = np.minimum(np.minimum(r, g), b)
    mx = np.maximum(np.maximum(r, g), b)
    near_white = (mn > white_min) & ((mx - mn) < 60)
    return bg, green_tinge | near_white


def neighbors_true(mask):
    out = np.zeros_like(mask)
    out[1:, :] |= mask[:-1, :]
    out[:-1, :] |= mask[1:, :]
    out[:, 1:] |= mask[:, :-1]
    out[:, :-1] |= mask[:, 1:]
    return out


def peel(rgb, max_iter, stop_ratio, white_min=170):
    removed_total = 0
    first_n = None
    for _ in range(max_iter):
        bg, peelable = masks(rgb, white_min)
        ring = peelable & neighbors_true(bg)
        n = int(ring.sum())
        if n == 0:
            break
        if first_n is None:
            first_n = n
        elif n < stop_ratio * first_n:
            # 輪郭リングを食い尽くした後の内部白(靴など)への侵食を止める
            break
        rgb[ring] = [0, 255, 0]
        removed_total += n
    return removed_total


def edge_trim(rgb, rings):
    """Unconditionally drop `rings` boundary rings to erase the blend band.

    At strip resolution the white/green blend band is only 1-2 px, while art
    lineart is 4-6 px, so a small trim removes residue without harming art.
    """
    removed_total = 0
    for _ in range(rings):
        bg, _ = masks(rgb)
        ring = ~bg & neighbors_true(bg)
        n = int(ring.sum())
        if n == 0:
            break
        rgb[ring] = [0, 255, 0]
        removed_total += n
    return removed_total


def recolor_residue(rgb, dark, max_iter=10):
    """Recolor the leftover pale/green blend band to a dark lineart color.

    Marches inward from the background through contiguous pale or green-tinged
    pixels, turning them into the lineart color instead of deleting them. The
    march stops at the art's own dark lineart, which shields interior whites
    (sneakers, clipboard) and skin from any change.
    """
    recolored_total = 0
    r = rgb[..., 0].astype(np.int16)
    g = rgb[..., 1].astype(np.int16)
    b = rgb[..., 2].astype(np.int16)
    frontier = (g - np.maximum(r, b)) > 100
    for _ in range(max_iter):
        r = rgb[..., 0].astype(np.int16)
        g = rgb[..., 1].astype(np.int16)
        b = rgb[..., 2].astype(np.int16)
        bg = (g - np.maximum(r, b)) > 100
        mn = np.minimum(np.minimum(r, g), b)
        mx = np.maximum(np.maximum(r, g), b)
        pale = (mn > 150) & ((mx - mn) < 80)
        greenish = ((g - np.maximum(r, b)) > 15) & (g > 120)
        ring = (pale | greenish) & ~bg & ~frontier & neighbors_true(frontier)
        n = int(ring.sum())
        if n == 0:
            break
        rgb[ring] = dark
        frontier |= ring
        recolored_total += n
    return recolored_total


def green_kill(rgb, excess=8, key_threshold=96.0):
    """Neutralize chroma contamination everywhere in the sprite.

    Any pixel whose G channel exceeds max(R,B) by more than `excess` is a
    chroma-key blend in this palette (no legitimate green art). Clamp G down
    to max(R,B), preserving luminance and shape. Pixels close enough to the
    key to be removed by the extractor's keying (distance <= key_threshold)
    are left untouched so the background still keys out cleanly.
    """
    r = rgb[..., 0].astype(np.int16)
    g = rgb[..., 1].astype(np.int16)
    b = rgb[..., 2].astype(np.int16)
    mx = np.maximum(r, b)
    dist2 = r.astype(np.int32) ** 2 + (g - 255).astype(np.int32) ** 2 + b.astype(np.int32) ** 2
    keyable = dist2 <= int(key_threshold * key_threshold)
    target = (g - mx > excess) & ~keyable
    rgb[..., 1] = np.where(target, mx.astype(np.uint8), rgb[..., 1])
    return int(target.sum())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("strip", type=Path)
    ap.add_argument("--max-peel", type=int, default=14)
    ap.add_argument("--stop-ratio", type=float, default=0.3)
    ap.add_argument("--white-min", type=int, default=170)
    ap.add_argument("--edge-trim", type=int, default=0)
    ap.add_argument("--recolor", action="store_true", help="recolor leftover pale/green blend band to lineart dark")
    ap.add_argument("--dark", default="25,22,28", help="R,G,B lineart color used by --recolor")
    ap.add_argument("--green-kill", action="store_true", help="clamp G down to max(R,B) for chroma-contaminated pixels")
    ap.add_argument("--output", type=Path, default=None)
    args = ap.parse_args()
    im = Image.open(args.strip).convert("RGB")
    rgb = np.array(im)
    removed = peel(rgb, args.max_peel, args.stop_ratio, args.white_min)
    removed += edge_trim(rgb, args.edge_trim)
    recolored = 0
    if args.recolor:
        dark = [int(v) for v in args.dark.split(",")]
        recolored = recolor_residue(rgb, dark)
    killed = green_kill(rgb) if args.green_kill else 0
    out = args.output or args.strip
    Image.fromarray(rgb).save(out)
    print(f"{args.strip.name}: peeled {removed}, recolored {recolored}, green-killed {killed} -> {out}")


if __name__ == "__main__":
    main()
