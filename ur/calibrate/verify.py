"""The verification render, and M1's acceptance numbers.

Two outputs, and the order matters. The video is first because it is the only
thing that can catch a calibration that is wrong in a way the residual likes: a
fit that has locked onto the ultimate paint instead of the soccer paint, or onto
one arc of the circle, reports a comfortable number and is badly wrong. Lines
drawn on the grass through a full pan cannot hide that.

The numbers are second and are deliberately *held out*. The per-frame residual
in calibration.json is a training error: it is measured on the very pixels the
pose was fitted to, so it can only flatter. M1's gate asks for something else -
points whose field positions are known independently, checked on frames the fit
never saw.

    python -m ur.calibrate.verify work/p0001 --video --accept
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

import cv2
import numpy as np

from . import features as F
from . import fit, mask, paint, render, run
from . import world as W
from .camera import FixedCamera, Pose


def load(work: Path) -> tuple[FixedCamera, list[Pose | None], dict]:
    cal = json.loads((work / "calibration.json").read_text(encoding="utf-8"))
    cam = FixedCamera(C=np.array(cal["camera"]["position_yd"], float),
                      image_w=cal["camera"]["image_w"],
                      image_h=cal["camera"]["image_h"])
    poses: list[Pose | None] = []
    for rec in cal["frames"]:
        if rec.get("H") is None:
            poses.append(None)
            continue
        c = rec["camera"]
        poses.append(Pose(pan=np.radians(c["pan_deg"]), tilt=np.radians(c["tilt_deg"]),
                          f=c["focal_px"], roll=np.radians(c["roll_deg"])))
    return cam, poses, cal


# --------------------------------------------------------------------------- #
# the render
# --------------------------------------------------------------------------- #

def make_video(work: Path, out: Path, *, fps: int = 15, show_ultimate: bool = True,
               every: int = 1) -> Path:
    cam, poses, cal = load(work)
    paths = sorted((work / "frames").glob("*.jpg"))
    rng = np.random.default_rng(run.SEED)
    rm = mask.build(paths)

    vt = cal.get("venue_transform", {})
    venue = W.VenueTransform(x_sign=vt.get("x_sign", 1), y_sign=vt.get("y_sign", 1),
                             x_offset=vt.get("x_offset", 60.0),
                             y_offset=vt.get("y_offset", W.UFA_WIDTH / 2),
                             source=vt.get("source", ""),
                             residual_yd=vt.get("residual_yd"))
    flen = (cal.get("field_length") or {}).get("field_length_yd") or 120.0
    field = W.UltimateField(length_yd=flen)

    tmp = out.parent / "_frames"
    if tmp.exists():
        for f in tmp.glob("*.jpg"):
            f.unlink()
    tmp.mkdir(parents=True, exist_ok=True)

    n = 0
    for i, (p, pose) in enumerate(zip(paths, poses)):
        if i % every:
            continue
        bgr = cv2.imread(str(p))
        rec = cal["frames"][i]
        if pose is None:
            img = bgr.copy()
            cv2.putText(img, f"frame {i}  NO CALIBRATION", (14, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (60, 60, 255), 2, cv2.LINE_AA)
        else:
            px, pm = run.paint_pixels(bgr, rm.mask, rng=rng)
            res = rec.get("residual_yd")
            conf = rec.get("confidence", 0.0)
            label = (f"f{i:04d}  residual {res:.3f} yd  confidence {conf:.2f}  "
                     f"focal {pose.f:.0f}px  pan {np.degrees(pose.pan):+.1f}deg"
                     if res is not None else f"f{i:04d}  no residual")
            img = render.draw(bgr, cam, pose, venue=venue if show_ultimate else None,
                              field=field if show_ultimate else None,
                              paint=pm, label=label,
                              opts=render.RenderOptions(show_ultimate=show_ultimate,
                                                        show_paint=True))
            img = render.legend(img)
        cv2.imwrite(str(tmp / f"{n:06d}.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 90])
        n += 1

    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
           "-framerate", str(fps), "-start_number", "0",
           "-i", str(tmp / "%06d.jpg"),
           "-c:v", "libx264", "-crf", "18", "-preset", "medium",
           "-pix_fmt", "yuv420p", str(out)]
    subprocess.run(cmd, check=True)
    for f in tmp.glob("*.jpg"):
        f.unlink()
    tmp.rmdir()
    return out


# --------------------------------------------------------------------------- #
# held-out acceptance
# --------------------------------------------------------------------------- #

def accept(work: Path, *, n_holdout: int = 10, seed: int = 20260827) -> dict:
    """M1's gate, measured on frames the pose was not fitted to being right about.

    The check uses the same two features the pipeline knows - but the *test* is
    different from the *fit*: for each held-out frame, take the paint pixels
    RANSAC independently says lie on the centre circle, back-project them, and
    ask how far they land from a circle of exactly 10.0066 yd. That distance is a
    real-world error in yards against geometry fixed by the Laws of the Game, not
    a self-consistency score.

    Honest about what it is not: these are still soccer-frame errors. Ultimate
    frame error is this plus the venue transform's, which is reported separately
    because the transform is the weaker of the two and blending them would hide
    that.
    """
    cam, poses, cal = load(work)
    paths = sorted((work / "frames").glob("*.jpg"))
    rng = np.random.default_rng(seed)
    rm = mask.build(paths)

    usable = [i for i, (p, rec) in enumerate(zip(poses, cal["frames"]))
              if p is not None and rec.get("confidence", 0) >= 0.5]
    if len(usable) < n_holdout:
        raise RuntimeError(f"only {len(usable)} confident frames")
    picks = sorted(rng.choice(usable, size=n_holdout, replace=False).tolist())

    rows = []
    for i in picks:
        bgr = cv2.imread(str(paths[i]))
        region = cv2.bitwise_and(rm.mask, cv2.bitwise_not(F.player_mask(bgr)))
        pm = paint.largest_components(paint.paint_mask(bgr, region=region), min_area=60)
        ell = F.find_centre_circle_ransac(pm)
        if ell is None or ell.inliers is None or len(ell.inliers) < 200:
            rows.append({"frame": i, "n": 0, "mean_yd": None, "max_yd": None,
                         "note": "no independent conic on this frame"})
            continue
        px = ell.inliers
        if len(px) > 1500:
            px = px[rng.choice(len(px), 1500, replace=False)]
        wpt, ok = fit.backproject(cam, poses[i], px)
        good = ok & np.isfinite(wpt).all(axis=1)
        err = np.abs(np.hypot(wpt[good, 0], wpt[good, 1]) - W.CENTRE_CIRCLE_R)
        # A handful of pixels near the horizon back-project enormously; report
        # both the full distribution and a 99th-percentile-trimmed version so a
        # single wild pixel cannot decide a pass or a fail either way.
        trim = err[err <= np.percentile(err, 99)]
        rows.append({"frame": i, "n": int(good.sum()),
                     "mean_yd": round(float(err.mean()), 4),
                     "p95_yd": round(float(np.percentile(err, 95)), 4),
                     "max_yd": round(float(err.max()), 4),
                     "mean_trimmed_yd": round(float(trim.mean()), 4),
                     "max_trimmed_yd": round(float(trim.max()), 4)})

    scored = [r for r in rows if r.get("mean_yd") is not None]
    mean_of_means = float(np.mean([r["mean_yd"] for r in scored]))
    worst = float(np.max([r["max_yd"] for r in scored]))
    worst_trim = float(np.max([r["max_trimmed_yd"] for r in scored]))
    return {
        "held_out_frames": picks,
        "per_frame": rows,
        "mean_error_yd": round(mean_of_means, 4),
        "max_error_yd": round(worst, 4),
        "max_error_trimmed_yd": round(worst_trim, 4),
        "gate": {"mean_yd": 0.75, "max_yd": 1.5},
        "pass_mean": bool(mean_of_means < 0.75),
        "pass_max": bool(worst < 1.5),
        "pass_max_trimmed": bool(worst_trim < 1.5),
        "frame": "soccer",
        "note": "Errors are distances from back-projected circle pixels to a circle "
                "of exactly 10.0066 yd (9.15 m, Laws of the Game). Independent of "
                "the fit in that RANSAC re-selects the pixels per frame, but it "
                "tests the same two features the pipeline uses - there is no other "
                "exactly-known geometry on this pitch to test against.",
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="ur.calibrate.verify")
    p.add_argument("work")
    p.add_argument("--eval-dir", default="eval/m1")
    p.add_argument("--video", action="store_true")
    p.add_argument("--accept", action="store_true")
    p.add_argument("--every", type=int, default=1)
    args = p.parse_args(argv)
    work, ev = Path(args.work), Path(args.eval_dir)
    ev.mkdir(parents=True, exist_ok=True)

    if args.video:
        out = make_video(work, ev / f"{work.name}_verification.mp4", every=args.every)
        print(f"[verify] wrote {out} ({out.stat().st_size / 1e6:.1f} MB)")

    if args.accept:
        res = accept(work)
        (ev / "m1_acceptance.json").write_text(json.dumps(res, indent=2) + "\n",
                                               encoding="utf-8")
        print(f"\n[verify] M1 acceptance, {len(res['held_out_frames'])} held-out frames")
        print(f"{'frame':>7} {'n px':>7} {'mean yd':>9} {'p95 yd':>8} {'max yd':>8} "
              f"{'mean trim':>10} {'max trim':>9}")
        for r in res["per_frame"]:
            if r.get("mean_yd") is None:
                print(f"{r['frame']:>7} {'-':>7}  {r.get('note', '')}")
                continue
            print(f"{r['frame']:>7} {r['n']:>7} {r['mean_yd']:>9.4f} {r['p95_yd']:>8.4f} "
                  f"{r['max_yd']:>8.4f} {r['mean_trimmed_yd']:>10.4f} "
                  f"{r['max_trimmed_yd']:>9.4f}")
        print(f"\n  mean over frames : {res['mean_error_yd']:.4f} yd   "
              f"(gate < 0.75)  {'PASS' if res['pass_mean'] else 'FAIL'}")
        print(f"  worst single px  : {res['max_error_yd']:.4f} yd   "
              f"(gate < 1.5)   {'PASS' if res['pass_max'] else 'FAIL'}")
        print(f"  worst, 99% trim  : {res['max_error_trimmed_yd']:.4f} yd   "
              f"(gate < 1.5)   {'PASS' if res['pass_max_trimmed'] else 'FAIL'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
