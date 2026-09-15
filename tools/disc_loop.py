"""The tag-score-ask loop from `docs/27` and `docs/08` open question 7.

    python -m tools.disc_loop work/p0001

One turn of the loop, from whatever tags exist right now:

  1. **Re-solve** with the human's tags as hard constraints (`ur.disc` already
     does this; this runs it).
  2. **Score** what came out against tags the solver was not given
     (`tools.disc_score`), which is the only measurement here that can be wrong
     in the direction of saying the model is bad.
  3. **Decide whether to stop**, against the threshold that scoring calibrated -
     not against a number chosen here.
  4. **Ask for the next tag** where the solver's own margin is thinnest, as a
     link straight to that moment in the viewer.

The point of the loop is that step 4 gets shorter every time. Tagging every
throw of every possession is twenty keystrokes forever; asking only where the
solver is unsure is a cost that falls as the model improves.

## The two things that would make this dishonest, and what stops them

**Calibrating the stopping rule against the physics checks.** They can say a
sequence is implausible and can never say a plausible one is right, so a
threshold read off them would be a threshold read off nothing. The threshold
comes from `tools.disc_score`'s held-out curve, and when there are too few
held-out frames to fit one, this refuses to stop rather than stopping on a
guess.

**Training on its own output.** A confident wrong holder fed back as a
constraint is how this fails silently, and it is the same shape as the withdrawn
`identity_switches_caught: "2 of 2"` in round 2 - a detector agreeing with the
analysis that produced it. So the only constraints `ur.disc` ever accepts are
events with `source: "human"`, and this tool never writes an event file. It
asks; a person answers.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from tools import disc_score

VIEWER = "https://bmccall17.github.io/ultimate-radar/"


def turn(work: Path, *, every: int = 3, target: float = 0.9) -> dict:
    from ur import disc

    disc.build(work, verbose=False)
    d = json.loads((work / "disc.json").read_text(encoding="utf-8"))
    diag = d["diagnostics"]
    sc = disc_score.score(work, every=every)

    thr = (sc.get("calibration") or {}).get("threshold_yd")
    marg = [s.get("margin_yd") for s in d["samples"]]
    tagged = [s["source"] == "human" for s in d["samples"]]
    untagged = [m for m, t in zip(marg, tagged) if not t and m is not None]

    out = {
        "possession_id": d["possession_id"],
        "human_tagged_frames": diag["human_tagged_frames"],
        "frames": diag["frames"],
        "score": sc,
        "threshold_yd": thr,
        "target_accuracy": target,
    }
    if thr is None:
        out["stop"] = False
        out["why"] = ("no calibrated threshold yet - "
                      + ((sc.get("calibration") or {}).get("why")
                         or sc.get("verdict")
                         or "the held-out curve never reaches the target accuracy"
                         ).rstrip(".")
                      + ". Stopping now would be stopping on a guess.")
    else:
        below = [m for m in untagged if m < thr]
        out["frames_below_threshold"] = len(below)
        out["confidence"] = round(1 - len(below) / max(1, len(untagged)), 4)
        out["stop"] = not below
        out["why"] = (
            f"every untagged frame's margin is at or above {thr} yd, which is "
            f"where held-out tags say the solver is {target:.0%} right"
            if not below else
            f"{len(below)} of {len(untagged)} untagged frames sit below {thr} yd")
    # With timing-only tags the useful question is not "which frame" but "who
    # holds this span" - `ur/spans.py` ranks them by its own margin, and one
    # answer settles a whole span rather than a frame.
    sp = work / "spans.json"
    if sp.exists():
        doc = json.loads(sp.read_text(encoding="utf-8"))
        if doc.get("ask_next"):
            out["ask_next"] = doc["ask_next"]
            out["ask_next_kind"] = "span"
            return out
    out["ask_next"] = diag["ask_next"]
    out["ask_next_kind"] = "frame"
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="tools.disc_loop")
    p.add_argument("work")
    p.add_argument("--every", type=int, default=3)
    p.add_argument("--target", type=float, default=0.9)
    p.add_argument("--url", default=VIEWER,
                   help="viewer base URL, for the 'tag this moment' links")
    a = p.parse_args(argv)
    work = Path(a.work)
    r = turn(work, every=a.every, target=a.target)

    print(f"[loop] {r['possession_id']}: {r['human_tagged_frames']} of "
          f"{r['frames']} frames carry a human tag")
    sc = r["score"]
    if "held_out" in sc:
        print(f"[loop] held-out accuracy {sc['held_out']['mean_frame_accuracy']} "
              f"(spread {sc['held_out']['spread_across_folds']}), "
              f"unaided {sc['unaided']['frame_accuracy']}")
    else:
        print(f"[loop] not scorable yet: {sc.get('verdict')}")
    print(f"[loop] threshold {r['threshold_yd']} yd, "
          f"confidence {r.get('confidence')}")
    print(f"[loop] {'STOP - ' if r['stop'] else 'KEEP GOING - '}{r['why']}")
    if not r["stop"]:
        print("")
        print("  Answer these next - select the player and press `c`, which "
              "turns a guess into a hard constraint:")
        for q in r["ask_next"]:
            if r.get("ask_next_kind") == "span":
                print(f"    t={q['t']:>6.2f}s  {q['question']}"
                      f"  (the solver says {q['holder_guessed']}, margin "
                      f"{q['margin_yd']} yd)")
                print(f"              {a.url}#t={q['t']}")
            else:
                print(f"    t={q['t']:>6.2f}s  margin {q['margin_yd']:>7.3f}"
                      f" yd   {a.url}#t={q['t']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
