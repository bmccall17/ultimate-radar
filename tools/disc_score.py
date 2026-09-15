"""Score the holder inference against a human's tags, holding some of them back.

    python -m tools.disc_score work/p0001 --out eval/m9

`docs/27` establishes that the unaided inference is wrong, and establishes it
against *physics* - throws that alternate direction, flights stuck on the
duration floor. That is a check that can only ever say a sequence is
implausible. It cannot say a plausible one is right, and it cannot say **which**
frames are wrong. Tags can.

So this is the first thing in the project that scores a holder sequence against
truth, and everything about it is arranged so the number cannot flatter itself:

- **The truth is only the human's tags.** A frame no tag speaks for is not
  scored, in either direction. There is no filling in.
- **Held-out tags are withheld from the solver, not just from the scoring.** The
  solver is re-run with a subset as hard constraints and never sees the rest.
  Scoring a solver on a constraint you handed it measures nothing.
- **Every third tag, over all three folds.** With a dozen tags a single split is
  a coin toss; rotating the residue and averaging is nearly free and says how
  much the split mattered. The spread between folds is reported, because a mean
  over three folds that disagree is not a measurement.
- **Only `source: "human"` tags are ever used as constraints.** `docs/27`'s
  second trap - do not let the loop train on its own output - is enforced here
  rather than remembered: a `suggested` or `example` event is not truth and is
  not a constraint. `events@1` names the three sources for this reason.

## Two numbers, and they answer different questions

**Unaided** re-runs the inference with *no* tags at all and scores it on every
frame the tags determine. That is the honest version of the negative result in
`docs/27`, and it is the number to quote when asked whether holder inference
works.

**Held-out** is the loop's number: two thirds of the tags in, the other third
scored. It is what tells you whether a human's cost per possession can fall -
if it is high, the next possession needs fewer tags.

## And a calibration curve, which is the point of the loop

Each scored frame carries the solver's own min-marginal margin in yards
(`ur.disc.margins`). Grouping the held-out frames by margin gives accuracy as a
function of the solver's confidence - the only honest way to choose a stopping
threshold, because the physics checks cannot supply one. The curve is reported
whether or not it is monotone; a margin that does not predict accuracy is a
finding about the margin.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from ur import disc


def human_events(events: dict) -> list[dict]:
    """Tags a person made. Nothing else is truth and nothing else is a constraint."""
    return sorted((e for e in events.get("events", [])
                   if e.get("source") == "human"
                   and e.get("type") in ("throw", "catch", "possession_start")),
                  key=lambda e: float(e["t"]))


def solve(doc: dict, cost: np.ndarray, ids: list[str],
          given: list[dict]) -> tuple[list[int], np.ndarray, list[int | None]]:
    """Re-run the inference with `given` as hard constraints, and nothing else."""
    none = len(ids)
    tagged = disc.from_events(doc, {"events": given}, ids)
    forced = cost.copy()
    for f, who in enumerate(tagged):
        if who is None:
            continue
        keep = forced[f, who]
        forced[f] = np.inf
        forced[f, who] = 0.0 if not np.isfinite(keep) else min(keep, 0.0)
    return disc.viterbi(forced, none), disc.margins(forced, none), tagged


def score(work: Path, *, every: int = 3) -> dict:
    doc = json.loads((work / "possession.json").read_text(encoding="utf-8"))
    ev = json.loads((work / "events.json").read_text(encoding="utf-8"))
    fps = float(doc["possession"]["fps"])
    ids, cost, _ = disc.emission_costs(doc)
    none = len(ids)
    label = {i: k for i, k in enumerate(ids)}
    label[none] = "in flight"

    tags = human_events(ev)
    truth = disc.from_events(doc, {"events": tags}, ids)
    n_truth = sum(1 for t in truth if t is not None)
    out: dict = {
        "possession_id": doc["possession"]["id"],
        "human_tags": len(tags),
        "frames": len(truth),
        "frames_the_tags_determine": n_truth,
        "note": "Truth is the tags and only the tags. A frame no tag speaks for "
                "is not scored in either direction.",
    }
    named = [e for e in tags if e.get("player")]
    out["human_tags_naming_a_player"] = len(named)
    if len(tags) >= 4 and not named:
        # The normal case now, and it is not a failure - it is the tagging design
        # working. Timing-only tags fix when the disc was in flight, which is what
        # `ur/spans.py` needs, and they contain no identity, which is what a score
        # needs. Saying "0.0" here would be scoring the solver against nothing.
        out["verdict"] = (
            f"not scorable: {len(tags)} tags, none naming a player. They fix the "
            "timing, which is what ur.spans solves from; scoring needs the other "
            "half. Name the receiver on a throw or two - select the player, then "
            "press `c` - and those become the held-out truth. Start with the "
            "throws ur.spans is least sure of; `spans.json` ranks them.")
        return out
    if len(tags) < 4:
        out["verdict"] = ("not scorable: fewer than four human tags. Two throws "
                          "and two catches is the least that leaves anything to "
                          "hold out.")
        return out

    # ---- unaided: the inference with nothing given, scored on every tagged frame
    path0, marg0, _ = solve(doc, cost, ids, [])
    idx = [f for f, t in enumerate(truth) if t is not None]
    hit0 = [path0[f] == truth[f] for f in idx]
    out["unaided"] = {
        "scored_frames": len(idx),
        "frame_accuracy": round(float(np.mean(hit0)), 4),
        "held_frame_accuracy": _held_only(truth, path0, none, idx),
        "confusion_top": _confusion(truth, path0, idx, label),
        "what_it_means": "the holder inference with no human input at all, "
                         "scored against a person for the first time",
    }

    # ---- held out: every `every`-th tag, rotating the residue
    folds = []
    for r in range(every):
        given = [e for i, e in enumerate(tags) if i % every != r]
        held = [e for i, e in enumerate(tags) if i % every == r]
        path, marg, given_map = solve(doc, cost, ids, given)
        # A frame counts only if the full tag set determines it and the reduced
        # set does not. Scoring a frame the solver was handed measures nothing.
        fs = [f for f in idx if given_map[f] is None]
        hits = [path[f] == truth[f] for f in fs]
        folds.append({
            "residue": r, "given_tags": len(given), "held_tags": len(held),
            "scored_frames": len(fs),
            "frame_accuracy": round(float(np.mean(hits)), 4) if fs else None,
            "held_frame_accuracy": _held_only(truth, path, none, fs),
            "margins": [(float(marg[f]) if np.isfinite(marg[f]) else None,
                         bool(path[f] == truth[f])) for f in fs],
        })
    acc = [f["frame_accuracy"] for f in folds if f["frame_accuracy"] is not None]
    out["held_out"] = {
        "every": every,
        "folds": [{k: v for k, v in f.items() if k != "margins"} for f in folds],
        "mean_frame_accuracy": round(float(np.mean(acc)), 4) if acc else None,
        "spread_across_folds": (round(float(max(acc) - min(acc)), 4)
                                if len(acc) > 1 else None),
        "what_it_means": "two thirds of the tags given as hard constraints, the "
                         "other third withheld from the solver and scored",
    }

    # ---- the calibration curve
    pairs = [(m, ok) for f in folds for m, ok in f["margins"] if m is not None]
    out["calibration"] = _calibrate(pairs)
    out["calibration_note"] = (
        "Accuracy against held-out tags, grouped by the solver's own min-marginal "
        "margin in yards. This is the only honest source of a stopping threshold: "
        "the physics checks in ur.disc can say a sequence is implausible and can "
        "never say a plausible one is right.")
    return out


def _held_only(truth, path, none, frames) -> float | None:
    """Accuracy on frames where somebody is holding it, not in flight.

    `in flight` is a large share of a tagged possession and is the easy half:
    a flight is bracketed by two tags a fraction of a second apart. Reporting it
    mixed in with the holders inflates the number.
    """
    fs = [f for f in frames if truth[f] != none]
    if not fs:
        return None
    return round(float(np.mean([path[f] == truth[f] for f in fs])), 4)


def _confusion(truth, path, frames, label) -> list[dict]:
    got: dict[tuple, int] = {}
    for f in frames:
        if path[f] != truth[f]:
            k = (label[truth[f]], label[path[f]])
            got[k] = got.get(k, 0) + 1
    top = sorted(got.items(), key=lambda kv: -kv[1])[:6]
    return [{"truth": a, "inferred": b, "frames": n} for (a, b), n in top]


def _calibrate(pairs: list[tuple[float, bool]], bins: int = 4) -> dict:
    if len(pairs) < 8:
        return {"rows": [], "threshold_yd": None,
                "why": f"only {len(pairs)} held-out frames; a curve fitted to "
                       "that would be a shape, not a calibration"}
    pairs = sorted(pairs)
    per = max(1, len(pairs) // bins)
    rows = []
    for i in range(0, len(pairs), per):
        chunk = pairs[i:i + per]
        if len(chunk) < 3:
            if rows:
                rows[-1]["n"] += len(chunk)
            continue
        rows.append({"margin_lo_yd": round(chunk[0][0], 2),
                     "margin_hi_yd": round(chunk[-1][0], 2),
                     "n": len(chunk),
                     "accuracy": round(sum(1 for _, ok in chunk if ok)
                                       / len(chunk), 3)})
    # The stopping threshold: the lowest margin above which every bin is at
    # least 90 % right. Not tuned - read off the curve, and None if no bin
    # reaches it, which is the honest answer when the margin does not separate.
    thr = None
    for i, r in enumerate(rows):
        if all(x["accuracy"] >= 0.9 for x in rows[i:]):
            thr = r["margin_lo_yd"]
            break
    return {"rows": rows, "threshold_yd": thr, "target_accuracy": 0.9,
            "monotone": all(rows[i]["accuracy"] <= rows[i + 1]["accuracy"] + 1e-9
                            for i in range(len(rows) - 1))}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="tools.disc_score")
    p.add_argument("work")
    p.add_argument("--every", type=int, default=3, help="hold out every Nth tag")
    p.add_argument("--out", default=None, help="directory for the JSON")
    a = p.parse_args(argv)
    work = Path(a.work)
    res = score(work, every=a.every)

    print(f"[disc_score] {res['possession_id']}: {res['human_tags']} human tags, "
          f"determining {res['frames_the_tags_determine']} of {res['frames']} frames")
    if "verdict" in res:
        print(f"[disc_score] {res['verdict']}")
        return 1
    u = res["unaided"]
    print(f"\n  UNAIDED (no tags given, {u['scored_frames']} frames scored)")
    print(f"    frame accuracy          {u['frame_accuracy']:.3f}")
    print(f"    on frames somebody holds it  {u['held_frame_accuracy']}")
    for c in u["confusion_top"]:
        print(f"      truth {c['truth']:>10}  inferred {c['inferred']:>10}  "
              f"{c['frames']} frames")
    h = res["held_out"]
    print(f"\n  HELD OUT (every {h['every']}rd tag, {len(h['folds'])} folds)")
    for f in h["folds"]:
        print(f"    fold {f['residue']}: {f['given_tags']} given, "
              f"{f['held_tags']} held, {f['scored_frames']} frames, "
              f"accuracy {f['frame_accuracy']}  "
              f"(holders only {f['held_frame_accuracy']})")
    print(f"    mean {h['mean_frame_accuracy']}  "
          f"spread across folds {h['spread_across_folds']}")
    c = res["calibration"]
    print("\n  CALIBRATION (accuracy by the solver's own margin)")
    if not c["rows"]:
        print(f"    {c['why']}")
    for r in c["rows"]:
        print(f"    {r['margin_lo_yd']:>7.2f} - {r['margin_hi_yd']:>7.2f} yd  "
              f"n={r['n']:>4}  accuracy {r['accuracy']:.3f}")
    print(f"    stopping threshold: {c.get('threshold_yd')} yd "
          f"(for {c.get('target_accuracy')} accuracy)")

    if a.out:
        out = Path(a.out)
        out.mkdir(parents=True, exist_ok=True)
        dest = out / f"disc_score_{res['possession_id']}.json"
        dest.write_text(json.dumps(res, indent=2) + "\n", encoding="utf-8")
        print(f"\n[disc_score] -> {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
