"""
Reproduces the registration measurements in docs/11-m0-review.md.

Shows that whole-frame image registration reports a static camera on this broadcast,
because the rendered graphics are the strongest alignment signal in the image, and that
masking to the playing surface recovers the real camera motion.

    python -m tools.regcheck work/p0001/frames --out eval/m1

Writes registration_mask.png (255 = use this pixel for registration).
"""
import argparse, glob, os
import cv2, numpy as np

# Image-space regions to exclude. Measured on this broadcast at 1920x1080; re-check per feed.
BANNER   = (0, 980, 1920, 1080)   # sponsor banner, rendered on top, moves 0 px
SCOREBUG = (500, 915, 1420, 990)  # score bug, same
HORIZON  = 430                    # above this is stands/sky: off the ground plane, wrong parallax

def build_mask(h, w):
    m = np.ones((h, w), np.uint8) * 255
    for x0, y0, x1, y1 in (BANNER, SCOREBUG):
        m[y0:y1, x0:x1] = 0
    m[:HORIZON, :] = 0
    return m

def shift(a, b, mask=None):
    """Translation from a to b by phase correlation, with the correlation peak."""
    x, y = a.copy(), b.copy()
    if mask is not None:
        f = (mask > 0).astype(np.float32)
        x, y = x * f, y * f
    win = cv2.createHanningWindow((x.shape[1], x.shape[0]), cv2.CV_32F)
    (dx, dy), peak = cv2.phaseCorrelate(x, y, win)
    return dx, dy, peak

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("frames")
    ap.add_argument("--out", default="eval/m1")
    ap.add_argument("--step", type=int, default=30, help="frames between samples")
    a = ap.parse_args()

    fs = sorted(glob.glob(os.path.join(a.frames, "*.jpg")))[::a.step]
    if len(fs) < 2:
        raise SystemExit(f"need at least 2 frames, found {len(fs)} in {a.frames}")
    g = [cv2.cvtColor(cv2.imread(f), cv2.COLOR_BGR2GRAY).astype(np.float32) for f in fs]
    h, w = g[0].shape
    mask = build_mask(h, w)
    os.makedirs(a.out, exist_ok=True)
    cv2.imwrite(os.path.join(a.out, "registration_mask.png"), mask)

    print(f"usable registration area: {100 * (mask > 0).mean():.1f}% of frame\n")
    print(f"{'pair':18s} {'whole dx':>9s} {'peak':>7s} {'masked dx':>11s} {'peak':>7s}")
    missed = 0
    for i in range(len(g) - 1):
        dw, _, pw = shift(g[i], g[i + 1])
        dm, _, pm = shift(g[i], g[i + 1], mask)
        if abs(dw) < 1.0 and abs(dm) > 3.0:
            missed += 1
        name = f"{os.path.basename(fs[i])[:6]}->{os.path.basename(fs[i+1])[:6]}"
        print(f"{name:18s} {dw:9.1f} {pw:7.3f} {dm:11.1f} {pm:7.3f}")
    n = len(g) - 1
    print(f"\nwhole-frame registration reported a static camera on {missed}/{n} pairs")
    if missed:
        print("=> every registration, matching and GMC step must run on the mask, not the raw frame")

if __name__ == "__main__":
    main()
