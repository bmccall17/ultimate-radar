"""Fitting the camera to the paint.

The objective is a one-directional chamfer: project the world model into the
image, look up each point's distance to the nearest detected paint, and sum a
robust loss. One-directional on purpose — it asks "is every part of my model
sitting on paint", never "is every piece of paint explained". Extra paint
therefore costs nothing, which matters here because the ultimate lines and the
pylons are painted over the soccer markings and are not in the soccer model.

Two guards that are easy to leave out and expensive to leave out:

- A model point that projects outside the image is charged the full capped
  distance, not skipped. Skipping it lets the optimiser score zero by swinging
  the model off-screen entirely, which it will find immediately.
- A fit is only reported when enough of the model was actually in shot. A
  residual computed from three visible points is not a small residual, it is an
  absent measurement, and AD-1 requires the difference to be legible downstream.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import least_squares

from . import world as W
from .camera import FixedCamera, Pose

HUBER_PX = 6.0
MIN_VISIBLE_FRAC = 0.25


@dataclass
class FitResult:
    pose: Pose
    cost: float                  # mean robust loss, pixels
    rms_px: float                # rms distance-to-paint over visible model points
    visible_frac: float
    ok: bool
    reason: str = ""

    def to_dict(self) -> dict:
        return {**self.pose.to_dict(),
                "cost_px": round(float(self.cost), 4),
                "rms_px": round(float(self.rms_px), 4),
                "visible_frac": round(float(self.visible_frac), 4),
                "ok": bool(self.ok), **({"reason": self.reason} if self.reason else {})}


def _sample(features: list[W.Feature], stride: int = 1) -> tuple[np.ndarray, np.ndarray]:
    pts, wts = [], []
    for f in features:
        p = f.points[::stride]
        pts.append(p)
        wts.append(np.full(len(p), f.weight))
    return np.vstack(pts), np.concatenate(wts)


def sample_bilinear(field: np.ndarray, xy: np.ndarray) -> np.ndarray:
    """Bilinear lookup into the distance field.

    Not a refinement — a correctness fix. Sampling the distance field with
    integer indices makes the objective piecewise constant, so the optimiser's
    finite differences see an exactly zero gradient for any step smaller than a
    pixel and it terminates at its starting point while reporting success. That
    is what "the fit does not move" looked like before this existed.
    """
    h, w = field.shape
    x = np.clip(xy[:, 0], 0, w - 1.001)
    y = np.clip(xy[:, 1], 0, h - 1.001)
    x0 = np.floor(x).astype(np.int32)
    y0 = np.floor(y).astype(np.int32)
    x1, y1 = x0 + 1, y0 + 1
    fx, fy = x - x0, y - y0
    return (field[y0, x0] * (1 - fx) * (1 - fy) + field[y0, x1] * fx * (1 - fy)
            + field[y1, x0] * (1 - fx) * fy + field[y1, x1] * fx * fy)


def residuals(cam: FixedCamera, pose: Pose, dist: np.ndarray,
              pts: np.ndarray, wts: np.ndarray, cap: float) -> tuple[np.ndarray, float]:
    """Per-model-point distance to nearest paint. Returns (residuals, visible frac)."""
    h, w = dist.shape
    img, ok = cam.project(pts, pose)
    inside = ok & np.isfinite(img).all(axis=1)
    if inside.any():
        inside &= ((img[:, 0] >= 0) & (img[:, 0] < w)
                   & (img[:, 1] >= 0) & (img[:, 1] < h))
    r = np.full(len(pts), cap, float)
    if inside.any():
        r[inside] = sample_bilinear(dist, img[inside])
    return r * wts, float(inside.mean())


def _huber(r: np.ndarray, delta: float = HUBER_PX) -> np.ndarray:
    a = np.abs(r)
    return np.where(a <= delta, 0.5 * r ** 2, delta * (a - 0.5 * delta)) / delta


def cost(cam: FixedCamera, pose: Pose, dist: np.ndarray,
         pts: np.ndarray, wts: np.ndarray, cap: float) -> tuple[float, float]:
    r, vis = residuals(cam, pose, dist, pts, wts, cap)
    return float(_huber(r).mean()), vis


# --------------------------------------------------------------------------- #
# coarse search - no clever geometry, just enough compute
# --------------------------------------------------------------------------- #

def coarse_search(dist: np.ndarray, w: int, h: int, features: list[W.Feature],
                  *, cap: float = 60.0, scale: int = 4,
                  c_grid: dict | None = None, top_k: int = 8) -> list[tuple[float, FixedCamera, Pose]]:
    """Grid over camera centre and pose, scored on a downsampled distance field.

    Deliberately dumb. A closed-form bootstrap from the conic exists, but it
    carries a two-fold ambiguity and several ways to be subtly wrong, and this
    runs in seconds.
    """
    import cv2

    small = cv2.resize(dist, (w // scale, h // scale), interpolation=cv2.INTER_NEAREST) / 1.0
    sh, sw = small.shape
    pts, wts = _sample(features, stride=6)

    g = c_grid or {}
    sxs = g.get("sx", np.linspace(-24, 24, 5))
    sys_ = g.get("sy", np.linspace(-58, -32, 5))
    szs = g.get("sz", np.linspace(7, 20, 5))
    pans = g.get("pan", np.linspace(-0.85, 0.85, 19))
    tilts = g.get("tilt", np.linspace(0.04, 0.42, 9))
    fs = g.get("f", np.geomspace(700, 3600, 11))

    out: list[tuple[float, FixedCamera, Pose]] = []
    for sx in sxs:
        for sy in sys_:
            for sz in szs:
                cam = FixedCamera(C=np.array([sx, sy, sz]), image_w=sw, image_h=sh)
                for pan in pans:
                    for tilt in tilts:
                        for f in fs:
                            pose = Pose(pan=pan, tilt=tilt, f=f / scale)
                            c, vis = cost(cam, pose, small, pts, wts, cap / scale)
                            if vis >= MIN_VISIBLE_FRAC:
                                out.append((c, cam, pose))
    out.sort(key=lambda t: t[0])
    # De-duplicate: many grid cells land on the same basin.
    picked: list[tuple[float, FixedCamera, Pose]] = []
    for c, cam, pose in out:
        if all(np.linalg.norm(cam.C - p[1].C) > 6.0 or abs(pose.pan - p[2].pan) > 0.12
               for p in picked):
            full = FixedCamera(C=cam.C, image_w=w, image_h=h)
            picked.append((c, full, Pose(pan=pose.pan, tilt=pose.tilt, f=pose.f * scale)))
        if len(picked) >= top_k:
            break
    return picked


# --------------------------------------------------------------------------- #
# refinement
# --------------------------------------------------------------------------- #

def refine_pose(cam: FixedCamera, pose: Pose, dist: np.ndarray,
                features: list[W.Feature], *, cap: float = 60.0,
                with_roll: bool = True, stride: int = 2) -> FitResult:
    """Solve pan/tilt/focal (and roll) for one frame, camera centre fixed."""
    pts, wts = _sample(features, stride=stride)
    f0 = pose.f

    def unpack(x):
        return Pose(pan=x[0], tilt=x[1], f=x[2] * f0,
                    roll=(x[3] if with_roll else pose.roll))

    def fun(x):
        r, _ = residuals(cam, unpack(x), dist, pts, wts, cap)
        return np.sqrt(_huber(r) + 1e-12)

    x0 = [pose.pan, pose.tilt, 1.0] + ([pose.roll] if with_roll else [])
    lo = [pose.pan - 0.5, max(-0.1, pose.tilt - 0.3), 0.55] + ([-0.25] if with_roll else [])
    hi = [pose.pan + 0.5, pose.tilt + 0.3, 1.8] + ([0.25] if with_roll else [])
    sol = least_squares(fun, x0, bounds=(lo, hi), method="trf",
                        x_scale=[0.05, 0.05, 0.05] + ([0.02] if with_roll else []),
                        diff_step=1e-3, max_nfev=400)
    best = unpack(sol.x)
    r, vis = residuals(cam, best, dist, pts, wts, cap)
    rms = float(np.sqrt(np.mean((r / np.maximum(wts, 1e-9)) ** 2)))
    ok = vis >= MIN_VISIBLE_FRAC
    return FitResult(pose=best, cost=float(_huber(r).mean()), rms_px=rms,
                     visible_frac=vis, ok=ok,
                     reason="" if ok else f"only {vis:.0%} of the model was in shot")


def bundle(cam: FixedCamera, poses: list[Pose], dists: list[np.ndarray],
           features: list[W.Feature], *, cap: float = 60.0,
           stride: int = 3) -> tuple[FixedCamera, list[Pose]]:
    """Solve the shared camera centre and every pose together.

    The centre is the parameter the per-frame fit cannot see: any single frame
    can trade centre against pose and land on the same picture. Several frames
    at different pans cannot, because the centre has to explain all of them at
    once. This is what makes the 3-DOF model honest rather than merely small.
    """
    pts, wts = _sample(features, stride=stride)
    n = len(poses)
    f0 = np.array([p.f for p in poses])

    def unpack(x):
        C = x[:3]
        rest = x[3:].reshape(n, 4)
        return C, [Pose(pan=r[0], tilt=r[1], f=r[2] * f0[i], roll=r[3])
                   for i, r in enumerate(rest)]

    def fun(x):
        C, ps = unpack(x)
        cam_i = FixedCamera(C=C, image_w=cam.image_w, image_h=cam.image_h)
        out = []
        for p, d in zip(ps, dists):
            r, _ = residuals(cam_i, p, d, pts, wts, cap)
            out.append(np.sqrt(_huber(r) + 1e-12))
        return np.concatenate(out)

    x0 = np.concatenate([np.asarray(cam.C, float),
                         np.concatenate([[p.pan, p.tilt, 1.0, p.roll] for p in poses])])
    lo = np.concatenate([cam.C - np.array([18.0, 18.0, 9.0]),
                         np.concatenate([[p.pan - 0.4, max(-0.1, p.tilt - 0.25), 0.6, -0.25]
                                         for p in poses])])
    hi = np.concatenate([cam.C + np.array([18.0, 18.0, 9.0]),
                         np.concatenate([[p.pan + 0.4, p.tilt + 0.25, 1.7, 0.25]
                                         for p in poses])])
    sol = least_squares(fun, x0, bounds=(lo, hi), method="trf", max_nfev=300,
                        diff_step=1e-3,
                        x_scale=np.concatenate([[1.0, 1.0, 0.5],
                                                np.tile([0.05, 0.05, 0.05, 0.02], n)]))
    C, ps = unpack(sol.x)
    return FixedCamera(C=C, image_w=cam.image_w, image_h=cam.image_h), ps


# --------------------------------------------------------------------------- #
# seeded bootstrap - much sharper than the blind grid
# --------------------------------------------------------------------------- #

def _ellipse_of_projection(cam: FixedCamera, pose: Pose, r: float,
                           n: int = 72) -> tuple[float, float, float, float, float] | None:
    """Fit an ellipse to the projected world circle. (cx, cy, a, b, angle_rad)."""
    import cv2

    pts, ok = cam.project(W.circle_points(0.0, 0.0, r, n), pose)
    good = ok & np.isfinite(pts).all(axis=1)
    if good.sum() < 12:
        return None
    p = pts[good].astype(np.float32)
    if np.abs(p).max() > 1e5:
        return None
    (cx, cy), (aa, bb), ang = cv2.fitEllipse(p)
    return float(cx), float(cy), float(aa), float(bb), float(np.radians(ang))


def seed_pose(cam: FixedCamera, ell, *, r: float = W.CENTRE_CIRCLE_R,
              pan0: float = 0.0, tilt0: float = 0.25, f0: float = 1800.0) -> Pose | None:
    """Aim the camera so its projected centre circle matches the observed ellipse.

    Five residuals (centre, size, axis ratio, orientation) against three unknowns.
    Overdetermined on purpose: matching the centre alone leaves the fit free to
    trade tilt against focal length, and the two produce visibly different
    pictures that a chamfer would then have to disentangle from a bad start.
    """
    obs_c = np.array(ell.centre, float)
    obs_r = max(ell.mean_radius_px, 1e-3)
    obs_ratio = min(ell.axes) / max(max(ell.axes), 1e-9)
    obs_ang = np.radians(ell.angle_deg)

    def fun(x):
        pose = Pose(pan=x[0], tilt=x[1], f=x[2] * f0)
        got = _ellipse_of_projection(cam, pose, r)
        if got is None:
            return np.array([50.0, 50.0, 5.0, 5.0, 5.0])
        cx, cy, aa, bb, ang = got
        pr = max((aa + bb) / 4.0, 1e-6)
        ratio = min(aa, bb) / max(max(aa, bb), 1e-9)
        dang = np.arctan2(np.sin(ang - obs_ang), np.cos(ang - obs_ang))
        # Orientation of a near-circular ellipse is meaningless, so let its
        # weight fall away as the ellipse rounds out.
        w_ang = float(np.clip(1.0 - ratio, 0.0, 1.0))
        return np.array([(cx - obs_c[0]) / 40.0,
                         (cy - obs_c[1]) / 40.0,
                         np.log(pr / obs_r) * 3.0,
                         (ratio - obs_ratio) * 4.0,
                         np.sin(dang) * 3.0 * w_ang])

    best, best_cost = None, np.inf
    for p0 in (pan0 - 0.45, pan0, pan0 + 0.45):
        for t0 in (0.10, tilt0, 0.40):
            for fm in (0.5, 1.0, 1.9):
                try:
                    sol = least_squares(fun, [p0, t0, fm],
                                        bounds=([-1.3, -0.05, 0.15], [1.3, 0.75, 4.0]),
                                        method="trf", max_nfev=220,
                                        x_scale=[0.05, 0.05, 0.05])
                except Exception:
                    continue
                c = float(np.sum(sol.fun ** 2))
                if c < best_cost:
                    best_cost, best = c, Pose(pan=sol.x[0], tilt=sol.x[1], f=sol.x[2] * f0)
    if best is None or best_cost > 4.0:
        return None
    return best


def bootstrap(dist: np.ndarray, w: int, h: int, features: list[W.Feature], ell,
              *, cap: float = 60.0, top_k: int = 6,
              c_grid: dict | None = None) -> list[tuple[float, FixedCamera, Pose]]:
    """Grid the camera centre only; solve the pose analytically-ish at each.

    Collapsing pan/tilt/focal into a solve is what makes a fine centre grid
    affordable, and the centre is the parameter a single frame is worst at
    pinning down — so this spends the compute where it is actually needed.
    """
    g = c_grid or {}
    sxs = g.get("sx", np.linspace(-30, 30, 13))
    sys_ = g.get("sy", np.linspace(-62, -28, 12))
    szs = g.get("sz", np.linspace(5, 24, 9))
    pts, wts = _sample(features, stride=3)

    scored: list[tuple[float, FixedCamera, Pose]] = []
    for sx in sxs:
        for sy in sys_:
            for sz in szs:
                cam = FixedCamera(C=np.array([sx, sy, sz]), image_w=w, image_h=h)
                pose = seed_pose(cam, ell)
                if pose is None:
                    continue
                c, vis = cost(cam, pose, dist, pts, wts, cap)
                if vis >= MIN_VISIBLE_FRAC:
                    scored.append((c, cam, pose))
    scored.sort(key=lambda t: t[0])

    picked: list[tuple[float, FixedCamera, Pose]] = []
    for c, cam, pose in scored:
        if all(np.linalg.norm(cam.C - p[1].C) > 5.0 for p in picked):
            picked.append((c, cam, pose))
        if len(picked) >= top_k:
            break
    return picked


# --------------------------------------------------------------------------- #
# fitting in world coordinates - the version that actually converges
# --------------------------------------------------------------------------- #
#
# Chamfering the model against a distance field has one structural flaw on this
# footage: the halfway line's painted extent is the pitch width, which is not
# published, so a good share of the modelled line has no paint to sit on and is
# charged a large residual no matter how right the camera is. That noise swamps
# the signal - the anchor frame scored 12 px rms while visibly well aligned.
#
# Turning it around fixes it. RANSAC has already said which pixels belong to the
# circle and which to the halfway line, so back-project *those* through the
# candidate homography and ask how far each lands from where it belongs:
#
#     circle pixel  ->  | |(x, y)| - 10.0066 |   yards
#     line pixel    ->  | x |                    yards
#
# Every residual is a real pixel with a real world meaning, there are no
# unmatched model points to invent error, and the answer comes out in yards -
# the unit M1's acceptance gate is written in.

@dataclass
class WorldFit:
    pose: Pose
    circle_rms_yd: float
    line_rms_yd: float
    rms_yd: float
    p95_yd: float
    n_circle: int
    n_line: int
    ok: bool
    reason: str = ""

    def to_dict(self) -> dict:
        return {**self.pose.to_dict(),
                "circle_rms_yd": round(float(self.circle_rms_yd), 4),
                "line_rms_yd": round(float(self.line_rms_yd), 4),
                "rms_yd": round(float(self.rms_yd), 4),
                "p95_yd": round(float(self.p95_yd), 4),
                "n_circle": int(self.n_circle), "n_line": int(self.n_line),
                "ok": bool(self.ok), **({"reason": self.reason} if self.reason else {})}


def backproject(cam: FixedCamera, pose: Pose, px: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Image pixels -> ground-plane yards. Second return marks points in front."""
    H = cam.homography(pose)
    Hinv = np.linalg.inv(H)
    hom = np.column_stack([px, np.ones(len(px))]) @ Hinv.T
    z = hom[:, 2]
    ok = np.abs(z) > 1e-9
    out = np.full((len(px), 2), np.nan)
    out[ok] = hom[ok, :2] / z[ok, None]
    # Behind the horizon the ground plane folds; those points have no position.
    fwd = np.zeros(len(px), bool)
    fwd[ok] = True
    return out, fwd


def world_residuals(cam: FixedCamera, pose: Pose, circle_px: np.ndarray,
                    line_px: np.ndarray, *, r: float = W.CENTRE_CIRCLE_R,
                    cap_yd: float = 12.0) -> tuple[np.ndarray, np.ndarray]:
    parts, tags = [], []
    if len(circle_px):
        w, ok = backproject(cam, pose, circle_px)
        d = np.full(len(circle_px), cap_yd)
        good = ok & np.isfinite(w).all(axis=1)
        if good.any():
            d[good] = np.hypot(w[good, 0], w[good, 1]) - r
        parts.append(np.clip(d, -cap_yd, cap_yd))
        tags.append(np.zeros(len(circle_px), np.int8))
    if len(line_px):
        w, ok = backproject(cam, pose, line_px)
        d = np.full(len(line_px), cap_yd)
        good = ok & np.isfinite(w).all(axis=1)
        if good.any():
            d[good] = w[good, 0]
        parts.append(np.clip(d, -cap_yd, cap_yd))
        tags.append(np.ones(len(line_px), np.int8))
    if not parts:
        return np.zeros(0), np.zeros(0, np.int8)
    return np.concatenate(parts), np.concatenate(tags)


def _summarise(res: np.ndarray, tags: np.ndarray, pose: Pose,
               min_pts: int = 120) -> WorldFit:
    c, ln = res[tags == 0], res[tags == 1]
    rms = lambda a: float(np.sqrt(np.mean(a ** 2))) if len(a) else float("nan")
    all_abs = np.abs(res)
    ok = len(res) >= min_pts
    return WorldFit(pose=pose, circle_rms_yd=rms(c), line_rms_yd=rms(ln),
                    rms_yd=rms(res),
                    p95_yd=float(np.percentile(all_abs, 95)) if len(res) else float("nan"),
                    n_circle=int(len(c)), n_line=int(len(ln)), ok=ok,
                    reason="" if ok else f"only {len(res)} feature pixels")


def refine_world(cam: FixedCamera, pose: Pose, circle_px: np.ndarray,
                 line_px: np.ndarray, *, f_scale: float = 0.35,
                 with_roll: bool = True) -> WorldFit:
    f0 = pose.f

    def unpack(x):
        return Pose(pan=x[0], tilt=x[1], f=x[2] * f0,
                    roll=(x[3] if with_roll else pose.roll))

    def fun(x):
        res, _ = world_residuals(cam, unpack(x), circle_px, line_px)
        return res

    x0 = [pose.pan, pose.tilt, 1.0] + ([pose.roll] if with_roll else [])
    lo = [pose.pan - 0.6, max(-0.15, pose.tilt - 0.35), 0.4] + ([-0.3] if with_roll else [])
    hi = [pose.pan + 0.6, pose.tilt + 0.35, 2.4] + ([0.3] if with_roll else [])
    sol = least_squares(fun, x0, bounds=(lo, hi), method="trf", loss="cauchy",
                        f_scale=f_scale, diff_step=1e-4, max_nfev=600,
                        x_scale=[0.02, 0.02, 0.02] + ([0.01] if with_roll else []))
    best = unpack(sol.x)
    res, tags = world_residuals(cam, best, circle_px, line_px)
    return _summarise(res, tags, best)


def bundle_world(cam: FixedCamera, poses: list[Pose],
                 obs: list[tuple[np.ndarray, np.ndarray]],
                 *, f_scale: float = 0.35) -> tuple[FixedCamera, list[Pose]]:
    """Shared camera centre, one pose per frame, all solved together.

    The centre is what a single frame cannot pin down: any one view can trade
    centre against pose and produce the same picture. Several views at different
    pans cannot, because one centre has to explain all of them.
    """
    n = len(poses)
    f0 = np.array([p.f for p in poses])

    def unpack(x):
        C = x[:3]
        rest = x[3:].reshape(n, 4)
        return C, [Pose(pan=r[0], tilt=r[1], f=r[2] * f0[i], roll=r[3])
                   for i, r in enumerate(rest)]

    def fun(x):
        C, ps = unpack(x)
        ci = FixedCamera(C=C, image_w=cam.image_w, image_h=cam.image_h)
        out = []
        for p, (cpx, lpx) in zip(ps, obs):
            res, _ = world_residuals(ci, p, cpx, lpx)
            out.append(res)
        return np.concatenate(out)

    x0 = np.concatenate([np.asarray(cam.C, float),
                         np.concatenate([[p.pan, p.tilt, 1.0, p.roll] for p in poses])])
    lo = np.concatenate([cam.C - np.array([25.0, 25.0, 12.0]),
                         np.concatenate([[p.pan - 0.5, max(-0.15, p.tilt - 0.3), 0.5, -0.3]
                                         for p in poses])])
    hi = np.concatenate([cam.C + np.array([25.0, 25.0, 12.0]),
                         np.concatenate([[p.pan + 0.5, p.tilt + 0.3, 2.2, 0.3]
                                         for p in poses])])
    sol = least_squares(fun, x0, bounds=(lo, hi), method="trf", loss="cauchy",
                        f_scale=f_scale, diff_step=1e-4, max_nfev=400,
                        x_scale=np.concatenate([[1.0, 1.0, 0.5],
                                                np.tile([0.02, 0.02, 0.02, 0.01], n)]))
    C, ps = unpack(sol.x)
    return FixedCamera(C=C, image_w=cam.image_w, image_h=cam.image_h), ps
