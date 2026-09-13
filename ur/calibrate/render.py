"""Draw the world model back onto the video.

docs/04-milestones.md calls this "the only honest way to see whether calibration
is working", and it is built before the calibration rather than after for exactly
that reason. A residual is a number that can be small for the wrong reasons — a
fit that has locked onto the ultimate paint instead of the soccer paint, or onto
half the circle, will report a comfortable residual and be badly wrong. Lines
drawn on the grass cannot lie about that.

Colour convention, consistent across every render this project makes:

    cyan     soccer geometry (what the calibration was actually fitted to)
    yellow   ultimate field (soccer geometry plus the venue transform - so a
             yellow line that is off while the cyan lines are on means the venue
             transform is wrong, not the calibration)
    magenta  detected paint
    red      horizon, and anything the fit was forbidden to use
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from . import world as W
from .camera import FixedCamera, Pose

CYAN = (255, 235, 60)
YELLOW = (60, 235, 255)
MAGENTA = (255, 0, 255)
RED = (60, 60, 255)
GREY = (150, 150, 150)


def _polyline(img, pts_img, ok, colour, thickness=2, closed=False):
    """Draw only the runs of a polyline that are actually in front of the camera."""
    h, w = img.shape[:2]
    pts = pts_img
    runs, cur = [], []
    n = len(pts)
    order = list(range(n)) + ([0] if closed and n else [])
    for i in order:
        if ok[i] and np.isfinite(pts[i]).all() and -4 * w < pts[i, 0] < 5 * w and -4 * h < pts[i, 1] < 5 * h:
            cur.append(pts[i])
        else:
            if len(cur) > 1:
                runs.append(cur)
            cur = []
    if len(cur) > 1:
        runs.append(cur)
    for run in runs:
        cv2.polylines(img, [np.round(np.array(run)).astype(np.int32)], False,
                      colour, thickness, cv2.LINE_AA)


@dataclass
class RenderOptions:
    show_paint: bool = True
    show_horizon: bool = True
    show_ultimate: bool = True
    show_mask: bool = False
    thickness: int = 2


def draw(frame: np.ndarray, cam: FixedCamera, pose: Pose,
         venue: W.VenueTransform | None = None,
         field: W.UltimateField | None = None,
         paint: np.ndarray | None = None,
         mask: np.ndarray | None = None,
         label: str = "",
         opts: RenderOptions | None = None) -> np.ndarray:
    opts = opts or RenderOptions()
    img = frame.copy()
    h, w = img.shape[:2]

    if opts.show_mask and mask is not None:
        shade = img.copy()
        shade[mask == 0] = (shade[mask == 0] * 0.35).astype(np.uint8)
        img = shade

    if opts.show_paint and paint is not None:
        img[paint > 0] = MAGENTA

    # --- soccer geometry: what the fit was actually against -------------------
    for feat in W.soccer_features():
        pts, ok = cam.project(feat.points, pose)
        _polyline(img, pts, ok, CYAN, opts.thickness, closed=feat.closed)

    # --- the ultimate field, via the venue transform ---------------------------
    if opts.show_ultimate and venue is not None and field is not None:
        for name, poly in field.outline().items():
            dense = []
            for a, b in zip(poly[:-1], poly[1:]):
                dense.append(W.segment_points(a, b, step=0.5))
            dense = np.vstack(dense) if dense else poly
            pts, ok = cam.project(venue.to_soccer(dense), pose)
            _polyline(img, pts, ok, YELLOW, opts.thickness)
        py, okp = cam.project(venue.to_soccer(field.pylons()), pose)
        for p, o in zip(py, okp):
            if o and np.isfinite(p).all():
                cv2.circle(img, (int(round(p[0])), int(round(p[1]))), 6, YELLOW, 2, cv2.LINE_AA)

    # --- horizon ---------------------------------------------------------------
    if opts.show_horizon:
        H = cam.homography(pose)
        Hinv = np.linalg.inv(H)
        a, b, c = Hinv[2]
        if abs(b) > 1e-12:
            xs = np.array([0.0, w - 1.0])
            ys = -(a * xs + c) / b
            if np.isfinite(ys).all() and np.abs(ys).max() < 10 * h:
                cv2.line(img, (int(xs[0]), int(round(ys[0]))),
                         (int(xs[1]), int(round(ys[1]))), RED, 1, cv2.LINE_AA)
                cv2.putText(img, "horizon", (12, int(round(ys[0])) - 8),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, RED, 1, cv2.LINE_AA)

    if label:
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.62, 2)
        cv2.rectangle(img, (8, 8), (20 + tw, 22 + th), (0, 0, 0), -1)
        cv2.putText(img, label, (14, 16 + th), cv2.FONT_HERSHEY_SIMPLEX, 0.62,
                    (255, 255, 255), 2, cv2.LINE_AA)
    return img


def legend(img: np.ndarray) -> np.ndarray:
    rows = [("soccer geometry (fitted)", CYAN),
            ("ultimate field (via venue transform)", YELLOW),
            ("detected paint", MAGENTA)]
    h = img.shape[0]
    y0 = h - 18 * len(rows) - 14
    cv2.rectangle(img, (8, y0 - 8), (330, h - 8), (0, 0, 0), -1)
    for i, (text, colour) in enumerate(rows):
        y = y0 + 14 + 18 * i
        cv2.line(img, (18, y - 4), (44, y - 4), colour, 3, cv2.LINE_AA)
        cv2.putText(img, text, (52, y), cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                    (235, 235, 235), 1, cv2.LINE_AA)
    return img
