"""Cut a rectangle out of a frame and optionally magnify it.

Used throughout the M0 report to look at paint, jersey digits and distant
players at real pixel scale. Magnification is nearest-neighbour on purpose: a
smooth interpolation invents detail that is not in the source, and the whole
point of these crops is to judge what detail is there.

    python -m tools.crop --frame survey/uniform/007_t1800.0.png \
        --rect 0,330,1920,140 --zoom 2 --out eval/m0/far_sideline.png

    python -m tools.crop --frame f.png --grid 120 --out eval/m0/f_grid.png
"""

from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np


def draw_grid(img: np.ndarray, step: int, ox: int = 0, oy: int = 0) -> np.ndarray:
    out = img.copy()
    h, w = out.shape[:2]
    for x in range(0, w, step):
        cv2.line(out, (x, 0), (x, h), (0, 0, 255), 1)
        cv2.putText(out, str(x + ox), (x + 2, 14), cv2.FONT_HERSHEY_SIMPLEX, 0.4,
                    (0, 0, 255), 1, cv2.LINE_AA)
    for y in range(0, h, step):
        cv2.line(out, (0, y), (w, y), (255, 0, 0), 1)
        cv2.putText(out, str(y + oy), (2, y + 14), cv2.FONT_HERSHEY_SIMPLEX, 0.4,
                    (255, 0, 0), 1, cv2.LINE_AA)
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="tools.crop")
    p.add_argument("--frame", required=True)
    p.add_argument("--rect", default=None, help="x,y,w,h in source pixels")
    p.add_argument("--zoom", type=float, default=1.0)
    p.add_argument("--grid", type=int, default=0, help="grid spacing in source px, 0 = off")
    p.add_argument("--enhance", action="store_true",
                   help="CLAHE on L channel - makes faint paint visible")
    p.add_argument("--out", required=True)
    args = p.parse_args(argv)

    img = cv2.imread(str(args.frame))
    if img is None:
        raise SystemExit(f"cannot read {args.frame}")
    ox = oy = 0
    if args.rect:
        x, y, w, h = (int(v) for v in args.rect.split(","))
        H, W = img.shape[:2]
        x, y = max(0, x), max(0, y)
        img = img[y:min(H, y + h), x:min(W, x + w)]
        ox, oy = x, y

    if args.enhance:
        lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
        lab[:, :, 0] = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8)).apply(lab[:, :, 0])
        img = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)

    if args.grid:
        img = draw_grid(img, args.grid, ox, oy)
    if args.zoom != 1.0:
        interp = cv2.INTER_NEAREST if args.zoom > 1 else cv2.INTER_AREA
        img = cv2.resize(img, None, fx=args.zoom, fy=args.zoom, interpolation=interp)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out), img)
    print(f"[crop] {out}  {img.shape[1]}x{img.shape[0]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
