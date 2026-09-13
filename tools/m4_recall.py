"""M4's observed gate, re-specified: per-player recall, position-matched.

    python -m tools.m4_recall work/p0001

The gate `docs/04-milestones.md` originally set compared two *counts* — the
tracker's observed slot-frames against the number of players visible. A count
comparison is a weak thing to gate on, because it can be satisfied by counting
the wrong objects: admitting the detections `ur/team.py` flags `weak_team` would
have added about 1.1 detections per frame, over half of them referees and camera
crew, and bought roughly 8 points of "observed" by putting non-players into
player slots. The number would have passed and the product would have been worse.
`docs/15-m4-review.md` has the full argument.

**This asks the question that gate was trying to ask.** For each of the 20 frames
a human labelled, take every box labelled `sol` or `chill` — a real player, in
kit, on the field. Ask whether a slot *of that team* is `observed` within a
threshold of it. A referee cannot improve this number, because referees are not
in the denominator, so the incentive that made the old gate dangerous is gone.

Two thresholds matter and both are reported. **Greedy** asks whether *any*
same-team observed slot is within range; **one-to-one** solves an assignment so
that one slot can cover only one player. Greedy is the review's specification;
one-to-one is stricter and exists because greedy can over-count. In ultimate two
same-team players inside 1.5 yd of each other is uncommon but real — a stack, a
poach switch — and when it happens a greedy match lets one observed slot answer
for both of them. Where the two numbers agree, the threshold is not doing the
work. Where they diverge, they say how much double-counting there is.

**The denominator is detected-and-labelled players**, which is the honest limit of
this measurement: a player the detector never found has no box, so no label, so
no place in the denominator. M2 measured that miss at 3 players over these same
20 frames (recall 0.9873), so a second denominator of 237 rather than 234 is
reported alongside. Neither is wrong; they answer slightly different questions,
and quoting only the first would flatter the result.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from scipy.optimize import linear_sum_assignment

THRESHOLDS = (1.0, 1.5, 2.0)
GATE_THRESHOLD = 1.5
GATE_RECALL = 0.90          # the review's recorded expectation, not a spec number


def measure(work: Path, labels_path: Path, m2_path: Path) -> dict:
    det = json.loads((work / "detections.json").read_text(encoding="utf-8"))
    poss = json.loads((work / "possession.json").read_text(encoding="utf-8"))
    lab = json.loads(labels_path.read_text(encoding="utf-8"))
    m2 = json.loads(m2_path.read_text(encoding="utf-8"))

    by_frame = {d["f"]: d["dets"] for d in det["frames"]}
    players = poss["players"]
    missed = {int(r["frame"]): int(r.get("missed", 0)) for r in m2["frames"]}

    # Truth: every box a human called a player, with the field position the
    # pipeline computed for it. Positions come from detections.json, not from the
    # tracker, so the tracker is never scored against its own output.
    truth = []
    no_position = 0
    for r in lab["labels"]:
        if r["cls"] not in ("sol", "chill"):
            continue
        d = by_frame[r["f"]][r["i"]]
        if d.get("field") is None:
            no_position += 1
            continue
        truth.append({"f": int(r["f"]), "i": int(r["i"]), "team": r["cls"],
                      "xy": np.asarray(d["field"], float),
                      "weak_team": bool(d.get("weak_team"))})

    frames = sorted({t["f"] for t in truth})
    results = {}
    for thr in THRESHOLDS:
        greedy_hits, o2o_hits = 0, 0
        per_frame = []
        for f in frames:
            rows = [t for t in truth if t["f"] == f]
            obs = [(p["id"], p["team"], np.asarray(p["est"][f], float))
                   for p in players if p["state"][f] == "observed"
                   and p["est"][f] is not None]
            g = 0
            for t in rows:
                near = [np.hypot(*(t["xy"] - o[2])) for o in obs if o[1] == t["team"]]
                if near and min(near) <= thr:
                    g += 1
            greedy_hits += g

            # One-to-one: a slot may answer for only one player.
            o = 0
            for team in ("sol", "chill"):
                tr = [t for t in rows if t["team"] == team]
                ob = [x for x in obs if x[1] == team]
                if not tr or not ob:
                    continue
                cost = np.full((len(tr), len(ob)), 1e6)
                for a, t in enumerate(tr):
                    for b, x in enumerate(ob):
                        dd = float(np.hypot(*(t["xy"] - x[2])))
                        if dd <= thr:
                            cost[a, b] = dd
                ri, ci = linear_sum_assignment(cost)
                o += int(sum(1 for a, b in zip(ri, ci) if cost[a, b] < 1e6))
            o2o_hits += o
            per_frame.append({"frame": f, "labelled_players": len(rows),
                              "observed_slots": len(obs),
                              "greedy_matched": g, "one_to_one_matched": o})
        results[str(thr)] = {
            "greedy": round(greedy_hits / max(len(truth), 1), 4),
            "one_to_one": round(o2o_hits / max(len(truth), 1), 4),
            "greedy_matched": greedy_hits,
            "one_to_one_matched": o2o_hits,
            "per_frame": per_frame,
        }

    n_lab = len(truth)
    n_missed = sum(missed.get(f, 0) for f in frames)
    gate = results[str(GATE_THRESHOLD)]
    wide = {k: round(v["one_to_one_matched"] / max(n_lab + n_missed, 1), 4)
            for k, v in results.items()}

    # Where did the misses go? A labelled player with no same-team observed slot
    # near it is either a slot the tracker lost, or one it never had.
    miss_detail = []
    for t in truth:
        obs = [(p["id"], np.asarray(p["est"][t["f"]], float)) for p in players
               if p["team"] == t["team"] and p["state"][t["f"]] == "observed"
               and p["est"][t["f"]] is not None]
        near = min([np.hypot(*(t["xy"] - o[1])) for o in obs], default=np.inf)
        if near > GATE_THRESHOLD:
            miss_detail.append({"f": t["f"], "i": t["i"], "team": t["team"],
                                "nearest_same_team_observed_yd":
                                    (None if not np.isfinite(near) else round(float(near), 2)),
                                "was_weak_team": t["weak_team"]})

    return {
        "schema": "ultimate-radar/m4-recall-acceptance@1",
        "possession": det["possession_id"],
        "supersedes": ("docs/04-milestones.md M4's 'observed fraction within 5 points "
                       "of the visible fraction'. That compared two counts and could "
                       "be satisfied by counting referees; see docs/15-m4-review.md."),
        "method": ("every box hand-labelled sol or chill on the 20 M2/M3 held-out "
                   "frames, matched against slots of the same team whose state is "
                   "`observed`, by field distance"),
        "labels": str(labels_path),
        "n_frames": len(frames),
        "labelled_players": n_lab,
        "labelled_players_without_a_field_position": no_position,
        "detector_missed_on_these_frames": n_missed,
        "denominator_note": ("labelled_players counts players the detector found and a "
                             "human confirmed. The detector missed "
                             f"{n_missed} more on these frames (M2 recall 0.9873), so "
                             f"the wider denominator is {n_lab + n_missed}."),
        "gate": {"threshold_yd": GATE_THRESHOLD,
                 "expectation_recorded_before_measuring": GATE_RECALL},
        "recall_at_threshold": {k: {"greedy": v["greedy"], "one_to_one": v["one_to_one"]}
                                for k, v in results.items()},
        "recall_against_wider_denominator": wide,
        "pass": bool(gate["one_to_one"] >= GATE_RECALL),
        "by_threshold": results,
        "misses_at_gate_threshold": miss_detail,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="tools.m4_recall")
    p.add_argument("work")
    p.add_argument("--labels", default="eval/m3/team_labels.json")
    p.add_argument("--m2", default="eval/m2/labels.json")
    p.add_argument("--out", default="eval/m4/m4_recall_acceptance.json")
    a = p.parse_args(argv)
    res = measure(Path(a.work), Path(a.labels), Path(a.m2))
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=2) + chr(10), encoding="utf-8")

    print(f"  frames            : {res['n_frames']}")
    print(f"  labelled players  : {res['labelled_players']}  "
          f"(detector missed {res['detector_missed_on_these_frames']} more; "
          f"wider denominator {res['labelled_players'] + res['detector_missed_on_these_frames']})")
    print()
    print(f"  {'threshold':>10} {'greedy':>8} {'one-to-one':>11} {'1-to-1 vs wider':>16}")
    for thr in THRESHOLDS:
        r = res["by_threshold"][str(thr)]
        print(f"  {thr:>8.1f} yd {r['greedy']:>8.4f} {r['one_to_one']:>11.4f} "
              f"{res['recall_against_wider_denominator'][str(thr)]:>16.4f}")
    g = res["by_threshold"][str(GATE_THRESHOLD)]
    print()
    print(f"  GATE at {GATE_THRESHOLD} yd, one-to-one: {g['one_to_one']:.4f}   "
          f"(expected >= {GATE_RECALL} before measuring)  "
          f"{'PASS' if res['pass'] else 'FAIL'}")
    print(f"  misses at {GATE_THRESHOLD} yd: {len(res['misses_at_gate_threshold'])}, "
          f"of which {sum(1 for m in res['misses_at_gate_threshold'] if m['was_weak_team'])} "
          "were excluded from association as weak_team")
    print(f"\n  -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
