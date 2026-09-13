"""M2 — run the detector over a possession and write detections.json.

    python -m ur.detect.run work/p0001

Per docs/03-data-contracts.md. Two things this stage does beyond detecting:

**Projects the foot point to field coordinates**, using the per-frame homography
from M1, and only when that frame's calibration confidence allows it — AD-1 says
a frame whose homography is poor must down-weight its detections rather than
silently corrupt them, so `field` is simply absent below the threshold rather
than being filled in with something plausible.

**Flags what is not a player.** M0 measured the reject class and the M0 review
sharpened it: referees stand on the field in black-and-grey stripes, and
photographers and camera operators sit on the grass just beyond the far
touchline, inside the frame, in nearly every wide shot. The geometric filter
catches most of the second group and cannot catch the first — that is `ur.team`'s
job, and the mechanism is not the one predicted here. The M0 review expected
luminance *variance*; measured, a Chill jersey's light number and a box drawn
round two overlapping players both have high torso variance too. What separates a
referee is that stripes are periodic and vertically coherent. See `ur/team.py`.

The bounds test runs in the **soccer** frame, not the ultimate frame. Across the
pitch the venue transform is measured; along it the x offset is still an
assumption (docs/08-risks.md #5), so an along-field rejection would be
enforcing a number nobody has measured. The possession is played around midfield
where that test would be inactive anyway, so nothing is lost by being honest
about it.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np

from ..calibrate import fit as CFIT
from ..calibrate import world as W
from ..calibrate.camera import FixedCamera, Pose
from .model import SEED, PersonDetector

MIN_CALIB_CONFIDENCE = 0.5      # docs/03: below this, no observed samples
BOUNDS_MARGIN_YD = 2.0          # AD-3
MIN_BOX_H = 12                  # below this it is not a player at this framing

# How far one pixel of foot-point error moves a position on the ground. Near the
# horizon this diverges: a person standing at the advertising boards, well beyond
# the touchline, back-projects to y = 21-29 yd and lands *inside* the field
# bounds, so the geometric reject filter waves through every camera operator and
# photographer at the far edge. The distance is not wrong so much as meaningless
# there, and the honest response is to refuse to state it rather than to state it
# and filter on it.
MAX_YD_PER_PX = 0.45
# Bottom-of-box against a real foot. M2 assumed 3.0 px and said so. M3 measured it
# on 50 hand-checked detections (eval/m3/foot_labels.json): the 2-D offset has an
# rms of 5.83 px, nearly twice the assumption, and at 3.0 px only 46 % of truths
# fell inside the disc the viewer would draw - against the >= 80 % that
# docs/05-uncertainty.md makes the product's honesty argument rest on. An
# uncertainty disc that does not contain the truth is worse than no disc.
#
# The value is the rms of the measured offset, which is the ordinary definition of
# a 1-sigma scale, and it delivers 94 % containment. 4.08 px would hit exactly
# 80 %; the rms is preferred because it is a definition rather than a number
# reverse-engineered from the gate it has to pass.
FOOT_UNCERTAINTY_PX = 5.83

# A standing adult, in yards. Used only to ask whether a box is the size a person
# at the claimed distance would be - not to measure anybody.
PLAYER_HEIGHT_YD = 2.02         # ~1.85 m
MIN_HEIGHT_RATIO = 0.62         # observed box height / height predicted at that spot


def load_calibration(work: Path):
    cal = json.loads((work / "calibration.json").read_text(encoding="utf-8"))
    cam = FixedCamera(C=np.array(cal["camera"]["position_yd"], float),
                      image_w=cal["camera"]["image_w"],
                      image_h=cal["camera"]["image_h"])
    poses, confs = [], []
    for rec in cal["frames"]:
        if rec.get("H") is None:
            poses.append(None)
            confs.append(0.0)
            continue
        c = rec["camera"]
        poses.append(Pose(pan=np.radians(c["pan_deg"]), tilt=np.radians(c["tilt_deg"]),
                          f=c["focal_px"], roll=np.radians(c["roll_deg"])))
        confs.append(float(rec.get("confidence", 0.0)))
    return cal, cam, poses, confs


def expected_height_px(cam: FixedCamera, pose: Pose, sx: float, sy: float) -> float | None:
    """Pixel height of a standing person at soccer-frame (sx, sy).

    Projects the foot and the top of a PLAYER_HEIGHT_YD vertical segment there.
    """
    import numpy as _np

    from ..calibrate.camera import intrinsics, rotation

    R = rotation(pose.pan, pose.tilt, pose.roll)
    t = -R @ _np.asarray(cam.C, float)
    K = intrinsics(pose.f, cam.image_w, cam.image_h)
    out = []
    for z in (0.0, PLAYER_HEIGHT_YD):
        p = K @ (R @ _np.array([sx, sy, z]) + t)
        if p[2] <= 1e-6:
            return None
        out.append(p[:2] / p[2])
    return float(abs(out[0][1] - out[1][1]))


def soccer_bounds(cal: dict) -> dict:
    """Ultimate sidelines in soccer-frame y, with the AD-3 margin."""
    vt = cal.get("venue_transform", {})
    y0 = -float(vt.get("y_offset", W.UFA_WIDTH / 2.0))     # near sideline
    y1 = y0 + W.UFA_WIDTH                                  # far sideline
    flen = (cal.get("field_length") or {}).get("field_length_yd") or 120.0
    return {"y_near": y0, "y_far": y1,
            "y_min": y0 - BOUNDS_MARGIN_YD, "y_max": y1 + BOUNDS_MARGIN_YD,
            "x_min": -flen / 2.0 - BOUNDS_MARGIN_YD,
            "x_max": flen / 2.0 + BOUNDS_MARGIN_YD,
            "x_is_measured": bool((cal.get("venue_transform") or {}).get("measured"))
                             and (cal.get("field_length") or {}).get("verdict") != "unresolved"}


def run(work: Path, *, threshold: float = 0.25, batch: int = 8,
        model_id: str | None = None, verbose: bool = True) -> dict:
    cal, cam, poses, confs = load_calibration(work)
    clip = json.loads((work / "clip.json").read_text(encoding="utf-8"))
    paths = sorted((work / "frames").glob("*.jpg"))
    bounds = soccer_bounds(cal)

    det = PersonDetector(model_id or "ustc-community/dfine-medium-coco",
                         threshold=threshold, batch_size=batch)
    if verbose:
        print(f"[detect] {det.info()}")
        print(f"[detect] soccer-frame sidelines y = {bounds['y_near']:.2f} .. "
              f"{bounds['y_far']:.2f}; along-field bounds "
              f"{'measured' if bounds['x_is_measured'] else 'ASSUMED, not enforced'}")

    A = np.array([[cal["venue_transform"]["x_sign"], 0.0, cal["venue_transform"]["x_offset"]],
                  [0.0, cal["venue_transform"]["y_sign"], cal["venue_transform"]["y_offset"]],
                  [0.0, 0.0, 1.0]])

    frames_out, n_raw, n_kept = [], 0, 0
    for i0 in range(0, len(paths), batch):
        chunk_paths = paths[i0:i0 + batch]
        imgs = [cv2.imread(str(p)) for p in chunk_paths]
        results = det.detect(imgs)
        for k, dets in enumerate(results):
            i = i0 + k
            pose, conf = poses[i], confs[i]
            recs = []
            for d in dets:
                n_raw += 1
                if d.height < MIN_BOX_H:
                    continue
                rec = {"box": [round(float(v), 2) for v in d.box],
                       "score": round(float(d.score), 4),
                       "foot": [round(float(v), 2) for v in d.foot],
                       "team": None, "team_score": None}
                if pose is not None and conf >= MIN_CALIB_CONFIDENCE:
                    foot = np.array([d.foot, [d.foot[0], d.foot[1] + 1.0]])
                    wpt, ok = CFIT.backproject(cam, pose, foot)
                    if ok[0] and np.isfinite(wpt[0]).all() and np.isfinite(wpt[1]).all():
                        sx, sy = float(wpt[0][0]), float(wpt[0][1])
                        yd_per_px = float(np.hypot(*(wpt[1] - wpt[0])))
                        rec["yd_per_px"] = round(yd_per_px, 4)
                        rec["sigma_yd"] = round(yd_per_px * FOOT_UNCERTAINTY_PX, 3)
                        if yd_per_px > MAX_YD_PER_PX:
                            rec["in_bounds"] = False
                            rec["note"] = (f"{yd_per_px:.2f} yd per pixel of foot error - "
                                           "too near the horizon for the position to mean "
                                           "anything, so none is stated")
                        else:
                            rec["soccer"] = [round(sx, 3), round(sy, 3)]
                            u = A @ np.array([sx, sy, 1.0])
                            rec["field"] = [round(float(u[0]), 3), round(float(u[1]), 3)]

                            # Is this box the size a standing person at that spot
                            # would be? The geometric bounds test alone waves the
                            # far-side camera crew through, because a foot point
                            # at the advertising boards back-projects to y = 21-29
                            # and lands inside the field. But those people are
                            # further away than that position implies, so their
                            # boxes are far too short for it - which says plainly
                            # that their feet are not on the ground where the
                            # homography claims.
                            exp_h = expected_height_px(cam, pose, sx, sy)
                            ratio = (d.height / exp_h) if exp_h and exp_h > 1e-6 else None
                            if ratio is not None:
                                rec["height_ratio"] = round(float(ratio), 3)

                            inb = bounds["y_min"] <= sy <= bounds["y_max"]
                            if bounds["x_is_measured"]:
                                inb = inb and bounds["x_min"] <= sx <= bounds["x_max"]
                            if inb and ratio is not None and ratio < MIN_HEIGHT_RATIO:
                                inb = False
                                rec["note"] = (f"box is {ratio:.2f} of the height a person "
                                               "standing there would be; its feet are not "
                                               "on the ground at that position")
                            rec["in_bounds"] = bool(inb)
                    else:
                        rec["in_bounds"] = None
                        rec["note"] = "foot point does not back-project"
                else:
                    rec["in_bounds"] = None
                    rec["note"] = ("calibration confidence below "
                                   f"{MIN_CALIB_CONFIDENCE}; no field position")
                recs.append(rec)
                n_kept += 1
            frames_out.append({"f": i, "dets": recs})
        if verbose and (i0 // batch) % 10 == 0:
            print(f"[detect] {i0 + len(chunk_paths)}/{len(paths)} frames")

    doc = {
        "schema": "ultimate-radar/detections@1",
        "possession_id": clip["possession_id"],
        "method": {
            "model": det.model_id,
            "licence": "Apache-2.0 code and Apache-2.0 weights, both checked "
                       "(docs/07-licenses.md)",
            "fine_tuned": False,
            "tiling": "none - whole frame. M0 measured players at 50-130 px, not the "
                      "25-45 px the architecture assumed, so SAHI is measure-first",
            "score_threshold": threshold,
            "min_box_height_px": MIN_BOX_H,
            "min_calibration_confidence": MIN_CALIB_CONFIDENCE,
            "max_yd_per_px": MAX_YD_PER_PX,
            "player_height_yd": PLAYER_HEIGHT_YD,
            "min_height_ratio": MIN_HEIGHT_RATIO,
            "foot_uncertainty_px": FOOT_UNCERTAINTY_PX,
            "sigma_note": "sigma_yd is foot_uncertainty_px multiplied by the local "
                          "ground-plane scale, so it grows with distance the way the "
                          "real uncertainty does. foot_uncertainty_px is MEASURED "
                          "(eval/m3/m3_foot_acceptance.json), not assumed: 5.83 px "
                          "rms on 50 hand-checked detections, giving 94 % containment "
                          "against the >= 80 % docs/05 requires. It covers the foot "
                          "point ONLY - M1 calibration error is separate and adds in "
                          "quadrature.",
            "bounds": bounds,
            "team_assignment": "not done here - M3 fills team and team_score",
            "seed": SEED,
        },
        "frames": frames_out,
    }
    (work / "detections.json").write_text(json.dumps(doc, indent=1) + "\n",
                                          encoding="utf-8")
    if verbose:
        per = n_kept / max(len(paths), 1)
        inb = sum(1 for fr in frames_out for d in fr["dets"] if d.get("in_bounds"))
        print(f"\n[detect] {n_kept} detections over {len(paths)} frames "
              f"({per:.1f}/frame); {inb} inside the field bounds "
              f"({inb / max(n_kept, 1):.0%})")
    return doc


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="ur.detect.run")
    p.add_argument("work")
    p.add_argument("--threshold", type=float, default=0.25)
    p.add_argument("--batch", type=int, default=8)
    p.add_argument("--model", default=None)
    a = p.parse_args(argv)
    run(Path(a.work), threshold=a.threshold, batch=a.batch, model_id=a.model)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
