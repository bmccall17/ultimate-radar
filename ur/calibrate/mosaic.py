"""Pose for the frames the paint cannot reach, from the rest of the picture.

AD-4's amendment says to *"keep the mosaic for stretches where too little paint
is visible"*, `docs/28` § "what it does not fix" names it as the thing that caps
a possession, and `docs/29` measured what it costs not to have it: p0006 and
p0007 lose three quarters and two thirds of their frames, and every possession
that ends in a goal goes blind for the last few seconds as the camera tilts into
the endzone. This is that stage.

## What makes it work: the camera centre does not move

AD-4's amendment establishes that this is a fixed broadcast hard camera - it
pans, tilts and zooms, and it does not translate. For a camera that only
rotates, the mapping between two of its images is **exactly**

    x_j = K_j R_j R_i^T K_i^-1 x_i

for every scene point, near or far, with no dependence on depth. The crowd, the
sponsor boards, the video board and the grass all obey it. So a frame with no
usable paint on it is not a frame with no information: it shares thousands of
features with frames whose pose is known, and those correspondences pin its own
pose exactly.

What that buys is **no chaining**. Chaining a homography frame to frame drifts -
measured, in `docs/29`, at 0.76 yd after one second and 2.4 yd after four,
because each step's error is carried into the next. Here every frame is solved
directly against several frames whose pose is already known, so the error is
one registration's worth however far away the nearest source is.

**Positions come from the composed homography, not from the recovered pose**,
and that is the opposite of what was expected. See `COMPOSE_NOT_MODEL` below:
the camera model is the principled route and it measured worse, 0.61 yd against
0.20 yd at a one-frame gap.

## Recovering the pose, in closed form

Given a solved frame `j` and the measured image homography `G` taking `i` to
`j`, the identity above rearranges to

    K_i R_i = G^-1 K_j R_j  =:  M

With the principal point at the image centre, `K_i = diag(f, f, 1)`, so

    M M^T = K_i K_i^T = diag(f^2, f^2, 1)

Normalise `M` so that `(M M^T)[2,2] = 1` and the focal length falls straight out
as `sqrt((M M^T)[0,0])`; `R_i = K_i^-1 M`, re-orthonormalised. No optimiser, no
initial guess, nothing to converge to the wrong answer.

## What keeps it honest

- **Only frames solved from paint are ever sources**, and only those that the
  known-geometry check did not contradict. `docs/27`'s second trap in another
  costume: a pose derived from a mosaic must not become the evidence for the
  next one. Frames this module solves are marked `basis: "mosaic"` and are not
  promoted to sources.
- **Every frame is solved against every solved frame it overlaps**, not against
  its neighbour, and the estimates have to agree. The spread between them is
  reported per frame as `mosaic_spread_yd` and drives the confidence, so a frame
  whose sources disagree says so instead of averaging them into a plausible lie.
- **It never overwrites a frame the paint solved.** It only fills.
- **The accuracy is measured, not asserted.** `tools/mosaic_check.py` hides
  contiguous blocks of frames whose pose *is* known, re-derives them with this
  module, and reports the error against the truth as a function of how far the
  frame sits from the nearest surviving source.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from . import camera as C

# ORB rather than a learned matcher: it is in OpenCV, it is BSD, and the thing
# being matched is a rigid scene between frames 1/15 s apart. `docs/07` gate.
N_FEATURES = 3000
FAST_THRESHOLD = 7
RATIO = 0.75
MIN_MATCHES = 40
MIN_INLIERS = 30
RANSAC_PX = 3.0

# How far away a source frame may be. Beyond about three seconds the overlap
# with a panning, zooming camera is gone and the match fails anyway; the limit
# is here so the search does not cost more than it returns.
MAX_SOURCE_GAP = 45

# How many solved frames to try per unsolved frame. Taking the nearest few is
# not enough - the point of the spread is that they are independent - so this
# spreads its picks either side.
N_SOURCES = 6

# A source must have been solved from paint and not contradicted by the
# known-geometry check. docs/28's whole argument is that a self-consistent fit
# can be badly wrong, so agreeing with the paint is necessary and not sufficient.
SOURCE_MIN_CONFIDENCE = 0.5
SOURCE_MAX_KNOWN_GEOMETRY_ERR_YD = 1.0

# How wrong a filled frame is, as a function of how far it sits from the nearest
# paint-solved frame. **Measured, not assumed** - `tools/mosaic_check.py` hid
# contiguous blocks of p0001's paint-solved frames, re-derived them from the
# rest, and compared. Median yards on the ground, over 798 held-out frames:
#
#     gap (frames)     1      5     10     20     30     45
#     gap (seconds)  0.07   0.33   0.67   1.33   2.00   3.00
#     median yd      0.20   0.37   0.70   1.26   1.95   2.37
#     p90 yd         0.33   0.78   1.49   2.75   3.13   3.71
#
# This is the curve the confidence is read off, through the same
# `exp(-error / 0.45)` every other frame goes through, so a filled frame and a
# paint-solved frame are comparable numbers. Re-measure it on any possession
# with `tools/mosaic_check.py` before trusting it on new footage.
ERR_BY_GAP = ((1, 0.20), (5, 0.37), (10, 0.70), (20, 1.26), (30, 1.95), (45, 2.37))
CONF_SCALE_YD = 0.45          # the same constant ur/calibrate/run.py uses

# When is a paint-refined mosaic pose to be believed? Measured, and the answer
# is a cliff rather than a slope. `tools/mosaic_check.py --refit` on p0001, 375
# held-out frames, against their true poses:
#
#     in-sample residual   frames   true error: median    p90     max
#     < 0.20 yd               238                0.014   0.070   0.292
#     < 0.25 yd               261                0.015   0.162   2.964
#     >= 0.20 yd              137                3.109   5.476
#
# Below 0.20 yd not one of 238 frames is out by more than 0.3 yd. Above it the
# median is three yards. The refit is bimodal - it either locks onto the right
# answer essentially exactly or onto a wrong one several yards away - and the
# residual is what tells them apart, at a correlation of +0.81.
#
# So an accepted refit is scored on its own residual exactly like any other
# paint fit, with no special case and no floor, because its measured error is
# smaller than a paint fit's. A rejected one keeps the pure mosaic pose and the
# prior's confidence.
REFIT_MAX_RMS_YD = 0.20

# ...and a residual is not enough on its own, which cost a round trip to find
# out. The cliff above was measured by holding out frames of p0001 whose paint
# was good; the frames a refit is actually for have degenerate paint, and there
# a low residual means the optimiser found *a* consistent answer, not the right
# one. So a refit is also required to survive the one check in this project that
# is independent of the solve - two points whose field position is known exactly,
# located in image space only. If it cannot be run on a frame, the refit is not
# accepted: "not testable" is not a pass (`groundtruth.check_frame`).
REFIT_MAX_KNOWN_GEOMETRY_YD = 0.75      # the same bar docs/04 sets for M1
FIT_PRIOR_SIGMAS = 3.0        # mirrors ur.calibrate.fit.PRIOR_SIGMAS, for the note


def expected_error_yd(gap: int) -> float:
    """Interpolated from the measured curve; extrapolated linearly past the end."""
    xs = [g for g, _ in ERR_BY_GAP]
    ys = [e for _, e in ERR_BY_GAP]
    if gap <= xs[0]:
        return ys[0]
    if gap >= xs[-1]:
        slope = (ys[-1] - ys[-2]) / (xs[-1] - xs[-2])
        return ys[-1] + slope * (gap - xs[-1])
    return float(np.interp(gap, xs, ys))


@dataclass
class Solved:
    f: int
    pose: C.Pose
    H: np.ndarray                 # image pixel -> field yard, as calibration.json
    spread_yd: float
    n_sources: int
    inliers: int


def _orb():
    return cv2.ORB_create(nfeatures=N_FEATURES, fastThreshold=FAST_THRESHOLD)


def features(paths: list[Path], region: np.ndarray, which: list[int]) -> dict:
    """ORB keypoints and descriptors, computed once per frame.

    `region` excludes the burnt-in graphics - the score bug and the lower third
    are painted on the output, not on the world, so they do not move when the
    camera does and they would anchor every registration towards no motion at
    all. Everything else is fair game, deliberately: the stands and the sponsor
    boards are the most textured and most rigid thing in the frame, and unlike
    the paint they are still there when the camera looks at the endzone.
    """
    orb = _orb()
    out = {}
    for i in which:
        img = cv2.imread(str(paths[i]), cv2.IMREAD_GRAYSCALE)
        if img is None:
            continue
        kp, des = orb.detectAndCompute(img, region)
        if des is not None and len(kp) >= MIN_MATCHES:
            out[i] = (np.float32([k.pt for k in kp]), des)
    return out


def _homography(a, b) -> tuple[np.ndarray | None, int]:
    """Image homography taking frame a to frame b, or None."""
    (pa, da), (pb, db) = a, b
    matches = cv2.BFMatcher(cv2.NORM_HAMMING).knnMatch(da, db, k=2)
    good = [m for m, n in (p for p in matches if len(p) == 2)
            if m.distance < RATIO * n.distance]
    if len(good) < MIN_MATCHES:
        return None, len(good)
    src = pa[[m.queryIdx for m in good]].reshape(-1, 1, 2)
    dst = pb[[m.trainIdx for m in good]].reshape(-1, 1, 2)
    H, inl = cv2.findHomography(src, dst, cv2.RANSAC, RANSAC_PX)
    n = int(inl.sum()) if inl is not None else 0
    return (H if n >= MIN_INLIERS else None), n


def pose_from_homography(G: np.ndarray, source: C.Pose, w: int, h: int
                         ) -> C.Pose | None:
    """The pose of frame i, given `G` taking i to a frame whose pose is known.

    Exact for a camera that only rotates, which AD-4's amendment establishes
    this one is. See the module docstring for the algebra.
    """
    Kj = C.intrinsics(source.f, w, h)
    Rj = C.rotation(source.pan, source.tilt, source.roll)
    try:
        M = np.linalg.inv(G) @ Kj @ Rj                     # = K_i R_i, up to scale
    except np.linalg.LinAlgError:
        return None
    # The principal point is the image centre, not the origin, so `K` is not
    # diag(f, f, 1) and `M M^T` is not diagonal. Shifting the principal point to
    # the origin first makes it so, and the identity below then holds exactly.
    # Getting this wrong is not subtle: it put the held-out frames 51 yd out at a
    # one-frame gap, where they should have been within centimetres.
    T = np.array([[1.0, 0.0, -w / 2.0], [0.0, 1.0, -h / 2.0], [0.0, 0.0, 1.0]])
    N = T @ M                                              # = diag(f, f, 1) R_i
    scale = np.linalg.norm(N[2])                           # last row is R_i[2], unit
    if scale <= 1e-12:
        return None
    N = N / scale
    S = N @ N.T                                            # = diag(f^2, f^2, 1)
    fsq = (S[0, 0] + S[1, 1]) / 2.0
    if not np.isfinite(fsq) or fsq <= 1.0:
        return None
    f = float(np.sqrt(fsq))
    R = np.diag([1.0 / f, 1.0 / f, 1.0]) @ N
    # Nearest proper rotation. A residual far from orthonormal means the
    # homography was not a rotation of this camera, so the frame is refused.
    U, s, Vt = np.linalg.svd(R)
    if s[0] / max(s[2], 1e-9) > 1.05:
        return None
    R = U @ Vt
    if np.linalg.det(R) < 0:
        R = U @ np.diag([1.0, 1.0, -1.0]) @ Vt
    pan, tilt, roll = C.angles_from_rotation(R)
    if not (-0.2 < tilt < 1.4) or abs(roll) > 1.0:
        return None
    return C.Pose(pan=pan, tilt=tilt, f=f, roll=roll)


def ground_points(cam: C.FixedCamera, pose: C.Pose, px: np.ndarray
                  ) -> tuple[np.ndarray, np.ndarray]:
    """Image pixels -> field yards, under one pose.

    This direction rather than the other, and it matters. Projecting field
    points *to* pixels and comparing two poses there measures pixels, which is
    not a quantity anything downstream uses: near the horizon a pixel is worth
    several yards and at the near sideline it is worth an inch, so a pixel
    difference says almost nothing about how wrong a position is. The first
    version of the mosaic check did exactly that and reported "51 yd" errors
    that were 51 px.

    `inv(H)` returns a negative `w` for points in front of this camera - the
    fourth place in this project to meet that, see `HANDOFF.md` - so the sign is
    taken from a point known to be on the field rather than assumed.
    """
    H = cam.homography(pose)                     # ground -> image
    try:
        Hi = np.linalg.inv(H)
    except np.linalg.LinAlgError:
        return np.full((len(px), 2), np.nan), np.zeros(len(px), bool)
    hom = np.column_stack([px, np.ones(len(px))]) @ Hi.T
    wq = hom[:, 2]
    ok = np.abs(wq) > 1e-9
    out = np.full((len(px), 2), np.nan)
    out[ok] = hom[ok, :2] / wq[ok, None]
    # In front of the camera, the ground->image depth is positive. Re-project and
    # keep only the points that come back where they started.
    back, vis = cam.project(np.nan_to_num(out), pose)
    ok &= vis & (np.hypot(*(back - px).T) < 1.0)
    return out, ok


def _image_probe(cam: C.FixedCamera, n: int = 6) -> np.ndarray:
    """A grid of image pixels below the horizon, where the field is."""
    w, h = cam.image_w, cam.image_h
    return np.array([[x, y] for x in np.linspace(0.12 * w, 0.88 * w, n)
                            for y in np.linspace(0.55 * h, 0.92 * h, n)], float)


COMPOSE_NOT_MODEL = """Why the ground homography is composed rather than rebuilt
from the recovered pose.

Both are available: `H_s @ G` composes the measured image-to-image homography
onto a source frame's ground homography, and `pose_from_homography` recovers
pan, tilt, roll and focal and rebuilds it through the 4-DOF camera model. The
model route is the principled one and it is **worse**, measured on p0001 with
held-out blocks: 0.61 yd median at a one-frame gap against 0.05 yd for
composition, where a one-frame gap should be near exact.

The reason is that a measured `G` is not exactly a rotation-induced homography -
the camera centre is pinned to a venue value, the lens is not perfectly
rectilinear, and the matcher has noise. A ground-plane homography has eight
degrees of freedom and absorbs all of that harmlessly for ground points, which
is all anything downstream asks of it. Forcing it onto the four-parameter
manifold does not remove the error; it redistributes it into the ground mapping.

The pose is still recovered, because `calibration.json` carries a camera block
and the viewer draws a frustum from it, but positions come from the composed H.
"""


def _combine(cands: list[np.ndarray], probe: np.ndarray
             ) -> tuple[np.ndarray | None, float]:
    """One homography from several, robustly, plus how far apart they were.

    Averaging 3x3 matrices is meaningless. These are combined where they are
    comparable - on the ground, in yards - by taking the per-point median of
    where each candidate puts the probe pixels and re-fitting a homography to
    that. The spread is the disagreement the median hid, and it is the only
    thing the module can see at run time about its own accuracy.
    """
    pts = []
    for H in cands:
        hom = np.column_stack([probe, np.ones(len(probe))]) @ H.T
        w = hom[:, 2]
        if np.any(np.abs(w) < 1e-9):
            continue
        pts.append(hom[:, :2] / w[:, None])
    if not pts:
        return None, float("inf")
    stack = np.stack(pts)
    med = np.median(stack, axis=0)
    spread = float(np.max([np.median(np.hypot(*(q - med).T)) for q in stack])) \
        if len(stack) > 1 else 0.0
    if len(stack) == 1:
        return cands[0], 0.0
    H, _ = cv2.findHomography(probe.reshape(-1, 1, 2).astype(np.float32),
                              med.reshape(-1, 1, 2).astype(np.float32), 0)
    return (H if H is not None else cands[0]), spread


def agreement_yd(cam: C.FixedCamera, poses: list[C.Pose], probe: np.ndarray
                 ) -> float:
    """How far apart the candidate poses put the same patch of ground, in yards."""
    pts = []
    for p in poses:
        xy, ok = ground_points(cam, p, probe)
        if ok.sum() < 4:
            return float("inf")
        pts.append(np.where(ok[:, None], xy, np.nan))
    if len(pts) < 2:
        return 0.0
    stack = np.stack(pts)
    med = np.nanmedian(stack, axis=0)
    spreads = [np.nanmedian(np.hypot(*(q - med).T)) for q in stack]
    return float(np.nanmax(spreads))


def fill(paths: list[Path], cal_frames: list[dict], cam: C.FixedCamera,
         region: np.ndarray, field: dict, *, sources: set[int] | None = None,
         targets: set[int] | None = None, verbose: bool = True) -> dict[int, Solved]:
    """Solve every frame that has no pose, against the frames that do.

    `sources` and `targets` are for the held-out check in
    `tools/mosaic_check.py`; the pipeline passes neither and gets the obvious
    thing - paint-solved frames are sources, unsolved frames are targets.
    """
    n = len(cal_frames)
    if sources is None:
        sources = {i for i, r in enumerate(cal_frames)
                   if r.get("camera") and r.get("confidence", 0) >= SOURCE_MIN_CONFIDENCE
                   and not str(r.get("basis", "")).startswith("mosaic")
                   and (r.get("known_geometry_err_yd") is None
                        or r["known_geometry_err_yd"] <= SOURCE_MAX_KNOWN_GEOMETRY_ERR_YD)}
    if targets is None:
        targets = {i for i in range(n) if i not in sources}
    if not sources or not targets:
        if verbose:
            print(f"[mosaic] {len(sources)} sources, {len(targets)} to fill - "
                  "nothing to do")
        return {}

    def pose_of(rec: dict) -> C.Pose:
        c = rec["camera"]
        return C.Pose(pan=np.radians(c["pan_deg"]), tilt=np.radians(c["tilt_deg"]),
                      f=float(c["focal_px"]), roll=np.radians(c.get("roll_deg", 0.0)))

    known: dict[int, C.Pose] = {i: pose_of(cal_frames[i]) for i in sources}
    source_H: dict[int, np.ndarray] = {i: np.asarray(cal_frames[i]["H"], float)
                                       for i in sources}
    want = sorted(targets, key=lambda i: min((abs(i - s) for s in sources),
                                             default=n))
    feats = features(paths, region, sorted(set(want) | set(sources)))
    if verbose:
        print(f"[mosaic] {len(sources)} paint-solved sources, {len(targets)} frames "
              f"to fill; ORB on {len(feats)} frames")

    out: dict[int, Solved] = {}
    # Only ever match against paint-solved frames. A mosaic pose must not become
    # the evidence for the next mosaic pose - that is how a chain gets back in.
    for i in want:
        if i not in feats:
            continue
        near = sorted((s for s in sources if abs(s - i) <= MAX_SOURCE_GAP and s in feats),
                      key=lambda s: abs(s - i))[:N_SOURCES]
        cands, poses, inl_total = [], [], 0
        for s in near:
            G, inl = _homography(feats[i], feats[s])
            if G is None:
                continue
            # `G` takes frame i to frame s and `H_s` takes frame s to the field,
            # so `H_s @ G` takes frame i to the field. Composed rather than
            # rebuilt through the camera model: see `COMPOSE_NOT_MODEL`.
            cands.append(np.asarray(source_H[s], float) @ G)
            p = pose_from_homography(G, known[s], cam.image_w, cam.image_h)
            if p is not None:
                poses.append(p)
            inl_total += inl
        if not cands:
            continue
        probe = _image_probe(cam)
        H, spread = _combine(cands, probe)
        if H is None:
            continue
        pose = (C.Pose(pan=float(np.median([p.pan for p in poses])),
                       tilt=float(np.median([p.tilt for p in poses])),
                       f=float(np.median([p.f for p in poses])),
                       roll=float(np.median([p.roll for p in poses])))
                if poses else None)
        if pose is None:
            continue
        out[i] = Solved(f=i, pose=pose, H=H, spread_yd=spread,
                        n_sources=len(cands), inliers=inl_total)
    if verbose:
        got = len(out)
        sp = [s.spread_yd for s in out.values() if np.isfinite(s.spread_yd)]
        print(f"[mosaic] filled {got} of {len(targets)}"
              + (f"; source agreement median {np.median(sp):.3f} yd, "
                 f"p90 {np.percentile(sp, 90):.3f} yd" if sp else ""))
    return out


# --------------------------------------------------------------------------- #
# the stage
# --------------------------------------------------------------------------- #

def fill_document(work: Path, *, verbose: bool = True) -> dict:
    """Read calibration.json, fill what the paint could not reach, write it back.

    A stage that runs alone on one possession, which is `AGENTS.md`'s working
    style, and re-runnable: any frame a previous run filled is thrown away first,
    so this is idempotent rather than compounding.
    """
    import json

    from . import mask as M

    path = work / "calibration.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    frames = doc["frames"]
    paths = sorted((work / "frames").glob("*.jpg"))
    cam = C.FixedCamera(C=np.asarray(doc["camera"]["position_yd_soccer"]
                                     if "position_yd_soccer" in doc["camera"]
                                     else doc["camera"]["position_yd"], float),
                        image_w=doc["camera"]["image_w"],
                        image_h=doc["camera"]["image_h"])
    field = json.loads((work / "clip.json").read_text(encoding="utf-8"))["field"]

    # Idempotence: a frame an earlier run filled goes back to being empty, so a
    # second run cannot quietly build on the first.
    undone = 0
    for r in frames:
        # Both bases, and this is not a detail: the first version cleared only
        # `mosaic`, so a second run found the previous run's `mosaic+paint`
        # frames sitting above the confidence threshold and took them as
        # SOURCES. That is docs/27's second trap exactly - a derived answer
        # becoming the evidence for the next one - and it appeared within an
        # hour of the docstring warning about it.
        if str(r.get("basis", "")).startswith("mosaic"):
            undone += 1
            for k in ("H", "camera", "mosaic_gap", "mosaic_spread_yd",
                      "mosaic_sources", "basis", "H_mosaic", "camera_mosaic",
                      "refit_rms_yd", "refit_moved_yd", "refit_circle_span_deg",
                      "refit_n_px", "refit_at_box_edge", "refit_rejected"):
                r.pop(k, None)
            r["H"] = None
            r["confidence"] = 0.0
            r["note"] = "no pose"
    if verbose and undone:
        print(f"[mosaic] cleared {undone} frames filled by a previous run")

    static, _ = M.static_region(paths)
    region = np.full(static.shape, 255, np.uint8)
    region[static > 0] = 0

    before = sum(1 for r in frames if r.get("confidence", 0) >= 0.5)
    got = fill(paths, frames, cam, region, field, verbose=verbose)
    sources = {i for i, r in enumerate(frames)
               if r.get("camera") and r.get("confidence", 0) >= SOURCE_MIN_CONFIDENCE
               and (r.get("known_geometry_err_yd") is None
                    or r["known_geometry_err_yd"] <= SOURCE_MAX_KNOWN_GEOMETRY_ERR_YD)}

    for i, s in sorted(got.items()):
        gap = min((abs(i - j) for j in sources), default=999)
        err = expected_error_yd(gap)
        # The disagreement between sources is the only thing measurable at run
        # time, so where it is worse than the curve predicts, it wins.
        if np.isfinite(s.spread_yd):
            err = max(err, s.spread_yd)
        rec = frames[i]
        rec["H"] = [[round(float(v), 10) for v in row] for row in (s.H / s.H[2, 2])]
        rec["camera"] = {**s.pose.to_dict(), "n_circle_px": 0, "n_line_px": 0,
                         "p95_yd": None}
        rec["confidence"] = round(float(np.clip(np.exp(-err / CONF_SCALE_YD), 0, 1)), 4)
        rec["basis"] = "mosaic"
        rec["mosaic_gap"] = gap
        rec["mosaic_spread_yd"] = (round(float(s.spread_yd), 4)
                                   if np.isfinite(s.spread_yd) else None)
        rec["mosaic_sources"] = s.n_sources
        rec["note"] = (
            f"no usable paint; pose registered against {s.n_sources} paint-solved "
            f"frame(s) {gap} frame(s) away. H is composed from the measured image "
            f"homography and is what positions come from; `camera` is recovered "
            f"through the 4-DOF model for the viewer's frustum and is not "
            f"bit-identical to it. Expected error {err:.2f} yd "
            f"(ur/calibrate/mosaic.py ERR_BY_GAP).")

    # The paint gets the last word, inside the box the mosaic's measured accuracy
    # allows. This is where the circle-only frames come back.
    refit_with_paint(work, doc, verbose=verbose)
    for rec in frames:
        if rec.get("basis") != "mosaic" or "refit_rms_yd" not in rec:
            continue
        gt = rec.get("refit_known_geometry_err_yd")
        if gt is None or gt > REFIT_MAX_KNOWN_GEOMETRY_YD                 or rec["refit_rms_yd"] >= REFIT_MAX_RMS_YD:
            # Rejected: the refit is as likely to have locked onto the wrong
            # answer as the right one, so the pure mosaic pose and its prior
            # confidence stand. The attempt is left in the record.
            rec["refit_rejected"] = (
                "the known-geometry check could not test this frame, so nothing "
                "independent confirms which paint the refit found"
                if gt is None else
                f"known-geometry error {gt:.2f} yd: the refit is self-consistent "
                "on paint that is not where it thinks it is"
                if gt > REFIT_MAX_KNOWN_GEOMETRY_YD else
                f"residual {rec['refit_rms_yd']:.3f} yd is at or above "
                f"{REFIT_MAX_RMS_YD} yd")
            rec.pop("H_refit", None)
            rec["H"] = rec["H_mosaic"]
            rec["camera"] = rec["camera_mosaic"]
            rec.pop("H_mosaic", None)
            rec.pop("camera_mosaic", None)
            continue
        rec.pop("H_mosaic", None)
        rec.pop("camera_mosaic", None)
        rec["confidence"] = round(float(np.clip(
            np.exp(-rec["refit_rms_yd"] / CONF_SCALE_YD), 0, 1)), 4)
        rec["basis"] = "mosaic+paint"
        rec["note"] = (
            f"no halfway line; pose registered against {rec['mosaic_sources']} "
            f"paint-solved frame(s) {rec['mosaic_gap']} away, then refined against "
            f"this frame's own paint inside a {FIT_PRIOR_SIGMAS:.0f}-sigma box "
            f"(residual {rec['refit_rms_yd']:.3f} yd over {rec['refit_n_px']} px, "
            f"arc {rec['refit_circle_span_deg']:.0f} deg, moved "
            f"{rec['refit_moved_yd']:.2f} yd from the prior).")

    # **Every pose faces the same gate, whatever produced it.** The mosaic path
    # originally scored a filled frame on the registration gap alone and never
    # asked the one question that is independent of the solve. On p0003 that let
    # a frame whose refit had been rejected at 12.6 yd keep a confidence of 0.64,
    # because the fallback mosaic pose had never been checked either. docs/28
    # built this check precisely because a self-consistent pose can be badly
    # wrong; there is no reason a mosaic pose should be exempt from it.
    check_known_geometry(work, doc, verbose=verbose)

    after = sum(1 for r in frames if r.get("confidence", 0) >= 0.5)
    doc.setdefault("method", {})["mosaic"] = {
        "module": "ur.calibrate.mosaic",
        "filled": len(got),
        "frames_over_confidence_0_5_before": before,
        "frames_over_confidence_0_5_after": after,
        "err_by_gap_yd": [list(x) for x in ERR_BY_GAP],
        "measured_on": "p0001, 798 held-out frames, tools/mosaic_check.py",
        "note": "Only paint-solved frames are ever sources. A filled frame is "
                "never promoted to a source, so nothing here is registered "
                "against anything this module produced.",
    }
    path.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    if verbose:
        print(f"[mosaic] frames at confidence >= 0.5: {before} -> {after} "
              f"of {len(frames)}")
    return doc


def main(argv: list[str] | None = None) -> int:
    import argparse

    p = argparse.ArgumentParser(prog="ur.calibrate.mosaic")
    p.add_argument("work")
    a = p.parse_args(argv)
    fill_document(Path(a.work))
    return 0



# --------------------------------------------------------------------------- #
# the paint gets the last word
# --------------------------------------------------------------------------- #

def refit_with_paint(work: Path, doc: dict, *, verbose: bool = True) -> int:
    """Let the paint refine each filled pose, inside the box the prior allows.

    This is the half that matters. `docs/29` measured the bottleneck: **every
    frame with a halfway line in shot calibrates, and frames without one
    collapse** - 223 of p0006's 450, 321 of p0010's. `docs/28` had already
    established that circle-only frames are not inherently worse (on p0003 they
    were *better* on focal than the line-bearing ones) and removed the confidence
    penalty on them, but the solve still ran away, because a circle pins the
    plane and the scale and leaves rotation about its normal unobserved.

    The mosaic pose observes exactly that direction, from the stands and the
    boards, which have nothing to do with the paint. So: bound the refinement to
    the box the mosaic's measured accuracy allows, and let the circle do the rest
    inside it. Neither source is sufficient alone and together they are
    well posed.
    """
    from . import groundtruth as GT
    from . import mask as M
    from . import run as R
    from . import fit as FIT

    filled = [r for r in doc["frames"] if r.get("basis") == "mosaic"]
    if not filled:
        return 0
    paths = sorted((work / "frames").glob("*.jpg"))
    cam = C.FixedCamera(C=np.asarray(doc["camera"].get("position_yd_soccer",
                                                       doc["camera"]["position_yd"]),
                                     float),
                        image_w=doc["camera"]["image_w"],
                        image_h=doc["camera"]["image_h"])
    vt = doc["venue_transform"]
    A = np.array([[vt["x_sign"], 0.0, vt["x_offset"]],
                  [0.0, vt["y_sign"], vt["y_offset"]],
                  [0.0, 0.0, 1.0]])
    rm = M.build(paths)
    rng = np.random.default_rng(20260827)
    improved = 0
    for rec in filled:
        i = rec["f"]
        c = rec["camera"]
        prior = C.Pose(pan=np.radians(c["pan_deg"]), tilt=np.radians(c["tilt_deg"]),
                       f=float(c["focal_px"]), roll=np.radians(c.get("roll_deg", 0.0)))
        sigma = max(expected_error_yd(rec["mosaic_gap"]),
                    rec.get("mosaic_spread_yd") or 0.0)
        bgr = cv2.imread(str(paths[i]))
        if bgr is None:
            continue
        px, _ = R.paint_pixels(bgr, rm.mask, rng=rng)
        # Associate, refine, repeat with a shrinking gate - the same loop
        # `ur.calibrate.run.icp` uses, and it is not optional. Associating once
        # against a prior that is two yards out assigns pixels to the wrong
        # feature and then fits beautifully to the wrong assignment: measured
        # that way, the refined pose's error tracked the prior's sigma at a ratio
        # of 0.999, which is a refit that has learned nothing. The box stays
        # anchored on the original prior throughout; only the association moves.
        cur, res = prior, None
        for gate in R.ASSOC_GATE_YD:
            cpx, lpx = R.associate(cam, cur, px, gate, rng=rng)
            if len(cpx) + len(lpx) < R.MIN_TOTAL_PX:
                break
            res = FIT.refine_world_prior(cam, cur, cpx, lpx, sigma, anchor=prior)
            cur = res.pose
        if res is None or not res.ok or not np.isfinite(res.rms_yd):
            continue
        # A refit that has run to the edge of the box is a refit the box is
        # deciding rather than the paint, and it is recorded as such.
        probe = _image_probe(cam)
        moved = agreement_yd(cam, [prior, res.pose], probe)
        if not np.isfinite(moved):
            continue
        # Now that the paint has spoken, the homography comes from the model
        # again: `COMPOSE_NOT_MODEL` is an argument about a pose nothing on the
        # frame itself has checked, and this one has been fitted to its own
        # pixels. Same construction as `write_calibration`.
        H = A @ np.linalg.inv(cam.homography(res.pose))
        H = H / H[2, 2]
        rec["H"] = [[round(float(v), 10) for v in row] for row in H]
        # Keep the mosaic answer beside the refined one: if the refit is
        # rejected below, the mosaic pose is what stands.
        rec["H_mosaic"] = rec["H"]
        rec["camera_mosaic"] = rec["camera"]
        rec["refit_rms_yd"] = round(float(res.rms_yd), 5)
        rec["refit_moved_yd"] = round(float(moved), 4)
        rec["refit_circle_span_deg"] = round(float(res.circle_span_deg), 1)
        rec["refit_n_px"] = int(res.n_circle + res.n_line)
        rec["refit_at_box_edge"] = bool(moved > 0.9 * FIT.PRIOR_SIGMAS * sigma)
        # **The residual cannot tell you the refit found the right paint.** On
        # p0003 and p0008, refits with residuals of 0.129-0.150 yd over a 220-360
        # degree arc and 900 line pixels came back 3.6, 12.6 and 17.7 yd wrong:
        # a prior a yard out makes `associate` hand the optimiser a *different*
        # set of white pixels - a penalty arc read as the centre circle, a goal
        # line read as the halfway line - and the fit is then perfectly
        # self-consistent and completely wrong. That is docs/28 Part 2 exactly,
        # and the known-geometry check is the thing built for it: it finds two
        # points whose field position is known to the inch, in image space only,
        # and measures where this pose puts them.
        rec["refit_known_geometry_err_yd"] = (
            None if (g := GT.check_frame(bgr, rm.mask, cam, res.pose)) is None
            else round(float(g), 4))
        rec["camera"] = {**res.pose.to_dict(), "n_circle_px": res.n_circle,
                         "n_line_px": res.n_line,
                         "p95_yd": (None if not np.isfinite(res.p95_yd)
                                    else round(float(res.p95_yd), 5))}
        improved += 1
    if verbose:
        n = sum(1 for r in filled if "refit_rms_yd" in r)
        edge = sum(1 for r in filled if r.get("refit_at_box_edge"))
        if n:
            rms = [r["refit_rms_yd"] for r in filled if "refit_rms_yd" in r]
            print(f"[mosaic] paint refined {n} of {len(filled)} filled frames; "
                  f"median residual {np.median(rms):.3f} yd, {edge} sat on the "
                  "edge of the prior box")
    return improved


def check_known_geometry(work: Path, doc: dict, *, verbose: bool = True) -> None:
    """Run the known-geometry check over every mosaic-derived pose, and let it bite.

    `ur/calibrate/run.py` already does this for every frame the paint solved:
    find two points whose field position is known exactly, in image space only,
    back-project them through the frame's own camera model, and fold how far
    they land from where they must be into the confidence. It is the only check
    in the project that is independent of the solve, and `docs/28` Part 2 is the
    story of what happens without it.

    Mosaic frames went round it. They get it here, through the same
    `groundtruth.penalty_yd` and the same `exp(-total / 0.45)`, so a filled
    frame's confidence means what every other frame's confidence means.
    """
    from . import groundtruth as GT
    from . import mask as M

    filled = [r for r in doc["frames"] if str(r.get("basis", "")).startswith("mosaic")]
    if not filled:
        return
    paths = sorted((work / "frames").glob("*.jpg"))
    cam = C.FixedCamera(C=np.asarray(doc["camera"].get("position_yd_soccer",
                                                       doc["camera"]["position_yd"]),
                                     float),
                        image_w=doc["camera"]["image_w"],
                        image_h=doc["camera"]["image_h"])
    rm = M.build(paths)
    tested = demoted = 0
    for rec in filled:
        c = rec["camera"]
        pose = C.Pose(pan=np.radians(c["pan_deg"]), tilt=np.radians(c["tilt_deg"]),
                      f=float(c["focal_px"]), roll=np.radians(c.get("roll_deg", 0.0)))
        bgr = cv2.imread(str(paths[rec["f"]]))
        if bgr is None:
            continue
        g = GT.check_frame(bgr, rm.mask, cam, pose)
        rec["known_geometry_err_yd"] = None if g is None else round(float(g), 4)
        if g is None:
            continue
        tested += 1
        before = rec["confidence"]
        base = -CONF_SCALE_YD * np.log(max(before, 1e-9))
        total = float(np.hypot(base, GT.penalty_yd(g)))
        rec["confidence"] = round(float(np.clip(np.exp(-total / CONF_SCALE_YD), 0, 1)), 4)
        if rec["confidence"] < 0.5 <= before:
            demoted += 1
    if verbose:
        print(f"[mosaic] known-geometry check ran on {tested} of {len(filled)} "
              f"filled frames; {demoted} dropped below the threshold because of it")

if __name__ == "__main__":
    raise SystemExit(main())
