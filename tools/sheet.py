"""Build a labelled contact sheet from a directory of frames.

Looking at thirty frames one at a time is slow and makes it easy to lose track
of which is which. A single labelled grid answers "how is this game framed?" in
one look, and the label under each cell is the source timestamp, so anything
interesting can be pulled back at full resolution.

    python -m tools.sheet --frames survey/uniform --out eval/m0/uniform_sheet.jpg --cols 6
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import cv2
import numpy as np

_T = re.compile(r"t(-?[0-9.]+)")


def build(frames: list[Path], cols: int, cell_w: int, label_h: int) -> np.ndarray:
    rows = (len(frames) + cols - 1) // cols
    first = cv2.imread(str(frames[0]))
    if first is None:
        raise SystemExit(f"cannot read {frames[0]}")
    cell_h = round(cell_w * first.shape[0] / first.shape[1])
    sheet = np.full((rows * (cell_h + label_h), cols * cell_w, 3), 24, np.uint8)

    for i, f in enumerate(frames):
        img = cv2.imread(str(f))
        if img is None:
            continue
        img = cv2.resize(img, (cell_w, cell_h), interpolation=cv2.INTER_AREA)
        r, c = divmod(i, cols)
        y0 = r * (cell_h + label_h)
        x0 = c * cell_w
        sheet[y0:y0 + cell_h, x0:x0 + cell_w] = img
        m = _T.search(f.stem)
        t = float(m.group(1)) if m else i
        label = f"{i:02d}  {int(t // 60):02d}:{t % 60:04.1f}  ({t:.0f}s)"
        cv2.putText(sheet, label, (x0 + 6, y0 + cell_h + label_h - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (230, 230, 230), 1, cv2.LINE_AA)
        cv2.rectangle(sheet, (x0, y0), (x0 + cell_w - 1, y0 + cell_h - 1), (70, 70, 70), 1)
    return sheet


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="tools.sheet")
    p.add_argument("--frames", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--cols", type=int, default=6)
    p.add_argument("--cell-w", type=int, default=460)
    p.add_argument("--label-h", type=int, default=24)
    p.add_argument("--glob", default="*.png")
    p.add_argument("--limit", type=int, default=None)
    args = p.parse_args(argv)

    frames = sorted(Path(args.frames).glob(args.glob))
    if args.limit:
        frames = frames[: args.limit]
    if not frames:
        raise SystemExit(f"no frames matching {args.glob} in {args.frames}")
    sheet = build(frames, args.cols, args.cell_w, args.label_h)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out), sheet, [cv2.IMWRITE_JPEG_QUALITY, 88])
    print(f"[sheet] {len(frames)} frames -> {out}  ({sheet.shape[1]}x{sheet.shape[0]})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
