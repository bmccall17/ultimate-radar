"""Burn detections onto the clip.

    python -m ur.detect.overlay work/p0001 --out eval/m2/p0001_detections.mp4

Draws what the stage actually decided, not a tidied version of it: boxes kept as
players in green, boxes the filters rejected in red with the reason, and the
per-detection sigma that M3 and M4 will inherit. A render that hides the rejects
cannot show you that the filter is throwing away real players, which is the
failure worth catching.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

import cv2
import numpy as np

GREEN = (60, 220, 60)
RED = (60, 60, 235)
AMBER = (0, 190, 255)


def render(work: Path, out: Path, *, fps: int = 15) -> Path:
    det = json.loads((work / "detections.json").read_text(encoding="utf-8"))
    by_frame = {d["f"]: d["dets"] for d in det["frames"]}
    paths = sorted((work / "frames").glob("*.jpg"))
    tmp = out.parent / "_det_frames"
    if tmp.exists():
        for f in tmp.glob("*.jpg"):
            f.unlink()
    tmp.mkdir(parents=True, exist_ok=True)

    for i, p in enumerate(paths):
        img = cv2.imread(str(p))
        dets = by_frame.get(i, [])
        n_in = 0
        for d in dets:
            x0, y0, x1, y1 = [int(round(v)) for v in d["box"]]
            inb = d.get("in_bounds")
            colour = GREEN if inb else (RED if inb is False else AMBER)
            cv2.rectangle(img, (x0, y0), (x1, y1), colour, 2)
            if inb:
                n_in += 1
                sig = d.get("sigma_yd")
                if sig is not None:
                    cv2.putText(img, f"{sig:.2f}yd", (x0, min(img.shape[0] - 4, y1 + 14)),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.4, colour, 1, cv2.LINE_AA)
            else:
                note = (d.get("note") or "")[:22]
                if note:
                    cv2.putText(img, note, (x0, max(11, y0 - 4)),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.36, colour, 1, cv2.LINE_AA)
        cv2.putText(img, f"f{i:04d}   {n_in} kept as players, {len(dets) - n_in} rejected",
                    (14, 34), cv2.FONT_HERSHEY_SIMPLEX, 0.85, (255, 255, 255), 2, cv2.LINE_AA)
        rows = [("kept: inside the field, plausible size", GREEN),
                ("rejected: out of bounds, or too short for its distance", RED)]
        y0 = img.shape[0] - 18 * len(rows) - 90
        cv2.rectangle(img, (8, y0 - 8), (470, y0 + 18 * len(rows) + 6), (0, 0, 0), -1)
        for k, (t, c) in enumerate(rows):
            y = y0 + 14 + 18 * k
            cv2.line(img, (18, y - 4), (40, y - 4), c, 3, cv2.LINE_AA)
            cv2.putText(img, t, (48, y), cv2.FONT_HERSHEY_SIMPLEX, 0.42,
                        (235, 235, 235), 1, cv2.LINE_AA)
        cv2.imwrite(str(tmp / f"{i:06d}.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 90])

    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-framerate", str(fps), "-start_number", "0",
                    "-i", str(tmp / "%06d.jpg"), "-c:v", "libx264", "-crf", "18",
                    "-preset", "medium", "-pix_fmt", "yuv420p", str(out)], check=True)
    for f in tmp.glob("*.jpg"):
        f.unlink()
    tmp.rmdir()
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="ur.detect.overlay")
    p.add_argument("work")
    p.add_argument("--out", default=None)
    a = p.parse_args(argv)
    work = Path(a.work)
    out = Path(a.out) if a.out else Path("eval/m2") / f"{work.name}_detections.mp4"
    r = render(work, out)
    print(f"[overlay] wrote {r} ({r.stat().st_size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
