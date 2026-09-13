"""Which pixels are allowed to influence registration.

M0's review measured the failure this module exists to prevent: on this
broadcast, whole-frame phase correlation reported **a static camera on 10 of 11
frame pairs** while the camera was panning 38-360 px. The rendered score bug and
sponsor banner are 12.6 % of the frame, move exactly 0 px, and score 0.973 and
0.867 on peak response against 0.054 for the playing surface. They win by more
than an order of magnitude. `tools/regcheck.py` reproduces it.

So nothing registers against a raw frame. Three exclusions:

1. **Rendered graphics**, found by temporal stillness rather than hard-coded
   boxes — while the camera pans, the only pixels that do not change are the ones
   drawn on top. Measured with a *median* over frame pairs so that the sponsor
   banner rotating its advert (which it does, once, around t = 15 s) does not
   rescue it into the usable region.
2. **Everything above the horizon.** The stands and the buildings are not on the
   ground plane, so their apparent motion is parallax, not camera motion; a
   homography fitted through them is wrong even when it converges cleanly.
   Bootstrapped from a constant row, then re-derived from the calibration itself
   — the horizon is exactly the vanishing line of the ground plane, which the
   homography hands you for free.
3. **Players**, once M2 exists. Not yet.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

BOOTSTRAP_HORIZON = 430          # measured on this broadcast at 1080p; replaced by
                                 # horizon_from_homography once a calibration exists
HORIZON_MARGIN_PX = 18           # the vanishing line is exact; the paint near it is not


@dataclass
class RegistrationMask:
    mask: np.ndarray             # uint8, 255 = usable
    static_frac: float
    horizon_row: int
    source: str

    @property
    def usable_frac(self) -> float:
        return float(self.mask.mean() / 255.0)

    def to_dict(self) -> dict:
        return {"usable_frac": round(self.usable_frac, 4),
                "static_frac": round(self.static_frac, 4),
                "horizon_row": int(self.horizon_row),
                "source": self.source}


def static_region(frames: list[Path], *, stride: int = 30, max_pairs: int = 12,
                  thresh: float = 2.0) -> tuple[np.ndarray, float]:
    """Pixels that do not change while the camera moves = drawn on top.

    Returns (uint8 mask where 255 means static, fraction static).
    """
    picks = frames[::stride][: max_pairs + 1]
    if len(picks) < 3:
        picks = frames[: max_pairs + 1]
    diffs = []
    prev = None
    for p in picks:
        img = cv2.imread(str(p), cv2.IMREAD_GRAYSCALE)
        if img is None:
            continue
        img = img.astype(np.float32)
        if prev is not None:
            diffs.append(np.abs(img - prev))
        prev = img
    if not diffs:
        raise RuntimeError("could not read enough frames to find the static region")
    # Median, not mean: the banner swaps its advert once, and a mean would let
    # that one large difference promote 12 % of the frame back into use.
    med = np.median(np.stack(diffs, axis=0), axis=0)
    static = (med < thresh).astype(np.uint8) * 255
    # Rendered graphics are solid blocks; speckle from flat grass is not.
    static = cv2.morphologyEx(static, cv2.MORPH_OPEN,
                              cv2.getStructuringElement(cv2.MORPH_RECT, (25, 9)))
    static = cv2.morphologyEx(static, cv2.MORPH_CLOSE,
                              cv2.getStructuringElement(cv2.MORPH_RECT, (61, 21)))
    return static, float(static.mean() / 255.0)


def horizon_from_homography(H_world_to_img: np.ndarray, w: int, h: int) -> int | None:
    """The ground plane's vanishing line, as an image row.

    Ground points map through H; the line where the third homogeneous coordinate
    vanishes is the horizon. Returns the topmost row of the ground's image, or
    None when the horizon is outside the frame (a steeply-tilted shot, where the
    whole frame is ground and nothing needs cutting).
    """
    Hinv = np.linalg.inv(np.asarray(H_world_to_img, float))
    # Image point (x, y, 1) is on the horizon when the world point behind it is
    # at infinity: the third row of Hinv, dotted with (x, y, 1), is zero.
    a, b, c = Hinv[2]
    xs = np.array([0.0, w - 1.0])
    if abs(b) < 1e-12:
        return None
    ys = -(a * xs + c) / b
    row = int(np.ceil(max(ys.max(), 0.0))) + HORIZON_MARGIN_PX
    if row <= 0 or row >= h:
        return None
    return row


def build(frames: list[Path], *, horizon_row: int | None = None,
          H_world_to_img: np.ndarray | None = None) -> RegistrationMask:
    first = cv2.imread(str(frames[0]), cv2.IMREAD_GRAYSCALE)
    if first is None:
        raise RuntimeError(f"cannot read {frames[0]}")
    h, w = first.shape

    static, static_frac = static_region(frames)

    source = "static region by temporal median difference"
    if H_world_to_img is not None:
        derived = horizon_from_homography(H_world_to_img, w, h)
        if derived is not None:
            horizon_row = derived
            source += "; horizon from the ground plane's vanishing line"
    if horizon_row is None:
        horizon_row = BOOTSTRAP_HORIZON
        source += f"; horizon bootstrapped at row {BOOTSTRAP_HORIZON}"

    mask = np.full((h, w), 255, np.uint8)
    mask[static > 0] = 0
    mask[:max(0, min(h, horizon_row)), :] = 0
    return RegistrationMask(mask=mask, static_frac=static_frac,
                            horizon_row=int(horizon_row), source=source)


def apply(img: np.ndarray, mask: np.ndarray) -> np.ndarray:
    if img.ndim == 3:
        return cv2.bitwise_and(img, img, mask=mask)
    return cv2.bitwise_and(img, mask)
