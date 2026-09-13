"""Measure players on real frames, without a detector.

M0 has to answer "how tall is a player in pixels" and "are the two kits
separable" before any detector exists. The trick is that a grass pitch is the
easiest background in sport: segment the green, and what is left standing on it
is people.

Method, per frame:

  1. HSV threshold for grass -> a green mask.
  2. Largest connected green component, convex-hulled -> the playing surface.
     This is what keeps the crowd, the stands and the sideline out of the count.
  3. Inside the surface, non-green pixels are candidate foreground.
  4. Painted lines are removed by an opening with a wide horizontal kernel
     (lines are locally wide and flat; players are not).
  5. Connected components, filtered on area, height and aspect ratio.

Everything is thresholds, so everything is arguable. That is why the tool always
writes an annotated overlay next to the numbers: the numbers are only worth what
a human sees when they look at the overlay. Check it before quoting anything.

    python -m tools.measure blobs --frames survey/uniform --out eval/m0/blobs
    python -m tools.measure crops --frame survey/uniform/012_t3000.0.png --out eval/m0/crops
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path

import cv2
import numpy as np

# Grass, in OpenCV HSV (H 0-179). Wide enough for sun and shadow on the same
# pitch, tight enough to exclude the blue/black Wind Chill kit and the stands.
GRASS_LO = np.array([28, 40, 40], dtype=np.uint8)
GRASS_HI = np.array([95, 255, 255], dtype=np.uint8)

MIN_BLOB_AREA = 40
MIN_H = 6
MAX_H = 400
MIN_ASPECT = 0.9   # height / width
MAX_ASPECT = 9.0


@dataclass
class Blob:
    x: int
    y: int
    w: int
    h: int
    area: int
    fill: float          # blob area / bbox area; a person is ~0.4-0.7
    aspect: float
    foot_y: int
    torso_lab: tuple[float, float, float]
    torso_bgr: tuple[float, float, float]


def field_mask(bgr: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return (grass mask, filled playing-surface mask).

    The fill is done per column between the first and last grass row rather than
    by flood fill. A flood fill seeded at a corner silently inverts whenever the
    grass happens to touch that corner, which turns the whole sky into playing
    surface; the column band cannot fail that way, and it is also the right
    shape for the job, since the surface really is one contiguous vertical run
    in every column of a broadcast frame.
    """
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    grass = cv2.inRange(hsv, GRASS_LO, GRASS_HI)

    closed = cv2.morphologyEx(
        grass, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))
    )
    n, labels, stats, _ = cv2.connectedComponentsWithStats(closed, connectivity=8)
    if n <= 1:
        return grass, np.zeros_like(grass)

    # Pick the pitch, not the trees behind the stand: the pitch is the green
    # component that owns most of the bottom of the frame. Trees are green and
    # can be large, but they are never at the camera's feet.
    H = grass.shape[0]
    bottom = labels[int(0.66 * H):, :]
    counts = np.bincount(bottom.ravel(), minlength=n)
    counts[0] = 0
    if counts.max() < 0.02 * grass.size:
        return grass, np.zeros_like(grass)  # no real pitch in this frame
    biggest = int(np.argmax(counts))
    comp = labels == biggest

    surface = np.zeros_like(grass)
    rows = np.arange(comp.shape[0])[:, None]
    has = comp.any(axis=0)
    if not has.any():
        return grass, surface
    top = np.where(comp, rows, comp.shape[0]).min(axis=0).astype(np.int32)
    bot = np.where(comp, rows, -1).max(axis=0).astype(np.int32)

    # A player standing on the far touchline cuts a notch in the grass, which
    # would otherwise push the band below their own feet and exclude them.
    # A running min/max over a window wider than a player closes the notch.
    win = max(31, comp.shape[1] // 24) | 1
    top = np.asarray(cv2.erode(top.reshape(1, -1).astype(np.float32),
                               np.ones((1, win), np.uint8)).ravel(), dtype=np.int32)
    bot = np.asarray(cv2.dilate(bot.reshape(1, -1).astype(np.float32),
                                np.ones((1, win), np.uint8)).ravel(), dtype=np.int32)

    for c in np.where(has)[0]:
        if bot[c] >= top[c]:
            surface[top[c]:bot[c] + 1, c] = 255
    return grass, surface


def find_blobs(bgr: np.ndarray, *, min_h: int = MIN_H) -> tuple[list[Blob], np.ndarray]:
    grass, surface = field_mask(bgr)
    fg = cv2.bitwise_and(cv2.bitwise_not(grass), surface)

    # Painted lines: locally wide and flat. An opening with a long horizontal
    # kernel keeps them and nothing else, so subtracting it removes them.
    lines = cv2.morphologyEx(
        fg, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (35, 1))
    )
    fg = cv2.subtract(fg, lines)
    fg = cv2.morphologyEx(
        fg, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 7))
    )

    n, labels, stats, cents = cv2.connectedComponentsWithStats(fg, connectivity=8)
    lab_img = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)
    # A player stands on grass, so the *foot* must lie inside the surface even
    # when the head pokes above the far touchline.
    H, W = fg.shape
    out: list[Blob] = []
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        if area < MIN_BLOB_AREA or h < min_h or h > MAX_H or w == 0:
            continue
        fx, fy = int(x + w // 2), min(H - 1, int(y + h) - 1)
        if surface[fy, fx] == 0:
            continue
        aspect = h / w
        if not (MIN_ASPECT <= aspect <= MAX_ASPECT):
            continue
        comp = labels[y:y + h, x:x + w] == i
        # Torso = rows 20-55% down the box, the part that is jersey on everyone.
        t0, t1 = y + int(0.20 * h), y + max(int(0.55 * h), int(0.20 * h) + 1)
        sel = (labels[t0:t1, x:x + w] == i)
        if sel.sum() < 4:
            continue
        lab_px = lab_img[t0:t1, x:x + w][sel].astype(np.float32)
        bgr_px = bgr[t0:t1, x:x + w][sel].astype(np.float32)
        out.append(
            Blob(
                x=int(x), y=int(y), w=int(w), h=int(h), area=int(area),
                fill=round(float(comp.sum()) / (w * h), 3),
                aspect=round(float(aspect), 2),
                foot_y=int(y + h),
                torso_lab=tuple(round(float(v), 1) for v in lab_px.mean(axis=0)),
                torso_bgr=tuple(round(float(v), 1) for v in bgr_px.mean(axis=0)),
            )
        )
    return out, fg


def annotate(bgr: np.ndarray, blobs: list[Blob]) -> np.ndarray:
    img = bgr.copy()
    for b in blobs:
        cv2.rectangle(img, (b.x, b.y), (b.x + b.w, b.y + b.h), (0, 255, 255), 1)
        cv2.putText(img, str(b.h), (b.x, max(10, b.y - 3)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 255, 255), 1, cv2.LINE_AA)
    cv2.putText(img, f"{len(blobs)} blobs", (12, 28),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2, cv2.LINE_AA)
    return img


def cmd_blobs(args: argparse.Namespace) -> int:
    src = Path(args.frames)
    frames = sorted(src.glob("*.png")) if src.is_dir() else [src]
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    records = []
    for f in frames:
        bgr = cv2.imread(str(f))
        if bgr is None:
            continue
        blobs, _ = find_blobs(bgr, min_h=args.min_h)
        cv2.imwrite(str(out / f"{f.stem}_annot.jpg"), annotate(bgr, blobs),
                    [cv2.IMWRITE_JPEG_QUALITY, 92])
        records.append({"frame": f.name, "n": len(blobs), "blobs": [asdict(b) for b in blobs]})
        hs = [b.h for b in blobs]
        print(f"{f.name}: {len(blobs):>3} blobs  h min/med/max = "
              f"{min(hs) if hs else 0}/{int(np.median(hs)) if hs else 0}/{max(hs) if hs else 0}")
    (out / "blobs.json").write_text(json.dumps(records, indent=1) + "\n", encoding="utf-8")
    print(f"\n[measure] {len(records)} frames -> {out}/blobs.json  (+ annotated jpgs)")
    return 0


def cmd_crops(args: argparse.Namespace) -> int:
    """Cut each blob out at 1:1 and again upscaled, for legibility judging."""
    bgr = cv2.imread(str(args.frame))
    if bgr is None:
        raise SystemExit(f"cannot read {args.frame}")
    blobs, _ = find_blobs(bgr, min_h=args.min_h)
    blobs.sort(key=lambda b: -b.h)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    pad = args.pad
    H, W = bgr.shape[:2]
    index = []
    for i, b in enumerate(blobs[: args.limit]):
        x0, y0 = max(0, b.x - pad), max(0, b.y - pad)
        x1, y1 = min(W, b.x + b.w + pad), min(H, b.y + b.h + pad)
        crop = bgr[y0:y1, x0:x1]
        cv2.imwrite(str(out / f"{i:02d}_h{b.h}_y{b.foot_y}.png"), crop)
        big = cv2.resize(crop, None, fx=args.zoom, fy=args.zoom, interpolation=cv2.INTER_NEAREST)
        cv2.imwrite(str(out / f"{i:02d}_h{b.h}_y{b.foot_y}_x{args.zoom}.png"), big)
        index.append({"i": i, **asdict(b)})
    (out / "index.json").write_text(json.dumps(index, indent=1) + "\n", encoding="utf-8")
    print(f"[measure] {len(index)} crops -> {out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="tools.measure")
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("blobs")
    b.add_argument("--frames", required=True, help="a PNG or a directory of PNGs")
    b.add_argument("--out", required=True)
    b.add_argument("--min-h", type=int, default=MIN_H)
    b.set_defaults(fn=cmd_blobs)

    c = sub.add_parser("crops")
    c.add_argument("--frame", required=True)
    c.add_argument("--out", required=True)
    c.add_argument("--limit", type=int, default=24)
    c.add_argument("--pad", type=int, default=4)
    c.add_argument("--zoom", type=int, default=6)
    c.add_argument("--min-h", type=int, default=MIN_H)
    c.set_defaults(fn=cmd_crops)

    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
