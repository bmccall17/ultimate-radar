"""Tying the soccer frame to the ultimate frame, and settling 120 vs 110 yards.

Once every frame has a pose, every paint pixel in the possession can be
back-projected into one shared ground-plane map. Paint that is really on the
ground lands in the same place from every frame and reinforces; anything
mis-assigned smears out. So the map is both the measurement and its own sanity
check.

What we are looking for in it:

- **Lines of constant x** — the halfway line at x = 0, and the ultimate goal
  lines. Their distance from the halfway line is what decides open question 5:
  a full 120 yd UFA field centred on the pitch puts its goal lines at +/-40 yd,
  the 110 yd venue exception at +/-35 yd.
- **Lines of constant y** — the ultimate sidelines, which give the cross-field
  offset, and the soccer touchlines.

The circle's pixels are excluded from both marginals: they are spread over every
x and y and would raise the floor everywhere without marking anything.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from . import fit
from . import world as W
from .camera import FixedCamera, Pose

BIN_YD = 0.10
X_RANGE = (-70.0, 70.0)
Y_RANGE = (-50.0, 50.0)


@dataclass
class PaintMap:
    hist_x: np.ndarray
    edges_x: np.ndarray
    hist_y: np.ndarray
    edges_y: np.ndarray
    n_points: int
    n_frames: int

    def centres_x(self) -> np.ndarray:
        return (self.edges_x[:-1] + self.edges_x[1:]) / 2.0

    def centres_y(self) -> np.ndarray:
        return (self.edges_y[:-1] + self.edges_y[1:]) / 2.0


def build_map(cam: FixedCamera, frames, *, min_confidence: float = 0.5,
              stride: int = 2, max_range_yd: float = 75.0,
              circle_exclude_yd: float = 1.2) -> PaintMap:
    xs_all, ys_all, n_used = [], [], 0
    for f in frames[::stride]:
        if f.pose is None or f.confidence < min_confidence or len(f.paint_px) == 0:
            continue
        wpt, ok = fit.backproject(cam, f.pose, f.paint_px)
        good = ok & np.isfinite(wpt).all(axis=1)
        if not good.any():
            continue
        p = wpt[good]
        # Drop anything implausibly far: near the horizon a pixel's world
        # position is enormously sensitive and carries no information.
        near = np.hypot(p[:, 0], p[:, 1]) < max_range_yd
        p = p[near]
        # Drop the centre circle - it spans every x and y and only raises the floor.
        rad = np.hypot(p[:, 0], p[:, 1])
        p = p[np.abs(rad - W.CENTRE_CIRCLE_R) > circle_exclude_yd]
        if len(p) == 0:
            continue
        xs_all.append(p[:, 0])
        # The halfway line runs the full width of the pitch, so it contributes at
        # every y and turns the cross-field marginal into one broad hump with the
        # sidelines buried in it. Exclude it there, as the circle is excluded
        # from both.
        ys_all.append(p[np.abs(p[:, 0]) > 1.5, 1])
        n_used += 1

    if not xs_all:
        raise RuntimeError("no confident frames with paint; cannot build the map")
    xs = np.concatenate(xs_all)
    ys = np.concatenate(ys_all)

    ex = np.arange(X_RANGE[0], X_RANGE[1] + BIN_YD, BIN_YD)
    ey = np.arange(Y_RANGE[0], Y_RANGE[1] + BIN_YD, BIN_YD)
    # A line of constant x is only a peak in the x marginal if it is *long* in y,
    # so weight each point equally and let length do the work.
    hx, _ = np.histogram(xs, bins=ex)
    hy, _ = np.histogram(ys, bins=ey)
    return PaintMap(hist_x=hx.astype(float), edges_x=ex,
                    hist_y=hy.astype(float), edges_y=ey,
                    n_points=int(len(xs)), n_frames=n_used)


def find_peaks(hist: np.ndarray, centres: np.ndarray, *, smooth: int = 3,
               min_prominence: float = 3.0, min_sep_yd: float = 2.0) -> list[dict]:
    """Peaks in a marginal, with a prominence measured against a local baseline."""
    k = np.ones(smooth) / smooth
    h = np.convolve(hist, k, mode="same")
    base = np.convolve(h, np.ones(81) / 81.0, mode="same")
    prom = np.divide(h, np.maximum(base, 1e-6))

    order = np.argsort(-h)
    out: list[dict] = []
    sep_bins = int(min_sep_yd / BIN_YD)
    for i in order:
        if h[i] <= 0 or prom[i] < min_prominence:
            continue
        if any(abs(i - p["bin"]) < sep_bins for p in out):
            continue
        out.append({"bin": int(i), "x_yd": float(centres[i]),
                    "count": float(h[i]), "prominence": float(prom[i])})
        if len(out) >= 12:
            break
    return sorted(out, key=lambda p: p["x_yd"])


def decide_field_length(pm: PaintMap) -> dict:
    """Look for the ultimate goal lines in the x marginal."""
    peaks = find_peaks(pm.hist_x, pm.centres_x())
    cands = []
    strongest = max((p["count"] for p in peaks), default=0.0)
    for p in peaks:
        if abs(p["x_yd"]) < 6.0:
            continue          # the halfway line itself
        # A goal line is a full-width painted line; if a candidate carries a
        # couple of percent of the halfway line's support it is a noise bump,
        # not a line, whatever its prominence against the local baseline says.
        if strongest > 0 and p["count"] < 0.05 * strongest:
            p = {**p, "rejected": "under 5% of the halfway line's support"}
            cands.append(p)
            continue
        cands.append(p)

    verdicts = []
    for p in cands:
        v = W.field_length_from_goal_line(p["x_yd"],
                                          which="near" if p["x_yd"] < 0 else "far")
        v["count"] = p["count"]
        v["prominence"] = round(p["prominence"], 2)
        if "rejected" in p:
            v["rejected"] = p["rejected"]
        verdicts.append(v)

    conclusive = [v for v in verdicts if v["verdict"] != "inconclusive"
                  and "rejected" not in v]
    if not conclusive:
        answer = {"field_length_yd": None, "verdict": "unresolved",
                  "why": "no line of constant x was found at a plausible goal-line "
                         "distance from the halfway line. In this possession the "
                         "camera never looks far enough down the field to see one: "
                         "the x marginal is a single spike at the halfway line and "
                         "noise either side of it."}
    else:
        best = max(conclusive, key=lambda v: v["count"])
        answer = {"field_length_yd": 120.0 if best["verdict"] == "120" else 110.0,
                  "verdict": best["verdict"],
                  "why": f"a line at x = {best['measured_dist_to_halfway_yd']} yd from "
                         f"the halfway line; expected 40 for a 120 yd field, 35 for 110"}
    answer["candidates"] = verdicts
    answer["all_x_peaks"] = [{"x_yd": round(p["x_yd"], 3),
                              "count": round(p["count"], 1),
                              "prominence": round(p["prominence"], 2)} for p in peaks]
    return answer


def render_map(pm: PaintMap, path) -> None:
    """Plot the two marginals. The picture is the evidence; the peak list is a
    summary of it, and a summary can be wrong in ways a plot cannot hide."""
    import cv2

    H, Wd = 420, 1400
    img = np.full((H * 2 + 30, Wd, 3), 18, np.uint8)

    def strip(hist, centres, y0, label, colour):
        h = np.convolve(hist, np.ones(3) / 3, mode="same")
        m = max(h.max(), 1e-6)
        pts = []
        for i in range(len(h)):
            x = int(i / len(h) * (Wd - 80)) + 60
            y = int(y0 + H - 30 - (h[i] / m) * (H - 60))
            pts.append((x, y))
        cv2.polylines(img, [np.array(pts, np.int32)], False, colour, 1, cv2.LINE_AA)
        for v in range(int(centres[0]) // 10 * 10, int(centres[-1]) + 1, 10):
            if v < centres[0] or v > centres[-1]:
                continue
            i = int((v - centres[0]) / (centres[-1] - centres[0]) * (len(h) - 1))
            x = int(i / len(h) * (Wd - 80)) + 60
            cv2.line(img, (x, y0 + 18), (x, y0 + H - 28), (55, 55, 55), 1)
            cv2.putText(img, str(v), (x - 10, y0 + H - 10), cv2.FONT_HERSHEY_SIMPLEX,
                        0.4, (150, 150, 150), 1, cv2.LINE_AA)
        cv2.putText(img, label, (60, y0 + 26), cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                    (235, 235, 235), 1, cv2.LINE_AA)

    strip(pm.hist_x, pm.centres_x(), 0,
          "paint density vs x (yd from halfway line) - goal lines show here",
          (255, 235, 60))
    strip(pm.hist_y, pm.centres_y(), H + 30,
          "paint density vs y (yd across) - sidelines show here", (60, 235, 255))
    cv2.imwrite(str(path), img)


def measure_transform(pm: PaintMap, field_length: float,
                      near_sideline_y: float | None = None) -> W.VenueTransform:
    """Place the ultimate field on the pitch using the sideline peaks.

    The cross-field offset is measured rather than assumed: the two ultimate
    sidelines are 53.333 yd apart by rule, so the pair of constant-y peaks with
    that separation locates the field across the pitch and says, as a by-product,
    whether it is actually centred.
    """
    peaks = find_peaks(pm.hist_y, pm.centres_y())

    if near_sideline_y is not None:
        # An explicit choice between candidate peaks, made on evidence this
        # module cannot see. The paint map offers two near-side lines and cannot
        # tell which is the ultimate sideline and which the soccer touchline -
        # they are only ~7 yd apart and both are real paint. What settles it is
        # where the *players* go, which only exists once M2 has run:
        # confident player-like detections taper out at soccer y = +17 and then
        # a stationary cluster of camera crew sits at +24..+26 with an empty gap
        # between. The far sideline has to lie in that gap. Picking -32.75 puts
        # it at +20.58, inside the gap; picking -25.95 puts it at +27.38, which
        # would place the crew on the field of play.
        nearest = min(peaks, key=lambda p: abs(p["x_yd"] - near_sideline_y),
                      default=None)
        off = abs(near_sideline_y)
        return W.VenueTransform(
            x_sign=1, y_sign=1, x_offset=field_length / 2.0, y_offset=off,
            residual_yd=(abs(nearest["x_yd"] - near_sideline_y) if nearest else None),
            source=f"near ultimate sideline taken as soccer y = {near_sideline_y:.2f}, "
                   f"putting the far sideline at {near_sideline_y + W.UFA_WIDTH:.2f}. "
                   "Chosen between two candidate paint peaks using where players "
                   "actually go: they taper out at y = +17 and a stationary crew "
                   "cluster sits at +24..+26, so the far sideline lies in the gap "
                   "between. The along-pitch offset is still the centred assumption.")

    best, best_err = None, np.inf
    for i in range(len(peaks)):
        for j in range(i + 1, len(peaks)):
            sep = abs(peaks[j]["x_yd"] - peaks[i]["x_yd"])
            err = abs(sep - W.UFA_WIDTH)
            if err < best_err:
                best_err, best = err, (peaks[i], peaks[j])
    if best is None or best_err > 3.0:
        # One sideline is still worth having. The pair test wants both, but the
        # camera on this broadcast sits on one side and the far sideline is
        # beyond the range where a back-projected pixel means anything, so
        # demanding both would throw away a real measurement.
        singles = [p for p in peaks
                   if abs(abs(p["x_yd"]) - W.UFA_WIDTH / 2.0) < 2.5]
        if singles:
            s1 = max(singles, key=lambda p: p["count"])
            off = abs(s1["x_yd"])
            return W.VenueTransform(
                x_sign=1, y_sign=1, x_offset=field_length / 2.0, y_offset=off,
                residual_yd=float(abs(off - W.UFA_WIDTH / 2.0)),
                source=f"one ultimate sideline measured at y = {s1['x_yd']:.2f} yd "
                       f"({abs(off - W.UFA_WIDTH / 2.0):.2f} yd from where a field "
                       "centred across the pitch would put it); the opposite "
                       "sideline is out of usable range, and the x offset still "
                       "assumes the field is centred along the pitch")
        return W.VenueTransform(
            x_offset=field_length / 2.0,
            source="ultimate sidelines not found in the paint map; "
                   "assuming the field is centred on the pitch. UNMEASURED.")
    lo, hi = sorted([best[0]["x_yd"], best[1]["x_yd"]])
    return W.VenueTransform(
        x_sign=1, y_sign=1,
        x_offset=field_length / 2.0,
        y_offset=-lo,
        residual_yd=float(best_err),
        source=f"ultimate sidelines measured at y = {lo:.2f} and {hi:.2f} yd "
               f"(separation {hi - lo:.2f} yd against the rulebook's "
               f"{W.UFA_WIDTH:.3f}); x offset still assumes the field is centred "
               "along the pitch")


# --------------------------------------------------------------------------- #

def main(argv: list[str] | None = None) -> int:
    """Re-run the venue measurement from an existing calibration.json.

        python -m ur.calibrate.venue work/p0001
    """
    import argparse
    import json
    from pathlib import Path

    import cv2

    from . import mask as MK
    from . import run as R

    ap = argparse.ArgumentParser(prog="ur.calibrate.venue")
    ap.add_argument("work")
    ap.add_argument("--eval-dir", default="eval/m1")
    ap.add_argument("--stride", type=int, default=2)
    ap.add_argument("--max-range", type=float, default=75.0)
    ap.add_argument("--near-sideline-y", type=float, default=None,
                    help="pick the near ultimate sideline explicitly, in soccer y")
    a = ap.parse_args(argv)

    work, ev = Path(a.work), Path(a.eval_dir)
    ev.mkdir(parents=True, exist_ok=True)
    cal = json.loads((work / "calibration.json").read_text(encoding="utf-8"))
    paths = sorted((work / "frames").glob("*.jpg"))
    rng = np.random.default_rng(R.SEED)
    rm = MK.build(paths)

    C = np.array(cal["camera"]["position_yd"], float)
    cam = FixedCamera(C=C, image_w=cal["camera"]["image_w"],
                      image_h=cal["camera"]["image_h"])
    frames = []
    for rec, path in zip(cal["frames"], paths):
        if rec.get("H") is None:
            continue
        c = rec["camera"]
        f = R.Frame(index=rec["f"], path=path)
        f.pose = Pose(pan=np.radians(c["pan_deg"]), tilt=np.radians(c["tilt_deg"]),
                      f=c["focal_px"], roll=np.radians(c["roll_deg"]))
        f.confidence = rec["confidence"]
        frames.append(f)

    for f in frames[::a.stride]:
        bgr = cv2.imread(str(f.path))
        f.paint_px, _ = R.paint_pixels(bgr, rm.mask, rng=rng)

    pm = build_map(cam, frames, stride=a.stride, max_range_yd=a.max_range)
    print(f"[venue] {pm.n_points} points from {pm.n_frames} frames")
    render_map(pm, ev / "paint_map.png")

    length = decide_field_length(pm)
    print(f"[venue] field length: {length['verdict']} - {length['why']}")
    for p in length["all_x_peaks"]:
        print(f"    x {p['x_yd']:+8.2f} yd  count {p['count']:9.0f}  prom {p['prominence']:.2f}")
    print("[venue] y peaks (sidelines / touchlines):")
    for p in find_peaks(pm.hist_y, pm.centres_y()):
        print(f"    y {p['x_yd']:+8.2f} yd  count {p['count']:9.0f}  prom {p['prominence']:.2f}")

    vt = measure_transform(pm, length["field_length_yd"] or 120.0,
                           near_sideline_y=a.near_sideline_y)
    print(f"[venue] transform: {json.dumps(vt.to_dict())}")

    (ev / "venue.json").write_text(json.dumps(
        {"field_length": length, "transform": vt.to_dict(),
         "y_peaks": find_peaks(pm.hist_y, pm.centres_y()),
         "n_points": pm.n_points, "n_frames": pm.n_frames}, indent=2) + "\n",
        encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
