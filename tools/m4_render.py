"""Watch the tracker. Two panes, 24 seconds, evidence state drawn honestly.

    python -m tools.m4_render work/p0001                 # -> eval/m4/p0001_tracks.mp4
    python -m tools.m4_render work/p0001 --stills 60 150 240 330

M1 produced a verification video, M2 a detections video, M3 a possession video.
M4 produced one JSON file, and that is the wrong order of operations: **a tracker
is the first stage whose failures are temporal.** A slot that swaps identities, a
ghost that dead-reckons somewhere no human could have run to, a referee quietly
holding a defender's slot for six seconds — none of those appear in a per-frame
statistic and all of them are obvious within thirty seconds of watching.

Left pane: the broadcast, with each slot drawn as a ring **on the ground** at its
field position, sized to its sigma in real yards. Right pane: the same fourteen
slots overhead, with the camera's footprint on the field.

Evidence state is rendered per `docs/05-uncertainty.md`, in form rather than hue —
hue is team identity and nothing else:

- `observed`    solid ring, filled centre
- `interpolated` dashed ring, hollow centre
- `predicted`   dashed ring, hollow centre, sigma disc drawn — a ghost
- `unknown`     hatched, nearly gone

**The sigma disc is the single most useful thing on screen.** It is drawn at true
field scale, so it shrinks and grows meaningfully: a slot observed last frame has
a ring about a third of a yard across, and one that has been guessing for two
seconds has one several yards across. If the truth is routinely outside the disc,
that is visible here long before the sigma-calibration gate is computed.

**Detections the tracker did not use are drawn too**, in grey, tagged `weak_team`
or `unassigned`. Without them the render answers "where does the tracker think
people are" but not "what is standing where the tracker has nobody", and the
second question is the one that says whether excluding `weak_team` was right.

**Drawing is clipped off the rendered graphics and above the horizon.** M3's
render put projected field lines straight across the sponsor banner. The clip uses
the same two exclusions `ur/calibrate/mask.py` uses for registration — static
graphic regions, and everything above the ground plane's vanishing line — but
takes the horizon from *this frame's* homography rather than a single bootstrap
row, and deliberately does not use that module's third exclusion (players), which
is unbuilt today and would erase the overlay exactly where the players are if it
ever lands.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

import cv2
import numpy as np

from ur.calibrate import mask as MASK

SOL = (245, 245, 240)      # BGR, light kit
CHILL = (214, 127, 63)     # BGR, drawn blue so it reads against a dark shirt
GREY = (150, 150, 150)
LINE = (110, 200, 130)
WARN = (60, 190, 240)
BG = (28, 34, 26)

RADAR_W, RADAR_H = 780, 360
TIMELINE_H = 250
STILL_FRAMES = (60, 150, 240, 330)


# --------------------------------------------------------------------------- #
# projection


def inverse_with_sign(H, image_w: int, image_h: int):
    """field -> image, plus the sign of w that means 'in front of the camera'.

    `H` is normalised so `H[2][2] = 1`, which pins the sign of w for image->field
    and leaves the inverse's overall scale free. On this footage every point
    genuinely in front of the camera comes back with w NEGATIVE, so a naive
    `w > 0` test rejects the whole field and draws nothing at all.
    """
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


def ground_ellipse(Ms, x, y, radius_yd, n=28):
    """A circle of `radius_yd` on the ground, as it appears in the image."""
    pts = []
    for k in range(n):
        th = k / n * 2 * np.pi
        p, w = project(Ms, x + radius_yd * np.cos(th), y + radius_yd * np.sin(th))
        if w <= 1e-9:
            return None
        pts.append(p)
    return np.round(np.array(pts)).astype(np.int32)


def dashed_polyline(img, pts, colour, thickness=2, on=4, off=4):
    n = len(pts)
    for i in range(n):
        if (i // on) % 2:
            continue
        cv2.line(img, tuple(pts[i]), tuple(pts[(i + 1) % n]), colour, thickness,
                 cv2.LINE_AA)


# --------------------------------------------------------------------------- #
# the draw clip


def build_clip_mask(work: Path, image_w: int, image_h: int) -> np.ndarray:
    """Static graphic regions, as 255 = safe to draw on."""
    frames = sorted((work / "frames").glob("*.jpg"))
    static, frac = MASK.static_region(frames)
    safe = np.full((image_h, image_w), 255, np.uint8)
    safe[static > 0] = 0
    print(f"[m4_render] static graphic regions cover {frac:.1%} of the frame")
    return safe


def frame_clip(safe: np.ndarray, pf: dict, image_w: int, image_h: int) -> np.ndarray:
    """`safe`, additionally cut above this frame's own horizon."""
    out = safe.copy()
    H = np.asarray(pf["H"], float)
    row = MASK.horizon_from_homography(np.linalg.inv(H), image_w, image_h)
    if row is None:
        row = MASK.BOOTSTRAP_HORIZON
    row = int(max(0, min(image_h, row + MASK.HORIZON_MARGIN_PX)))
    out[:row, :] = 0
    return out


def blend_clipped(base: np.ndarray, drawn: np.ndarray, clip: np.ndarray) -> np.ndarray:
    """Keep `drawn` where the clip allows it, `base` everywhere else."""
    m = clip.astype(bool)
    out = base.copy()
    out[m] = drawn[m]
    return out


# --------------------------------------------------------------------------- #
# panes


def draw_video_pane(img, P, n, safe):
    field = P["field"]
    pf = P["camera"]["per_frame"][n]
    if pf is None:
        cv2.putText(img, f"f{n:04d}   calibration confidence below 0.5 - "
                         "no position is stated on this frame",
                    (18, 44), cv2.FONT_HERSHEY_SIMPLEX, 0.9, WARN, 2, cv2.LINE_AA)
        return img

    clip = frame_clip(safe, pf, P["camera"]["image_w"], P["camera"]["image_h"])
    drawn = img.copy()
    Ms = inverse_with_sign(pf["H"], P["camera"]["image_w"], P["camera"]["image_h"])

    L, W = field["length_yd"], field["width_yd"]
    segs = [([x, 0.0], [x, W]) for x in (0.0, field["endzone_yd"], L / 2.0,
                                         L - field["endzone_yd"], L)]
    segs += [([0.0, 0.0], [L, 0.0]), ([0.0, W], [L, W])]
    for a, b in segs:
        prev = None
        for i in range(41):
            fx = a[0] + (b[0] - a[0]) * i / 40
            fy = a[1] + (b[1] - a[1]) * i / 40
            p, w = project(Ms, fx, fy)
            cur = tuple(np.round(p).astype(int)) if w > 1e-9 else None
            if prev and cur:
                cv2.line(drawn, prev, cur, LINE, 2, cv2.LINE_AA)
            prev = cur

    # What the tracker chose not to use.
    for r in P["unused_detections"][n]:
        p, w = project(Ms, r["xy"][0], r["xy"][1])
        if w <= 1e-9:
            continue
        q = tuple(np.round(p).astype(int))
        cv2.drawMarker(drawn, q, GREY, cv2.MARKER_TILTED_CROSS, 16, 2, cv2.LINE_AA)
        cv2.putText(drawn, r["why"], (q[0] + 8, q[1] + 14),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, GREY, 1, cv2.LINE_AA)

    off = P["possession"]["offense"]
    for pl in P["players"]:
        st, xy = pl["state"][n], pl["est"][n]
        if xy is None:
            continue
        sig = pl["sigma"][n]
        p, w = project(Ms, xy[0], xy[1])
        if w <= 1e-9:
            continue
        c = SOL if pl["team"] == off else CHILL
        q = tuple(np.round(p).astype(int))

        if st == "unknown":
            ring = ground_ellipse(Ms, xy[0], xy[1], min(sig, 8.0))
            if ring is not None:
                dashed_polyline(drawn, ring, (90, 90, 90), 1, on=2, off=6)
            continue

        # The sigma disc, at true field scale.
        ring = ground_ellipse(Ms, xy[0], xy[1], max(sig, 0.25))
        if ring is not None:
            if st in ("observed", "provisional"):
                cv2.polylines(drawn, [ring], True, c, 2, cv2.LINE_AA)
            else:
                dashed_polyline(drawn, ring, c, 2, on=3, off=3)
        if st in ("observed", "provisional"):
            cv2.circle(drawn, q, 4, c, -1, cv2.LINE_AA)
            cv2.circle(drawn, q, 4, (0, 0, 0), 1, cv2.LINE_AA)
        else:
            cv2.circle(drawn, q, 4, c, 1, cv2.LINE_AA)
        tag = (q[0] + 9, q[1] - 9)
        cv2.putText(drawn, pl["id"], tag, cv2.FONT_HERSHEY_SIMPLEX, 0.56,
                    (0, 0, 0), 4, cv2.LINE_AA)
        cv2.putText(drawn, pl["id"], tag, cv2.FONT_HERSHEY_SIMPLEX, 0.56, c, 1,
                    cv2.LINE_AA)

    img = blend_clipped(img, drawn, clip)
    cov = P["derived"]["coverage"][n]
    cv2.putText(img, f"f{n:04d}   {cov}/14 observed   calib {pf['confidence']:.2f}",
                (18, 44), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2, cv2.LINE_AA)
    # This used to be the literal "gates NOT measured", which stayed on the render
    # for the whole of M4 after the gates were in fact measured. A caption that
    # cannot go out of date is one that reads the file it is captioning.
    g = P.get("gates") or {}
    banner = (f"M4 tracker - per-player recall {g['per_player_recall']:.4f} "
              f"on {g.get('measured_on', '?')}"
              if P.get("gates_measured") and g.get("per_player_recall") is not None
              else "M4 tracker - gates NOT measured")
    cv2.putText(img, banner, (18, 76),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, WARN, 2, cv2.LINE_AA)
    return img


def draw_radar(P, n):
    field = P["field"]
    L, W = field["length_yd"], field["width_yd"]
    pad = 22
    r = np.full((RADAR_H, RADAR_W, 3), BG, np.uint8)

    def rx(x):
        return int(round(pad + x / L * (RADAR_W - 2 * pad)))

    def ry(y):
        return int(round(pad + y / W * (RADAR_H - 2 * pad)))

    cv2.rectangle(r, (rx(0), ry(0)), (rx(L), ry(W)), (38, 50, 34), -1)
    pf = P["camera"]["per_frame"][n]
    if pf is not None:
        fp = footprint(P, n)
        if fp is not None and len(fp) >= 3:
            poly = np.array([[rx(p[0]), ry(p[1])] for p in fp], np.int32)
            ov = r.copy()
            cv2.fillPoly(ov, [poly], (58, 78, 52))
            r = cv2.addWeighted(ov, 0.55, r, 0.45, 0)
            cv2.polylines(r, [poly], True, (110, 160, 100), 1, cv2.LINE_AA)

    cv2.rectangle(r, (rx(0), ry(0)), (rx(L), ry(W)), (95, 110, 88), 1)
    for x in (field["endzone_yd"], L - field["endzone_yd"]):
        cv2.line(r, (rx(x), ry(0)), (rx(x), ry(W)), (70, 82, 64), 1)
    cv2.line(r, (rx(L / 2), ry(0)), (rx(L / 2), ry(W)), (60, 70, 55), 1)

    for rec in P["unused_detections"][n]:
        cv2.drawMarker(r, (rx(rec["xy"][0]), ry(rec["xy"][1])), GREY,
                       cv2.MARKER_TILTED_CROSS, 9, 1, cv2.LINE_AA)

    off = P["possession"]["offense"]
    scale = (RADAR_W - 2 * pad) / L
    for pl in P["players"]:
        st, xy = pl["state"][n], pl["est"][n]
        if xy is None:
            continue
        c = SOL if pl["team"] == off else CHILL
        sig = pl["sigma"][n]
        cx, cy = rx(xy[0]), ry(xy[1])
        rad = max(2, int(round(sig * scale)))
        if st == "unknown":
            cv2.circle(r, (cx, cy), rad, (78, 78, 78), 1, cv2.LINE_AA)
            continue
        ov = r.copy()
        cv2.circle(ov, (cx, cy), rad, c, -1, cv2.LINE_AA)
        r = cv2.addWeighted(ov, 0.16, r, 0.84, 0)
        cv2.circle(r, (cx, cy), rad, c, 1, cv2.LINE_AA)
        if st in ("observed", "provisional"):
            cv2.circle(r, (cx, cy), 4, c, -1, cv2.LINE_AA)
        else:
            cv2.circle(r, (cx, cy), 4, c, 1, cv2.LINE_AA)
        cv2.putText(r, pl["id"], (cx + 6, cy - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.4,
                    c, 1, cv2.LINE_AA)

    counts = {}
    for pl in P["players"]:
        counts[pl["state"][n]] = counts.get(pl["state"][n], 0) + 1
    txt = "  ".join(f"{k} {v}" for k, v in
                    sorted(counts.items(), key=lambda kv: -kv[1]))
    cv2.putText(r, txt, (10, RADAR_H - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.44,
                (190, 200, 185), 1, cv2.LINE_AA)
    cv2.putText(r, "attacking ->", (rx(L / 2) - 30, ry(0) - 9),
                cv2.FONT_HERSHEY_SIMPLEX, 0.42, (130, 145, 122), 1, cv2.LINE_AA)
    return r



def draw_timeline(P, n):
    """One row per slot, the whole possession, with a playhead.

    This is the instrument the video alone does not give you. A slot that goes
    dark for six seconds, or flickers between observed and predicted twenty times,
    is a pattern across time - you cannot see it in any single frame, and it is
    exactly the kind of failure a tracker has.
    """
    nf = P["possession"]["frames"]
    rows = P["players"]
    lab_w, rh, gap = 34, 13, 3
    h = len(rows) * (rh + gap) + 26
    img = np.full((h, RADAR_W, 3), BG, np.uint8)
    x0, x1 = lab_w, RADAR_W - 8
    colour = {"observed": (120, 200, 120), "provisional": (150, 210, 235),
              "interpolated": (190, 180, 90),
              "predicted": (70, 140, 220), "unknown": (62, 62, 62)}
    off = P["possession"]["offense"]
    for k, pl in enumerate(rows):
        y = 4 + k * (rh + gap)
        c = SOL if pl["team"] == off else CHILL
        cv2.putText(img, pl["id"], (3, y + rh - 2), cv2.FONT_HERSHEY_SIMPLEX,
                    0.38, c, 1, cv2.LINE_AA)
        for f, st in enumerate(pl["state"]):
            xa = int(x0 + (x1 - x0) * f / nf)
            xb = max(xa + 1, int(x0 + (x1 - x0) * (f + 1) / nf))
            cv2.rectangle(img, (xa, y), (xb, y + rh - 1), colour[st], -1)
    px = int(x0 + (x1 - x0) * n / nf)
    cv2.line(img, (px, 0), (px, h - 22), (255, 255, 255), 1)
    for k, (t, c) in enumerate((("observed", colour["observed"]),
                                ("interpolated", colour["interpolated"]),
                                ("predicted", colour["predicted"]),
                                ("unknown", colour["unknown"]))):
        xx = 10 + k * 105
        cv2.rectangle(img, (xx, h - 16), (xx + 12, h - 6), c, -1)
        cv2.putText(img, t, (xx + 16, h - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.36,
                    (200, 205, 195), 1, cv2.LINE_AA)
    return img


def footprint(P, n):
    """The ground the camera can see, clipped to the field."""
    pf = P["camera"]["per_frame"][n]
    if pf is None:
        return None
    H = np.asarray(pf["H"], float)
    Wi, Hi = P["camera"]["image_w"], P["camera"]["image_h"]

    def w_of(p):
        return H[2, 0] * p[0] + H[2, 1] * p[1] + H[2, 2]

    sgn = 1.0 if w_of([Wi / 2, Hi - 1]) >= 0 else -1.0
    poly = [[0, 0], [Wi, 0], [Wi, Hi], [0, Hi]]
    eps = 1e-6

    def clip(pts, inside, cut):
        out = []
        for i in range(len(pts)):
            a, b = pts[i], pts[(i + 1) % len(pts)]
            ia, ib = inside(a), inside(b)
            if ia:
                out.append(a)
            if ia != ib:
                out.append(cut(a, b))
        return out

    poly = clip(poly, lambda p: sgn * w_of(p) > eps,
                lambda a, b: (lambda t: [a[0] + t * (b[0] - a[0]),
                                         a[1] + t * (b[1] - a[1])])(
                    (sgn * w_of(a) - eps) / (sgn * w_of(a) - sgn * w_of(b))))
    if len(poly) < 3:
        return None
    g = []
    for p in poly:
        q = H @ np.array([p[0], p[1], 1.0])
        g.append([q[0] / q[2], q[1] / q[2]])
    L, W = P["field"]["length_yd"], P["field"]["width_yd"]
    for axis, val, lower in ((0, -6, True), (0, L + 6, False),
                             (1, -6, True), (1, W + 6, False)):
        g = clip(g,
                 (lambda ax, v, lo: lambda p: p[ax] >= v if lo else p[ax] <= v)(
                     axis, val, lower),
                 (lambda ax, v: lambda a, b: (lambda t: [a[0] + t * (b[0] - a[0]),
                                                         a[1] + t * (b[1] - a[1])])(
                     (v - a[ax]) / (b[ax] - a[ax])))(axis, val))
        if len(g) < 3:
            return None
    return g


def compose(work: Path, P, n, safe, paths):
    """One composite frame. Width and height are kept even for the encoder."""
    img = draw_video_pane(cv2.imread(str(paths[n])), P, n, safe)
    h = 760
    # Even width, or libx264 with yuv420p refuses the whole encode - the video
    # pane came out 1351 px wide, the composite 2131, and ffmpeg failed with a
    # generic external-library error that says nothing about parity.
    vw = int(img.shape[1] * h / img.shape[0]) // 2 * 2
    vid = cv2.resize(img, (vw, h))
    panel = np.full((h, RADAR_W, 3), BG, np.uint8)
    panel[6:6 + RADAR_H] = draw_radar(P, n)
    tl = draw_timeline(P, n)
    y = 6 + RADAR_H + 8
    panel[y:y + tl.shape[0]] = tl
    y += tl.shape[0] + 10
    legend = [("ring on the ground = sigma, at TRUE FIELD SCALE", (235, 235, 235)),
              ("solid ring + filled dot = observed this frame", (235, 235, 235)),
              ("dashed + hollow = interpolated or predicted (a guess)", (200, 205, 195)),
              ("grey x = a detection the tracker did not use", GREY)]
    for k, (t, c) in enumerate(legend):
        if y + 16 * k + 12 < h:
            cv2.putText(panel, t, (10, y + 16 * k + 10), cv2.FONT_HERSHEY_SIMPLEX,
                        0.42, c, 1, cv2.LINE_AA)
    out = np.hstack([vid, panel])
    assert out.shape[0] % 2 == 0 and out.shape[1] % 2 == 0,         f"composite {out.shape[1]}x{out.shape[0]} must be even for yuv420p"
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="tools.m4_render")
    p.add_argument("work")
    p.add_argument("--out", default=None)
    p.add_argument("--stills", type=int, nargs="*", default=None)
    p.add_argument("--fps", type=int, default=15)
    a = p.parse_args(argv)

    work = Path(a.work)
    P = json.loads((work / "possession.json").read_text(encoding="utf-8"))
    paths = sorted((work / "frames").glob("*.jpg"))
    print("[m4_render] building the draw clip from static graphic regions...")
    safe = build_clip_mask(work, P["camera"]["image_w"], P["camera"]["image_h"])
    print(f"[m4_render] {100 * (safe > 0).mean():.1f}% of the frame is safe to draw on")

    if a.stills is not None:
        picks = a.stills or list(STILL_FRAMES)
        tiles = [compose(work, P, n, safe, paths) for n in picks]
        sc = 0.5
        tiles = [cv2.resize(t, None, fx=sc, fy=sc) for t in tiles]
        rows = [np.hstack(tiles[i:i + 2]) for i in range(0, len(tiles), 2)]
        w = max(r.shape[1] for r in rows)
        rows = [np.hstack([r, np.full((r.shape[0], w - r.shape[1], 3), 20, np.uint8)])
                for r in rows]
        out = Path(a.out or "eval/m4/p0001_tracks_stills.jpg")
        out.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(out), np.vstack(rows), [cv2.IMWRITE_JPEG_QUALITY, 92])
        print(f"[m4_render] {out}  frames {picks}")
        return 0

    out = Path(a.out or f"eval/m4/{work.name}_tracks.mp4")
    tmp = out.parent / "_m4_frames"
    tmp.mkdir(parents=True, exist_ok=True)
    for f in tmp.glob("*.jpg"):
        f.unlink()
    n_frames = P["possession"]["frames"]
    for n in range(n_frames):
        cv2.imwrite(str(tmp / f"{n:06d}.jpg"), compose(work, P, n, safe, paths),
                    [cv2.IMWRITE_JPEG_QUALITY, 90])
        if n % 60 == 0:
            print(f"[m4_render] {n}/{n_frames}")
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                    "-framerate", str(a.fps), "-start_number", "0",
                    "-i", str(tmp / "%06d.jpg"), "-c:v", "libx264", "-crf", "21",
                    "-preset", "medium", "-pix_fmt", "yuv420p", str(out)], check=True)
    for f in tmp.glob("*.jpg"):
        f.unlink()
    tmp.rmdir()
    print(f"[m4_render] wrote {out} ({out.stat().st_size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
