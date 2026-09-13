"""The geometry on the ground, in yards, with its sources.

Two frames live here and the difference matters (see docs/04-milestones.md M1,
"report two error budgets, not one"):

**Soccer frame** — origin at the centre circle's centre, `sx` along the pitch's
long axis, `sy` across it. Everything in it comes from the FIFA Laws of the Game
and is exact to the millimetre, which is why calibration is done here.

**Ultimate frame** — the contract frame from docs/03-data-contracts.md. Origin at
the back corner of the defending endzone on the near sideline, `X` 0..120 along
the direction of attack, `Y` 0..53.333 across toward the far sideline.

They are related by one `VenueTransform`, measured once per venue. Its error is a
separate budget from the per-frame calibration error, and blending the two would
hide which half is bad.

M0 established that Breese Stevens carries no gridiron paint at all
(docs/00-footage-report.md Q2), so the soccer markings are not a convenience
here — they are the only exactly-specified geometry on the field.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

M_PER_YD = 0.9144


def m(metres: float) -> float:
    """Metres to yards. The Laws of the Game are metric; this project is not."""
    return metres / M_PER_YD


# --------------------------------------------------------------------------- #
# Soccer pitch — FIFA Laws of the Game, Law 1. Exact.
# --------------------------------------------------------------------------- #

CENTRE_CIRCLE_R = m(9.15)        # 10.0066 yd
PENALTY_AREA_DEPTH = m(16.5)     # 18.0446 yd
PENALTY_AREA_HALF_W = m(40.32 / 2)
GOAL_AREA_DEPTH = m(5.5)
GOAL_AREA_HALF_W = m(18.32 / 2)
PENALTY_SPOT_DIST = m(11.0)
PENALTY_ARC_R = m(9.15)
LINE_WIDTH = m(0.12)             # Law 1 allows up to 12 cm

# Breese Stevens' own pitch length and width are NOT published and are NOT
# needed for the features this project uses. Anything that depends on them
# (touchlines, goal lines, penalty areas) is only emitted when a length/width is
# supplied, and is never required.
BREESE_PITCH_L: float | None = None
BREESE_PITCH_W: float | None = None


# --------------------------------------------------------------------------- #
# UFA field — Rule Book v13.0, verified in M0. eval/ufa-rulebook-2025-v13.pdf
# --------------------------------------------------------------------------- #

UFA_WIDTH = 160.0 / 3.0          # 53.333 yd, rule 2.1.1
UFA_ENDZONE = 20.0               # rule 2.1.1
UFA_PLAYING_FULL = 80.0          # rule 2.1.1
UFA_PLAYING_SHORT = 70.0         # rule 2.3.3, the 110 yd venue exception
UFA_BRICK_FULL = 20.0            # rule 2.3.1
UFA_BRICK_SHORT = 15.0           # rule 2.3.3
UFA_REVERSE_BRICK = 10.0         # rule 2.3.2, behind the goal line


@dataclass(frozen=True)
class UltimateField:
    """A UFA field. `length_yd` is the open question in docs/08-risks.md #5."""

    length_yd: float = 120.0

    @property
    def is_full(self) -> bool:
        return abs(self.length_yd - 120.0) < 1e-6

    @property
    def width_yd(self) -> float:
        return UFA_WIDTH

    @property
    def endzone_yd(self) -> float:
        return UFA_ENDZONE

    @property
    def brick_yd(self) -> float:
        return UFA_BRICK_FULL if self.is_full else UFA_BRICK_SHORT

    @property
    def goal_lines(self) -> tuple[float, float]:
        return UFA_ENDZONE, self.length_yd - UFA_ENDZONE

    def centreline_marks(self) -> dict[str, float]:
        """The seven marked points down the centre of the field, by X.

        Rules 2.2.1 / 2.3.1 / 2.3.2. These are painted, at exactly known
        positions, and are the richest correspondence source the ultimate paint
        offers — see docs/02-architecture.md, "world geometry available".
        """
        g0, g1 = self.goal_lines
        b = self.brick_yd
        return {
            "reverse_brick_near": g0 - UFA_REVERSE_BRICK,
            "goal_line_near": g0,
            "brick_near": g0 + b,
            "midfield": self.length_yd / 2.0,
            "brick_far": g1 - b,
            "goal_line_far": g1,
            "reverse_brick_far": g1 + UFA_REVERSE_BRICK,
        }

    def pylons(self) -> np.ndarray:
        """The ten pylons of rule 2.2.1, as (X, Y) in ultimate yards.

        Four endzone back corners, four goal-line ends, and the centre of each
        back line.
        """
        g0, g1 = self.goal_lines
        w = self.width_yd
        pts = []
        for x in (0.0, self.length_yd):          # back lines
            pts += [(x, 0.0), (x, w), (x, w / 2.0)]
        for x in (g0, g1):                       # goal lines
            pts += [(x, 0.0), (x, w)]
        return np.array(pts, dtype=np.float64)

    def outline(self) -> dict[str, np.ndarray]:
        """Painted lines, as polylines in ultimate yards, for the overhead view
        and for the verification render."""
        w, L = self.width_yd, self.length_yd
        g0, g1 = self.goal_lines
        out = {
            "perimeter": np.array([(0, 0), (L, 0), (L, w), (0, w), (0, 0)], float),
            "goal_line_near": np.array([(g0, 0), (g0, w)], float),
            "goal_line_far": np.array([(g1, 0), (g1, w)], float),
        }
        return out


# --------------------------------------------------------------------------- #
# Feature models, sampled as points for chamfer alignment
# --------------------------------------------------------------------------- #

@dataclass
class Feature:
    """A named piece of ground truth, sampled densely enough to chamfer against.

    `points` are in the soccer frame. `weight` lets a feature we trust more (a
    circle, whose radius is exact and whose curvature pins scale) count for more
    than one we trust less.
    """

    name: str
    points: np.ndarray               # (N, 2) in soccer yards
    weight: float = 1.0
    closed: bool = False


def circle_points(cx: float, cy: float, r: float, n: int = 360) -> np.ndarray:
    a = np.linspace(0.0, 2.0 * np.pi, n, endpoint=False)
    return np.stack([cx + r * np.cos(a), cy + r * np.sin(a)], axis=1)


def segment_points(p0, p1, step: float = 0.25) -> np.ndarray:
    p0, p1 = np.asarray(p0, float), np.asarray(p1, float)
    n = max(2, int(np.linalg.norm(p1 - p0) / step) + 1)
    t = np.linspace(0.0, 1.0, n)[:, None]
    return p0[None, :] * (1 - t) + p1[None, :] * t


def soccer_features(half_line_extent: float = 40.0) -> list[Feature]:
    """What is reliably visible on this broadcast, and exactly specified.

    Deliberately short. The centre circle and the halfway line are present in
    every frame of p0001; the penalty area is not, and anything depending on the
    unpublished pitch length or width is excluded entirely rather than guessed.

    `half_line_extent` is how far along the halfway line to sample, in yards
    either side of centre. It is a sampling extent, not a claim about the pitch
    width — points that fall outside the image are discarded by the fit.
    """
    return [
        Feature("centre_circle", circle_points(0.0, 0.0, CENTRE_CIRCLE_R),
                weight=2.0, closed=True),
        Feature("halfway_line",
                segment_points((0.0, -half_line_extent), (0.0, half_line_extent)),
                weight=1.0),
    ]


# --------------------------------------------------------------------------- #
# Soccer frame <-> ultimate frame
# --------------------------------------------------------------------------- #

@dataclass
class VenueTransform:
    """Maps soccer-frame yards to ultimate-frame yards.

    Deliberately rigid — a flip, a rotation of exactly 0 or 90 degrees, and a
    translation. Both fields are rectangles painted on the same flat ground with
    a tape measure; anything more expressive than this would be fitting noise,
    and would let calibration error leak in disguised as geometry.

        X = x_sign * sx + x_offset
        Y = y_sign * sy + y_offset

    `x_offset` is where the ultimate field's X=0 back line sits along the pitch,
    measured from the centre circle. For a field centred on the pitch it is
    length/2. **Measure it; do not assume centring** — that assumption is what
    open question 5 (120 vs 110 yd) turns on.
    """

    x_sign: int = 1
    y_sign: int = 1
    x_offset: float = 60.0
    y_offset: float = UFA_WIDTH / 2.0
    source: str = "assumed: ultimate field centred on the pitch, UNMEASURED"
    residual_yd: float | None = None

    def to_ultimate(self, pts: np.ndarray) -> np.ndarray:
        pts = np.asarray(pts, float).reshape(-1, 2)
        return np.stack([self.x_sign * pts[:, 0] + self.x_offset,
                         self.y_sign * pts[:, 1] + self.y_offset], axis=1)

    def to_soccer(self, pts: np.ndarray) -> np.ndarray:
        pts = np.asarray(pts, float).reshape(-1, 2)
        return np.stack([(pts[:, 0] - self.x_offset) / self.x_sign,
                         (pts[:, 1] - self.y_offset) / self.y_sign], axis=1)

    @property
    def is_measured(self) -> bool:
        return self.residual_yd is not None

    def to_dict(self) -> dict:
        return {"x_sign": self.x_sign, "y_sign": self.y_sign,
                "x_offset": round(self.x_offset, 4),
                "y_offset": round(self.y_offset, 4),
                "source": self.source,
                "residual_yd": None if self.residual_yd is None
                else round(self.residual_yd, 4),
                "measured": self.is_measured}


def field_length_from_goal_line(goal_line_sx: float, which: str = "near") -> dict:
    """Decide 120 vs 110 yd from one goal line's distance to the halfway line.

    docs/08-risks.md open question 5. A UFA field laid centred on the pitch puts
    its goal lines at +/-40 yd from the centre circle when the field is the full
    120 yd (80 yd between goal lines), and +/-35 yd when the 110 yd venue
    exception applies (70 yd between them). A 5 yd difference, needing only
    *one* goal line and the halfway line in the same frame — which is far more
    likely than getting both goal lines at once, since this camera never frames
    the whole field.

    Returns the verdict and, importantly, how far the measurement sits from each
    hypothesis, so a marginal answer reads as marginal instead of as a decision.
    """
    d = abs(goal_line_sx)
    err_full, err_short = abs(d - 40.0), abs(d - 35.0)
    # Tight on purpose. The per-frame calibration residual is ~0.15 yd, so a real
    # goal line lands within a fraction of a yard of one hypothesis or the other.
    # A loose tolerance lets a noise bump 1.75 yd from 40 "decide" a question that
    # every field coordinate depends on, which is exactly the kind of confident
    # wrong answer this project exists not to produce.
    if min(err_full, err_short) > 1.0:
        verdict = "inconclusive"
    else:
        verdict = "120" if err_full < err_short else "110"
    return {
        "which_goal_line": which,
        "measured_dist_to_halfway_yd": round(d, 3),
        "expected_120_yd": 40.0, "err_if_120_yd": round(err_full, 3),
        "expected_110_yd": 35.0, "err_if_110_yd": round(err_short, 3),
        "verdict": verdict,
        "assumes": "the ultimate field is centred on the soccer pitch along its length",
    }
