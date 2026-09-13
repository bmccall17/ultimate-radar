"""The motion model: an integrated Ornstein-Uhlenbeck velocity, in field yards.

The state is `[x, y, vx, vy]` on the ground plane, in yards and yards per second —
never pixels. AD-1 gives the reason: on a panning, zooming broadcast a stationary
player has large screen velocity, so a pixel-space motion model is meaningless,
and the usual fix (global motion compensation) degrades exactly when the camera
zooms hard, which is when ultimate is most interesting. We already have a
homography, so using it one stage earlier makes the motion model *physical* — a
person accelerates at most about 6 yd/s² and sprints at most about 9.5 yd/s, and
those are real constraints rather than tuned pixel thresholds.

**Velocity is mean-reverting, not a free random walk.** It decays toward zero with
the ~2.6 s time constant `docs/05-uncertainty.md` gives for dead reckoning, and is
driven by noise scaled so its stationary spread is `SIGMA_V_INF`. That single
choice does three things at once: the mean coasts to a stop rather than sprinting
off the field, the velocity *uncertainty* saturates instead of growing past what a
human can do, and the association gate downstream widens at a rate the physics
allows. Damping the mean without damping the covariance, or vice versa, gets one
of those three wrong — see the note on SIGMA_V_INF.

## How this went wrong twice before it went right

**Attempt 1, piecewise white-noise acceleration** (`Q = G Gᵀ σ_a²`). Its velocity
variance grows as `σ_a² · dt · T`, which depends on the frame rate. At 15 fps it
left the filter believing a player unobserved for two seconds had a velocity
uncertainty of 1.5 yd/s, when someone last seen running at 5 yd/s could by then be
doing anything between −5 and +5. The consequence was not subtle: **736
detections, a median of 13 yd from every slot, failed the association gate**,
because no slot believed a player could have got that far. Real players went
unassigned while their own slots sat predicting confidently in the wrong place.

**Attempt 2, undamped covariance** — propagate the mean damped, the covariance
not. That overshot the other way, reaching 7.8 yd/s after 2.2 s, which puts most
of the probability mass beyond a flat-out sprint.

The OU model is the honest middle, and it is one model rather than two glued
together.
"""

from __future__ import annotations

import numpy as np

# docs/05: dead reckoning uses constant velocity with an exponential damp, time
# constant ~2.6 s. Here that damping is the model, not a cosmetic touch-up.
DAMP_TAU_S = 2.6

# Stationary 1-sigma of one velocity component, yd/s. **Measured**, not chosen:
# `tools/m4_speed.py` differences raw detection foot points over a range of
# baselines and subtracts the foot-point noise M3 measured, then inverts the
# integrated-OU displacement variance. On p0001 the estimate rises out of the
# noise and settles at 2.50, 2.64, 2.63 yd/s for baselines of 0.8, 1.3 and 2.0 s
# (eval/m4/m4_speed.json).
#
# It is NOT a sprint speed. A sprint is ~9.5 yd/s (AD-1); this is the spread of a
# velocity *component* over a whole point, most of which is spent moving
# moderately or standing.
SIGMA_V_INF = 2.6

# Kept because AD-1 quotes it: the acceleration scale, ~4 yd/s² of unmodelled
# acceleration against a physical maximum near 6. The OU model expresses the same
# physics through SIGMA_V_INF and DAMP_TAU_S, since q = 2 σ_v² / τ.
SIGMA_ACCEL = 4.0


def transition(dt: float, tau: float = DAMP_TAU_S) -> np.ndarray:
    """F for the damped constant-velocity model over `dt` seconds."""
    a = float(np.exp(-dt / tau))
    d = tau * (1.0 - a)          # integral of the decaying velocity over dt
    F = np.eye(4)
    F[0, 2] = d
    F[1, 3] = d
    F[2, 2] = a
    F[3, 3] = a
    return F


def process_noise(dt: float, sigma_v: float = SIGMA_V_INF,
                  tau: float = DAMP_TAU_S) -> np.ndarray:
    """Exact discretisation of the integrated-OU model, x and y independent.

    With `a = e^{-dt/τ}` and σ the stationary velocity spread:

        Q_vv = σ² (1 − a²)
        Q_pv = σ² τ (1 − a)²
        Q_pp = σ² τ² (2dt/τ − 3 + 4a − a²)

    As `dt → 0` the position term tends to `(2/3) σ² dt³ / τ`, which is exactly
    `q dt³/3` for `q = 2σ²/τ` — the white-noise-acceleration limit, as it must be.
    Velocity variance saturates at `σ²` however long the gap; position keeps
    growing, because a player unobserved for long enough really could be anywhere,
    but at a rate the physics allows rather than one the frame rate implies.
    """
    a = float(np.exp(-dt / tau))
    s2 = sigma_v ** 2
    q_vv = s2 * (1.0 - a * a)
    q_pv = s2 * tau * (1.0 - a) ** 2
    q_pp = s2 * tau * tau * (2.0 * dt / tau - 3.0 + 4.0 * a - a * a)
    q_pp = max(q_pp, 0.0)        # the bracket is non-negative but rounds below 0
    Q = np.zeros((4, 4))
    for i, j in ((0, 2), (1, 3)):        # (position, velocity) pair per axis
        Q[i, i] = q_pp
        Q[i, j] = q_pv
        Q[j, i] = q_pv
        Q[j, j] = q_vv
    return Q


H = np.array([[1.0, 0.0, 0.0, 0.0],
              [0.0, 1.0, 0.0, 0.0]])


class Track:
    """One slot's filter. Never created or destroyed mid-possession — see AD-2."""

    def __init__(self, sigma_v: float = SIGMA_V_INF, tau: float = DAMP_TAU_S):
        self.x = np.zeros(4)
        self.P = np.eye(4) * 1e6
        self.started = False
        self.sigma_v = sigma_v
        self.tau = tau

    # -- lifecycle ---------------------------------------------------------- #

    def start(self, xy, sigma: float, v_sigma: float | None = None) -> None:
        """Seed from a first observation. Velocity is unknown, and says so.

        The default is the model's own stationary velocity spread: a player first
        seen could be standing still or sprinting, and claiming to know which
        would make the very next prediction confident and wrong.
        """
        if v_sigma is None:
            v_sigma = self.sigma_v
        self.x = np.array([xy[0], xy[1], 0.0, 0.0], float)
        self.P = np.diag([sigma ** 2, sigma ** 2, v_sigma ** 2, v_sigma ** 2])
        self.started = True

    # -- the two steps ------------------------------------------------------ #

    def predict(self, dt: float) -> None:
        """One step of the OU model.

        Mean and covariance go through the same transition, which is the point:
        the damping is the model, not a smoothing of the mean. Because the process
        noise is the exact discretisation of that model, the filter never becomes
        more certain by damping — velocity uncertainty rises to its stationary
        bound and stops.
        """
        F = transition(dt, self.tau)
        self.x = F @ self.x
        self.P = F @ self.P @ F.T + process_noise(dt, self.sigma_v, self.tau)

    def innovation(self, z, R):
        """(residual, S) for a candidate measurement, without consuming it."""
        y = np.asarray(z, float) - H @ self.x
        S = H @ self.P @ H.T + R
        return y, S

    def update(self, z, R) -> None:
        y, S = self.innovation(z, R)
        K = self.P @ H.T @ np.linalg.inv(S)
        self.x = self.x + K @ y
        # Joseph form: stays symmetric and positive-definite under repeated use,
        # which the short form does not once the covariance gets small.
        I_KH = np.eye(4) - K @ H
        self.P = I_KH @ self.P @ I_KH.T + K @ R @ K.T

    # -- readouts ----------------------------------------------------------- #

    @property
    def position(self) -> np.ndarray:
        return self.x[:2].copy()

    @property
    def velocity(self) -> np.ndarray:
        return self.x[2:].copy()

    @property
    def speed(self) -> float:
        return float(np.hypot(*self.x[2:]))

    def position_sigma(self) -> float:
        """One number for the disc the viewer draws.

        The rms of the two principal standard deviations of the position
        covariance. A single radius understates an elongated ellipse along its
        long axis, which is worth knowing; it is used because
        `docs/03-data-contracts.md` stores one `sigma` per sample and
        `docs/05-uncertainty.md` draws one disc.
        """
        ev = np.linalg.eigvalsh(self.P[:2, :2])
        return float(np.sqrt(np.clip(ev, 0.0, None).mean()))


def mahalanobis2(y: np.ndarray, S: np.ndarray) -> float:
    """Squared Mahalanobis distance of an innovation. Chi-square, 2 DOF."""
    try:
        return float(y @ np.linalg.solve(S, y))
    except np.linalg.LinAlgError:
        return float("inf")
