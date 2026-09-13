"""Measure the stationary velocity spread the motion model assumes.

    python -m tools.m4_speed work/p0001

`ur/track/kalman.py` needs one number it cannot invent: `SIGMA_V_INF`, the
stationary 1-sigma of a velocity component. It sets how fast the filter's
uncertainty grows while a player is unobserved, which sets how far the
association gate reaches, which decides whether a player who leaves frame is
re-claimed by their own slot or by somebody else's. Guessing it is how the first
two versions of that file went wrong.

**Single-frame differencing cannot measure it.** The foot point carries about
0.6 yd of noise, so a displacement over 1/15 s implies a velocity error near
9 yd/s — larger than the thing being measured. The fix is to difference over a
longer baseline and subtract the noise, which is possible because M3 measured the
noise instead of assuming it:

    Var[Δp over k frames] = Var[true displacement] + 2 σ_pos²

so σ_v(k) = sqrt(max(0, Var[Δp] − 2 σ_pos²)) / (k·dt). Positions come from
`detections.json` — the raw back-projected foot points, not the filter's own
smoothed state, which would make the measurement circular. The link between two
frames comes from `tracks.json`, so this must run after a first tracking pass;
the value it reports is fed back and the pass re-run.

The estimate is reported per baseline. A short baseline is dominated by noise; a
long one understates, because a player changes velocity within it. The value to
take is where the curve flattens, and the tool prints the curve rather than one
number so that judgement is visible rather than buried.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from ur.track.kalman import DAMP_TAU_S

BASELINES = (2, 3, 5, 8, 12, 20, 30)


def measure(work: Path) -> dict:
    det = json.loads((work / "detections.json").read_text(encoding="utf-8"))
    trk = json.loads((work / "tracks.json").read_text(encoding="utf-8"))
    clip = json.loads((work / "clip.json").read_text(encoding="utf-8"))
    dt = 1.0 / float(clip["fps"])
    by_frame = {d["f"]: d["dets"] for d in det["frames"]}

    # Raw detection position and its stated sigma, per (slot, frame).
    raw: dict[str, dict[int, tuple[np.ndarray, float]]] = {}
    for s in trk["slots"]:
        m = {}
        for smp in s["samples"]:
            if smp["state"] != "observed" or smp["det"] is None:
                continue
            d = by_frame[smp["f"]][smp["det"]]
            if d.get("field") is None:
                continue
            m[smp["f"]] = (np.asarray(d["field"], float),
                           float(d.get("sigma_yd") or 0.6))
        raw[s["slot"]] = m

    rows = []
    for k in BASELINES:
        d2, noise2, n = [], [], 0
        for m in raw.values():
            for f, (p, s1) in m.items():
                nxt = m.get(f + k)
                if nxt is None:
                    continue
                q, s2 = nxt
                d2.append(float(np.sum((q - p) ** 2)))     # 2-D squared displacement
                noise2.append(s1 * s1 + s2 * s2)           # both foot points, 2-D
                n += 1
        if n < 30:
            continue
        # Per component: halve the 2-D quantities.
        var_comp = 0.5 * (float(np.mean(d2)) - float(np.mean(noise2)))
        var_comp = max(var_comp, 0.0)
        T = k * dt
        # Naive: assumes the velocity is constant over the baseline, i.e. T << tau.
        sigma_naive = float(np.sqrt(var_comp)) / T
        # Model-consistent: the integrated-OU displacement variance,
        #   Var = 2 sigma_v^2 tau^2 (T/tau - 1 + e^{-T/tau}),
        # which is the same model the filter propagates. Inverting it removes the
        # bias the naive form carries once T is a real fraction of tau - at the
        # baselines where this measurement is usable, T/tau reaches 0.8, so that
        # bias is not small.
        r = T / DAMP_TAU_S
        shape = 2.0 * DAMP_TAU_S ** 2 * (r - 1.0 + float(np.exp(-r)))
        sigma_ou = float(np.sqrt(var_comp / shape)) if shape > 1e-9 else float("nan")
        rows.append({"baseline_frames": k, "baseline_s": round(T, 4), "n": n,
                     "T_over_tau": round(r, 3),
                     "rms_displacement_yd": round(float(np.sqrt(np.mean(d2))), 3),
                     "noise_rms_yd": round(float(np.sqrt(np.mean(noise2))), 3),
                     "sigma_v_naive_yd_s": round(sigma_naive, 3),
                     "sigma_v_yd_s": round(sigma_ou, 3)})
    return {"schema": "ultimate-radar/m4-speed@1",
            "possession": trk["possession_id"],
            "method": ("displacement of the raw detection foot point between two "
                       "frames linked by the same slot, with the measured "
                       "foot-point noise subtracted in quadrature"),
            "note": ("short baselines are noise-dominated, long ones understate "
                     "because a player changes velocity within them; take the "
                     "value where the curve flattens"),
            "by_baseline": rows}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="tools.m4_speed")
    p.add_argument("work")
    p.add_argument("--out", default="eval/m4/m4_speed.json")
    a = p.parse_args(argv)
    res = measure(Path(a.work))
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=2) + chr(10), encoding="utf-8")
    print(f"{'baseline':>9} {'T/tau':>6} {'n':>6} {'rms disp':>9} {'noise':>7} "
          f"{'naive':>7} {'sigma_v':>8}")
    for r in res["by_baseline"]:
        print(f"{r['baseline_s']:>8.3f}s {r['T_over_tau']:>6.2f} {r['n']:>6} "
              f"{r['rms_displacement_yd']:>9.3f} {r['noise_rms_yd']:>7.3f} "
              f"{r['sigma_v_naive_yd_s']:>7.3f} {r['sigma_v_yd_s']:>8.3f}")
    print(f"\n  -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
