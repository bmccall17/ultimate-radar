"""Render possession.json back onto the broadcast — the M3 artifact.

    python -m tools.m3_render work/p0001                  # -> eval/m3/p0001_possession.mp4
    python -m tools.m3_render work/p0001 --stills 60 150 240 330

This draws the pipeline's *output* rather than its intermediates: each slot's
field position projected back into the image through the same homography the
viewer uses, with its sigma drawn as the ellipse a circle on the ground actually
makes. If the markers sit on feet and the projected sidelines sit on paint, the
chain from paint to pose to position to overlay is closed. If they drift, this is
where it shows, and no number in detections.json would have said so.

It is deliberately the *round trip*. `ur.detect.overlay` draws boxes, which only
proves the detector fired; `ur.calibrate.verify` draws lines, which only proves
the camera model. Neither would catch a mistake in the field->image direction,
which is the direction the viewer depends on and the only one nothing else uses.

**The sign trap.** `H` is normalised so `H[2][2] = 1`, which fixes the sign of the
homogeneous `w` for image->field and leaves the inverse's overall scale free. On
this footage every point genuinely in front of the camera comes back through
`inv(H)` with **w negative**, so the obvious `w > 0` visibility test rejects the
entire field and draws nothing at all. The reference sign is taken per frame from
a point that must be in front - the bottom centre of the image, pushed through H
and straight back.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

import cv2
import numpy as np

SOL = (245, 245, 240)      # BGR: light kit
CHILL = (214, 127, 63)     # BGR: drawn blue so it reads against a dark shirt
LINE = (120, 230, 140)
WARN = (60, 190, 240)


def inverse_with_sign(H, image_w: int, image_h: int):
    """field -> image, plus the sign that means 'in front of the camera'."""
    H = np.asarray(H, float)
    M = np.linalg.inv(H)
    g = H @ np.array([image_w / 2.0, image_h - 1.0, 1.0])
    g = g[:2] / g[2]
    b = M @ np.array([g[0], g[1], 1.0])
    return M, (1.0 if b[2] >= 0 else -1.0)


def project(Ms, x, y):
    M, sgn = Ms
    q = M @ np.array([x, y, 1.0])
    return q[:2] / q[2], sgn * q[2]


def draw_frame(img, P, n):
    field = P["field"]
    pf = P["camera"]["per_frame"][n]
    cov = P["derived"]["coverage"][n]
    if pf is None:
        cv2.putText(img, f"f{n:04d}   calibration confidence below 0.5 - "
                         "no position is stated on this frame",
                    (18, 44), cv2.FONT_HERSHEY_SIMPLEX, 0.95, WARN, 2, cv2.LINE_AA)
        return img

    Ms = inverse_with_sign(pf["H"], P["camera"]["image_w"], P["camera"]["image_h"])
    L, W = field["length_yd"], field["width_yd"]
    segs = [([x, 0.0], [x, W]) for x in (0.0, field["endzone_yd"], L / 2.0,
                                         L - field["endzone_yd"], L)]
    segs += [([0.0, 0.0], [L, 0.0]), ([0.0, W], [L, W])]
    for a, b in segs:
        pts = []
        for i in range(41):
            fx = a[0] + (b[0] - a[0]) * i / 40
            fy = a[1] + (b[1] - a[1]) * i / 40
            p, w = project(Ms, fx, fy)
            pts.append(tuple(np.round(p).astype(int)) if w > 1e-9 else None)
        for u, v in zip(pts, pts[1:]):
            if u and v:
                cv2.line(img, u, v, LINE, 2, cv2.LINE_AA)

    off = P["possession"]["offense"]
    for pl in P["players"]:
        if pl["state"][n] != "observed":
            continue
        xy, sig = pl["est"][n], pl["sigma"][n]
        p, w = project(Ms, xy[0], xy[1])
        if w <= 1e-9:
            continue
        c = SOL if pl["team"] == off else CHILL
        ring = []
        for k in range(25):
            th = k / 24 * 2 * np.pi
            e, ew = project(Ms, xy[0] + sig * np.cos(th), xy[1] + sig * np.sin(th))
            if ew > 1e-9:
                ring.append(e)
        if len(ring) > 3:
            cv2.polylines(img, [np.round(np.array(ring)).astype(np.int32)],
                          True, c, 1, cv2.LINE_AA)
        q = tuple(np.round(p).astype(int))
        cv2.drawMarker(img, q, c, cv2.MARKER_CROSS, 20, 2, cv2.LINE_AA)
        tag = tuple(np.round(p).astype(int) + np.array([9, -9]))
        cv2.putText(img, pl["id"], tag, cv2.FONT_HERSHEY_SIMPLEX, 0.58,
                    (0, 0, 0), 4, cv2.LINE_AA)
        cv2.putText(img, pl["id"], tag, cv2.FONT_HERSHEY_SIMPLEX, 0.58, c, 1, cv2.LINE_AA)

    cv2.putText(img, f"f{n:04d}   {cov}/14 slots observed   calib {pf['confidence']:.2f}",
                (18, 44), cv2.FONT_HERSHEY_SIMPLEX, 0.95, (255, 255, 255), 2, cv2.LINE_AA)
    # The caption is taken from the file rather than assumed: this tool was written
    # against ur/standin.py, which M4 replaced and M6 deleted, and a render that
    # still shouted STAND-IN over the tracker's real output would be the wrong
    # kind of wrong.
    note = ("positions measured; SLOT IDENTITY IS A STAND-IN"
            if P.get("stand_in") else
            "positions and slot identities are the M4 tracker (ur.track.run)")
    cv2.putText(img, note,
                (18, 76), cv2.FONT_HERSHEY_SIMPLEX, 0.62, WARN, 2, cv2.LINE_AA)
    return img


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="tools.m3_render")
    p.add_argument("work")
    p.add_argument("--out", default=None)
    p.add_argument("--stills", type=int, nargs="*", default=None)
    p.add_argument("--fps", type=int, default=15)
    a = p.parse_args(argv)

    work = Path(a.work)
    P = json.loads((work / "possession.json").read_text(encoding="utf-8"))
    paths = sorted((work / "frames").glob("*.jpg"))

    if a.stills is not None:
        picks = a.stills or [60, 150, 240, 330]
        tiles = [draw_frame(cv2.imread(str(paths[n])), P, n) for n in picks]
        sc = 0.52
        tiles = [cv2.resize(t, None, fx=sc, fy=sc) for t in tiles]
        rows = [np.hstack(tiles[i:i + 2]) for i in range(0, len(tiles), 2)]
        w = max(r.shape[1] for r in rows)
        rows = [np.hstack([r, np.full((r.shape[0], w - r.shape[1], 3), 20, np.uint8)])
                for r in rows]
        out = Path(a.out or "eval/m3/p0001_possession_stills.jpg")
        out.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(out), np.vstack(rows), [cv2.IMWRITE_JPEG_QUALITY, 92])
        print(f"[m3_render] {out}  frames {picks}")
        return 0

    out = Path(a.out or f"eval/m3/{work.name}_possession.mp4")
    tmp = out.parent / "_m3_frames"
    tmp.mkdir(parents=True, exist_ok=True)
    for f in tmp.glob("*.jpg"):
        f.unlink()
    for n in range(P["possession"]["frames"]):
        img = draw_frame(cv2.imread(str(paths[n])), P, n)
        cv2.imwrite(str(tmp / f"{n:06d}.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 90])
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-framerate", str(a.fps), "-start_number", "0",
                    "-i", str(tmp / "%06d.jpg"), "-c:v", "libx264", "-crf", "18",
                    "-preset", "medium", "-pix_fmt", "yuv420p", str(out)], check=True)
    for f in tmp.glob("*.jpg"):
        f.unlink()
    tmp.rmdir()
    print(f"[m3_render] wrote {out} ({out.stat().st_size / 1e6:.1f} MB)")
    print("[m3_render] the committed copy is re-encoded smaller: "
          "ffmpeg -i <out> -vf scale=1600:-2 -crf 23 -preset slow <out>")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
