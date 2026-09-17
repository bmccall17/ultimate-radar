"""The check that a repair pass cannot improve the tracker's own score.

    python -m tools.human_positions            # every possession in work/
    python -m tools.human_positions work/p0003

`anchor` produces `confirmed`, and CONTEXT.md is blunt about what that means:
every `confirmed` frame is human-sourced. So a metric that counts `confirmed`
frames rewards the tracker for work a person did. #8 names three places this
would show up - per-player recall, the sigma containment sample, and the span
solver's grade - and asks for a named check that none of them has been reached.

`ur/human.py` is the mechanism: every frame a correction created **or moved**
comes back out of `human`, and `blind()` hands a grader a document those frames
are missing from. This module is the check that nobody has forgotten to call it.

## How it can fail

Trusting that three call sites still carry a `blind()` is exactly the kind of
thing that rots, and a check that read the source for the word would pass on a
call that had been commented out. So this runs the graders instead:

1. Build a **probe keyframe** - every slot and the disc placed a fixed distance
   away, on a spread of frames across the possession, through `ur.resolve` so it
   goes in by exactly the route a person's save does. Nothing is written; the
   probe exists only inside this process.
2. Run each grader three times over the probed possession: with its exclusion
   switched off, as it normally runs, and on `blind()` of the document.
3. Require the last two to be **identical**, and require the first to differ
   from them - otherwise the probe never reached that grader and the agreement
   says nothing.

A grader that blinds its input answers the same as the blinded document, because
`blind` is idempotent. A grader that does not sees the probe's twelve-yard
displacement and separates from it. Delete any of the three `HU.blind` calls and
this row goes red on the next run, which is the property a gate is for.

The third run is what stops this being a row that cannot fail. Per-player recall
asks for `observed`, an anchor produces `confirmed`, and `docs/05`'s ramp never
moves the bracketing observations - so the probe cannot reach it at all, and its
agreement is structural rather than tested. The run reports that as
`unreachable` and does not count it. AD-11.

The probe is deterministic - a fixed displacement on a fixed stride, no RNG -
because AGENTS rule 6 says a number that moves between runs is not a measurement.

## What it does not claim

It does not say the graders are *right*, only that a person's hand is not in
them. And it says nothing about the artefact: a correction is supposed to make
the published page better, and it does. `blind` is a grading view and never a
publishing one.
"""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

from tools import checks as C
from ur import grading as GV
from ur import human as HU
from ur import provenance as PV
from ur import resolve as R

# Far enough that nothing could mistake it for noise: the recall gate matches at
# 1.5 yd and the sigma discs are under a yard, so a leak of this size cannot hide
# inside a rounding.
PROBE_YD = 12.0
# How many keyframes the probe lays down. Enough that the ramps between them
# reach the whole possession, so a grader reading any part of it sees the probe.
PROBE_KEYFRAMES = 8

# Where each grader's ground truth lives. A possession with no hand labels cannot
# exercise the first two at all - there is nothing to score against - so the row
# says which graders it actually ran rather than quietly reporting a pass over
# checks that never happened.
RECALL_LABELS = Path("eval/m3/team_labels.json")
RECALL_M2 = Path("eval/m2/labels.json")
FOOT_EVAL = Path("eval/m4")


def probe_log(doc: dict) -> dict:
    """A keyframe of anchors on every slot and the disc, at a fixed stride.

    Placed through the correction log rather than by writing positions, so what
    is being tested is the route a person's save actually takes: the same
    `anchor` op, the same `docs/05` ramp, the same marks left behind.
    """
    n = int(doc["possession"]["frames"])
    stride = max(1, n // PROBE_KEYFRAMES)
    frames = list(range(0, n, stride))
    width = float(doc["field"]["width_yd"]) if doc.get("field") else 53.333
    corrections = []
    for k, f in enumerate(frames):
        for p in doc["players"]:
            xy = p["est"][f] or [60.0, width / 2.0]
            # Wrapped inside the field rather than clamped: a clamp would pile
            # several slots onto the sideline, and an anchor on top of another
            # anchor tests less than one beside it.
            corrections.append({"id": f"probe-{k}-{p['id']}",
                                "keyframe": f"probe-{k}",
                                "op": "anchor", "slot": p["id"], "f": f,
                                "xy": [xy[0], (xy[1] + PROBE_YD) % width]})
        if doc.get("disc") and doc.get("disc_meta"):
            d = doc["disc"][f]
            if d:
                corrections.append({"id": f"probe-{k}-disc",
                                    "keyframe": f"probe-{k}",
                                    "op": "anchor", "slot": R.DISC, "f": f,
                                    "xy": [d[0], (d[1] + PROBE_YD) % width]})
    log = R.empty_log(doc["possession"].get("id", "probe"))
    log["corrections"] = corrections
    return log


def probed(doc: dict) -> dict:
    """The possession with the probe keyframes applied. Nothing is written."""
    return R.resolve(copy.deepcopy(doc), probe_log(doc), verbose=False)


def _recall(work: Path, doc: dict, blind: bool = True):
    from tools import m4_recall
    r = m4_recall.measure(work, RECALL_LABELS, RECALL_M2, poss=doc, blind=blind)
    return r["recall_at_threshold"]


def _containment(work: Path, doc: dict, blind: bool = True):
    from tools import m4_foot
    r = m4_foot.score(work, FOOT_EVAL, poss=doc, write=False, blind=blind)
    return (r["sigma_gate"]["inside_count"], r["position_gate"]["median_yd"])


def _solver(work: Path, doc: dict, blind: bool = True):
    from tools import gates
    ev = json.loads((work / "events.json").read_text(encoding="utf-8"))
    r = gates.grade_spans(work, doc, ev, blind=blind)
    return None if r is None else (r[0], r[1], r[3])


def graders(work: Path, doc: dict) -> dict:
    """The graders that have ground truth for this possession, by name."""
    out = {}
    if (work / "events.json").exists():
        out["the solver grade"] = _solver
    # The hand labels for these two are p0001's frames and p0001's detection
    # indices. Pointing them at another possession would not measure a weaker
    # thing, it would index into the wrong file, so they run where they belong.
    if work.name == "p0001" and RECALL_LABELS.exists() and RECALL_M2.exists():
        out["the recall denominator"] = _recall
    if work.name == "p0001" and (FOOT_EVAL / "foot_labels.json").exists():
        out["the sigma containment sample"] = _containment
    return out


def contaminated(events: dict, ids: list[str]) -> dict:
    """The tags with a **wrong** name on every one that currently grades.

    The identity half of the probe, and the same argument as `probe_log` makes
    about positions: put something in that the grader must not be reading, and
    require the number not to follow. Here the something is the defect itself -
    a name the tracker supplied - so a grader that skips `ur.provenance` sees a
    holder it was never meant to be scored against and separates.

    **It mangles the names that are already excluded, not the ones that grade**,
    and getting that backwards is the whole reason this needed a second pass.
    Contaminating a *grading* tag takes it out of the sample, so the grade moves
    for a perfectly legitimate reason and the probe reports a leak that is not
    one. Contaminating an *excluded* tag must change nothing, because that tag
    was never in the sample - which is exactly the claim #4 makes, tested
    directly.

    A tag that already grades is left alone, and so is a timing-only one.

    The wrong name is the **next slot round the list**, not a random one: AGENTS
    rule 6 says a number that moves between runs is not a measurement, and a
    probe that shuffles is a probe whose failures nobody can reproduce.
    """
    out = dict(events)
    out["events"] = []
    for e in events.get("events") or ():
        named = e.get("player")
        if PV.grades(e) or named is None or named not in ids or len(ids) < 2:
            out["events"].append(e)
            continue
        wrong = ids[(ids.index(named) + 1) % len(ids)]
        out["events"].append({**e, "player": wrong, PV.KEY: PV.TRACKER})
    return out


def _offence(doc: dict) -> list[str]:
    """The slots a holder can be, which is the set a wrong name comes from."""
    off = doc["possession"]["offense"]
    return [p["id"] for p in doc["players"] if p["team"] == off]


def _same(a, b) -> bool:
    """Compare two graders' answers, NaN included.

    A NaN never equals itself, so a plain `==` reports a difference between two
    runs that produced the same empty sample - a red row for a check that
    actually held. Rendering both sides and comparing the text says what a
    reader means by "the same number", which is the claim being made.
    """
    return (json.dumps(a, sort_keys=True, default=repr)
            == json.dumps(b, sort_keys=True, default=repr))


def audit(work: Path) -> dict:
    """Which graders ran, how each one came out, and what the probe could reach.

    Three verdicts, and the difference between the last two is the whole reason
    this runs each grader twice rather than once:

    - **leaked** - the grader's answer moved with the hand-placed positions in.
      The failure this gate exists for.
    - **excluded** - the probe moved what the grader reads, and the grader
      answered the same anyway. The exclusion did work.
    - **unreachable** - the probe could not change this grader's input at all,
      so the pass says nothing about the exclusion. Per-player recall is here:
      it asks for `observed`, an anchor produces `confirmed`, and docs/05's ramp
      never touches the bracketing observations - so a correction cannot enter
      it whatever `blind` does. Reporting that as a tested pass would be a row
      that cannot fail wearing a gate's clothes (AD-11).
    """
    # Unblinded, because the probe is laid down on top of it and each grader is
    # then run with its own exclusion on and off. Through the view all the same.
    doc = GV.load(work, blinded=False)[0]
    with_probe = probed(doc)
    verdict = {}
    for name, fn in graders(work, doc).items():
        raw = fn(work, with_probe, blind=False)      # what a leak would look like
        kept = fn(work, with_probe)                  # what the grader answers
        clean = fn(work, HU.blind(with_probe))       # with the hand off entirely
        if not _same(kept, clean):
            verdict[name] = ("leaked", f"{kept} vs {clean}")
        elif _same(raw, clean):
            verdict[name] = ("unreachable", "the probe cannot change its input")
        else:
            verdict[name] = ("excluded", f"{raw} unblinded, {kept} as run")
    marked = sum(len(HU.touched(p)) for p in with_probe["players"])
    return {"possession": work.name, "verdict": verdict,
            "ran": list(verdict),
            "leaked": [f"{k} ({v[1]})" for k, v in verdict.items()
                       if v[0] == "leaked"],
            "excluded": [k for k, v in verdict.items() if v[0] == "excluded"],
            "probe_frames": marked}


def identity_verdict(work: Path, doc: dict,
                     ev: dict | None = None) -> tuple[str, str] | None:
    """Can a name the tracker supplied move the span grade? #4.

    Positions are held blinded throughout, so the only thing that varies is the
    name. Four runs, and the fourth is what makes this a check rather than a
    row that cannot fail:

    - **clean** - the real tags, grader blinding on. The baseline.
    - **kept** - the mangled tags, grader blinding on. Must equal `clean`.
    - **base** / **raw** - the real and the mangled tags with no name blinding.
      They must differ, or the probe reached nothing.

    `kept` differing from `clean` is the failure: a name the tracker supplied
    moved a number. `raw` agreeing with `base` means the mangling was invisible
    even unblinded, so the agreement above is structural and says nothing
    (AD-11).

    **On the corpus today this passes, and it is not vacuous.** Every tag is
    tracker-sourced, so every one gets a wrong name; the blinded grade does not
    move and the unblinded one does. The exclusion is demonstrated. What is
    missing is ground truth, and that shows up where it belongs - in
    `span identity accuracy` reading 0/0.
    """
    if ev is None:
        if not GV.has_events(work):
            return None
        ev = GV.read_events(work)
    from tools import gates
    positions_only = HU.blind(doc)          # held still, so only the name varies
    dirty = contaminated(ev, _offence(doc))
    base = gates.grade_spans(work, positions_only, ev, blind=False)
    raw = gates.grade_spans(work, positions_only, dirty, blind=False)
    kept = gates.grade_spans(work, doc, dirty)
    clean = gates.grade_spans(work, doc, ev)

    if not _same(kept, clean):
        return ("leaked", f"{kept} vs {clean}")
    # `base` is the fourth run and the whole reason this is a check. Comparing
    # `raw` against `clean` instead - the first version of this - compares
    # "names in" against "names out", which differ for a reason that has nothing
    # to do with the probe. Every possession came back `excluded` and the row was
    # green while `contaminated` had changed not one tag. A row that cannot fail
    # wearing a gate's clothes, in the ticket about exactly that (AD-11).
    if _same(raw, base):
        return ("unreachable", "the probe changed no name a grader could see: "
                               "no tag here carries provenance, so none grades")
    return ("excluded", f"{raw} contaminated and unblinded, {kept} as run")


def check(works: list[Path]) -> dict:
    """One gate over every possession, and the list of graders it reached."""
    out: dict = {"possession": "human positions (the repair-mode trap)",
                 "checks": []}
    ran: list[str] = []
    leaked: list[str] = []
    excluded: list[str] = []
    for work in works:
        if not GV.has(work):
            continue
        r = audit(work)
        ran += [f"{r['possession']}: {g}" for g in r["ran"]]
        leaked += [f"{r['possession']}: {g}" for g in r["leaked"]]
        excluded += [f"{r['possession']}: {g}" for g in r["excluded"]]
    out["checks"].append(C.gate(
        "no human position in a metric",
        # `excluded` rather than `ran`: a run where the probe reached nothing
        # proves nothing, and this row has to be able to fail to be a gate.
        not leaked and bool(excluded),
        (f"{len(excluded)} of {len(ran)} grader run(s) saw the probe and "
         f"excluded it" if not leaked
         else f"{len(leaked)} leaked: {'; '.join(leaked)}")
        + ("" if excluded else " - the probe reached no grader, so nothing here "
                               "was tested"),
        "every grader answers the same with and without hand-placed positions",
        "a grader is reading positions a person placed, so the tracker scores "
        "better the more of the possession somebody fixes. Put the "
        "`ur.human.blind` back on whichever one is named above - #8"))

    # The same argument about the other half of what a person supplies. #4.
    id_leaked: list[str] = []
    id_excluded: list[str] = []
    id_ran: list[str] = []
    for work in works:
        if not GV.has(work):
            continue
        v = identity_verdict(work, GV.load(work, blinded=False)[0])
        if v is None:
            continue
        id_ran.append(work.name)
        if v[0] == "leaked":
            id_leaked.append(f"{work.name}: {v[1]}")
        elif v[0] == "excluded":
            id_excluded.append(work.name)
    out["checks"].append(C.gate(
        "no contaminated identity in a metric",
        not id_leaked and bool(id_excluded),
        (f"{len(id_excluded)} of {len(id_ran)} possession(s) had a mangled name "
         f"refused" if not id_leaked
         else f"{len(id_leaked)} leaked: {'; '.join(id_leaked)}")
        + ("" if id_excluded else " - the probe reached no grader, so nothing "
                                  "here was tested"),
        "every grader answers the same with and without a name the tracker "
        "supplied",
        "declare what carried each tagged identity - the footage, or the "
        "viewer's label - in events.json. Until then no span may be scored "
        "against, which is the point: a name read off the tracker cannot grade "
        "the tracker. #4"))
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="tools.human_positions")
    p.add_argument("work", nargs="*", default=None)
    a = p.parse_args(argv)
    works = ([Path(w) for w in a.work] if a.work
             else sorted(q for q in Path("work").iterdir()
                         if GV.has(q)))
    for work in works:
        if not GV.has(work):
            continue
        r = audit(work)
        print(f"  {r['possession']}  probe marked {r['probe_frames']} slot-frames")
        for g, (how, detail) in r["verdict"].items():
            print(f"      {how:<12} {g:<32} {detail}")
        if not r["ran"]:
            print("      no grader has ground truth for this possession")
    rep = check(works)
    print()
    for c in rep["checks"]:
        print(C.render(c))
    return C.tally([rep]).exit_code


if __name__ == "__main__":
    raise SystemExit(main())
