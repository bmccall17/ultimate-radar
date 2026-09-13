"""Lay out player crops at a FIXED magnification, for judging legibility.

A normal contact sheet resizes every cell to the same width, which is exactly
wrong here: the question is whether a 60-pixel-tall player's number can be read,
and rescaling him to match a 400-pixel one destroys the evidence. So each crop is
magnified by the same factor and pinned to the top-left of its cell, and the
label carries the player's true height in source pixels.

    python -m tools.jerseysheet --dirs eval/m0/jersey/* --zoom 4 --out eval/m0/jersey_sheet.png
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import cv2
import numpy as np

_H = re.compile(r"_h(\d+)_")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="tools.jerseysheet")
    p.add_argument("--root", required=True, help="directory of per-frame crop dirs")
    p.add_argument("--zoom", type=float, default=4.0)
    p.add_argument("--cols", type=int, default=8)
    p.add_argument("--cell", type=int, default=300)
    p.add_argument("--max-h", type=int, default=200, help="skip crops taller than this")
    p.add_argument("--out", required=True)
    args = p.parse_args(argv)

    crops: list[tuple[int, Path]] = []
    for f in sorted(Path(args.root).rglob("*.png")):
        if "_x" in f.stem:  # skip the pre-zoomed copies
            continue
        m = _H.search(f.stem)
        if not m:
            continue
        h = int(m.group(1))
        if h > args.max_h:
            continue
        crops.append((h, f))
    if not crops:
        raise SystemExit(f"no crops found under {args.root}")
    crops.sort(key=lambda c: -c[0])

    rows = (len(crops) + args.cols - 1) // args.cols
    cell = args.cell
    lab = 26
    sheet = np.full((rows * (cell + lab), args.cols * cell, 3), 20, np.uint8)

    for i, (h, f) in enumerate(crops):
        img = cv2.imread(str(f))
        if img is None:
            continue
        img = cv2.resize(img, None, fx=args.zoom, fy=args.zoom,
                         interpolation=cv2.INTER_NEAREST)
        img = img[:cell, :cell]
        r, c = divmod(i, args.cols)
        y0, x0 = r * (cell + lab), c * cell
        sheet[y0:y0 + img.shape[0], x0:x0 + img.shape[1]] = img
        cv2.putText(sheet, f"h={h}px  {f.parent.name[:9]}", (x0 + 4, y0 + cell + lab - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (220, 220, 220), 1, cv2.LINE_AA)
        cv2.rectangle(sheet, (x0, y0), (x0 + cell - 1, y0 + cell - 1), (60, 60, 60), 1)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out), sheet)
    print(f"[jerseysheet] {len(crops)} crops at {args.zoom}x -> {out} "
          f"({sheet.shape[1]}x{sheet.shape[0]})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
