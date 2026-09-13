"""M4's position and sigma-calibration gates, on a sample M3 never touched.

    python -m tools.m4_foot render work/p0001    # -> eval/m4/trkfoot_00.png ...
    python -m tools.m4_foot score  work/p0001    # reads eval/m4/foot_labels.json

Two gates from `docs/04-milestones.md` M4:

| Field position error, `observed` samples | median < 0.8 yd, p95 < 1.8 yd |
| Sigma calibration | >= 80 % of truths inside the drawn sigma disc |

**The sample is disjoint from `eval/m3/foot_labels.json` by construction**, and
that is the whole reason this file exists rather than reusing those 50. M3 set
`FOOT_UNCERTAINTY_PX` from that sample; `sigma_yd` is derived from it; the
tracker's measurement noise is derived from `sigma_yd`. Scoring the sigma gate on
the same 50 would be asking a constant whether it fits its own training data, and
it would say yes.

**What is compared to what.** The truth is a hand-read foot point, projected
through the same homography. It is compared against the **tracker's** estimate
for the slot holding that detection — not against the detection's own position.
Those differ: the filter combines several frames, so its estimate is not the
measurement it just consumed, and the gate asks about the tracker.

Reading is done exactly as in M3: a grid in source pixels around the box bottom
centre, the detection box drawn so it is never ambiguous whose feet are being
read, and the offset read off the grid rather than estimated. The rendering code
is imported from `tools/m3_foot.py` rather than copied, so the two measurements
stay comparable.

**A readability floor is applied and reported.** Boxes under 40 px tall cannot be
read to a pixel, so they are excluded from the sample — the same floor M3 used.
That biases the sample toward nearer players, so the fraction of the observed
population it excludes is reported rather than left implicit.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from tools.m3_foot import render_picks

SEED = 20260828          # deliberately not M3's seed
N_SAMPLES = 40
MIN_BOX_H = 40


def sample(work: Path, n: int = N_SAMPLES, seed: int = SEED,
           exclude: set[tuple[int, int]] | None = None) -> tuple[list, dict]:
    """Observed slot-samples, seeded, disjoint from `exclude`."""
    det = json.loads((work / "detections.json").read_text(encoding="utf-8"))
    poss = json.loads((work / "possession.json").read_text(encoding="utf-8"))
    by = {d["f"]: d["dets"] for d in det["frames"]}
    exclude = exclude or set()

    pool, n_obs, n_short = [], 0, 0
    for p in poss["players"]:
        for f, (st, di) in enumerate(zip(p["state"], p["det"])):
            if st != "observed" or di is None:
                continue
            n_obs += 1
            d = by[f][di]
            if (d["box"][3] - d["box"][1]) < MIN_BOX_H:
                n_short += 1
                continue
            if (f, di) in exclude:
                continue
            pool.append((f, di, p["id"]))
    rng = np.random.default_rng(seed)
    idx = rng.choice(len(pool), size=min(n, len(pool)), replace=False)
    picks = sorted((pool[int(k)] for k in idx), key=lambda r: (r[0], r[1]))
    return picks, {"observed_samples": n_obs,
                   "excluded_by_readability_floor": n_short,
                   "readability_floor_px": MIN_BOX_H,
                   "eligible_after_exclusions": len(pool)}


def m3_pairs() -> set[tuple[int, int]]:
    p = Path("eval/m3/foot_labels.json")
    if not p.exists():
        return set()
    return {(int(r["f"]), int(r["i"]))
            for r in json.loads(p.read_text(encoding="utf-8"))["labels"]}


def cmd_render(a) -> int:
    work, out = Path(a.work), Path(a.out)
    picks, meta = sample(work, a.n, exclude=m3_pairs())
    print(f"[m4_foot] {meta['observed_samples']} observed samples; "
          f"{meta['excluded_by_readability_floor']} below the {MIN_BOX_H} px "
          f"readability floor; {meta['eligible_after_exclusions']} eligible after "
          f"excluding M3's 50")
    render_picks(work, out, [(f, i) for f, i, _ in picks], prefix="trkfoot")
    print("[m4_foot] now write eval/m4/foot_labels.json: {f, i, dx, dy} per crop")
    return 0


def cmd_score(a) -> int:
    work, out = Path(a.work), Path(a.out)
    det = json.loads((work / "detections.json").read_text(encoding="utf-8"))
    poss = json.loads((work / "possession.json").read_text(encoding="utf-8"))
    by = {d["f"]: d["dets"] for d in det["frames"]}
    labels = json.loads((out / "foot_labels.json").read_text(encoding="utf-8"))

    # slot holding each (frame, detection)
    owner = {}
    for p in poss["players"]:
        for f, di in enumerate(p["det"]):
            if di is not None:
                owner[(f, di)] = p

    rows = []
    for lab in labels["labels"]:
        f, i = int(lab["f"]), int(lab["i"])
        d = by[f][i]
        p = owner.get((f, i))
        if p is None:
            continue
        # Project the hand-read foot point with H, which docs/03 defines as image
        # pixel -> ULTIMATE field yard. `CFIT.backproject` returns the *soccer*
        # frame, and using it here silently subtracted the venue transform from
        # one side of the comparison only - 60 yd along the field and 32.75
        # across. The symptom was a median error of 68 yd, which is at least the
        # kind of wrong that cannot be mistaken for a result.
        pf = poss["camera"]["per_frame"][f]
        if pf is None:
            continue
        H = np.asarray(pf["H"], float)
        fx, fy = d["foot"]
        q = H @ np.array([fx + float(lab["dx"]), fy + float(lab["dy"]), 1.0])
        truth = q[:2] / q[2]
        est = np.asarray(p["est"][f], float)
        raw = np.asarray(d["field"], float)
        sigma = float(p["sigma"][f])
        rows.append({
            "f": f, "i": i, "slot": p["id"],
            "dx": lab["dx"], "dy": lab["dy"],
            "tracker_error_yd": round(float(np.hypot(*(est - truth))), 4),
            "detection_error_yd": round(float(np.hypot(*(raw - truth))), 4),
            "sigma_yd": round(sigma, 4),
            "inside_sigma": bool(np.hypot(*(est - truth)) <= sigma),
            "box_h": round(d["box"][3] - d["box"][1], 1),
            "yd_per_px": d.get("yd_per_px"),
            "note": lab.get("note", ""),
        })

    e = np.array([r["tracker_error_yd"] for r in rows])
    ed = np.array([r["detection_error_yd"] for r in rows])
    sg = np.array([r["sigma_yd"] for r in rows])
    inside = float(np.mean(e <= sg))

    # A 2-D Gaussian with per-axis sigma contains only 39 % inside radius sigma,
    # so report what radius the measured errors actually need.
    need80 = float(np.percentile(e / sg, 80))

    # 40 samples is a small number to gate a percentage on. A Wilson interval
    # says how small: quote it next to the point estimate so nobody reads a
    # marginal pass as a settled one.
    n_in, n_tot = int((e <= sg).sum()), len(e)
    z = 1.96
    ph = n_in / max(n_tot, 1)
    denom = 1 + z * z / n_tot
    centre = (ph + z * z / (2 * n_tot)) / denom
    half = z * np.sqrt(ph * (1 - ph) / n_tot + z * z / (4 * n_tot * n_tot)) / denom
    wilson = (round(float(centre - half), 3), round(float(centre + half), 3))

    _, meta = sample(work, 0, exclude=m3_pairs())
    res = {
        "schema": "ultimate-radar/m4-foot-acceptance@1",
        "possession": det["possession_id"],
        "labelled_by": labels.get("labelled_by"),
        "convention": labels.get("convention"),
        "caveats": labels.get("caveats"),
        "disjoint_from": "eval/m3/foot_labels.json (by construction; seed 20260828)",
        "n": len(rows),
        "population": meta,
        "position_gate": {
            "gate": {"median_yd": 0.8, "p95_yd": 1.8},
            "median_yd": round(float(np.median(e)), 4),
            "mean_yd": round(float(e.mean()), 4),
            "p95_yd": round(float(np.percentile(e, 95)), 4),
            "max_yd": round(float(e.max()), 4),
            "pass": bool(np.median(e) < 0.8 and np.percentile(e, 95) < 1.8),
        },
        "detection_error_for_comparison": {
            "median_yd": round(float(np.median(ed)), 4),
            "p95_yd": round(float(np.percentile(ed, 95)), 4),
            "note": "the raw back-projected foot point, i.e. what the tracker was "
                    "given. If the tracker's error is lower, filtering helped.",
        },
        "sigma_gate": {
            "gate": 0.80,
            "fraction_inside_sigma": round(inside, 4),
            "inside_count": f"{n_in}/{n_tot}",
            "wilson_95_interval": wilson,
            "pass": bool(inside >= 0.80),
            "pass_is_marginal": bool(wilson[0] < 0.80 <= inside),
            "median_sigma_yd": round(float(np.median(sg)), 4),
            "error_over_sigma_p80": round(need80, 3),
            "note": ("`sigma` is the radius of the disc docs/05 says the viewer "
                     "draws, and the gate asks that >= 80 % of truths fall inside "
                     "it. A 2-D Gaussian with per-axis sigma contains only 39 % "
                     "within radius sigma, so a per-axis sigma cannot pass this "
                     "gate however well calibrated it is. error_over_sigma_p80 is "
                     "the multiple of the current sigma that would."),
        },
        "samples": rows,
    }
    (out / "m4_foot_acceptance.json").write_text(json.dumps(res, indent=2) + chr(10),
                                                 encoding="utf-8")

    pg, sgate = res["position_gate"], res["sigma_gate"]
    print(f"  n                  : {len(rows)} hand-checked observed samples")
    print(f"  population         : {meta['observed_samples']} observed, "
          f"{meta['excluded_by_readability_floor']} below the {MIN_BOX_H} px floor "
          f"({meta['excluded_by_readability_floor']/max(meta['observed_samples'],1):.0%})")
    print()
    print(f"  tracker error      : median {pg['median_yd']:.4f} yd   (gate < 0.8)")
    print(f"                       p95    {pg['p95_yd']:.4f} yd   (gate < 1.8)   "
          f"{'PASS' if pg['pass'] else 'FAIL'}")
    print(f"  detection error    : median {res['detection_error_for_comparison']['median_yd']:.4f}, "
          f"p95 {res['detection_error_for_comparison']['p95_yd']:.4f}  (what it was given)")
    print()
    print(f"  inside sigma disc  : {sgate['fraction_inside_sigma']:.1%} "
          f"({sgate['inside_count']})   (gate >= 80%)   "
          f"{'PASS' if sgate['pass'] else 'FAIL'}")
    lo, hi = sgate["wilson_95_interval"]
    print(f"                       95% interval {lo:.1%} to {hi:.1%} on n={n_tot} - "
          f"{'MARGINAL, not settled' if sgate['pass_is_marginal'] else 'clear of the gate'}")
    print(f"  median sigma       : {sgate['median_sigma_yd']:.3f} yd; "
          f"{sgate['error_over_sigma_p80']:.2f}x that would contain 80%")
    print(f"\n  -> {out / 'm4_foot_acceptance.json'}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="tools.m4_foot")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("render")
    r.add_argument("work")
    r.add_argument("--out", default="eval/m4")
    r.add_argument("-n", type=int, default=N_SAMPLES)
    r.set_defaults(fn=cmd_render)
    s = sub.add_parser("score")
    s.add_argument("work")
    s.add_argument("--out", default="eval/m4")
    s.set_defaults(fn=cmd_score)
    a = p.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
