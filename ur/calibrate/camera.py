"""A broadcast hard camera: fixed in space, free in pan, tilt and focal length.

This is the substance of the AD-4 amendment in docs/02-architecture.md. A general
homography has eight degrees of freedom, and on this footage the only geometry
reliably in shot is a circle and a line — seven constraints. Fitting eight
unknowns to seven constraints leaves a direction free to wander, and it wanders
silently.

But the camera does not translate. It sits on a tripod at the sideline and pans,
tilts and zooms. So the *right* model is three unknowns per frame against a
camera centre shared by the whole shot, and then seven constraints are
comfortably redundant rather than one short.

Conventions, fixed here once:

- World is the soccer frame from `world.py`: X along the pitch, Y across, Z up,
  ground at Z = 0. Yards.
- At pan = tilt = roll = 0 the camera looks along world +Y with world +Z up.
- `pan` rotates about world Z, `tilt` is positive downward, `roll` is about the
  optical axis and is near zero on a levelled head.
- Principal point at the image centre, square pixels, no skew. A broadcast lens
  violates all three slightly; the residual soaks it up and is reported rather
  than hidden.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# World -> camera at zero pan/tilt/roll: camera +Z forward along world +Y,
# camera +Y downward (image y grows downward), camera +X to the right.
BASE = np.array([[1.0, 0.0, 0.0],
                 [0.0, 0.0, -1.0],
                 [0.0, 1.0, 0.0]])


def rz(a: float) -> np.ndarray:
    c, s = np.cos(a), np.sin(a)
    return np.array([[c, s, 0.0], [-s, c, 0.0], [0.0, 0.0, 1.0]])


def rz_cam(a: float) -> np.ndarray:
    c, s = np.cos(a), np.sin(a)
    return np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])


def rx_cam(a: float) -> np.ndarray:
    c, s = np.cos(a), np.sin(a)
    return np.array([[1.0, 0.0, 0.0], [0.0, c, -s], [0.0, s, c]])


def rotation(pan: float, tilt: float, roll: float = 0.0) -> np.ndarray:
    """World -> camera rotation."""
    return rz_cam(roll) @ rx_cam(tilt) @ BASE @ rz(pan)


def angles_from_rotation(R: np.ndarray) -> tuple[float, float, float]:
    """Inverse of `rotation`. Returns (pan, tilt, roll).

    `rotation` has the form A @ BASE @ rz(pan) with A = rz_cam(roll) @ rx_cam(tilt),
    and A[2, 0] is identically zero. That single identity pins pan; the rest
    falls out of A.
    """
    pan = np.arctan2(-R[2, 0], R[2, 1])
    for candidate in (pan, pan + np.pi):
        A = R @ rz(candidate).T @ BASE.T
        tilt = np.arctan2(A[2, 1], A[2, 2])
        roll = np.arctan2(A[1, 0], A[0, 0])
        # A camera watching a field from a tripod looks downward, never up, and
        # is never upside down. That picks the branch.
        if -0.2 < tilt < 1.4 and abs(roll) < 1.0:
            return float(np.arctan2(np.sin(candidate), np.cos(candidate))), float(tilt), float(roll)
    A = R @ rz(pan).T @ BASE.T
    return float(pan), float(np.arctan2(A[2, 1], A[2, 2])), float(np.arctan2(A[1, 0], A[0, 0]))


def intrinsics(f: float, w: int, h: int) -> np.ndarray:
    return np.array([[f, 0.0, w / 2.0], [0.0, f, h / 2.0], [0.0, 0.0, 1.0]])


@dataclass
class Pose:
    """Where the camera is pointed in one frame."""

    pan: float
    tilt: float
    f: float
    roll: float = 0.0

    def as_array(self, with_roll: bool = True) -> np.ndarray:
        return (np.array([self.pan, self.tilt, self.f, self.roll]) if with_roll
                else np.array([self.pan, self.tilt, self.f]))

    def to_dict(self) -> dict:
        return {"pan_deg": round(float(np.degrees(self.pan)), 4),
                "tilt_deg": round(float(np.degrees(self.tilt)), 4),
                "roll_deg": round(float(np.degrees(self.roll)), 4),
                "focal_px": round(float(self.f), 3)}


@dataclass
class FixedCamera:
    """A camera centre, shared by every frame of a shot."""

    C: np.ndarray                 # (3,) world yards
    image_w: int
    image_h: int

    def homography(self, pose: Pose) -> np.ndarray:
        """Ground plane (world X, Y, 1) -> image pixels."""
        R = rotation(pose.pan, pose.tilt, pose.roll)
        t = -R @ np.asarray(self.C, float)
        K = intrinsics(pose.f, self.image_w, self.image_h)
        return K @ np.column_stack([R[:, 0], R[:, 1], t])

    def project(self, pts_world: np.ndarray, pose: Pose) -> tuple[np.ndarray, np.ndarray]:
        """Project ground points. Returns (pixels, visible mask).

        `visible` is False for anything behind the camera — those points do not
        have an image at all, and letting a negative depth divide through would
        put them somewhere plausible-looking and wrong.
        """
        pts = np.asarray(pts_world, float).reshape(-1, 2)
        H = self.homography(pose)
        hom = np.column_stack([pts, np.ones(len(pts))]) @ H.T
        z = hom[:, 2]
        ok = z > 1e-6
        out = np.full((len(pts), 2), np.nan)
        out[ok] = hom[ok, :2] / z[ok, None]
        return out, ok

    def to_dict(self) -> dict:
        return {"position_yd": [round(float(v), 4) for v in self.C],
                "image_w": self.image_w, "image_h": self.image_h}


# --------------------------------------------------------------------------- #
# Getting a camera out of a homography
# --------------------------------------------------------------------------- #

def decompose_homography(H: np.ndarray, w: int, h: int) -> tuple[FixedCamera, Pose] | None:
    """Recover (camera centre, pose) from a ground-plane homography.

    Zhang's single-plane decomposition, specialised to one unknown focal length:
    with the principal point pinned to the image centre and square pixels, the
    orthonormality of the first two rotation columns gives f in closed form.

    Returns None when the constraint yields no real focal length — which happens
    for a degenerate or badly-fitted H, and is worth returning honestly rather
    than clamping into something that looks like a camera.
    """
    H = np.asarray(H, float)
    cx, cy = w / 2.0, h / 2.0
    h1, h2, h3 = H[:, 0], H[:, 1], H[:, 2]

    def strip(col):
        return np.array([col[0] - cx * col[2], col[1] - cy * col[2], col[2]])

    a, b = strip(h1), strip(h2)
    denom = a[2] * b[2]
    num = -(a[0] * b[0] + a[1] * b[1])
    if abs(denom) < 1e-12:
        # Optical axis parallel to the plane's normal component; f is not
        # determined by orthogonality alone.
        return None
    f2 = num / denom
    if not np.isfinite(f2) or f2 <= 0:
        return None
    f = float(np.sqrt(f2))

    K = intrinsics(f, w, h)
    Kinv = np.linalg.inv(K)
    r1_raw, r2_raw, t_raw = Kinv @ h1, Kinv @ h2, Kinv @ h3
    n1 = np.linalg.norm(r1_raw)
    if n1 < 1e-12:
        return None
    lam = 1.0 / n1
    if t_raw[2] * lam < 0:      # camera must be in front of the plane
        lam = -lam
    r1, r2, t = r1_raw * lam, r2_raw * lam, t_raw * lam
    # Re-orthonormalise: the fit will not have produced an exactly valid rotation.
    r1 = r1 / np.linalg.norm(r1)
    r2 = r2 - (r1 @ r2) * r1
    n2 = np.linalg.norm(r2)
    if n2 < 1e-12:
        return None
    r2 = r2 / n2
    R = np.column_stack([r1, r2, np.cross(r1, r2)])
    U, _, Vt = np.linalg.svd(R)
    R = U @ Vt
    if np.linalg.det(R) < 0:
        R = U @ np.diag([1.0, 1.0, -1.0]) @ Vt

    C = -R.T @ t
    pan, tilt, roll = angles_from_rotation(R)
    return FixedCamera(C=C, image_w=w, image_h=h), Pose(pan=pan, tilt=tilt, f=f, roll=roll)


def homography_from_points(world: np.ndarray, image: np.ndarray) -> np.ndarray:
    """Plain DLT, world ground points -> image. Needs >= 4 correspondences."""
    import cv2

    world = np.asarray(world, np.float64).reshape(-1, 1, 2)
    image = np.asarray(image, np.float64).reshape(-1, 1, 2)
    H, _ = cv2.findHomography(world, image, method=0)
    if H is None:
        raise ValueError("degenerate correspondences: findHomography returned None")
    return H


def _selftest() -> None:
    """Round-trip the parameterisation. Run: python -m ur.calibrate.camera"""
    rng = np.random.default_rng(20260827)
    w, h = 1920, 1080
    worst_ang, worst_px = 0.0, 0.0
    for _ in range(400):
        C = np.array([rng.uniform(-30, 30), rng.uniform(-70, -35), rng.uniform(8, 25)])
        pose = Pose(pan=rng.uniform(-0.6, 0.6), tilt=rng.uniform(0.05, 0.5),
                    f=rng.uniform(900, 3000), roll=rng.uniform(-0.05, 0.05))
        cam = FixedCamera(C=C, image_w=w, image_h=h)
        H = cam.homography(pose)

        got = decompose_homography(H, w, h)
        assert got is not None, "decomposition failed on a well-formed homography"
        cam2, pose2 = got
        worst_ang = max(worst_ang, abs(pose2.pan - pose.pan), abs(pose2.tilt - pose.tilt),
                        abs(pose2.roll - pose.roll))
        worst_ang = max(worst_ang, abs(pose2.f - pose.f) / pose.f)
        assert np.allclose(cam2.C, C, atol=1e-4), f"centre {cam2.C} vs {C}"

        pts = rng.uniform(-45, 45, size=(60, 2))
        a, oka = cam.project(pts, pose)
        b, okb = cam2.project(pts, pose2)
        assert (oka == okb).all()
        if oka.any():
            worst_px = max(worst_px, float(np.nanmax(np.abs(a[oka] - b[oka]))))
    print(f"camera self-test ok: worst angle/focal error {worst_ang:.2e}, "
          f"worst reprojection {worst_px:.2e} px over 400 random poses")


if __name__ == "__main__":
    _selftest()
