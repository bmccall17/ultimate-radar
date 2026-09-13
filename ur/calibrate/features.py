"""Pulling the two useful shapes out of the paint: the halfway line and the circle.

Not used as correspondences — the fit is a chamfer against all the paint at once,
which is more robust than any point-picking. These are used to *seed* it. A blind
grid search over camera centre, pan, tilt and focal length has too many local
minima to trust on a frame this sparse; but the ellipse tells you almost directly
where the camera must be looking and how long the lens is, which collapses the
search to something a few seconds of compute settles honestly.

Also here: player suppression. Players wear white, and white on green is exactly
what the paint detector is looking for, so a Sol player in a white kit lights up
like a line. docs/04-milestones.md anticipates this — "use M2's detector once it
exists; a crude motion mask first" — and this is the crude version: anything
sitting on the grass that is too solid to be a line gets cut out of the paint.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

GRASS_LO = np.array([28, 40, 40], np.uint8)
GRASS_HI = np.array([95, 255, 255], np.uint8)


def player_mask(bgr: np.ndarray, *, min_area: int = 120, dilate: int = 5) -> np.ndarray:
    """Solid non-grass blobs standing on the grass. 255 = probably a player."""
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    grass = cv2.inRange(hsv, GRASS_LO, GRASS_HI)
    not_grass = cv2.bitwise_not(grass)
    # A painted line is thin: it does not survive an erosion that a torso does.
    solid = cv2.morphologyEx(not_grass, cv2.MORPH_OPEN,
                             cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))
    n, labels, stats, _ = cv2.connectedComponentsWithStats(solid, connectivity=8)
    out = np.zeros_like(solid)
    for i in range(1, n):
        if stats[i, cv2.CC_STAT_AREA] >= min_area:
            out[labels == i] = 255
    if dilate:
        out = cv2.dilate(out, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (dilate, dilate)))
    return out


@dataclass
class LineFit:
    """A line as (point, unit direction) plus the pixels that voted for it."""

    p0: np.ndarray
    d: np.ndarray
    n_px: int
    length_px: float
    inliers: np.ndarray | None = None    # (N, 2) image pixels that voted for it

    def signed_distance(self, pts: np.ndarray) -> np.ndarray:
        v = np.asarray(pts, float) - self.p0
        return v[:, 0] * self.d[1] - v[:, 1] * self.d[0]


@dataclass
class EllipseFit:
    centre: tuple[float, float]
    axes: tuple[float, float]        # full lengths, as cv2.fitEllipse returns
    angle_deg: float
    n_px: int
    rms_px: float
    inliers: np.ndarray | None = None    # (N, 2) image pixels on the conic

    @property
    def mean_radius_px(self) -> float:
        return (self.axes[0] + self.axes[1]) / 4.0


def _angular_coverage(pts: np.ndarray, cx: float, cy: float,
                      a: float, b: float, ang_deg: float, bins: int = 12) -> float:
    """Share of the conic's circumference that actually has inliers on it.

    The test that separates a circle from a line pretending to be one. Five
    nearly-collinear points fit a vast, needle-thin ellipse whose flank happens
    to run along the halfway line, and it can collect thousands of inliers and a
    tiny residual while being complete nonsense - on frame 134 that produced a
    97-yard reprojection error from a fit whose own numbers looked healthy. A
    genuine centre circle has inliers spread around it; the impostor has them
    all in one narrow sector.
    """
    t = np.radians(ang_deg)
    R = np.array([[np.cos(t), np.sin(t)], [-np.sin(t), np.cos(t)]])
    q = (pts - np.array([cx, cy])) @ R.T
    ra, rb = max(a / 2.0, 1e-6), max(b / 2.0, 1e-6)
    th = np.arctan2(q[:, 1] / rb, q[:, 0] / ra)
    idx = ((th + np.pi) / (2 * np.pi) * bins).astype(int) % bins
    return float(len(np.unique(idx))) / bins


def find_centre_circle_ransac(paint: np.ndarray, *, iters: int = 4000,
                              tol_px: float = 3.5, min_axis: float = 90.0,
                              max_axis: float = 2600.0, seed: int = 20260827,
                              min_inliers: int = 250, min_ratio: float = 0.05,
                              min_coverage: float = 0.5) -> EllipseFit | None:
    """Find the centre circle by RANSAC, without being told which line is which.

    The obvious approach — take the longest straight run as the halfway line,
    remove it, fit an ellipse to the rest — fails on this footage, and fails
    quietly. The longest straight run in a wide shot is the *ultimate* far
    sideline (1344 px in the anchor frame), not the halfway line (which is
    foreshortened to a few hundred), so the line was removed from the wrong
    place and the ellipse then fitted to a patch of boundary noise: axes
    151x335 px for a circle that is a thousand pixels across.

    So the circle is found first and on its own terms. Five points define a
    conic; a conic supported by thousands of paint pixels at this scale is the
    centre circle and nothing else on the pitch looks like it.
    """
    ys, xs = np.nonzero(paint)
    if len(xs) < min_inliers:
        return None
    pts = np.stack([xs, ys], axis=1).astype(np.float64)
    rng = np.random.default_rng(seed)
    n = len(pts)

    best_inl: np.ndarray | None = None
    best_score = 0
    for _ in range(iters):
        idx = rng.choice(n, size=5, replace=False)
        sample = pts[idx].astype(np.float32)
        # Degenerate (near-collinear) samples give meaningless conics.
        c = sample - sample.mean(axis=0)
        if np.linalg.svd(c, compute_uv=False)[1] < 8.0:
            continue
        try:
            (cx, cy), (a, b), ang = cv2.fitEllipse(sample)
        except cv2.error:
            continue
        if not (min_axis <= min(a, b) and max(a, b) <= max_axis):
            continue
        if min(a, b) / max(max(a, b), 1e-9) < min_ratio:
            continue
        d = _ellipse_residual(pts, cx, cy, a, b, ang)
        inl = np.abs(d) < tol_px
        score = int(inl.sum())
        if score > best_score and _angular_coverage(pts[inl], cx, cy, a, b, ang) >= min_coverage:
            best_score, best_inl = score, inl

    if best_inl is None or best_score < min_inliers:
        return None

    pts_in = pts[best_inl]
    for _ in range(3):
        (cx, cy), (a, b), ang = cv2.fitEllipse(pts_in.astype(np.float32))
        d = _ellipse_residual(pts, cx, cy, a, b, ang)
        pts_in = pts[np.abs(d) < tol_px]
        if len(pts_in) < min_inliers:
            return None
    (cx, cy), (a, b), ang = cv2.fitEllipse(pts_in.astype(np.float32))
    if (_angular_coverage(pts_in, cx, cy, a, b, ang) < min_coverage
            or min(a, b) / max(max(a, b), 1e-9) < min_ratio
            or max(a, b) > max_axis):
        return None
    rms = float(np.sqrt(np.mean(_ellipse_residual(pts_in, cx, cy, a, b, ang) ** 2)))
    return EllipseFit(centre=(float(cx), float(cy)), axes=(float(a), float(b)),
                      angle_deg=float(ang), n_px=int(len(pts_in)), rms_px=rms,
                      inliers=pts_in.copy())


def _ellipse_residual(pts: np.ndarray, cx: float, cy: float,
                      a: float, b: float, ang_deg: float) -> np.ndarray:
    """Approximate signed distance from each point to the ellipse, in pixels."""
    t = np.radians(ang_deg)
    R = np.array([[np.cos(t), np.sin(t)], [-np.sin(t), np.cos(t)]])
    q = (pts - np.array([cx, cy])) @ R.T
    ra, rb = max(a / 2.0, 1e-6), max(b / 2.0, 1e-6)
    return (np.hypot(q[:, 0] / ra, q[:, 1] / rb) - 1.0) * (ra + rb) / 2.0


def find_halfway_line(paint: np.ndarray, ell: EllipseFit | None = None,
                      *, min_len_frac: float = 0.10,
                      centre_tol_px: float = 40.0) -> LineFit | None:
    """The halfway line: a straight run that passes through the circle's centre.

    Without the circle to anchor it this picks the longest line in the frame,
    which on a wide shot is the ultimate sideline. With it, the test is
    geometric rather than a guess about which line happens to be longest — a
    diameter passes through the centre and the sidelines do not come close.
    """
    h, w = paint.shape
    min_len = int(min_len_frac * max(h, w))
    segs = cv2.HoughLinesP(paint, 1, np.pi / 360, threshold=70,
                           minLineLength=min_len, maxLineGap=30)
    if segs is None:
        return None
    segs = segs.reshape(-1, 4).astype(np.float64)

    ys, xs = np.nonzero(paint)
    pts = np.stack([xs, ys], axis=1).astype(np.float64)
    centre = np.array(ell.centre) if ell is not None else None

    best: LineFit | None = None
    lens = np.hypot(segs[:, 2] - segs[:, 0], segs[:, 3] - segs[:, 1])
    for i in np.argsort(-lens)[:60]:
        x1, y1, x2, y2 = segs[i]
        p0 = np.array([x1, y1])
        d = np.array([x2 - x1, y2 - y1])
        nrm = np.linalg.norm(d)
        if nrm < 1e-6:
            continue
        d = d / nrm
        for _ in range(3):
            v = pts - p0
            perp = np.abs(v[:, 0] * d[1] - v[:, 1] * d[0])
            inl = pts[perp < 4.0]
            if len(inl) < 50:
                break
            p0 = inl.mean(axis=0)
            _, _, vt = np.linalg.svd(inl - p0, full_matrices=False)
            d = vt[0] / np.linalg.norm(vt[0])
        else:
            if centre is not None:
                off = abs((centre - p0) @ np.array([d[1], -d[0]]))
                if off > centre_tol_px:
                    continue
            v = pts - p0
            perp = np.abs(v[:, 0] * d[1] - v[:, 1] * d[0])
            inl = pts[perp < 4.0]
            along = (inl - p0) @ d
            span = float(along.max() - along.min()) if len(along) else 0.0
            cand = LineFit(p0=p0, d=d, n_px=len(inl), length_px=span,
                           inliers=inl.copy())
            if best is None or cand.length_px > best.length_px:
                best = cand
    return best


def line_pixels_excluding_circle(line: LineFit, ell: EllipseFit | None,
                                 *, margin_px: float = 6.0) -> np.ndarray:
    """Halfway-line pixels with the circle's own pixels taken out.

    The line crosses the circle, so near the two crossings a pixel belongs to
    both and would be counted twice with contradictory meanings - once as "this
    is 10.0 yd from the centre" and once as "this is on x = 0". Both are true
    there, which makes those pixels uninformative rather than doubly informative.
    """
    if line.inliers is None or len(line.inliers) == 0:
        return np.zeros((0, 2))
    pts = line.inliers
    if ell is None or ell.inliers is None or len(ell.inliers) == 0:
        return pts
    d = _ellipse_residual(pts, ell.centre[0], ell.centre[1],
                          ell.axes[0], ell.axes[1], ell.angle_deg)
    return pts[np.abs(d) > margin_px]


def find_centre_circle(paint: np.ndarray, line: LineFit | None,
                       *, exclude_px: float = 7.0) -> EllipseFit | None:
    """Deprecated: kept only so older probes still import. Use the RANSAC version."""
    return find_centre_circle_ransac(paint)


def draw_features(bgr: np.ndarray, line: LineFit | None,
                  ell: EllipseFit | None) -> np.ndarray:
    img = bgr.copy()
    h, w = img.shape[:2]
    if line is not None:
        t = np.array([-2000.0, 2000.0])
        a = line.p0 + t[0] * line.d
        b = line.p0 + t[1] * line.d
        cv2.line(img, tuple(np.round(a).astype(int)), tuple(np.round(b).astype(int)),
                 (0, 255, 0), 2, cv2.LINE_AA)
    if ell is not None:
        cv2.ellipse(img, (int(ell.centre[0]), int(ell.centre[1])),
                    (int(ell.axes[0] / 2), int(ell.axes[1] / 2)),
                    ell.angle_deg, 0, 360, (0, 165, 255), 2, cv2.LINE_AA)
        cv2.drawMarker(img, (int(ell.centre[0]), int(ell.centre[1])), (0, 165, 255),
                       cv2.MARKER_CROSS, 22, 2)
    return img
