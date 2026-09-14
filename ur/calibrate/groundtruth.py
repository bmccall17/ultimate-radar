"""Check each frame against geometry whose position is known exactly.

This is the third and strongest input to `confidence`, and the only one that can
catch the failure that shipped two broken possessions.

The other two are weaker in ways that matter:

- **`residual_yd` is in-sample.** It is measured on the very pixels the frame was
  fitted to, so a fit that locked onto the wrong pixels scores beautifully.
- **Pose agreement with neighbours is out-of-sample but not independent.** The
  sequential pass initialises each frame from its neighbour's answer, so a stretch
  that drifts drifts *smoothly*. Being consistent with your neighbours is no
  defence when your neighbours are wrong in the same direction.

What neither can do is compare the frame to something outside the solve. On a
pitch with no gridiron paint, the two points whose field position is known exactly
and which appear in most frames are where the halfway line crosses the centre
circle — soccer-frame `(0, ±10.0066)`. Find them **in image space only**, from the
detected line and conic, back-project them through the frame's own camera model,
and measure how far the answer lands from where it must be. That number is in
yards and is exactly the quantity `docs/03` says confidence is about.

`ur/calibrate/accept.py` has done this for years, on twenty held-out frames, as
M1's acceptance gate. It was never run on p0002 or p0003 — and both were wrong by
4.6 and 8.7 yd while every in-possession signal looked healthy, with p0003
published on the live site throughout. **A test that is only ever run on the
possession it was written for is a test of that possession.** So it runs on every
frame now, and feeds the number the tracker already reads.

## It abstains rather than guessing

`accept.py`'s own docstring records an earlier version of this test reporting two
good frames as 10 and 34 yards wrong, because its per-frame RANSAC had locked onto
a spurious conic. A check that fires wrongly is worse than no check, because it
costs the signal you were relying on.

So this only ever *lowers* confidence, never raises it, and only when it has both
a conic and a line and they cross twice. A frame it cannot test keeps the
confidence the other two inputs gave it, and says so in `note`. That means a
possession where the geometry is never detectable is not condemned by this check —
it is simply not defended by it either, which is the honest position.
"""

from __future__ import annotations

import cv2
import numpy as np

from . import features as F
from . import fit, paint
from . import world as W

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


# Below this the check says nothing: a frame placed to within half a yard by
# known geometry is as good as this project measures anything.
TOLERANCE_YD = 0.5


def check_frame(bgr: np.ndarray, region: np.ndarray, cam, pose) -> float | None:
    """Reprojection error in yards at the two exactly-known points, or None.

    None means "not testable here", which is different from zero and must not be
    read as a pass.
    """
    if pose is None:
        return None
    usable = cv2.bitwise_and(region, cv2.bitwise_not(F.player_mask(bgr)))
    pm = paint.largest_components(paint.paint_mask(bgr, region=usable), min_area=60)
    ell = F.find_centre_circle_ransac(pm)
    if ell is None:
        return None
    line = F.find_halfway_line(pm, ell)
    if line is None:
        return None
    pts = line_ellipse_intersections(line, ell)
    if len(pts) != 2:
        return None
    # The camera sits on the -y side of the pitch, so the crossing higher in the
    # image is the far one, at world y = +R. This fixes only which label goes on
    # which point, never where the point is.
    far, near = (pts[0], pts[1]) if pts[0][1] < pts[1][1] else (pts[1], pts[0])
    truth = np.array([[0.0, +W.CENTRE_CIRCLE_R], [0.0, -W.CENTRE_CIRCLE_R]])
    got, ok = fit.backproject(cam, pose, np.array([far, near]))
    errs = [float(np.hypot(*(got[k] - truth[k])))
            if ok[k] and np.isfinite(got[k]).all() else np.nan
            for k in range(2)]
    if not np.isfinite(errs).any():
        return None
    return float(np.nanmean(errs))


def penalty_yd(err: float | None) -> float:
    """How much of that error counts against the frame.

    The tolerance is subtracted rather than the raw error being used, so a frame
    that is right does not accumulate a penalty for the test's own noise. Beyond
    it the error is taken at face value: being three yards from a point whose
    position is known exactly is being three yards wrong.
    """
    if err is None or not np.isfinite(err):
        return 0.0
    return max(0.0, float(err) - TOLERANCE_YD)
