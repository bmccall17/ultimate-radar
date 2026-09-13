"""M1 - calibrate one possession. Writes calibration.json.

    python -m ur.calibrate.run work/p0001

The pass in order:

1. **Registration mask.** Nothing sees a raw frame (docs/08-risks.md #10).
2. **Anchor.** One frame with a clean centre circle. RANSAC the conic, grid the
   camera centre, seed each pose from the ellipse, refine in world coordinates.
3. **Camera centre.** Bundled over frames spread across the pan. One centre has
   to explain all of them, which is what a single frame cannot pin down.
4. **Sequential pass.** Walk outward from the anchor, initialising each frame
   from its neighbour and re-associating paint pixels to the model at every
   step. Association is model-guided rather than re-detected per frame: once the
   camera is roughly known, "which pixels are the circle" is a question the model
   answers better than any detector, and it degrades gracefully when half the
   circle leaves the frame.
5. **Residual, confidence, and honesty.** Per AD-1, a frame whose calibration is
   weak must down-weight its detections rather than silently corrupt them. The
   confidence written here is what the tracker will read.

Every position this produces is in the *soccer* frame. Turning that into the
ultimate frame is a separate measurement with its own error - see venue.py.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from . import features, fit, mask, paint
from . import world as W
from .camera import FixedCamera, Pose

SEED = 20260827
MAX_FEATURE_PX = 900          # per feature per frame; more is slower, not better
ASSOC_GATE_YD = (2.5, 1.2, 0.7)
LINE_EXTENT_YD = 42.0
MIN_TOTAL_PX = 150


# --------------------------------------------------------------------------- #
# per-frame observation
# --------------------------------------------------------------------------- #

@dataclass
class Frame:
    index: int
    path: Path
    paint_px: np.ndarray = field(default_factory=lambda: np.zeros((0, 2)))
    pose: Pose | None = None
    rms_yd: float = float("nan")
    p95_yd: float = float("nan")
    n_circle: int = 0
    n_line: int = 0
    confidence: float = 0.0
    note: str = ""


def paint_pixels(bgr: np.ndarray, region: np.ndarray, *,
                 rng: np.random.Generator, max_px: int = 4000) -> tuple[np.ndarray, np.ndarray]:
    pl = features.player_mask(bgr)
    usable = cv2.bitwise_and(region, cv2.bitwise_not(pl))
    pm = paint.largest_components(paint.paint_mask(bgr, region=usable), min_area=60)
    ys, xs = np.nonzero(pm)
    px = np.stack([xs, ys], axis=1).astype(np.float64)
    if len(px) > max_px:
        px = px[rng.choice(len(px), max_px, replace=False)]
    return px, pm


def associate(cam: FixedCamera, pose: Pose, px: np.ndarray, gate_yd: float,
              *, r: float = W.CENTRE_CIRCLE_R,
              max_px: int = MAX_FEATURE_PX,
              rng: np.random.Generator | None = None) -> tuple[np.ndarray, np.ndarray]:
    """Split detected paint into circle pixels and halfway-line pixels.

    Done in world coordinates, so the gate is a distance in yards and is
    automatically scale-aware: the same 1.2 yd tolerance is a wide gate for
    near paint and a tight one for far paint, which is exactly the right
    behaviour and is awkward to express in pixels.
    """
    if len(px) == 0:
        return np.zeros((0, 2)), np.zeros((0, 2))
    wpt, ok = fit.backproject(cam, pose, px)
    good = ok & np.isfinite(wpt).all(axis=1)
    if not good.any():
        return np.zeros((0, 2)), np.zeros((0, 2))
    rad = np.hypot(wpt[:, 0], wpt[:, 1])
    on_circle = good & (np.abs(rad - r) < gate_yd)
    on_line = (good & ~on_circle & (np.abs(wpt[:, 0]) < gate_yd)
               & (np.abs(wpt[:, 1]) < LINE_EXTENT_YD))
    cpx, lpx = px[on_circle], px[on_line]
    if rng is not None:
        if len(cpx) > max_px:
            cpx = cpx[rng.choice(len(cpx), max_px, replace=False)]
        if len(lpx) > max_px:
            lpx = lpx[rng.choice(len(lpx), max_px, replace=False)]
    return cpx, lpx


def icp(cam: FixedCamera, pose: Pose, px: np.ndarray,
        rng: np.random.Generator) -> tuple[Pose, fit.WorldFit | None]:
    """Associate, refine, repeat with a shrinking gate."""
    cur, res = pose, None
    for gate in ASSOC_GATE_YD:
        cpx, lpx = associate(cam, cur, px, gate, rng=rng)
        if len(cpx) + len(lpx) < MIN_TOTAL_PX:
            break
        res = fit.refine_world(cam, cur, cpx, lpx)
        cur = res.pose
    return cur, res


def confidence_of(res: fit.WorldFit | None) -> float:
    """Turn a fit into the number AD-1 says the tracker must read.

    Three things make a calibration weak and they are not interchangeable, so
    they multiply rather than average: the residual being large, there being
    little paint to fit to, and - the one an rms hides completely - the halfway
    line being absent, which leaves the circle alone and the rotation about its
    axis barely constrained.
    """
    # res.ok already rejects the two failures that produce a *smaller* residual
    # than a good fit: a collapsed solve and a fit to too short an arc. Without
    # that, an rms of exactly 0.0000 scores a perfect quality term - which is
    # what p0003 did before this check existed.
    if res is None or not res.ok:
        return 0.0
    quality = float(np.exp(-max(res.rms_yd, 0.0) / 0.45))
    support = float(np.clip((res.n_circle + res.n_line) / 500.0, 0.0, 1.0))
    # A circle with no line is a near-degenerate view: it pins the plane but
    # leaves spin about the circle's normal weakly observed.
    geometry = 1.0 if res.n_line >= 40 else 0.55
    return float(np.clip(quality * support * geometry, 0.0, 1.0))


# --------------------------------------------------------------------------- #
# the pass
# --------------------------------------------------------------------------- #

def choose_anchor(frames: list[Frame], region: np.ndarray, rng) -> tuple[int, object]:
    """The frame with the strongest conic. Everything else is initialised from it."""
    best = (None, None, -1)
    for f in frames:
        bgr = cv2.imread(str(f.path))
        px, pm = paint_pixels(bgr, region, rng=rng)
        ell = features.find_centre_circle_ransac(pm)
        if ell is None:
            continue
        score = ell.n_px / max(ell.rms_px, 0.5)
        if score > best[2]:
            best = (f.index, ell, score)
    if best[0] is None:
        raise RuntimeError("no frame yielded a centre circle; cannot bootstrap")
    return best[0], best[1]


def calibrate(work: Path, *, anchor_stride: int = 20, bundle_n: int = 9,
              verbose: bool = True) -> dict:
    rng = np.random.default_rng(SEED)
    frame_paths = sorted((work / "frames").glob("*.jpg"))
    if not frame_paths:
        raise SystemExit(f"no frames in {work / 'frames'}")
    frames = [Frame(index=i, path=p) for i, p in enumerate(frame_paths)]

    rm = mask.build(frame_paths)
    if verbose:
        print(f"[calib] mask: {rm.to_dict()}")

    probe = [f for f in frames[::anchor_stride]]
    a_idx, ell = choose_anchor(probe, rm.mask, rng)
    if verbose:
        print(f"[calib] anchor frame {a_idx}: ellipse n={ell.n_px} rms={ell.rms_px:.2f}px")

    bgr = cv2.imread(str(frames[a_idx].path))
    h, w = bgr.shape[:2]
    px, pm = paint_pixels(bgr, rm.mask, rng=rng)
    dist = paint.distance_field(pm)
    cands = fit.bootstrap(dist, w, h, W.soccer_features(), ell, top_k=5,
                          c_grid={"sx": np.linspace(-26, 26, 9),
                                  "sy": np.linspace(-60, -30, 9),
                                  "sz": np.linspace(6, 22, 7)})
    if not cands:
        raise RuntimeError("bootstrap found no plausible camera")

    best = None
    for _, cam, pose in cands:
        p, res = icp(cam, pose, px, rng)
        if res is not None and (best is None or res.rms_yd < best[1].rms_yd):
            best = (cam, res)
    if best is None:
        raise RuntimeError("no bootstrap candidate converged")
    cam, anchor_res = best
    if verbose:
        print(f"[calib] anchor fit: C={np.round(cam.C, 2)} rms={anchor_res.rms_yd:.4f} yd")

    # --- pin the camera centre over several pans ---------------------------- #
    step = max(1, len(frames) // (bundle_n + 1))
    bundle_idx, obs, poses = [], [], []
    for i in range(step, len(frames) - 1, step):
        b = cv2.imread(str(frames[i].path))
        p_i, _ = paint_pixels(b, rm.mask, rng=rng)
        pose_i, res_i = icp(cam, anchor_res.pose, p_i, rng)
        if res_i is None or res_i.n_line < 40 or res_i.rms_yd > 1.5:
            continue
        cpx, lpx = associate(cam, pose_i, p_i, ASSOC_GATE_YD[-1], rng=rng)
        if len(cpx) + len(lpx) < MIN_TOTAL_PX:
            continue
        bundle_idx.append(i)
        obs.append((cpx, lpx))
        poses.append(pose_i)
    if len(obs) >= 3:
        cam, _ = fit.bundle_world(cam, poses, obs)
        if verbose:
            print(f"[calib] bundled over {len(obs)} frames -> C={np.round(cam.C, 2)}")
    elif verbose:
        print(f"[calib] only {len(obs)} frames usable for the bundle; centre left "
              "at the anchor's estimate")

    # --- sequential pass, outward from the anchor --------------------------- #
    frames[a_idx].pose = anchor_res.pose
    order = ([a_idx] + list(range(a_idx + 1, len(frames)))
             + list(range(a_idx - 1, -1, -1)))
    prev_pose = anchor_res.pose
    for k, i in enumerate(order):
        f = frames[i]
        if i == a_idx + 1 or i == a_idx:
            prev_pose = anchor_res.pose
        elif i == a_idx - 1:
            prev_pose = anchor_res.pose
        b = cv2.imread(str(f.path))
        f.paint_px, _ = paint_pixels(b, rm.mask, rng=rng)
        pose, res = icp(cam, prev_pose, f.paint_px, rng)
        if res is None:
            f.note = "too little paint to fit"
            f.confidence = 0.0
            f.pose = prev_pose
        else:
            f.pose = pose
            f.rms_yd, f.p95_yd = res.rms_yd, res.p95_yd
            f.n_circle, f.n_line = res.n_circle, res.n_line
            f.confidence = confidence_of(res)
            prev_pose = pose
        if verbose and k % 40 == 0:
            print(f"[calib] frame {i:4d}  rms {f.rms_yd:7.4f} yd  conf {f.confidence:.2f}  "
                  f"circle {f.n_circle:4d} line {f.n_line:4d}")

    return {"camera": cam, "frames": frames, "mask": rm, "anchor": a_idx}


# --------------------------------------------------------------------------- #

def write_calibration(work: Path, res: dict, venue_info: dict) -> dict:
    """calibration.json per docs/03-data-contracts.md.

    `H` is image pixel -> **ultimate** field yards, which is what the contract
    says and what everything downstream expects. The soccer-frame pose is stored
    alongside it, because that is what was actually fitted and the venue
    transform between the two carries its own error - see the two error budgets
    in docs/04-milestones.md M1.
    """
    cam, frames = res["camera"], res["frames"]
    vt: W.VenueTransform = venue_info["transform"]
    A = np.array([[vt.x_sign, 0.0, vt.x_offset],
                  [0.0, vt.y_sign, vt.y_offset],
                  [0.0, 0.0, 1.0]])

    out_frames = []
    for f in frames:
        if f.pose is None:
            out_frames.append({"f": f.index, "H": None, "residual_yd": None,
                               "confidence": 0.0, "shot": 0,
                               "note": f.note or "no pose"})
            continue
        H_w2i = cam.homography(f.pose)
        H_img2soccer = np.linalg.inv(H_w2i)
        H = A @ H_img2soccer
        H = H / H[2, 2]
        out_frames.append({
            "f": f.index,
            "H": [[round(float(v), 10) for v in row] for row in H],
            "residual_yd": None if not np.isfinite(f.rms_yd) else round(float(f.rms_yd), 5),
            "confidence": round(float(f.confidence), 4),
            "shot": 0,
            "camera": {**f.pose.to_dict(),
                       "n_circle_px": f.n_circle, "n_line_px": f.n_line,
                       "p95_yd": None if not np.isfinite(f.p95_yd) else round(float(f.p95_yd), 5)},
            **({"note": f.note} if f.note else {}),
        })

    doc = {
        "schema": "ultimate-radar/calibration@1",
        "possession_id": work.name,
        "shots": [{"from": 0, "to": len(frames) - 1,
                   "note": "one shot; M0 measured that a possession on this "
                           "broadcast typically contains no camera cut"}],
        "method": {
            "model": "fixed camera centre, per-frame pan/tilt/roll/focal",
            "why": "AD-4 as amended: the camera does not translate, and the only "
                   "geometry reliably in shot is a conic and a line (7 constraints), "
                   "which is one short of a free homography's 8 degrees of freedom",
            "fitted_to": "soccer centre circle (radius 9.15 m) and halfway line",
            "residual_units": "yards on the ground plane, in the soccer frame",
            "registration_mask": res["mask"].to_dict(),
            "anchor_frame": res["anchor"],
            "seed": SEED,
        },
        "camera": cam.to_dict(),
        "venue_transform": vt.to_dict(),
        "field_length": venue_info["length"],
        "anchors": [{"shot": 0, "frame": res["anchor"],
                     "correspondences": "none clicked - the anchor was solved from "
                                        "the detected conic, then bundled over "
                                        "frames spread across the pan"}],
        "frames": out_frames,
    }
    (work / "calibration.json").write_text(json.dumps(doc, indent=1) + "\n",
                                           encoding="utf-8")
    return doc


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="ur.calibrate.run")
    p.add_argument("work", help="possession working directory, e.g. work/p0001")
    p.add_argument("--eval-dir", default="eval/m1")
    args = p.parse_args(argv)
    work = Path(args.work)
    ev = Path(args.eval_dir)
    ev.mkdir(parents=True, exist_ok=True)

    res = calibrate(work)
    cam, frames = res["camera"], res["frames"]
    conf = np.array([f.confidence for f in frames])
    rms = np.array([f.rms_yd for f in frames])
    print(f"\n[calib] {len(frames)} frames: median rms {np.nanmedian(rms):.4f} yd, "
          f"confidence >=0.5 on {(conf >= 0.5).mean():.0%} of frames")

    from . import venue as V
    pm = V.build_map(cam, frames)
    print(f"[venue] paint map: {pm.n_points} points from {pm.n_frames} frames")
    V.render_map(pm, ev / "paint_map.png")
    length = V.decide_field_length(pm)
    print(f"[venue] field length: {length['verdict']} - {length['why']}")
    for c in length["all_x_peaks"]:
        print(f"        x peak {c['x_yd']:+8.2f} yd  count {c['count']:8.0f}  "
              f"prominence {c['prominence']:.2f}")
    flen = length["field_length_yd"] or 120.0
    vt = V.measure_transform(pm, flen)
    print(f"[venue] transform: {vt.to_dict()}")

    doc = write_calibration(work, res, {"transform": vt, "length": length})
    print(f"[calib] wrote {work / 'calibration.json'}")

    np.savez_compressed(ev / "calib_state.npz",
                        C=cam.C, image_w=cam.image_w, image_h=cam.image_h,
                        pan=np.array([f.pose.pan if f.pose else np.nan for f in frames]),
                        tilt=np.array([f.pose.tilt if f.pose else np.nan for f in frames]),
                        roll=np.array([f.pose.roll if f.pose else np.nan for f in frames]),
                        focal=np.array([f.pose.f if f.pose else np.nan for f in frames]),
                        rms=rms, conf=conf, anchor=res["anchor"],
                        mask=res["mask"].mask)
    print(f"[calib] wrote {ev / 'calib_state.npz'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
