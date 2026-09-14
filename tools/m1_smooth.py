"""Is a calibrated frame's pose consistent with its neighbours? An out-of-sample check.

    python -m tools.m1_smooth work/p0002

`residual_yd` is measured on the very points the frame was fitted to, so it is an
**in-sample** number: a pose fitted to fifty pixels of arc can have a tiny rms and
still be wrong, which is the whole reason `confidence_of` used to scale itself by
how much paint was visible. Replacing that scaling with a floor (`MIN_SUPPORT_PX`)
needs an argument the residual cannot make.

This is that argument, and it costs nothing because the camera already provides it.
AD-4's amendment establishes that this is a **fixed broadcast hard camera**: it
pans, tilts and zooms, and does not translate. Pan, tilt and focal length are
therefore smooth functions of time — an operator's hands move continuously — so a
frame whose pose disagrees with its own neighbours is wrong regardless of how
prettily it fitted its pixels.

The test: fit a local line through each pose parameter over a short window
*excluding the frame itself*, and ask how far that frame sits from it. A frame
left out of its own prediction is scored out of sample, which is the property the
residual lacks.

Reported per confidence band, so the question "are the frames this gate admits
actually any good" has a number rather than an opinion.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

# Half-width of the window a frame is predicted from. Five frames either side is a
# third of a second - long enough for a line to mean something, short enough that
# a real pan is locally straight.
HALF = 5

KEYS = ("pan_deg", "tilt_deg", "focal_px")


def leave_one_out(vals: np.ndarray, ok: np.ndarray) -> np.ndarray:
    """Residual of each frame against a line fitted to its neighbours only."""
    n = len(vals)
    out = np.full(n, np.nan)
    idx = np.arange(n)
    for i in range(n):
        lo, hi = max(0, i - HALF), min(n, i + HALF + 1)
        sel = (idx[lo:hi] != i) & ok[lo:hi]
        x = idx[lo:hi][sel].astype(float)
        y = vals[lo:hi][sel]
        if len(x) < 4 or not np.isfinite(y).all():
            continue
        a, b = np.polyfit(x, y, 1)
        out[i] = abs(vals[i] - (a * i + b))
    return out


def measure(work: Path) -> dict:
    cal = json.loads((work / "calibration.json").read_text(encoding="utf-8"))
    fr = cal["frames"]
    conf = np.array([r.get("confidence") or 0.0 for r in fr])
    res = np.array([r.get("residual_yd") if r.get("residual_yd") is not None
                    else np.nan for r in fr])
    ok = conf >= 0.5

    dev = {}
    for k in KEYS:
        v = np.array([(r.get("camera") or {}).get(k, np.nan) for r in fr], float)
        dev[k] = leave_one_out(v, ok)

    bands = [("confidence >= 0.5", ok),
             ("confidence 0.3-0.5", (conf >= 0.3) & (conf < 0.5)),
             ("confidence < 0.3", conf < 0.3)]
    rows = []
    for name, m in bands:
        if not m.any():
            continue
        row = {"band": name, "frames": int(m.sum()),
               "residual_yd_median": _q(res[m])}
        for k in KEYS:
            row[k] = _q(dev[k][m])
        rows.append(row)

    return {
        "schema": "ultimate-radar/m1-smoothness@1",
        "possession": cal["possession_id"],
        "method": ("each frame's pan, tilt and focal scored against a line fitted "
                   "to its neighbours WITHOUT it, over +/-%d frames. The camera is "
                   "fixed and only pans, tilts and zooms (AD-4), so these are "
                   "smooth in time and a frame that disagrees with its own "
                   "neighbours is wrong however well it fitted its own pixels."
                   % HALF),
        "why": ("residual_yd is in-sample - it is measured on the points the frame "
                "was fitted to - so it cannot say whether a fit resting on very "
                "little paint generalises. This can."),
        "bands": rows,
    }


def _q(v: np.ndarray):
    v = v[np.isfinite(v)]
    if not len(v):
        return None
    return {"median": round(float(np.median(v)), 4),
            "p90": round(float(np.percentile(v, 90)), 4)}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="tools.m1_smooth")
    p.add_argument("work")
    p.add_argument("--out", default=None)
    a = p.parse_args(argv)
    res = measure(Path(a.work))
    print(f"[smooth] {res['possession']}: pose agreement with neighbours, "
          "leave-one-out")
    print(f"{'band':<20}{'n':>6}{'residual':>10}{'pan deg':>10}"
          f"{'tilt deg':>10}{'focal px':>12}")
    for r in res["bands"]:
        def g(k):
            return f"{r[k]['median']:.3f}" if r.get(k) else "-"
        print(f"{r['band']:<20}{r['frames']:>6}{g('residual_yd_median'):>10}"
              f"{g('pan_deg'):>10}{g('tilt_deg'):>10}{g('focal_px'):>12}")
    if a.out:
        Path(a.out).write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8")
        print(f"[smooth] wrote {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
