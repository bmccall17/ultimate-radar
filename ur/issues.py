"""M5 — the system finding its own likely mistakes, and queueing them for a human.

    python -m ur.issues work/p0001
    python -m ur.issues fixtures/possession_demo.json --fixture

`docs/05-uncertainty.md` specifies three detectors. A fourth is added here, and
the reason it is added is the most useful thing M4 measured.

**Identity exchange** and **long blind stretch** are the two the spec names for
finding swaps. Run against the real tracker output in M4, *identity exchange
fired zero times over the whole possession*, and neither detector caught either
of the two identity switches that actually happened (`docs/17-m4-tracking.md`).

The reason is structural rather than a threshold being wrong. The exchange rule
looks for a **single-frame crossing** — two slots trading places between `f-1`
and `f` while both move more than 3 yd. That is the failure
`fixtures/possession_demo.json` injects, and it is a real failure mode. But on
real footage the swaps happen across a **dropout**: a slot stops being observed
for one to three seconds, dead-reckons, and comes back attached to a different
person. There is no crossing frame to see, and the gap is spent in `predicted`
rather than `unknown`, so the blind-stretch rule does not fire either.

So **re-acquisition surprise** is the fourth detector: when a slot goes from
estimated to observed, ask how far the new observation is from where the model
said the player would be, in units of the uncertainty the model itself was
claiming. A player who reappears well outside their own sigma disc is either a
bad dead reckoning or a different person, and both are worth a human's attention.

Every detector returns the same shape, because the viewer shows them in one
queue and the only thing that differs is the copy and the one-click fix.
"""

from __future__ import annotations

import argparse
import itertools
import json
from pathlib import Path

import numpy as np

# docs/05, "Identity exchange"
EXCHANGE_NEAR_YD = 1.6
EXCHANGE_MOVED_YD = 3.0
# docs/05, "Long blind stretch"
BLIND_STRETCH_S = 1.5
# The fourth detector, in two forms.
#
# `reacquire_surprise` asks how far a returning player is from the dead-reckoned
# position, in units of the sigma the model was claiming. **Measured on p0001 it
# fires zero times**, and the reason is worth keeping rather than tuning away:
# over all 161 re-acquisitions the largest is 1.73 sigma. A player who reappears
# 25 yd away after 8 s is only 1.56 sigma, because an honest covariance after 8 s
# says "could be 16 yd away in any direction". The tracker admitted the wrong
# player precisely *because* it was plausible, so any detector built on
# implausibility is blind to exactly the errors the tracker makes. It is kept
# because it does fire on the synthetic fixture, where sigmas are smaller.
REACQUIRE_SIGMAS = 2.5
REACQUIRE_MIN_YD = 1.5      # below this the surprise is not worth a human's time

# `contested_reacquisition` asks the question that does work: was more than one
# candidate plausible? A margin in chi-square units is a log-likelihood ratio, so
# a gap of 2.0 means the winner was only about e ~ 2.7 times more likely than the
# runner-up. Below that the assignment was close to a coin flip, and a human
# should see it. The statistic comes from the tracker, which is the only place it
# exists - see `assoc` in tracks.json.
CONTESTED_MARGIN_CHI2 = 2.0
# docs/05 suggests this as a sanity check on resolved output, not on raw tracks.
IMPLIED_SPEED_YD_S = 9.5

ESTIMATED = {"predicted", "unknown", "interpolated"}
ANCHORED = {"observed", "confirmed", "provisional"}


def _xy(p: dict, f: int):
    v = p["est"][f]
    return None if v is None else np.asarray(v, float)


def identity_exchange(players: list[dict], fps: float) -> list[dict]:
    """Two same-team slots trading places in one frame. docs/05, verbatim."""
    out = []
    for a, b in itertools.combinations(players, 2):
        if a["team"] != b["team"]:
            continue
        for f in range(1, len(a["est"])):
            Af, Ap, Bf, Bp = _xy(a, f), _xy(a, f - 1), _xy(b, f), _xy(b, f - 1)
            if any(v is None for v in (Af, Ap, Bf, Bp)):
                continue
            if (np.hypot(*(Af - Bp)) < EXCHANGE_NEAR_YD
                    and np.hypot(*(Bf - Ap)) < EXCHANGE_NEAR_YD
                    and np.hypot(*(Af - Ap)) > EXCHANGE_MOVED_YD
                    and np.hypot(*(Bf - Bp)) > EXCHANGE_MOVED_YD):
                out.append({
                    "kind": "identity_exchange",
                    "frame": f, "t": round(f / fps, 3),
                    "slots": [a["id"], b["id"]], "team": a["team"],
                    "fix": {"op": "swap", "slots": [a["id"], b["id"]], "from_f": f},
                    "why": (f"{a['id']} and {b['id']} traded places between frame "
                            f"{f - 1} and {f}; each ended within "
                            f"{EXCHANGE_NEAR_YD} yd of where the other just was."),
                })
    return out


def long_blind_stretch(players: list[dict], fps: float) -> list[dict]:
    """A slot unknown for long enough that a human should place them."""
    limit = int(round(BLIND_STRETCH_S * fps))
    out = []
    for p in players:
        run, start = 0, None
        for f, st in enumerate(p["state"] + [None]):
            if st == "unknown":
                start = f if run == 0 else start
                run += 1
                continue
            if run > limit:
                out.append({
                    "kind": "long_blind_stretch",
                    "frame": start, "t": round(start / fps, 3),
                    "slots": [p["id"]], "team": p["team"],
                    "frames": run, "seconds": round(run / fps, 2),
                    "fix": {"op": "anchor", "slot": p["id"], "f": start + run // 2},
                    "why": (f"{p['id']} was unknown for {run / fps:.1f} s from frame "
                            f"{start}. Nothing observed it; its position there is "
                            "not a measurement."),
                })
            run = 0
    return out


def cold_start(players: list[dict], fps: float) -> list[dict]:
    """Slots with no observation before their first appearance, grouped.

    docs/05 asks for these as ONE queue item rather than four, because on a tight
    opening shot it is routinely four players at once and four separate cards is
    four times the annoyance for one decision.
    """
    late = []
    for p in players:
        first = next((f for f, st in enumerate(p["state"])
                      if st in ANCHORED), None)
        if first is None:
            late.append((p, len(p["state"])))
        elif first > 0:
            late.append((p, first))
    if not late:
        return []
    worst = max(f for _, f in late)
    return [{
        "kind": "cold_start",
        "frame": 0, "t": 0.0,
        "slots": sorted(p["id"] for p, _ in late),
        "team": None,
        "fix": {"op": "anchor_group", "slots": sorted(p["id"] for p, _ in late)},
        "why": (f"{len(late)} slots were never observed before their first "
                f"appearance; the last of them arrives at frame {worst}. Their "
                "opening positions are a formation assumption, not an observation."),
    }]


def reacquire_surprise(players: list[dict], fps: float) -> list[dict]:
    """A slot that comes back far from where the model said it would be.

    The fourth detector, added because M4 measured the two specified ones missing
    every real switch. The statistic is deliberately the one already on screen:
    the distance from the dead-reckoned position, divided by the sigma the viewer
    was drawing at that moment. A player who reappears outside their own disc is
    news whether the cause is a bad prediction or a different person.
    """
    out = []
    for p in players:
        for f in range(1, len(p["state"])):
            if p["state"][f] not in ANCHORED:
                continue
            if p["state"][f - 1] not in ESTIMATED:
                continue
            prev, now = _xy(p, f - 1), _xy(p, f)
            if prev is None or now is None:
                continue
            sig = float(p["sigma"][f - 1]) or 1e-6
            d = float(np.hypot(*(now - prev)))
            if d < REACQUIRE_MIN_YD or d / sig < REACQUIRE_SIGMAS:
                continue
            # How long had it been estimating?
            gap = 0
            while f - 1 - gap >= 0 and p["state"][f - 1 - gap] in ESTIMATED:
                gap += 1
            out.append({
                "kind": "reacquire_surprise",
                "frame": f, "t": round(f / fps, 3),
                "slots": [p["id"]], "team": p["team"],
                "jump_yd": round(d, 2), "sigma_yd": round(sig, 2),
                "sigmas": round(d / sig, 2),
                "gap_frames": gap, "gap_s": round(gap / fps, 2),
                "fix": {"op": "confirm_or_swap", "slot": p["id"], "f": f},
                "why": (f"{p['id']} was estimated for {gap / fps:.1f} s and came back "
                        f"{d:.1f} yd from where it was predicted — {d / sig:.1f}x the "
                        "sigma it was claiming. Either the dead reckoning was wrong "
                        "or this is a different player."),
            })
    return out


def contested_reacquisition(players: list[dict], fps: float) -> list[dict]:
    """Every re-acquisition after a long gap, as a bounded review queue.

    **This detector used to pick.** It looked for a thin assignment margin, on the
    reasoning that a swap is ambiguous rather than surprising. Round 2 measured
    what that reasoning is worth on the four cases the ghost audit nominated, and
    the answer is: not enough to gate on. Ranked by displacement from the dead-
    reckoned position - the better feature - those four sit 3rd, 9th, 11th and
    13th of the twenty re-acquisitions in this possession, interleaved with six
    the audit never flagged. Any threshold that catches the 5.3 yd case admits
    thirteen of the twenty. And the four were never ground truth; they were the
    output of a worse metric.

    So the detector stops guessing which are swaps and emits **all of them**,
    ranked, each carrying what a human needs to decide: how long the slot was
    estimating, how far the observation landed from the prediction, how contested
    the assignment was, the kit probability it was taken on, and the runner-up it
    beat. Twenty clips is a bounded review. A detector tuned against an unlabelled
    guess is not a detector, it is a preference.

    The tracker marks these samples `provisional` for the same reason: they are
    observations of somebody, and whether it is the same somebody is exactly what
    is being asked.
    """
    out = []
    for p in players:
        reacq = p.get("reacquire")
        assoc = p.get("assoc") or []
        if not reacq:
            continue
        for f, r in enumerate(reacq):
            if not r:
                continue
            a = assoc[f] if f < len(assoc) else None
            jump = r.get("jump_from_prediction_yd")
            rank_key = jump if jump is not None else 0.0
            why = (f"{p['id']} was estimated for {r['gap_s']:.1f} s and came back "
                   f"{jump:.1f} yd from where it was dead-reckoned"
                   if jump is not None else
                   f"{p['id']} was estimated for {r['gap_s']:.1f} s before this")
            if a:
                why += (f", on a margin of {a['margin']:.2f} over "
                        f"{a['alts']} candidate(s), kit P {a['kit_p']:.2f}")
            why += (". Nobody has checked whether it is the same player. If it is "
                    "not, everything after it is the wrong player.")
            out.append({
                "kind": "contested_reacquisition",
                "frame": f, "t": round(f / fps, 3),
                "slots": [p["id"]], "team": p["team"],
                "gap_frames": r["gap_frames"], "gap_s": r["gap_s"],
                "jump_from_prediction_yd": jump,
                "rank_by": round(float(rank_key), 3),
                "candidates": (a or {}).get("alts"),
                "margin_chi2": (a or {}).get("margin"),
                "kit_p": (a or {}).get("kit_p"),
                "branch": (a or {}).get("branch"),
                "runner_up": (a or {}).get("runner_up"),
                "fix": {"op": "confirm_or_swap", "slot": p["id"], "f": f},
                "why": why,
            })
    out.sort(key=lambda r: -r["rank_by"])
    for i, r in enumerate(out):
        r["rank"] = i + 1
    return out


def implied_speed(players: list[dict], fps: float) -> list[dict]:
    """The sanity check docs/05 suggests running on resolved output."""
    out = []
    for p in players:
        for f in range(1, len(p["est"])):
            a, b = _xy(p, f - 1), _xy(p, f)
            if a is None or b is None:
                continue
            v = float(np.hypot(*(b - a))) * fps
            if v > IMPLIED_SPEED_YD_S:
                out.append({
                    "kind": "implied_speed",
                    "frame": f, "t": round(f / fps, 3),
                    "slots": [p["id"]], "team": p["team"],
                    "speed_yd_s": round(v, 1),
                    "fix": None,
                    "why": (f"{p['id']} moved {v:.1f} yd/s between frames {f - 1} "
                            f"and {f}, faster than a person runs."),
                })
    return out


DETECTORS = {
    "identity_exchange": identity_exchange,
    "long_blind_stretch": long_blind_stretch,
    "cold_start": cold_start,
    "reacquire_surprise": reacquire_surprise,
    "contested_reacquisition": contested_reacquisition,
}


def find(doc: dict, *, include_speed: bool = False) -> dict:
    fps = float(doc["possession"]["fps"])
    players = doc["players"]
    issues = []
    for name, fn in DETECTORS.items():
        issues.extend(fn(players, fps))
    # `contested_reacquisition` now emits every re-acquisition after a long gap,
    # which is a superset of what `reacquire_surprise` finds. Two cards for one
    # decision is the annoyance docs/05 groups cold starts to avoid, so the
    # surprise form is kept - it still fires on the fixture, where sigmas are
    # small enough for it to mean something - but only where it says something the
    # other has not already said.
    covered = {(r["slots"][0], r["frame"]) for r in issues
               if r["kind"] == "contested_reacquisition"}
    issues = [r for r in issues
              if r["kind"] != "reacquire_surprise"
              or (r["slots"][0], r["frame"]) not in covered]
    if include_speed:
        issues.extend(implied_speed(players, fps))
    issues.sort(key=lambda r: (r["frame"], r["kind"], r["slots"]))
    counts: dict[str, int] = {}
    for r in issues:
        counts[r["kind"]] = counts.get(r["kind"], 0) + 1
    return {
        "schema": "ultimate-radar/issues@1",
        "possession": doc["possession"]["id"],
        "method": {
            "module": "ur.issues",
            "specified_by": "docs/05-uncertainty.md",
            "identity_exchange": {"near_yd": EXCHANGE_NEAR_YD,
                                  "moved_yd": EXCHANGE_MOVED_YD},
            "long_blind_stretch_s": BLIND_STRETCH_S,
            "contested_reacquisition": {
                "emits": "every re-acquisition the tracker marked provisional",
                "min_gap_s": "ur.track.run REACQ_MIN_GAP_S",
                "ranked_by": "displacement from the dead-reckoned position",
                "changed_in": "round 2",
                "why": "it used to fire only on a thin assignment margin. Measured "
                       "on p0001, neither margin nor displacement separates the "
                       "nominated cases from the rest - any threshold catching the "
                       "smallest admits most of the set, and none of them is "
                       "labelled. So the whole set is emitted for review and the "
                       "threshold is set from human labels, not before them. See "
                       "docs/25-round-2-ghost-audit.md R4.",
            },
            "reacquire_surprise": {"sigmas": REACQUIRE_SIGMAS,
                                   "min_yd": REACQUIRE_MIN_YD,
                                   "added_in": "M5",
                                   "why": "M4 measured the two specified detectors "
                                          "catching 0 of 2 real identity switches, "
                                          "because both happened across a dropout "
                                          "rather than a single-frame crossing"},
        },
        "counts": counts,
        "issues": issues,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="ur.issues")
    p.add_argument("target", help="a possession working dir, or a possession.json")
    p.add_argument("--out", default=None)
    p.add_argument("--speed", action="store_true",
                   help="also run the implied-speed sanity check")
    a = p.parse_args(argv)

    t = Path(a.target)
    src = t / "possession.json" if t.is_dir() else t
    doc = json.loads(src.read_text(encoding="utf-8"))
    res = find(doc, include_speed=a.speed)
    out = Path(a.out) if a.out else (t / "issues.json" if t.is_dir()
                                     else src.with_name("issues.json"))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=1) + chr(10), encoding="utf-8")

    print(f"[issues] {src}")
    for k, v in sorted(res["counts"].items()):
        print(f"    {k:>22}  {v}")
    if not res["counts"]:
        print("    (none)")
    print(f"[issues] wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
