"""Every gate this project can check, in one command.

    python -m tools.gates                 # every possession in work/
    python -m tools.gates work/p0001      # just one

Written because the gates had spread out. M1 acceptance lived in `eval/m1-*`,
the structural check in `eval/m4-*`, the mosaic's accuracy in a tool nobody ran
twice, and three of the defects found on 2026-09-14 were things that **printed
success while being wrong** - an acceptance that exited 0 on FAIL, a loop bound
reporting "dropped 6" for every possession alike, a cliff calibrated on the
wrong population. A gate you have to remember is a gate that will be forgotten,
and a gate whose output you have to read carefully is only slightly better.

Exit code is non-zero if anything fails, so it can sit in front of a publish.

**Every threshold here is documented in `docs/30-findings-and-gates.md` with the
measurement it came from.** None of them are set to make current output pass; two
of them are currently failing on purpose, because that is what the state of the
project is.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

# --------------------------------------------------------------------------- #
# thresholds, each with the measurement behind it. docs/30 carries the argument.
# --------------------------------------------------------------------------- #

M1_MEAN_YD = 0.75          # docs/04 M1, unchanged since the first milestone
M1_MAX_YD = 1.5            # docs/04 M1
CALIB_FLOOR = 0.01174      # exp(-2 yd / 0.45): below this a pose says less than
                           # dead reckoning does. ur/detect/run.py
SECOND_DIFF_YD = 1.0       # p0001, the possession with no visible glitch, never
                           # exceeds 0.35 yd. ur/calibrate/mosaic.py
PUBLISH_MEDIAN_COVERAGE = 6    # below this the median frame is mostly empty
PUBLISH_MAX_BLANK = 0.35       # and this much of the scrub bar is nothing at all

# The disc gates. Both currently FAIL and are meant to: see docs/30.
SPAN_ACCURACY = 0.75       # of held-out identity tags, across >= 2 possessions
MARGIN_CORRELATION = 0.5   # the margin has to predict correctness to drive a loop
MIN_GRADED_SPANS = 8       # below this an accuracy is a coin-toss report


def _probe_centre(cal: dict) -> np.ndarray:
    return np.array([cal["camera"]["image_w"] / 2.0,
                     cal["camera"]["image_h"] * 0.55, 1.0])


def check_possession(work: Path) -> dict:
    out: dict = {"possession": work.name, "checks": []}

    def add(name, ok, got, want, note=""):
        out["checks"].append({"name": name, "pass": bool(ok), "got": got,
                              "want": want, "note": note})

    cal_p, poss_p = work / "calibration.json", work / "possession.json"
    if not poss_p.exists():
        add("pipeline has run", False, "no possession.json", "the pipeline run")
        return out
    cal = json.loads(cal_p.read_text(encoding="utf-8"))
    doc = json.loads(poss_p.read_text(encoding="utf-8"))

    acc_p = Path(f"eval/m1-{work.name}/m1_acceptance.json")
    if acc_p.exists():
        a = json.loads(acc_p.read_text(encoding="utf-8"))
        add("M1 acceptance, mean", a["mean_error_yd"] is not None
            and a["mean_error_yd"] < M1_MEAN_YD, a["mean_error_yd"],
            f"< {M1_MEAN_YD} yd")
        add("M1 acceptance, max", a["max_error_yd"] is not None
            and a["max_error_yd"] < M1_MAX_YD, a["max_error_yd"],
            f"< {M1_MAX_YD} yd")
        # Not a pass/fail - the number the mean has to be read beside.
        add("...measured on", True, f"{a.get('usable_fraction', 0):.0%} of frames",
            "reported, not gated",
            "a mean over the frames that already passed the confidence gate is "
            "not a statement about the possession")
    else:
        add("M1 acceptance", False, "not run", "eval/m1-<id>/m1_acceptance.json")

    st_p = Path(f"eval/m4-{work.name}/m4_structure_acceptance.json")
    if st_p.exists():
        st = json.loads(st_p.read_text(encoding="utf-8"))
        add("roster structure", st["pass"], f"{len(st['problems'])} problems",
            "zero, always (docs/04 M4)")
    else:
        add("roster structure", False, "not run", "eval/m4-<id>/...")

    # Physically impossible camera motion between drawn frames.
    probe = _probe_centre(cal)
    pts = {}
    for r in cal["frames"]:
        if r.get("H") and r.get("confidence", 0) >= CALIB_FLOOR:
            q = np.asarray(r["H"], float) @ probe
            if abs(q[2]) > 1e-9:
                pts[r["f"]] = q[:2] / q[2]
    ks = sorted(pts)
    worst, bad = 0.0, 0
    for i in range(1, len(ks) - 1):
        f, lo, hi = ks[i], ks[i - 1], ks[i + 1]
        if hi - lo > 20:
            continue
        u = (f - lo) / (hi - lo)
        d = float(np.hypot(*(pts[f] - (pts[lo] * (1 - u) + pts[hi] * u))))
        worst = max(worst, d)
        bad += d > SECOND_DIFF_YD
    add("camera motion is possible", bad == 0, f"{bad} frames, worst {worst:.2f} yd",
        f"0 frames over {SECOND_DIFF_YD} yd")

    # What a reader actually sees.
    pl, nf = doc["players"], doc["possession"]["frames"]
    seen = {"observed", "provisional", "weak", "confirmed"}
    cov = [sum(1 for p in pl if p["state"][f] in seen) for f in range(nf)]
    blank = sum(1 for v in cov if v == 0) / nf
    add("median roster in shot", np.median(cov) >= PUBLISH_MEDIAN_COVERAGE,
        f"{np.median(cov):.0f} of 14", f">= {PUBLISH_MEDIAN_COVERAGE}",
        "publishing gate, not a pipeline gate")
    add("frames with nothing at all", blank <= PUBLISH_MAX_BLANK, f"{blank:.0%}",
        f"<= {PUBLISH_MAX_BLANK:.0%}", "publishing gate")

    # The attacking direction, where the tracker can speak to it.
    dc = doc["possession"].get("attacking_direction_check", {})
    if dc.get("agrees") is False:
        add("attacking direction", False,
            f"declared {dc.get('declared')}, play drifts {dc.get('drift_yd')} yd",
            "the file and the play agree")
    return out


def check_disc(works: list[Path]) -> dict:
    """Grade the span solver wherever a human has named who held the disc."""
    from ur import spans as SP

    out: dict = {"possession": "disc / holder inference", "checks": []}
    graded, correct, pairs = 0, 0, []
    per = []
    for work in works:
        ev_p = work / "events.json"
        if not (work / "possession.json").exists() or not ev_p.exists():
            continue
        ev = json.loads(ev_p.read_text(encoding="utf-8"))
        doc = json.loads((work / "possession.json").read_text(encoding="utf-8"))
        nf = int(doc["possession"]["frames"])
        fps = float(doc["possession"]["fps"])
        off = doc["possession"]["offense"]
        ids = [p["id"] for p in doc["players"] if p["team"] == off]
        truth = [s.fixed for s in SP.spans_from_events(ev, nf, fps, ids)]
        if not any(t is not None for t in truth):
            continue
        blind = {"events": [{**e, "player": None} for e in ev.get("events", [])]}
        sp = SP.spans_from_events(blind, nf, fps, ids)
        if len(sp) < 2 or len(sp) != len(truth):
            continue
        SP.span_costs(doc, sp, ids)
        path, margins = SP.solve(doc, sp, ids)
        n = ok = 0
        for g, t, m in zip(path, truth, margins):
            if t is None:
                continue
            n += 1
            ok += (g == t)
            if np.isfinite(m):
                pairs.append((float(m), 1.0 if g == t else 0.0))
        graded += n
        correct += ok
        per.append(f"{work.name} {ok}/{n}")

    acc = correct / graded if graded else None
    out["checks"].append({
        "name": "span identity accuracy", "pass": bool(graded >= MIN_GRADED_SPANS
                                                       and acc is not None
                                                       and acc >= SPAN_ACCURACY),
        "got": (f"{correct}/{graded}" + (f" = {acc:.0%}" if acc is not None else "")
                + (f"  [{', '.join(per)}]" if per else "")),
        "want": f">= {SPAN_ACCURACY:.0%} over at least {MIN_GRADED_SPANS} spans",
        "note": "needs identity tags: select the player, then press `c`"})

    corr = None
    if len(pairs) >= MIN_GRADED_SPANS and len({p[1] for p in pairs}) > 1:
        corr = float(np.corrcoef([p[0] for p in pairs], [p[1] for p in pairs])[0, 1])
    out["checks"].append({
        "name": "margin predicts correctness",
        "pass": corr is not None and corr >= MARGIN_CORRELATION,
        "got": "not enough graded spans" if corr is None else f"r = {corr:+.2f}",
        "want": f"r >= {MARGIN_CORRELATION}",
        "note": "docs/27 step 4 asks for the next tag where the margin is "
                "thinnest; that is only a strategy if the margin means something"})
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="tools.gates")
    p.add_argument("work", nargs="*", default=None)
    a = p.parse_args(argv)
    works = ([Path(w) for w in a.work] if a.work
             else sorted(q for q in Path("work").iterdir()
                         if (q / "possession.json").exists()))
    reports = [check_possession(w) for w in works]
    reports.append(check_disc(works))

    failed = 0
    for r in reports:
        print(f"\n=== {r['possession']}")
        for c in r["checks"]:
            mark = "PASS" if c["pass"] else "FAIL"
            if not c["pass"]:
                failed += 1
            print(f"  [{mark}] {c['name']:<28} {str(c['got']):<34} want {c['want']}")
            if c.get("note") and not c["pass"]:
                print(f"         {c['note']}")
    print(f"\n{failed} check(s) failing. docs/30-findings-and-gates.md says which "
          "of those are known and deliberate.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
