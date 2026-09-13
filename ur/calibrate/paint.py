"""Finding the painted lines, and turning them into something to fit against.

White paint on grass is bright, unsaturated and — the part that does the work —
*thin*. A line survives an opening with a long thin kernel at its own
orientation; a torso does not survive one at any orientation. This is the same
detector that answered M0's question 2 (`tools/paint.py` now calls in here).

The output calibration actually consumes is a **distance transform**: for each
pixel, how far to the nearest paint. Fitting then asks only "how far is each
point of my world model from some paint", never "is every piece of paint
explained". That asymmetry is deliberate and it is what makes the fit robust to
the ultimate lines and pylons painted over the soccer markings — extra paint
costs nothing, missing paint costs everything.
"""

from __future__ import annotations

import cv2
import numpy as np

# Tuned on work/p0001 frame 000180 against the visible centre circle, which is
# the faintest thing the fit depends on. The night game plus a 5.4 Mbps encode
# make the soccer paint much lower-contrast than the M0 defaults assumed: at
# TOPHAT_THRESH 12 roughly a third of the circle went undetected, and the fit
# then locked onto whatever else was bright. See eval/m1/probe/paintbest.jpg.
MAX_SAT = 110
MIN_VAL = 105
KERNEL_LEN = 21
N_ANGLES = 12
TOPHAT_THRESH = 8


def paint_mask(bgr: np.ndarray, *, max_sat: int = MAX_SAT, min_val: int = MIN_VAL,
               kernel_len: int = KERNEL_LEN, n_angles: int = N_ANGLES,
               region: np.ndarray | None = None) -> np.ndarray:
    """Bright, unsaturated, locally brighter than its surroundings, and thin."""
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    bright = cv2.inRange(hsv, np.array([0, 0, min_val], np.uint8),
                         np.array([179, max_sat, 255], np.uint8))

    grey = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    bg = cv2.morphologyEx(grey, cv2.MORPH_OPEN,
                          cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (25, 25)))
    _, ridge = cv2.threshold(cv2.subtract(grey, bg), TOPHAT_THRESH, 255, cv2.THRESH_BINARY)

    cand = cv2.bitwise_and(bright, ridge)
    if region is not None:
        cand = cv2.bitwise_and(cand, region)

    acc = np.zeros_like(cand)
    base = np.zeros((kernel_len, kernel_len), np.uint8)
    cv2.line(base, (0, kernel_len // 2), (kernel_len - 1, kernel_len // 2), 1, 1)
    for a in np.linspace(0, 180, n_angles, endpoint=False):
        M = cv2.getRotationMatrix2D((kernel_len / 2 - 0.5, kernel_len / 2 - 0.5), a, 1.0)
        k = cv2.warpAffine(base, M, (kernel_len, kernel_len), flags=cv2.INTER_NEAREST)
        acc = cv2.bitwise_or(acc, cv2.morphologyEx(cand, cv2.MORPH_OPEN, k))
    return acc


def distance_field(paint: np.ndarray, *, cap_px: float = 60.0) -> np.ndarray:
    """Distance from every pixel to the nearest paint pixel, in pixels.

    Capped, because an unbounded distance lets a single badly-initialised model
    point dominate the objective and drag the whole fit after it.
    """
    inv = np.where(paint > 0, 0, 255).astype(np.uint8)
    dist = cv2.distanceTransform(inv, cv2.DIST_L2, 5)
    return np.minimum(dist, cap_px)


def coverage(paint: np.ndarray, region: np.ndarray | None = None) -> float:
    """Share of the usable region that is paint. A frame with almost none is a
    frame whose calibration cannot be trusted, whatever the optimiser reports."""
    if region is None:
        return float((paint > 0).mean())
    usable = region > 0
    if not usable.any():
        return 0.0
    return float((paint[usable] > 0).mean())


def largest_components(paint: np.ndarray, *, min_area: int = 120,
                       max_n: int = 40) -> np.ndarray:
    """Drop speckle. Chamfer is robust to extra paint but not to a fog of it."""
    n, labels, stats, _ = cv2.connectedComponentsWithStats(paint, connectivity=8)
    if n <= 1:
        return paint
    order = np.argsort(-stats[1:, cv2.CC_STAT_AREA]) + 1
    keep = [i for i in order[:max_n] if stats[i, cv2.CC_STAT_AREA] >= min_area]
    out = np.zeros_like(paint)
    for i in keep:
        out[labels == i] = 255
    return out
