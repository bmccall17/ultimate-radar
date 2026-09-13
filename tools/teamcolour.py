"""Are the two kits separable by torso colour alone? (M0 question 5, AD-3.)

Clusters the torso colour of person-like blobs and reports how far apart the two
groups sit, in CIELAB, where distance is at least roughly perceptual. The number
that matters is not the cluster means but the *overlap*: AD-3 makes team a hard
association gate, so a 1-in-50 misassignment is a 1-in-50 corrupted matchup.

The tool also writes a frame with each blob boxed in its cluster's colour. Look
at it. The clustering will happily put a referee, a ball boy and a spectator in
the dark cluster, and only the picture shows you that.

    python -m tools.teamcolour --blobs eval/m0/blobs_live/blobs.json \
        --frame survey/random/026_t5703.7.png --out eval/m0/teamcolour
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np

MIN_ASPECT, MAX_ASPECT = 1.5, 5.0
MIN_FILL, MAX_FILL = 0.30, 0.90
MIN_H = 20
SEED = 20260827


def person_like(b: dict) -> bool:
    return (MIN_ASPECT <= b["aspect"] <= MAX_ASPECT
            and MIN_FILL <= b["fill"] <= MAX_FILL
            and b["h"] >= MIN_H)


def kmeans2(x: np.ndarray, seed: int = SEED, iters: int = 100) -> tuple[np.ndarray, np.ndarray]:
    """Deterministic 2-means: seed at the extremes of the first principal axis."""
    xc = x - x.mean(axis=0)
    _, _, vt = np.linalg.svd(xc, full_matrices=False)
    proj = xc @ vt[0]
    centres = np.stack([x[proj.argmin()], x[proj.argmax()]])
    labels = np.zeros(len(x), dtype=int)
    for _ in range(iters):
        d = ((x[:, None, :] - centres[None, :, :]) ** 2).sum(axis=2)
        new = d.argmin(axis=1)
        if (new == labels).all():
            break
        labels = new
        for k in (0, 1):
            if (labels == k).any():
                centres[k] = x[labels == k].mean(axis=0)
    return labels, centres


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="tools.teamcolour")
    p.add_argument("--blobs", required=True)
    p.add_argument("--frame", default=None, help="frame to render clusters onto")
    p.add_argument("--out", required=True)
    args = p.parse_args(argv)

    records = json.loads(Path(args.blobs).read_text(encoding="utf-8"))
    blobs, origin = [], []
    for rec in records:
        for b in rec["blobs"]:
            if person_like(b):
                blobs.append(b)
                origin.append(rec["frame"])
    lab = np.array([b["torso_lab"] for b in blobs], dtype=np.float64)
    # OpenCV packs 8-bit Lab as L*255/100, a+128, b+128. Undo that.
    lab_real = np.stack([lab[:, 0] * 100.0 / 255.0, lab[:, 1] - 128.0, lab[:, 2] - 128.0], 1)

    labels, centres = kmeans2(lab_real)
    lo = 0 if centres[0][0] < centres[1][0] else 1
    hi = 1 - lo
    dark, light = lab_real[labels == lo], lab_real[labels == hi]

    sep = float(np.linalg.norm(centres[lo] - centres[hi]))
    # Overlap along L*, the axis that actually carries the light/dark split.
    thr = (dark[:, 0].mean() + light[:, 0].mean()) / 2
    wrong = int((dark[:, 0] > thr).sum() + (light[:, 0] <= thr).sum())

    res = {
        "n": len(blobs),
        "dark_cluster": {"n": len(dark),
                         "L_mean": round(float(dark[:, 0].mean()), 1),
                         "L_sd": round(float(dark[:, 0].std()), 1),
                         "L_p95": round(float(np.percentile(dark[:, 0], 95)), 1),
                         "a_mean": round(float(dark[:, 1].mean()), 1),
                         "b_mean": round(float(dark[:, 2].mean()), 1)},
        "light_cluster": {"n": len(light),
                          "L_mean": round(float(light[:, 0].mean()), 1),
                          "L_sd": round(float(light[:, 0].std()), 1),
                          "L_p05": round(float(np.percentile(light[:, 0], 5)), 1),
                          "a_mean": round(float(light[:, 1].mean()), 1),
                          "b_mean": round(float(light[:, 2].mean()), 1)},
        "centre_separation_deltaE": round(sep, 1),
        "L_threshold": round(float(thr), 1),
        "blobs_on_wrong_side_of_L_threshold": wrong,
        "seed": SEED,
    }
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "clusters.json").write_text(json.dumps(res, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(res, indent=2))

    if args.frame:
        stem = Path(args.frame).name
        img = cv2.imread(str(args.frame))
        if img is not None:
            for b, lb, src in zip(blobs, labels, origin):
                if src != stem:
                    continue
                colour = (60, 60, 255) if lb == lo else (255, 220, 60)
                cv2.rectangle(img, (b["x"], b["y"]), (b["x"] + b["w"], b["y"] + b["h"]),
                              colour, 2)
                cv2.putText(img, f"L{b['torso_lab'][0] * 100 / 255:.0f}",
                            (b["x"], max(12, b["y"] - 4)), cv2.FONT_HERSHEY_SIMPLEX,
                            0.4, colour, 1, cv2.LINE_AA)
            cv2.putText(img, "red = dark cluster    yellow = light cluster", (16, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2, cv2.LINE_AA)
            cv2.imwrite(str(out / f"clusters_{Path(args.frame).stem}.jpg"), img,
                        [cv2.IMWRITE_JPEG_QUALITY, 92])
            print(f"[teamcolour] rendered {out / f'clusters_{Path(args.frame).stem}.jpg'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
