"""Score the jersey gate against the hand readings M4 already made.

    python -m tools.m5_identity work/p0001

`docs/04-milestones.md` M5: "jersey numbers are correct for >= 5 of 7 players on
at least one team, with the rest honestly `null`."

The truth available is `eval/m4/identity_labels.json` — 48 hand readings at 1 Hz,
which give a modal jersey per slot for 12 of the 14. **That is not a roster**, and
the difference matters for reading this score:

- two slots (O5, O7) had no readable number at 1 Hz, so there is nothing to check
  the vote against;
- two slots switched identity during the possession (M4), so "the slot's jersey"
  is the number it held longest rather than a fact about one person;
- the hand readings themselves carry about 4 errors in 52 (M4), and duplicates
  across slots — two slots whose modal number is the same — are evidence that at
  least one of the pair is wrong.

So this reports three counts rather than one: verified correct, verified wrong,
and unverifiable. Only the first two are evidence about the vote.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path


def check(work: Path, labels: Path) -> dict:
    ids = json.loads((work / "identities.json").read_text(encoding="utf-8"))
    trk = json.loads((work / "tracks.json").read_text(encoding="utf-8"))
    lab = json.loads(labels.read_text(encoding="utf-8"))
    truth_by_det = {(r["f"], r["i"]): r["jersey"] for r in lab["labels"]}

    seen: dict[str, list[int]] = defaultdict(list)
    for s in trk["slots"]:
        for smp in s["samples"]:
            if smp["state"] != "observed" or smp["det"] is None:
                continue
            j = truth_by_det.get((smp["f"], smp["det"]))
            if j is not None:
                seen[s["slot"]].append(j)

    rows, per_team = [], defaultdict(lambda: {"correct": 0, "wrong": 0,
                                              "unverifiable": 0, "null": 0})
    for s in ids["slots"]:
        obs = seen.get(s["slot"], [])
        c = Counter(obs)
        truth = c.most_common(1)[0][0] if c else None
        got = s["jersey"]
        if truth is None:
            verdict = "no truth" if got is None else "unverifiable"
        elif got is None:
            verdict = "null"
        elif got == truth:
            verdict = "correct"
        else:
            verdict = "wrong"
        t = per_team[s["team"]]
        if verdict == "correct":
            t["correct"] += 1
        elif verdict == "wrong":
            t["wrong"] += 1
        elif verdict == "null":
            t["null"] += 1
        else:
            t["unverifiable"] += 1
        rows.append({"slot": s["slot"], "team": s["team"], "voted": got,
                     "hand_modal": truth, "hand_readings": dict(c),
                     "verdict": verdict, "support": s.get("support"),
                     "margin": s.get("margin"), "why_null": s.get("why_null")})

    best = max(per_team.items(), key=lambda kv: kv[1]["correct"])
    return {
        "schema": "ultimate-radar/m5-identity-acceptance@1",
        "possession": ids["possession_id"],
        "gate": "jersey correct for >= 5 of 7 on at least one team, rest null",
        "truth_source": str(labels),
        "truth_caveats": [
            "The truth is a modal jersey per slot from 48 hand readings at 1 Hz, "
            "not a team roster. Two slots had no readable number at all.",
            "Two slots switched identity during the possession, so their modal "
            "number is the person they held longest, not a property of the slot.",
            "The hand readings carry roughly 4 errors in 52 (M4), and duplicate "
            "modal numbers across slots are evidence at least one is wrong.",
        ],
        "per_team": {k: dict(v) for k, v in per_team.items()},
        "best_team": best[0],
        "best_team_correct": best[1]["correct"],
        "pass": bool(best[1]["correct"] >= 5 and best[1]["wrong"] == 0),
        "wrong_numbers_emitted": sum(v["wrong"] for v in per_team.values()),
        "slots": rows,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="tools.m5_identity")
    p.add_argument("work")
    p.add_argument("--labels", default="eval/m4/identity_labels.json")
    p.add_argument("--out", default="eval/m5/m5_identity_acceptance.json")
    a = p.parse_args(argv)
    res = check(Path(a.work), Path(a.labels))
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=2) + chr(10), encoding="utf-8")

    print(f"  {'slot':>5} {'voted':>6} {'hand':>5} {'verdict':>13}   hand readings")
    for r in res["slots"]:
        print(f"  {r['slot']:>5} {str(r['voted']):>6} {str(r['hand_modal']):>5} "
              f"{r['verdict']:>13}   {r['hand_readings'] or '-'}")
    print()
    for team, v in res["per_team"].items():
        print(f"  {team:>6}: {v['correct']} correct, {v['wrong']} wrong, "
              f"{v['null']} null with a truth to check, "
              f"{v['unverifiable']} unverifiable")
    print()
    print(f"  wrong numbers emitted anywhere: {res['wrong_numbers_emitted']}")
    print(f"  GATE >= 5 of 7 on a team      : best is {res['best_team']} with "
          f"{res['best_team_correct']}   {'PASS' if res['pass'] else 'FAIL'}")
    print(f"\n  -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
