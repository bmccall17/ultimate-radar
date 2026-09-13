"""Show every painted line on the pitch, so M0 can say what M1 has to work with.

White paint on grass is bright, unsaturated and *thin*. Players are bright and
unsaturated too, which is why the thinness test does the real work: a line
survives an opening with a long thin kernel at its own orientation, and a torso
does not survive one at any orientation.

Output is an overlay (paint in magenta over the frame) plus the raw mask, so the
question "is there a yard line here" is answered by looking rather than by
believing a Hough parameter.

    python -m tools.paint --frame survey/uniform/001_t360.0.png --out eval/m0/paint_t360
"""

from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np


def paint_mask(bgr: np.ndarray, *, max_sat: int = 90, min_val: int = 105,
               kernel_len: int = 31, n_angles: int = 12) -> np.ndarray:
    """Bright, unsaturated, thin -> paint."""
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    bright = cv2.inRange(hsv, np.array([0, 0, min_val], np.uint8),
                         np.array([179, max_sat, 255], np.uint8))

    # Local contrast: paint is brighter than the grass immediately around it.
    grey = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    bg = cv2.morphologyEx(grey, cv2.MORPH_OPEN,
                          cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (25, 25)))
    tophat = cv2.subtract(grey, bg)
    _, ridge = cv2.threshold(tophat, 12, 255, cv2.THRESH_BINARY)

    cand = cv2.bitwise_and(bright, ridge)

    # Keep only what survives a long thin opening at some orientation.
    acc = np.zeros_like(cand)
    base = np.zeros((kernel_len, kernel_len), np.uint8)
    cv2.line(base, (0, kernel_len // 2), (kernel_len - 1, kernel_len // 2), 1, 1)
    for a in np.linspace(0, 180, n_angles, endpoint=False):
        M = cv2.getRotationMatrix2D((kernel_len / 2 - 0.5, kernel_len / 2 - 0.5), a, 1.0)
        k = cv2.warpAffine(base, M, (kernel_len, kernel_len), flags=cv2.INTER_NEAREST)
        acc = cv2.bitwise_or(acc, cv2.morphologyEx(cand, cv2.MORPH_OPEN, k))
    return acc


def overlay(bgr: np.ndarray, mask: np.ndarray, alpha: float = 0.85) -> np.ndarray:
    out = bgr.copy()
    tint = np.zeros_like(out)
    tint[:] = (255, 0, 255)
    m = mask.astype(bool)
    out[m] = (alpha * tint[m] + (1 - alpha) * out[m]).astype(np.uint8)
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="tools.paint")
    p.add_argument("--frame", required=True)
    p.add_argument("--out", required=True, help="output directory")
    p.add_argument("--max-sat", type=int, default=90)
    p.add_argument("--min-val", type=int, default=105)
    p.add_argument("--kernel-len", type=int, default=31)
    args = p.parse_args(argv)

    bgr = cv2.imread(str(args.frame))
    if bgr is None:
        raise SystemExit(f"cannot read {args.frame}")
    mask = paint_mask(bgr, max_sat=args.max_sat, min_val=args.min_val,
                      kernel_len=args.kernel_len)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    stem = Path(args.frame).stem
    cv2.imwrite(str(out / f"{stem}_mask.png"), mask)
    cv2.imwrite(str(out / f"{stem}_overlay.jpg"), overlay(bgr, mask),
                [cv2.IMWRITE_JPEG_QUALITY, 92])
    pct = 100.0 * mask.mean() / 255
    print(f"[paint] {stem}: {pct:.2f}% of pixels classed as paint -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
