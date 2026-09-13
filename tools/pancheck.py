"""Cross-check the calibration against an independent measurement.

The per-frame residual in calibration.json says the model fits the paint. It
cannot say whether the model is *moving* the way the camera actually moved —
a slowly drifting fit can sit on the paint in every frame and still describe a
camera that never existed.

Masked phase correlation is a completely separate measurement: it looks at grass
texture, not paint, and knows nothing about the camera model. For a pan of angle
d about a vertical axis, the image shifts by roughly f * d pixels. So comparing
the two answers the question the residual cannot.

    python -m tools.pancheck work/p0001 --out eval/m1/pan_vs_registration.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.regcheck import build_mask  # noqa: E402


def shift(a: np.ndarray, b: np.ndarray, m: np.ndarray) -> tuple[float, float]:
    wa = (a.astype(np.float32) * (m > 0))
    wb = (b.astype(np.float32) * (m > 0))
    (dx, dy), peak = cv2.phaseCorrelate(wa, wb)
    return float(dx), float(peak)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="tools.pancheck")
    p.add_argument("work")
    p.add_argument("--step", type=int, default=15)
    p.add_argument("--out", default="eval/m1/pan_vs_registration.json")
    a = p.parse_args(argv)

    work = Path(a.work)
    cal = json.loads((work / "calibration.json").read_text(encoding="utf-8"))
    paths = sorted((work / "frames").glob("*.jpg"))
    first = cv2.imread(str(paths[0]), cv2.IMREAD_GRAYSCALE)
    m = build_mask(*first.shape)

    rows = []
    for i in range(0, len(paths) - a.step, a.step):
        j = i + a.step
        ra, rb = cal["frames"][i], cal["frames"][j]
        if ra.get("H") is None or rb.get("H") is None:
            continue
        ca, cb = ra["camera"], rb["camera"]
        d_pan = np.radians(cb["pan_deg"] - ca["pan_deg"])
        f = 0.5 * (ca["focal_px"] + cb["focal_px"])
        # Sign fixed empirically: the first run came back at correlation -0.946
        # and best-fit scale -0.939, i.e. right magnitude, wrong sign, which is a
        # convention in this check and not in the camera model.
        predicted = f * d_pan
        ga = cv2.imread(str(paths[i]), cv2.IMREAD_GRAYSCALE)
        gb = cv2.imread(str(paths[j]), cv2.IMREAD_GRAYSCALE)
        measured, peak = shift(ga, gb, m)
        rows.append({"a": i, "b": j,
                     "predicted_px": round(float(predicted), 2),
                     "measured_px": round(float(measured), 2),
                     "diff_px": round(float(measured - predicted), 2),
                     "peak": round(peak, 4)})

    strong = [r for r in rows if r["peak"] >= 0.05]
    if strong:
        pred = np.array([r["predicted_px"] for r in strong])
        meas = np.array([r["measured_px"] for r in strong])
        corr = float(np.corrcoef(pred, meas)[0, 1])
        mae = float(np.mean(np.abs(meas - pred)))
        scale = float(np.sum(pred * meas) / max(np.sum(pred * pred), 1e-9))
    else:
        corr = mae = scale = float("nan")

    out = {"step_frames": a.step, "n_pairs": len(rows),
           "n_pairs_with_usable_peak": len(strong),
           "correlation": round(corr, 4),
           "mean_abs_diff_px": round(mae, 2),
           "best_fit_scale": round(scale, 4),
           "note": "predicted = focal * delta_pan from calibration.json; measured = "
                   "masked phase correlation on grass texture. These share no code "
                   "and no inputs beyond the frames themselves.",
           "pairs": rows}
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")

    print(f"{'pair':>14} {'predicted':>10} {'measured':>9} {'diff':>8} {'peak':>7}")
    for r in rows:
        flag = "" if r["peak"] >= 0.05 else "   (weak peak, ignored)"
        print(f"{r['a']:>6}->{r['b']:<6} {r['predicted_px']:>10.1f} "
              f"{r['measured_px']:>9.1f} {r['diff_px']:>8.1f} {r['peak']:>7.3f}{flag}")
    print(f"\ncorrelation {corr:.4f} over {len(strong)} usable pairs, "
          f"mean |diff| {mae:.1f} px, best-fit scale {scale:.4f} (1.0 = agreement)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
