"""M1's acceptance test: known field points, reprojected, measured in yards.

The first version of this measured every detected circle pixel against a
10.0066 yd radius, and reported two of ten held-out frames as 10 and 34 yards
wrong. They were not wrong. Their calibration was smooth, consistent with their
neighbours, and residual 0.14 yd; what had failed was the *test*, whose own
per-frame RANSAC had locked onto a spurious conic. A test that fails for its own
reasons is worse than no test, because it costs you the one signal you were
relying on to catch real failures.

So this is the test docs/04-milestones.md actually specifies: points whose field
position is known exactly, checked by reprojection. On a pitch with no gridiron
paint the two exactly-known points available in nearly every frame are where the
halfway line crosses the centre circle — soccer-frame (0, +10.0066) and
(0, −10.0066).

Two things keep it honest:

- The points are located from the **image-space** line and conic only. The camera
  model is used solely to back-project them, never to find them.
- Every point is drawn on a montage. The numbers below are worth exactly as much
  as that picture, so look at it before quoting them.

What it is not: an independent check of the *features*. There is no other
exactly-known geometry on this pitch, so a systematic error in how the paint
detector centres a line would move the test and the fit together. It is a check
of the camera model and the fit, not of the detector.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np

from . import features as F
from . import fit, mask, paint
from . import world as W
from .verify import load


def line_ellipse_intersections(line, ell) -> np.ndarray:
    """Where a line crosses an ellipse, in image pixels. Up to two points."""
    t = np.radians(ell.angle_deg)
    R = np.array([[np.cos(t), np.sin(t)], [-np.sin(t), np.cos(t)]])
    ra, rb = ell.axes[0] / 2.0, ell.axes[1] / 2.0
    c = np.array(ell.centre)
    p = R @ (np.asarray(line.p0, float) - c)
    d = R @ np.asarray(line.d, float)
    A = (d[0] / ra) ** 2 + (d[1] / rb) ** 2
    B = 2.0 * (p[0] * d[0] / ra ** 2 + p[1] * d[1] / rb ** 2)
    C = (p[0] / ra) ** 2 + (p[1] / rb) ** 2 - 1.0
    disc = B * B - 4 * A * C
    if A < 1e-12 or disc < 0:
        return np.zeros((0, 2))
    s = np.sqrt(disc)
    return np.array([line.p0 + ((-B - s) / (2 * A)) * line.d,
                     line.p0 + ((-B + s) / (2 * A)) * line.d])


def run_accept(work: Path, *, n_holdout: int = 20, seed: int = 20260827,
               eval_dir: Path | None = None) -> dict:
    cam, poses, cal = load(work)
    paths = sorted((work / "frames").glob("*.jpg"))
    rng = np.random.default_rng(seed)
    rm = mask.build(paths)

    usable = [i for i, (p, rec) in enumerate(zip(poses, cal["frames"]))
              if p is not None and rec.get("confidence", 0) >= 0.5]
    picks = sorted(rng.choice(usable, size=n_holdout, replace=False).tolist())

    rows, tiles = [], []
    for i in picks:
        bgr = cv2.imread(str(paths[i]))
        region = cv2.bitwise_and(rm.mask, cv2.bitwise_not(F.player_mask(bgr)))
        pm = paint.largest_components(paint.paint_mask(bgr, region=region), min_area=60)
        ell = F.find_centre_circle_ransac(pm)
        line = F.find_halfway_line(pm, ell) if ell is not None else None
        if ell is None or line is None:
            rows.append({"frame": i, "note": "line or conic not found; not testable"})
            continue
        pts = line_ellipse_intersections(line, ell)
        if len(pts) != 2:
            rows.append({"frame": i, "note": "line does not cross the conic twice"})
            continue

        # The camera sits on the -y side of the pitch, so the crossing higher in
        # the image is the far one, at world y = +R. This fixes only which label
        # goes on which point, never where the point is.
        far, near = (pts[0], pts[1]) if pts[0][1] < pts[1][1] else (pts[1], pts[0])
        truth = np.array([[0.0, +W.CENTRE_CIRCLE_R], [0.0, -W.CENTRE_CIRCLE_R]])
        got, ok = fit.backproject(cam, poses[i], np.array([far, near]))
        errs = [float(np.hypot(*(got[k] - truth[k])))
                if ok[k] and np.isfinite(got[k]).all() else float("nan")
                for k in range(2)]
        rows.append({"frame": i,
                     "px_far": [round(float(v), 2) for v in far],
                     "px_near": [round(float(v), 2) for v in near],
                     "err_far_yd": round(errs[0], 4),
                     "err_near_yd": round(errs[1], 4),
                     "mean_yd": round(float(np.nanmean(errs)), 4),
                     "max_yd": round(float(np.nanmax(errs)), 4)})

        tile = bgr.copy()
        tile[pm > 0] = (255, 0, 255)
        cv2.ellipse(tile, (int(ell.centre[0]), int(ell.centre[1])),
                    (int(ell.axes[0] / 2), int(ell.axes[1] / 2)), ell.angle_deg,
                    0, 360, (0, 165, 255), 2, cv2.LINE_AA)
        for pt, name in ((far, "far (0,+10.01)"), (near, "near (0,-10.01)")):
            q = (int(round(pt[0])), int(round(pt[1])))
            cv2.drawMarker(tile, q, (60, 255, 60), cv2.MARKER_CROSS, 40, 3)
            cv2.putText(tile, name, (q[0] + 16, q[1] - 10), cv2.FONT_HERSHEY_SIMPLEX,
                        0.7, (60, 255, 60), 2, cv2.LINE_AA)
        cv2.putText(tile, f"f{i}   err {errs[0]:.3f} / {errs[1]:.3f} yd", (16, 40),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2, cv2.LINE_AA)
        tiles.append(cv2.resize(tile, (760, 428)))

    scored = [r for r in rows if "mean_yd" in r]
    means = [r["mean_yd"] for r in scored]
    maxes = [r["max_yd"] for r in scored]
    out = {
        "held_out_frames": picks,
        "per_frame": rows,
        "n_correspondences": 2 * len(scored),
        "mean_error_yd": round(float(np.mean(means)), 4) if means else None,
        "max_error_yd": round(float(np.max(maxes)), 4) if maxes else None,
        "gate": {"mean_yd": 0.75, "max_yd": 1.5},
        "pass_mean": bool(means and float(np.mean(means)) < 0.75),
        "pass_max": bool(maxes and float(np.max(maxes)) < 1.5),
        "frame": "soccer",
        "points": "halfway line x centre circle: soccer (0, +/-10.0066) yd",
        "independence": "points located from the image-space line and conic only; "
                        "the camera model only back-projects them",
        "verify_by_eye": "eval/m1/m1_acceptance_points.jpg",
    }
    if eval_dir is not None and tiles:
        cols = 2
        nrow = (len(tiles) + cols - 1) // cols
        sheet = np.full((nrow * 428, cols * 760, 3), 20, np.uint8)
        for k, t in enumerate(tiles):
            r_, c_ = divmod(k, cols)
            sheet[r_ * 428:(r_ + 1) * 428, c_ * 760:(c_ + 1) * 760] = t
        cv2.imwrite(str(eval_dir / "m1_acceptance_points.jpg"), sheet,
                    [cv2.IMWRITE_JPEG_QUALITY, 90])
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="ur.calibrate.accept")
    p.add_argument("work")
    p.add_argument("--eval-dir", default="eval/m1")
    p.add_argument("-n", type=int, default=20,
                   help="held-out frames. 20 is what eval/m1/m1_acceptance.json "
                        "records; docs/04 asks for at least 10. The default "
                        "matches the committed evidence so the plain command "
                        "reproduces the number in the write-up.")
    a = p.parse_args(argv)
    work, ev = Path(a.work), Path(a.eval_dir)
    ev.mkdir(parents=True, exist_ok=True)
    res = run_accept(work, n_holdout=a.n, eval_dir=ev)
    (ev / "m1_acceptance.json").write_text(json.dumps(res, indent=2) + "\n",
                                           encoding="utf-8")
    print(f"[accept] {res['n_correspondences']} held-out correspondences on "
          f"{len(res['held_out_frames'])} frames")
    print(f"{'frame':>7} {'far yd':>9} {'near yd':>9} {'max yd':>9}")
    for r in res["per_frame"]:
        if "mean_yd" not in r:
            print(f"{r['frame']:>7}   {r.get('note', '')}")
            continue
        print(f"{r['frame']:>7} {r['err_far_yd']:>9.4f} {r['err_near_yd']:>9.4f} "
              f"{r['max_yd']:>9.4f}")
    print(f"\n  mean error : {res['mean_error_yd']:.4f} yd  (gate < 0.75)  "
          f"{'PASS' if res['pass_mean'] else 'FAIL'}")
    print(f"  max error  : {res['max_error_yd']:.4f} yd  (gate < 1.5)   "
          f"{'PASS' if res['pass_max'] else 'FAIL'}")
    print(f"\n  verify the points by eye: {ev / 'm1_acceptance_points.jpg'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
