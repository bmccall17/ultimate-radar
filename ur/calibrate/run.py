"""M1 - calibrate one possession. Writes calibration.json.

    python -m ur.calibrate.run work/p0001

The pass in order:

1. **Registration mask.** Nothing sees a raw frame (docs/08-risks.md #10).
2. **Anchor.** One frame with a clean centre circle. RANSAC the conic, grid the
   camera centre, seed each pose from the ellipse, refine in world coordinates.
3. **Camera centre.** Bundled over frames spread across the pan. One centre has
   to explain all of them, which is what a single frame cannot pin down. The
   bundle is then **accepted or rejected on evidence**: the possession is solved
   with both the bundled centre and the anchor's own, and whichever produces the
   higher mean per-frame confidence wins. The bundle helps p0001 and destroys
   p0003, and it reports success either way - see the note at the decision.
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

from . import features, fit, groundtruth, mask, paint
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
    # How far this frame's pose sits from what its neighbours predict, in yards.
    # Reported so the two halves of `confidence` can be told apart downstream.
    pose_disagreement_yd: float = 0.0
    # Reprojection error at the two exactly-known points, or None where the
    # geometry could not be detected. None is "not tested", never "passed".
    known_geometry_err_yd: float | None = None
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


# How much paint a fit must rest on before it is worth anything at all.
#
# This used to be a *ramp* rather than a floor: confidence was multiplied by
# `(n_circle + n_line) / 500`, so a frame seeing 200 px of paint could not score
# above 0.40 however well it fitted, and `docs/03`'s gate of 0.5 threw it away.
#
# **Measured, that ramp was anti-correlated with accuracy.** On p0002 the frames
# it gated out have a median residual of 0.159 yd against 0.223 for the frames it
# accepted; on p0003, 0.197 against 0.221. It was discarding the *better* fits,
# because a frame that sees a small, sharply-imaged patch of the centre circle
# fits it precisely, and a frame that sees a great deal of paint spread to the far
# side of the pitch fits more of it less well. Across the three possessions it
# rejected 22, 33 and 138 frames whose fits were sound - a quarter of p0003.
#
# `docs/03` says plainly what this number is: "confidence derives from the
# residual". It is a statement about how far out a position from this frame is
# likely to be, and paint count is not that. So the support test becomes what it
# always should have been - a precondition for the fit being meaningful at all,
# answered yes or no - and error in yards sets the value.
MIN_SUPPORT_PX = 120

# The scale that turns an error in yards into a confidence. Unchanged: a frame
# whose positions are out by 0.45 yd scores e^-1.
CONF_SCALE_YD = 0.45

# Half-width of the window a frame's pose is predicted from, for the out-of-sample
# check below, and the order of the curve fitted through it.
#
# **The order is 2 and that is not a detail.** With a straight line, a third of a
# second of a real pan is not straight, and the curvature lands in the residual as
# if it were error: on p0002, which pans 50 degrees in 18 seconds, the resulting
# "disagreement" correlates with the pan rate at **+0.66**. It was measuring the
# camera accelerating, and rejecting frames for it - worst on exactly the fast,
# hard-to-calibrate possessions the check exists to help.
#
# A quadratic absorbs constant angular acceleration, which is what an operator's
# hands actually produce. The same measurement on p0002 falls to **-0.04**, and
# accepted frames go from 100 to 141 of 270. On p0001, which barely pans, it moves
# the correlation from +0.19 to +0.14 and accepted frames from 321 to 340 - so the
# well-behaved possession does not pay for it either.
SMOOTH_HALF = 5
SMOOTH_DEG = 2

# A representative ground range, in yards, for converting an angular or focal
# disagreement into the positional error it causes. The camera sits off the near
# touchline and the play is 40-80 yd away; 60 is the middle of that and the
# conversion is linear in it, so the choice moves every frame's number by the
# same factor rather than reordering them.
TYPICAL_RANGE_YD = 60.0


def confidence_of(res: fit.WorldFit | None) -> float:
    """The in-sample half of the confidence: how well the frame fitted its paint.

    `docs/03` says confidence derives from the residual, and this is that. What it
    no longer does is scale itself by how much paint was visible.

    **The paint-count ramp was measured anti-correlated with accuracy.** It used to
    multiply by `(n_circle + n_line) / 500`, so a frame seeing 200 px could not
    score above 0.40 however well it fitted, and `docs/03`'s gate of 0.5 discarded
    it. On p0002 the frames it gated out have a median residual of 0.159 yd against
    0.223 for the frames it accepted; on p0003, 0.197 against 0.221. It was
    throwing away the *better* fits - a frame seeing a small, sharply-imaged patch
    of the centre circle fits it precisely, while one seeing a lot of paint spread
    to the far side of the pitch fits more of it less well. Across three
    possessions that cost 22, 33 and 138 sound frames, a quarter of p0003.

    A floor remains, because a fit resting on almost nothing is not a measurement
    at all; it is the amount of paint below which `res.rms_yd` stops being a
    statistic.
    """
    # res.ok already rejects the two failures that produce a *smaller* residual
    # than a good fit: a collapsed solve and a fit to too short an arc. Without
    # that, an rms of exactly 0.0000 scores a perfect quality term - which is
    # what p0003 did before this check existed.
    if res is None or not res.ok:
        return 0.0
    if res.n_circle + res.n_line < MIN_SUPPORT_PX:
        return 0.0
    return float(np.clip(np.exp(-max(res.rms_yd, 0.0) / CONF_SCALE_YD), 0.0, 1.0))


def pose_disagreement_yd(frames: list["Frame"], cam) -> np.ndarray:
    """How far each frame's pose sits from what its neighbours predict, in yards.

    **This is the out-of-sample half, and it replaces a rule that guessed at it.**
    `confidence_of` used to halve itself when the halfway line was absent, on the
    sound geometric argument that a circle alone pins the plane but leaves spin
    about its normal weakly observed. Measured, that proxy is right on some
    possessions and wrong on others: on p0001 the circle-only frames deviate 3.8x
    on pan and 11x on focal, and the penalty is earning its keep; on p0003 they are
    *better* than the line-bearing frames on focal and equal on tilt, and the
    penalty was discarding a quarter of the possession for nothing.

    "Is the halfway line present" was never the question. The question is whether
    the pose is well conditioned, and that can be measured instead of predicted.
    AD-4's amendment establishes this is a fixed broadcast hard camera - it pans,
    tilts and zooms and does not translate - so pan, tilt and focal are smooth
    functions of time. Fit a line through each over a short window **excluding the
    frame itself**, and the frame's distance from that line is an out-of-sample
    error, which is exactly what an in-sample residual cannot be.

    Converted to yards so it can be added to the residual rather than weighed
    against it: an angular error theta displaces a point at range R by R*theta, and
    a fractional focal error df/f scales the range by the same fraction.
    """
    n = len(frames)
    out = np.zeros(n)
    have = np.array([f.pose is not None and f.confidence > 0 for f in frames])
    if have.sum() < 2 * SMOOTH_HALF:
        return out

    series = {
        "pan": np.array([f.pose.pan if f.pose else np.nan for f in frames]),
        "tilt": np.array([f.pose.tilt if f.pose else np.nan for f in frames]),
        "f": np.array([f.pose.f if f.pose else np.nan for f in frames]),
    }
    idx = np.arange(n)
    dev = {k: np.zeros(n) for k in series}
    for k, v in series.items():
        for i in range(n):
            lo, hi = max(0, i - SMOOTH_HALF), min(n, i + SMOOTH_HALF + 1)
            sel = (idx[lo:hi] != i) & have[lo:hi] & np.isfinite(v[lo:hi])
            x = idx[lo:hi][sel].astype(float)
            y = v[lo:hi][sel]
            if len(x) < SMOOTH_DEG + 3 or not np.isfinite(v[i]):
                continue
            dev[k][i] = abs(v[i] - np.polyval(np.polyfit(x, y, SMOOTH_DEG), i))

    fmed = float(np.nanmedian(series["f"][have])) if have.any() else 1.0
    ang = np.hypot(dev["pan"], dev["tilt"]) * TYPICAL_RANGE_YD
    scale = (dev["f"] / max(fmed, 1e-6)) * TYPICAL_RANGE_YD
    return np.hypot(ang, scale)


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


def sequential_pass(cam: FixedCamera, frame_paths, a_idx: int, anchor_pose: Pose,
                    region: np.ndarray, rng, *, verbose: bool = True,
                    label: str = "") -> list[Frame]:
    """Solve every frame, walking outward from the anchor in both directions.

    Each frame is initialised from its neighbour's answer rather than from the
    anchor's, because over a long pan the anchor's pose is a bad starting guess
    and ICP will happily converge to a self-consistent wrong one.
    """
    frames = [Frame(index=i, path=p) for i, p in enumerate(frame_paths)]
    frames[a_idx].pose = anchor_pose
    order = ([a_idx] + list(range(a_idx + 1, len(frames)))
             + list(range(a_idx - 1, -1, -1)))
    prev_pose = anchor_pose
    tag = f"[{label}] " if label else ""
    for k, i in enumerate(order):
        f = frames[i]
        if i in (a_idx, a_idx + 1, a_idx - 1):
            prev_pose = anchor_pose
        b = cv2.imread(str(f.path))
        f.paint_px, _ = paint_pixels(b, region, rng=rng)
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
            # _summarise already worked out WHY a fit is not ok, and the run used
            # to throw that away - so a possession that scored 0.00 everywhere
            # gave no clue which of the four failures it was. Keep it.
            f.note = res.reason
            prev_pose = pose
        if verbose and k % 40 == 0:
            print(f"[calib] {tag}frame {i:4d}  rms {f.rms_yd:7.4f} yd  "
                  f"conf {f.confidence:.2f}  circle {f.n_circle:4d} line {f.n_line:4d}"
                  + (f"  [{f.note}]" if f.note else ""))

    # The out-of-sample half. It can only run once every frame has a pose, which
    # is why it is a second pass rather than part of the loop above.
    dev = pose_disagreement_yd(frames, cam)
    for f, d in zip(frames, dev):
        if f.confidence <= 0.0:
            continue
        f.pose_disagreement_yd = float(d)
        # ...and the independent third: how far this frame puts two points whose
        # field position is known exactly. Neither of the other two can catch a
        # stretch that locked onto the wrong pixels and then drifted smoothly,
        # because both are computed from the same solve. See groundtruth.py.
        bgr = cv2.imread(str(f.path))
        f.known_geometry_err_yd = groundtruth.check_frame(bgr, region, cam, f.pose)
        gt = groundtruth.penalty_yd(f.known_geometry_err_yd)
        total = float(np.sqrt((f.rms_yd if np.isfinite(f.rms_yd) else 0.0) ** 2
                              + d ** 2 + gt ** 2))
        f.confidence = float(np.clip(np.exp(-total / CONF_SCALE_YD), 0.0, 1.0))
    if verbose:
        tested = [f.known_geometry_err_yd for f in frames
                  if f.known_geometry_err_yd is not None]
        if tested:
            print(f"[calib] {tag}known-geometry check: {len(tested)} of "
                  f"{len(frames)} frames testable, median error "
                  f"{np.median(tested):.3f} yd, "
                  f"{sum(1 for e in tested if e > 1.0)} over 1 yd")
    return frames


def calibrate(work: Path, *, anchor_stride: int = 20, bundle_n: int = 9,
              camera_c: tuple[float, float, float] | None = None,
              verbose: bool = True) -> dict:
    """Solve every frame's pose. `camera_c` pins the camera centre.

    **Pin it whenever the venue has been measured.** The centre is a venue fact,
    not a per-possession one - AD-4's amendment says this camera pans, tilts and
    zooms and does not translate, and it does not translate between possessions
    either. Solving it per possession and choosing between candidates on mean
    per-frame confidence is an *in-sample* decision, and a self-consistently wrong
    camera satisfies it: p0002 and p0003 each landed ~20 yd from p0001's camera
    and failed the M1 reprojection gate by factors of 6 and 10 while reporting
    healthy residuals throughout. See ur/calibrate/venue.py BREESE_STEVENS_CAMERA_C.
    """
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
    if camera_c is not None:
        # A one-point grid: the pose is still solved per frame, only the centre
        # is given. Everything downstream is unchanged, which is the point -
        # this removes a free parameter rather than adding a special case.
        grid = {"sx": np.array([float(camera_c[0])]),
                "sy": np.array([float(camera_c[1])]),
                "sz": np.array([float(camera_c[2])])}
        if verbose:
            print(f"[calib] camera centre pinned to the venue's measured value "
                  f"{tuple(round(float(v), 4) for v in camera_c)}")
    else:
        grid = {"sx": np.linspace(-26, 26, 9),
                "sy": np.linspace(-60, -30, 9),
                "sz": np.linspace(6, 22, 7)}
    cands = fit.bootstrap(dist, w, h, W.soccer_features(), ell, top_k=5,
                          c_grid=grid)
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
    if camera_c is not None:
        bundle_n = 0          # nothing to pin; the centre is given
    for i in (range(step, len(frames) - 1, step) if camera_c is None else ()):
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
    cam_anchor = cam
    cam_bundled = None
    if camera_c is None and len(obs) >= 3:
        cam_bundled, _ = fit.bundle_world(cam_anchor, poses, obs)
        if verbose:
            print(f"[calib] bundled over {len(obs)} frames -> "
                  f"C={np.round(cam_bundled.C, 2)}")
    elif verbose:
        # Two very different reasons land here and they used to print the same
        # line. On every possession since the centre was pinned to the venue
        # value, `obs` is never even collected, so the message read "only 0
        # frames usable for the bundle" - which looks like a calibration that
        # failed, on a run where nothing was attempted or needed.
        if camera_c is not None:
            print("[calib] bundle skipped: the camera centre is a venue fact, "
                  "pinned (docs/28). --fit-camera-centre re-enables the solve.")
        else:
            print(f"[calib] only {len(obs)} frames usable for the bundle; centre "
                  "left at the anchor's estimate")

    # --- which camera centre, decided rather than assumed -------------------- #
    #
    # The bundle returns a camera whatever happens, and nothing used to ask
    # whether it had helped. On p0001 it does: mean confidence 0.694 against the
    # anchor centre's 0.591, and the venue transform's residual 0.0 yd against
    # 2.7. On p0003 it moved the centre to (-11.6, -24.2, 3.5) - three metres up
    # and *inside* the pitch - and every frame after it collapsed: mean
    # confidence 0.000 against the anchor centre's 0.420, 0 % of frames usable
    # against 54 %. The bundle reported success both times. HANDOFF § 8 again.
    #
    # Both bundle inputs and outputs look healthy when this happens - the ten
    # probe frames each fitted at rms 0.11-0.42 yd - so there is no local check
    # on the bundle that would catch it. The thing that can contradict it is the
    # only thing that matters: solve the whole possession with each centre and
    # keep the one the frames prefer.
    #
    # Mean confidence is the score because it is already the project's own
    # measure of a trustworthy frame (AD-1), and because it is immune to the two
    # ways a collapsed fit flatters itself - confidence_of() returns 0.0 for a
    # fit `_summarise` rejects, so the rms 0.0000 of a collapsed solve scores
    # nothing rather than scoring perfectly. There is no threshold here: it is
    # an argmax over two candidates, so it needs no tuning and no per-possession
    # constant.
    choice = {"candidates": []}
    passes = [("anchor", cam_anchor)]
    if cam_bundled is not None:
        passes.append(("bundled", cam_bundled))
    scored = []
    for k, (name, c) in enumerate(passes):
        # Each pass gets its own deterministic stream rather than continuing the
        # shared one. Sharing would make every pass depend on how many passes ran
        # before it - so a possession where the bundle was skipped and one where
        # it was rejected would solve the same camera differently, and a re-run
        # would stop being byte-identical. The seed is derived from the run's
        # seed and the pass index, so it is fixed regardless of that ordering.
        fr = sequential_pass(c, frame_paths, a_idx, anchor_res.pose, rm.mask,
                             np.random.default_rng([SEED, k]),
                             verbose=verbose, label=name if len(passes) > 1 else "")
        conf = np.array([f.confidence for f in fr])
        scored.append((float(conf.mean()), name, c, fr))
        choice["candidates"].append(
            {"centre": name, "position_yd_soccer": [round(float(v), 4) for v in c.C],
             "mean_confidence": round(float(conf.mean()), 4),
             "frac_confident": round(float((conf >= 0.5).mean()), 4)})
        if verbose and len(passes) > 1:
            print(f"[calib] {name} centre C={np.round(c.C, 2)}: mean confidence "
                  f"{conf.mean():.4f}, {(conf >= 0.5).mean():.0%} of frames >= 0.5")
    scored.sort(key=lambda t: t[0], reverse=True)
    _, chosen_name, cam, frames = scored[0]
    choice["chosen"] = chosen_name
    choice["why"] = ("highest mean per-frame confidence over the whole possession; "
                     "the bundle is accepted only when the frames say it helped")
    if verbose and len(passes) > 1:
        print(f"[calib] using the {chosen_name} centre")

    return {"camera": cam, "frames": frames, "mask": rm, "anchor": a_idx,
            "centre_choice": choice}


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
            "pose_disagreement_yd": round(float(f.pose_disagreement_yd), 5),
            "known_geometry_err_yd": (None if f.known_geometry_err_yd is None
                                      else round(float(f.known_geometry_err_yd), 4)),
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
            "centre_choice": res.get("centre_choice"),
            "seed": SEED,
        },
        "camera": cam.to_dict(),
        "venue_transform": vt.to_dict(),
        "field_length": venue_info["length"],
        "anchors": [{"shot": 0, "frame": res["anchor"],
                     "correspondences": "none clicked - the anchor was solved from "
                                        "the detected conic, then the camera centre "
                                        "was chosen between the anchor's own estimate "
                                        "and a bundle over frames spread across the "
                                        "pan, by whichever solved the possession with "
                                        "the higher mean confidence"}],
        "frames": out_frames,
    }
    (work / "calibration.json").write_text(json.dumps(doc, indent=1) + "\n",
                                           encoding="utf-8")
    return doc


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="ur.calibrate.run")
    p.add_argument("work", help="possession working directory, e.g. work/p0001")
    p.add_argument("--eval-dir", default="eval/m1")
    p.add_argument("--bundle-n", type=int, default=9,
                   help="frames to bundle the camera centre over. 0 skips the "
                        "bundle and leaves the centre at the anchor's estimate - "
                        "a diagnostic, since the bundle is the step that can move "
                        "a good anchor solve to a camera that does not exist.")
    p.add_argument("--fit-camera-centre", action="store_true",
                   help="solve the camera centre from this possession instead of "
                        "using the venue's measured one. Only for a new venue: "
                        "per-possession solves landed 20 yd out on p0002 and "
                        "p0003 while reporting healthy residuals. See "
                        "ur/calibrate/venue.py BREESE_STEVENS_CAMERA_C.")
    p.add_argument("--near-sideline", type=float, default=None,
                   help="soccer-frame y of the near ultimate sideline. Defaults to "
                        "the evidenced value for this venue; pass a value for a "
                        "different venue, or 'auto' behaviour by passing nan.")
    args = p.parse_args(argv)
    work = Path(args.work)
    ev = Path(args.eval_dir)
    ev.mkdir(parents=True, exist_ok=True)

    from . import venue as _V
    cc = None if args.fit_camera_centre else _V.BREESE_STEVENS_CAMERA_C
    res = calibrate(work, bundle_n=args.bundle_n, camera_c=cc)
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
    near = (V.BREESE_STEVENS_NEAR_SIDELINE_Y if args.near_sideline is None
            else args.near_sideline)
    if near is not None and np.isnan(near):
        near = None
    vt = V.measure_transform(pm, flen, near_sideline_y=near)
    print(f"[venue] near sideline: "
          f"{'unconstrained (peak pair)' if near is None else f'{near:+.2f} soccer y'}")
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
