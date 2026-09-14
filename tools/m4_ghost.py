"""Round 2 - the acceptance numbers for the ghost audit, measured the same way twice.

    python -m tools.m4_ghost baseline work/p0001   # freeze the before-set
    python -m tools.m4_ghost score    work/p0001   # score against it

`docs/25-round-2-ghost-audit.md` sets six numbers. Several are only meaningful
against a *frozen reference set*: "at least 150 of the near-miss slot-frames become
observations" is a claim about specific (slot, frame) pairs, and recomputing the set
from the new tracks would let the fix move its own goalposts - a slot that stops
being lost also stops contributing near-misses, so the denominator would shrink with
the numerator and the ratio would look good having proved nothing.

So `baseline` writes the pairs to `eval/m4/ghost_baseline.json` and `score` reads
them back. The baseline in the repo was taken from the pre-round-2 tracker.

**The near-miss definition, stated once so the two counts can be reconciled.** For
every slot-frame that is not `observed`/`confirmed`, take every detection in that
frame that is (a) in bounds, (b) not rejected as a non-player, and (c) whose kit
label is the slot's team *or* is too weak to call, and count the pair if the nearest
of them lies within 1.5 yd of the slot's estimated position. The audit's original
count took the single nearest detection of any kind, which drops an eligible
same-team detection whenever an ambiguous one happened to be nearer - exactly the
cases that bear on whether the association gate is at fault. This counts the
eligible set, which is why it reads 175 where the audit read 202.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

NEAR_YD = 1.5
FIELD_L, FIELD_W = 120.0, 160.0 / 3.0
ANCHORED = {"observed", "confirmed", "provisional"}
ESTIMATED = {"predicted", "unknown", "interpolated"}

# "Confidently classified" for the cross-team gate. The kit model is calibrated so
# that this is exactly the old hard boundary - see ur/team.py KIT_LOGIT_K.
CONFIDENT_P = 0.9


def _load(work: Path):
    trk = json.loads((work / "tracks.json").read_text(encoding="utf-8"))
    det = json.loads((work / "detections.json").read_text(encoding="utf-8"))
    clip = json.loads((work / "clip.json").read_text(encoding="utf-8"))
    return trk, det, clip


def _team_p(d: dict, team: str) -> float | None:
    """P(this detection's kit is `team`), from whichever field ur.team wrote.

    `team_p` is the probability of the label in `team`; the other team gets the
    complement, because there are exactly two kits.
    """
    p = d.get("team_p")
    if p is None:
        return None
    return float(p) if d.get("team") == team else 1.0 - float(p)


def _eligible(d: dict, team: str) -> bool:
    """Could this detection legitimately belong to a slot of `team`?"""
    if not d.get("in_bounds") or d.get("non_player") or d.get("field") is None:
        return False
    p = _team_p(d, team)
    if p is None:                       # pre-R1 output: fall back to the hard label
        return d.get("team") == team or bool(d.get("weak_team"))
    return p > 1.0 - CONFIDENT_P


def near_misses(trk: dict, det: dict) -> list[dict]:
    by_frame = {d["f"]: d["dets"] for d in det["frames"]}
    out = []
    for s in trk["slots"]:
        for smp in s["samples"]:
            if smp["state"] in ANCHORED or smp["xy"] is None:
                continue
            p = np.asarray(smp["xy"], float)
            best = None
            for i, d in enumerate(by_frame.get(smp["f"], [])):
                if not _eligible(d, s["team"]):
                    continue
                dist = float(np.hypot(*(np.asarray(d["field"], float) - p)))
                if dist <= NEAR_YD and (best is None or dist < best[0]):
                    best = (dist, i, d)
            if best:
                out.append({"slot": s["slot"], "f": smp["f"],
                            "dist_yd": round(best[0], 3), "det": best[1],
                            "why": ("weak_team" if best[2].get("weak_team")
                                    else "eligible_unassigned")})
    return out


def measure(work: Path) -> dict:
    trk, det, clip = _load(work)
    by_frame = {d["f"]: d["dets"] for d in det["frames"]}
    n_frames = int(clip["frames"])

    per_slot, off_field, cross_team, margins = {}, [], [], {}
    for s in trk["slots"]:
        states = [r["state"] for r in s["samples"]]
        n_obs = sum(1 for x in states if x in ANCHORED)
        per_slot[s["slot"]] = round(n_obs / n_frames, 4)

        m, nulls = [], 0
        for smp in s["samples"]:
            a = smp.get("assoc")
            if a:
                if a.get("margin") is None:
                    nulls += 1
                else:
                    m.append(float(a["margin"]))
            if smp["state"] not in ANCHORED or smp["xy"] is None:
                continue
            x, y = smp["xy"]
            if not (0.0 <= x <= FIELD_L and 0.0 <= y <= FIELD_W):
                off_field.append({"slot": s["slot"], "f": smp["f"],
                                  "xy": [round(x, 2), round(y, 2)]})
            d = by_frame[smp["f"]][smp["det"]] if smp["det"] is not None else None
            if d is not None:
                p = _team_p(d, s["team"])
                if p is not None and p < 1.0 - CONFIDENT_P:
                    cross_team.append({"slot": s["slot"], "f": smp["f"],
                                       "det_team": d.get("team"),
                                       "p_slot_team": round(p, 4)})
        margins[s["slot"]] = {
            "n": len(m), "nulls": nulls,
            "median": round(float(np.median(m)), 3) if m else None,
        }

    return {
        "possession": clip["possession_id"],
        "frames": n_frames,
        "observed_fraction": trk["diagnostics"]["observed_fraction"],
        "observed_fraction_per_slot": per_slot,
        "worst_slot": min(per_slot, key=per_slot.get),
        "worst_slot_fraction": min(per_slot.values()),
        "observed_off_field": len(off_field),
        "observed_off_field_detail": off_field[:20],
        "cross_team_confident": len(cross_team),
        "cross_team_detail": cross_team[:20],
        "margin": margins,
        "margin_null_total": sum(v["nulls"] for v in margins.values()),
        "margin_median_min": min(
            (v["median"] for v in margins.values() if v["median"] is not None),
            default=None),
        "near_misses_now": len(near_misses(trk, det)),
    }


def score(work: Path, baseline: Path) -> dict:
    """Recovery against the frozen set, and an honest denominator for it.

    The raw count is "how many of the baseline's blind slot-frames now carry an
    observation". Two things stop that number from reaching the total, and
    neither is a tracker failure, so both are counted rather than argued:

    - **Shared detections.** 57 of the 218 entries name a detection that another
      slot's entry also names. Two slots cannot both take one detection, so the
      jointly reachable maximum is the number of *distinct* (frame, detection)
      pairs, not the number of entries.
    - **Detections the other team explains better.** A near-miss records that a
      detection sat within 1.5 yd of where a slot was guessing - not that it was
      that slot's player. Where the detection went to a slot on the other team
      whose own kit profile is far closer to the detection's torso luminance, the
      baseline's expectation was the wrong one and recovering it would have been
      an error.
    """
    trk, det, _ = _load(work)
    base = json.loads(baseline.read_text(encoding="utf-8"))
    by_frame = {d["f"]: d["dets"] for d in det["frames"]}
    anchored = {(s["slot"], smp["f"]) for s in trk["slots"] for smp in s["samples"]
                if smp["state"] in ANCHORED}
    owner = {(smp["f"], smp["det"]): s["slot"] for s in trk["slots"]
             for smp in s["samples"] if smp["det"] is not None}

    # Each slot's own kit luminance, from the detections it took with a confident
    # kit call. This is the tracklet-level vote ur/team.py defers to M4; it is
    # used here to judge the baseline rather than to drive association, because
    # measured against the association it would move four cases.
    profile: dict[str, float] = {}
    for s in trk["slots"]:
        vals = [by_frame[smp["f"]][smp["det"]].get("torso_L")
                for smp in s["samples"] if smp["det"] is not None
                and (smp.get("assoc") or {}).get("kit_p", 0.0) >= CONFIDENT_P]
        vals = [v for v in vals if v is not None]
        if vals:
            profile[s["slot"]] = float(np.median(vals))

    pairs = [(r["slot"], r["f"]) for r in base["near_misses"]]
    distinct = len({(r["f"], r["det"]) for r in base["near_misses"]})
    recovered = [p for p in pairs if p in anchored]

    by_why: dict[str, dict] = {}
    other_team_better = 0
    for r in base["near_misses"]:
        d = by_why.setdefault(r["why"], {"n": 0, "recovered": 0})
        d["n"] += 1
        if (r["slot"], r["f"]) in anchored:
            d["recovered"] += 1
            continue
        who = owner.get((r["f"], r["det"]))
        if who is None or who[0] == r["slot"][0]:
            continue
        L = by_frame[r["f"]][r["det"]].get("torso_L")
        a, b = profile.get(r["slot"]), profile.get(who)
        if L is not None and a is not None and b is not None and abs(L - b) < abs(L - a):
            other_team_better += 1

    # `distinct` is fixed by the baseline and is the real denominator. The
    # other-team count is NOT subtracted from it: it is computed from the run
    # being scored, so folding it in would let the denominator move with the
    # numerator - the same mistake the frozen baseline exists to prevent. It is
    # reported alongside, as context for the remainder.
    out = measure(work)
    out["baseline"] = {
        "taken_from": base["taken_from"],
        "observed_fraction": base["measure"]["observed_fraction"],
        "worst_slot": base["measure"]["worst_slot"],
        "worst_slot_fraction": base["measure"]["worst_slot_fraction"],
        "near_miss_slot_frames": len(pairs),
        "distinct_detections": distinct,
        "shared_detections": len(pairs) - distinct,
        "other_team_explains_better": other_team_better,
        "recovered_as_observed": len(recovered),
        "recovered_fraction": round(len(recovered) / len(pairs), 4) if pairs else None,
        "recovered_of_distinct": (round(len(recovered) / distinct, 4)
                                  if distinct else None),
        "by_reason": by_why,
    }
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="tools.m4_ghost")
    p.add_argument("mode", choices=("baseline", "score", "measure"))
    p.add_argument("work")
    p.add_argument("--baseline", default="eval/m4/ghost_baseline.json")
    p.add_argument("--out", default=None)
    a = p.parse_args(argv)
    work, bl = Path(a.work), Path(a.baseline)

    if a.mode == "baseline":
        trk, det, _ = _load(work)
        doc = {"schema": "ultimate-radar/ghost-baseline@1",
               "taken_from": "ur.track.run before the round-2 rule changes "
                             "(docs/25-round-2-ghost-audit.md)",
               "near_yd": NEAR_YD,
               "measure": measure(work),
               "near_misses": near_misses(trk, det)}
        bl.parent.mkdir(parents=True, exist_ok=True)
        bl.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
        print(f"[ghost] baseline: {len(doc['near_misses'])} near-miss slot-frames "
              f"-> {bl}")
        res = doc["measure"]
    else:
        res = measure(work) if a.mode == "measure" else score(work, bl)
        if a.out:
            Path(a.out).write_text(json.dumps(res, indent=1) + "\n", encoding="utf-8")

    print(f"[ghost] observed_fraction {res['observed_fraction']:.4f}   "
          f"worst slot {res['worst_slot']} at {res['worst_slot_fraction']:.4f}")
    print(f"[ghost] observed off the field of play: {res['observed_off_field']}")
    print(f"[ghost] cross-team with both kits confident: "
          f"{res['cross_team_confident']}")
    print(f"[ghost] margin: {res['margin_null_total']} nulls, "
          f"lowest slot median {res['margin_median_min']}")
    b = res.get("baseline")
    if b:
        print(f"[ghost] near-miss recovery: {b['recovered_as_observed']} of "
              f"{b['near_miss_slot_frames']} ({b['recovered_fraction']:.1%})")
        print(f"            {b['shared_detections']} entries share a detection with "
              f"another slot, so the joint maximum is {b['distinct_detections']}: "
              f"{b['recovered_as_observed']}/{b['distinct_detections']} "
              f"= {b['recovered_of_distinct']:.1%}")
        print(f"            of the remainder, {b['other_team_explains_better']} went "
              f"to a slot whose own kit profile fits the detection better")
        for k, v in sorted(b["by_reason"].items()):
            print(f"            {k:>20}: {v['recovered']}/{v['n']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
