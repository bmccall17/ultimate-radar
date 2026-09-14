"""The M4 gate that should never be interesting: zero phantom or missing slots.

    python -m tools.m4_structure work/p0001

`docs/04-milestones.md` M4 lists "phantom or missing slots: zero, always". AD-2
is what makes that checkable rather than aspirational — there are exactly 7
offensive and 7 defensive players for the whole possession, slots are never
created or destroyed, and a slot with no detection degrades rather than
disappearing. So the check is structural, needs no ground truth, and should be
run on every tracker change. A gate that costs nothing to run has no excuse for
being run once.

It also enforces the project rule that is easy to violate by accident: **no
position without an evidence state and a sigma.** A sample carrying coordinates
and no sigma is exactly the kind of thing that looks fine in a viewer and is a
lie, so it is checked here rather than trusted.

The one thing worth explaining: a detection index may appear at most once per
frame across all slots. Two slots holding the same detection would be two players
standing in one place, which the roster constraint cannot express and the
assignment is supposed to forbid — but "supposed to" is what a check is for.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

VALID_STATES = {"observed", "provisional", "interpolated", "predicted", "unknown",
                "confirmed"}
# A detection was matched, so the sample carries one and must have a position.
ANCHORED_STATES = {"observed", "provisional"}

# "Confidently classified", matching ur/team.py WEAK_TEAM_P.
CONFIDENT_KIT_P = 0.9
# M4 is allowed predicted and interpolated; confirmed arrives with M5's corrections.
EXPECTED_STATES = {"observed", "provisional", "interpolated", "predicted", "unknown"}


def check(work: Path) -> dict:
    clip = json.loads((work / "clip.json").read_text(encoding="utf-8"))
    trk = json.loads((work / "tracks.json").read_text(encoding="utf-8"))
    det = json.loads((work / "detections.json").read_text(encoding="utf-8"))
    by_frame = {d["f"]: d["dets"] for d in det["frames"]}
    n_frames = int(clip["frames"])
    offense, defense = clip["offense"], clip["defense"]

    problems: list[str] = []
    slots = trk["slots"]

    if len(slots) != 14:
        problems.append(f"{len(slots)} slots, not 14")
    names = [s["slot"] for s in slots]
    dup = [k for k, v in Counter(names).items() if v > 1]
    if dup:
        problems.append(f"duplicate slot names: {dup}")
    per_team = Counter(s["team"] for s in slots)
    for team in (offense, defense):
        if per_team.get(team) != 7:
            problems.append(f"{per_team.get(team, 0)} slots for {team}, not 7")

    det_owner: dict[tuple[int, int], list[str]] = {}
    for s in slots:
        smp = s["samples"]
        if len(smp) != n_frames:
            problems.append(f"{s['slot']}: {len(smp)} samples, not {n_frames}")
        seen = set()
        for r in smp:
            f = r["f"]
            if f in seen:
                problems.append(f"{s['slot']}: frame {f} appears twice")
            seen.add(f)
            st = r.get("state")
            if st not in VALID_STATES:
                problems.append(f"{s['slot']} f{f}: state {st!r} is not a valid state")
            elif st not in EXPECTED_STATES:
                problems.append(f"{s['slot']} f{f}: state {st!r} should not exist at M4")
            if r.get("sigma") is None:
                problems.append(f"{s['slot']} f{f}: no sigma")
            elif r["xy"] is not None and not (r["sigma"] > 0):
                problems.append(f"{s['slot']} f{f}: position with sigma {r['sigma']}")
            if st in ANCHORED_STATES:
                if r.get("det") is None:
                    problems.append(f"{s['slot']} f{f}: {st} with no detection")
                if r.get("xy") is None:
                    problems.append(f"{s['slot']} f{f}: {st} with no position")
            if st in ("interpolated", "predicted") and r.get("xy") is None:
                problems.append(f"{s['slot']} f{f}: {st} with no position")
            di = r.get("det")
            if di is not None:
                if st not in ANCHORED_STATES:
                    problems.append(f"{s['slot']} f{f}: {st} but carries a detection")
                dets = by_frame.get(f, [])
                if di >= len(dets):
                    problems.append(f"{s['slot']} f{f}: detection index {di} out of range")
                else:
                    d = dets[di]
                    # AD-3 as amended in round 2: a slot may hold a detection
                    # whose nearer kit label is the other team, but only while
                    # that call is not confident. A *confident* cross-team hold
                    # is the failure AD-3 exists to prevent and is still a
                    # structural error. See docs/25-round-2-ghost-audit.md R1.
                    p_team = d.get("team_p")
                    if p_team is None:
                        p_own = 1.0 if d.get("team") == s["team"] else 0.0
                    else:
                        p_own = (float(p_team) if d.get("team") == s["team"]
                                 else 1.0 - float(p_team))
                    if p_own < 1.0 - CONFIDENT_KIT_P:
                        problems.append(
                            f"{s['slot']} f{f}: holds a {d.get('team')} detection "
                            f"at P {p_own:.2f} but the slot is {s['team']} (AD-3)")
                det_owner.setdefault((f, di), []).append(s["slot"])
        missing = set(range(n_frames)) - seen
        if missing:
            problems.append(f"{s['slot']}: missing frames {sorted(missing)[:5]}...")

    shared = {k: v for k, v in det_owner.items() if len(v) > 1}
    for (f, di), who in sorted(shared.items())[:10]:
        problems.append(f"f{f} detection {di} held by {who}")

    counts = Counter(r["state"] for s in slots for r in s["samples"])
    return {
        "schema": "ultimate-radar/m4-structure-acceptance@1",
        "possession": trk["possession_id"],
        "gate": "zero phantom or missing slots, always (docs/04 M4)",
        "slots": len(slots),
        "slots_per_team": dict(per_team),
        "frames": n_frames,
        "samples_expected": 14 * n_frames,
        "samples_found": sum(len(s["samples"]) for s in slots),
        "state_counts": dict(counts),
        "detections_held_by_more_than_one_slot": len(shared),
        "problems": problems,
        "pass": not problems,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="tools.m4_structure")
    p.add_argument("work")
    p.add_argument("--out", default="eval/m4/m4_structure_acceptance.json")
    a = p.parse_args(argv)
    res = check(Path(a.work))
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=2) + chr(10), encoding="utf-8")
    print(f"  slots            : {res['slots']}  {res['slots_per_team']}")
    print(f"  samples          : {res['samples_found']} of {res['samples_expected']} expected")
    print(f"  states           : " + ", ".join(f"{k} {v}" for k, v in
                                               sorted(res["state_counts"].items())))
    print(f"  shared detections: {res['detections_held_by_more_than_one_slot']}")
    print(f"  problems         : {len(res['problems'])}")
    for q in res["problems"][:20]:
        print(f"      {q}")
    print(f"\n  GATE zero phantom or missing slots: "
          f"{'PASS' if res['pass'] else 'FAIL'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
