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

Exit code is non-zero if anything fails, so it can sit in front of a publish -
and **only a gate can fail**. The run prints two totals, because it carries two
kinds of row: gates, which hold a measurement to a threshold and return a
verdict, and measurements, which report a number and claim nothing. Counting the
second kind into a green total inflates the number a reader trusts, and `docs/31`
closes an issue when a named check flips to PASS, which a row that cannot flip
never will. `tools/checks.py` holds the distinction; `docs/30` section 3 names
every measurement and why it has no threshold today.

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

from tools import checks as C
from tools import human_positions as HP
from ur import human as HU

_PID = __import__("re").compile(r"p\d{4}")

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


# Which ticket owns each gate. The convention, written down in docs/31:
# **an issue closes when a named check here flips to PASS**, never on opinion.
# So a failing check has to be able to say whose job it is, and a ticket that
# cannot name its check is a ticket without a definition of done - which is what
# the `needs-gate` label means.
#
# Keys match the START of a check's name, because the direction checks are named
# per quarter and the site checks are prefixed with the possession.
ISSUE = {
    "span identity accuracy": 1,
    "margin predicts correctness": 2,
    "Q1: opposite teams": 5,
    "Q2: opposite teams": 5,
    "Q3: opposite teams": 5,
    "Q4: opposite teams": 5,
    # Both of these can only fail once somebody has confirmed a direction, and
    # making the declaration agree with the confirmation is the last step of
    # landing AD-10 rather than separate work - so they sit with #5 rather than
    # getting a ticket that would have nothing in it but a clip.json edit.
    "declared direction holds": 5,
    "confirmations are readable": 5,
    # A measurement, not a gate: an unconfirmed quarter is a queue, not a
    # defect. Mapped so the ticket is findable the day it becomes failable.
    "...quarters confirmed": 5,
    # The unnamed span is the jersey-#20 player, who has no correct slot
    # anywhere in p0003 - the same root cause as #4, not a separate problem.
    "disc not lost for long": 4,
    # Likewise: a disc drawn on a slot whose marker has wandered onto somebody
    # else is the tracker losing the player, which is #4. The disc stage only
    # decides whether to publish the mistake.
    "no disc drawn on a guessed position": 4,
    # A measurement today, so it never fails and never shows a number here -
    # the mapping is so the ticket is findable the day it gets a threshold.
    "...longest blind stretch": 8,
    # Repair mode's own gate: the one thing that has to be true before a person
    # is invited to hand-place fourteen markers and a disc.
    "no human position in a metric": 8,
    # A name settled by elimination rendering at the strongest state the format
    # has is the disc stage's own doing, not the tracker's: the flag is in the
    # tag and the stage dropped it.
    "no confirmed disc from an inferred name": 15,
    # The two site checks that read the rendered sentence. docs/30 § 2.7.
    "no unmeasured percentage printed": 11,
    "an unmeasured page says so": 11,
    # The third rendered-page check, and the same shape of defect one pane over:
    # the data carried the tags and the list never read them.
    "published tags show on load": 12,
    # The fourth, and the only one about what the page refuses rather than what
    # it says. Same pane, same half-blindness: the guard never read D.events.
    "a self-pass is always refused": 25,
    "median roster in shot": 6,
    "frames with nothing at all": 6,
    "camera motion is possible": 6,
}
ISSUE_URL = "https://github.com/bmccall17/ultimate-radar/issues"


def _issue(name: str) -> int | None:
    bare = name.split(": ", 1)[1] if name[:1] == "p" and ": " in name else name
    for k, v in ISSUE.items():
        if bare.startswith(k) or name.startswith(k):
            return v
    return None


def _probe_centre(cal: dict) -> np.ndarray:
    return np.array([cal["camera"]["image_w"] / 2.0,
                     cal["camera"]["image_h"] * 0.55, 1.0])


def check_possession(work: Path) -> dict:
    out: dict = {"possession": work.name, "checks": []}

    def add(name, ok, got, want, note=""):
        """A gate: it can fail, and it counts in the failable total."""
        out["checks"].append(C.gate(name, ok, got, want, note))

    def report(name, got, why):
        """A measurement: a number with no threshold to hold it to. See
        tools/checks.py, and docs/30 § 3 for why each one is not a gate."""
        out["checks"].append(C.measurement(name, got, why))

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
        # The denominator the mean above has to be read beside. Not a gate: a
        # mean over the frames that already cleared the confidence gate is not a
        # statement about the possession, and there is no fraction below which
        # the possession is wrong - a thin denominator makes the MEAN weaker
        # evidence, it is not itself a defect. docs/30 § 2.1.
        report("...measured on", f"{a.get('usable_fraction', 0):.0%} of frames",
               "no threshold: this qualifies the mean above, docs/30 section 2.1")
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

    # Which way the offence actually moved. Never a gate: 2026-09-15 measured
    # that this quantity is not the attacking direction (docs/30 § 2.0), so
    # there is no value of it that is right or wrong. The cross-possession check
    # in check_directions is the one that can fail.
    report("offence drifts", f"{_drift(doc):+.1f} yd",
           "drift is not the attacking direction, docs/30 section 2.0")
    return out


def _drift(doc: dict) -> float:
    """Median per-player least-squares drift of the offence along x, in yards.

    Per player and least-squares rather than a centroid of whoever is in frame,
    so that panning the camera cannot move it. (Measured: on the possessions
    where every offence slot is anchored at both ends the two agree exactly, so
    the framing worry was unfounded - but the stronger statistic costs nothing.)
    """
    q = doc["possession"]
    nf = int(q["frames"])
    sl = []
    for pl in doc["players"]:
        if pl["team"] != q["offense"]:
            continue
        fs = [f for f in range(nf) if pl["est"][f]]
        if len(fs) < nf // 3:
            continue
        sl.append(np.polyfit(fs, [pl["est"][f][0] for f in fs], 1)[0] * nf)
    return float(np.median(sl)) if sl else float("nan")


def check_directions(works: list[Path]) -> dict:
    """Two teams cannot both attack the same endzone at the same time.

    This is the one statement about attacking direction that needs no assumption
    about the sport - not when ends are switched, not who receives the pull, only
    that at any instant the two teams attack opposite endzones. Within a quarter,
    then, a Sol confirmation and a Wind Chill confirmation must point opposite
    ways, and one of them settles the other.

    **This check used to be fed the drift of the offence, and that was the
    defect.** `ur.possess` fit the drift along x and `clip.json` recorded the
    answer as `attacking_direction`; on 2026-09-15 three of the four quarters cut
    came back with both teams drifting the same way. The frames are consistent
    across possessions and the movement is real (`docs/30` section 2.0), so the
    measurement was sound and the *interpretation* was wrong: the offence moving
    +x is not the offence attacking +x. AD-10 moved the fact to where it belongs -
    one direction per (quarter, team), confirmed by a human against the footage
    and resolved by `ur.direction`.

    So what fails here now is a contradiction between two people who watched, and
    that is a failure worth having: it means a quarter is mis-read off the score
    bug or a confirmation is wrong. A quarter nobody has confirmed has nothing to
    contradict, and says so rather than failing - the unconfirmed ones are counted
    in `...quarters confirmed`, which is reported beside these and is the number
    to read if every line below says PASS and the viewer still says `unverified`.
    """
    from ur import direction as DIR

    # NOTE, 2026-09-16: AD-10 is withdrawn and these checks outlive it for now.
    # Ends change every point, not every quarter, so a quarter-wide direction is
    # wrong about the sport, and the same-sign drift that appeared to contradict
    # the old per-possession model was never a contradiction - two possessions in
    # consecutive points drift the same way, legitimately. These rows pass today
    # only because nothing is confirmed and an empty quarter claims nothing, so a
    # green line here is NOT evidence that any direction is known. #5 replaces
    # them with checks keyed on a point, which can actually fail.
    out: dict = {"possession": "attacking direction (across possessions)",
                 "checks": []}

    clips: dict[str, dict] = {}
    for w in works:
        cp = w / "clip.json"
        if cp.exists() and (w / "possession.json").exists():
            clips[w.name] = json.loads(cp.read_text(encoding="utf-8"))

    try:
        obs = DIR.observations([w for w in works if w.name in clips])
    except ValueError as e:
        out["checks"].append(C.gate(
            "confirmations are readable", False, str(e),
            "every events.json:observed block parses",
            "a confirmation the resolver cannot read settles nothing"))
        return out
    table, conflicts = DIR.resolve(obs)

    quarters = sorted({int(c["quarter"]) for c in clips.values()
                       if c.get("quarter") is not None})
    confirmed_qs = {q for (q, _), e in table.items() if e["source"] == "confirmed"}

    for q in quarters:
        bad = [c for c in conflicts if c["quarter"] == q]
        here = sorted((t, e) for (qq, t), e in table.items() if qq == q)
        got = (", ".join(DIR.describe(e) for _, e in here)
               or "nobody has confirmed a direction in this quarter")
        out["checks"].append(C.gate(
            f"Q{q}: opposite teams disagree",
            not bad,
            "; ".join(c["detail"] for c in bad) if bad else got,
            "opposite ends (AD-10 WITHDRAWN - #5 re-keys to a point)",
            "two people watched the same quarter and disagree - watch it "
            "again and clear the wrong one with `python -m ur.direction "
            "clear <work>`"))

    # Never a gate. The checks above pass on an empty quarter because an empty
    # quarter makes no claim, which is honest and also useless - this is the line
    # that says how much of the job is actually done. Gating it would fail every
    # possession cut before somebody got round to watching it, and a queue is not
    # a defect. It becomes a gate the day confirming is somebody's standing job
    # rather than a backlog, and not before.
    out["checks"].append(C.measurement(
        "...quarters confirmed",
        f"{len(confirmed_qs)} of {len(quarters)}"
        + (f" (Q{', Q'.join(str(x) for x in sorted(set(quarters) - confirmed_qs))}"
           " unconfirmed)" if set(quarters) - confirmed_qs else ""),
        "a queue, not a defect: an unconfirmed quarter claims nothing"))

    # The declaration typed at cut time, now checkable against the resolved fact
    # rather than being the source of it (AD-10). This is the only thing that ever
    # catches a `--attacking-direction` copy-pasted from the previous possession.
    for pid in sorted(clips):
        clip = clips[pid]
        got = DIR.for_possession(table, clip.get("quarter"), clip["offense"])
        if got is None:
            continue
        agrees = got["direction"] == clip["attacking_direction"]
        # What to do about a mismatch depends on where the right answer came
        # from, and getting that backwards is the brief's second trap one human
        # step removed. `clip.json` is not an input to the resolver, so a DERIVED
        # value typed into it cannot feed back - but it stops looking derived the
        # moment it is there, and this check would then be agreeing with a
        # declaration that came from itself. So only a confirmation is allowed to
        # send somebody to re-cut.
        fix = ("re-cut with `--attacking-direction "
               f"{got['direction']}` - the cut is deterministic, so nothing "
               "downstream needs redoing"
               if got["source"] == "confirmed" else
               f"do NOT re-cut to {got['direction']} on this: it is derived from "
               f"{', '.join(got['from'])}, and typing it into clip.json turns a "
               "derivation into a declaration that then vouches for itself. "
               "Confirm this possession directly - `python -m ur.direction "
               f"confirm work/{pid} --direction=<+x|-x>` - and re-cut only if the "
               "confirmation still disagrees")
        out["checks"].append(C.gate(
            f"{pid}: declared direction holds", agrees,
            f"clip.json says {clip['attacking_direction']}, {DIR.describe(got)}",
            "the declaration matches what was confirmed", fix))
    return out


def grade_spans(work: Path, doc: dict, ev: dict, blind: bool = True
                ) -> tuple[int, int, list, str] | None:
    """Grade the span solver on one possession. `(correct, graded, pairs, note)`.

    Pulled out of `check_disc` so `tools/human_positions.py` can run it twice
    over one possession - once on the file and once with every hand-placed
    position taken out - and require the two to agree. A grade that moves when a
    person's work is removed is a grade that person was scoring.

    **The solver is graded on what the TRACKER produced.** A hand-placed position
    is the strongest evidence in the file and the cheapest way to make a span's
    emission cost come out right, so leaving it in would mean the solver scored
    better the more of the possession had been repaired - #8's trap, and the same
    shape as the contamination in #4. The published page still solves against the
    corrected positions; only the grade is blind to them. ur/human.py.
    """
    from ur import spans as SP

    # `blind=False` is for tools/human_positions.py only; see the note there.
    if blind:
        doc = HU.blind(doc)
    nf = int(doc["possession"]["frames"])
    fps = float(doc["possession"]["fps"])
    off = doc["possession"]["offense"]
    ids = [p["id"] for p in doc["players"] if p["team"] == off]
    tspans = SP.spans_from_events(ev, nf, fps, ids)
    truth = [s.fixed for s in tspans]
    if not any(t is not None for t in truth):
        return None
        # Tags that contradict each other are not truth. check_disc talks to the
        # solver directly rather than through ur.spans.build, so it has to repeat
        # build's refusal or it would quietly score against a contradiction.
        #
        # A *conflict* is no longer fatal: it means a throw went untagged, and
        # spans_from_events already leaves that span unknown, so it drops out of
        # the truth by itself. A *self-pass* is fatal - it is two tags that cannot
        # both be true, and nothing can be scored around it.
    bad = sum(1 for i in range(len(tspans) - 1)
              if tspans[i].fixed is not None
              and tspans[i].fixed == tspans[i + 1].fixed)
    if bad:
        return (0, 0, [], f"{work.name} NOT GRADED ({bad} self-passes in the tags)")
    unnamed = {"events": [{**e, "player": None} for e in ev.get("events", [])]}
    sp = SP.spans_from_events(unnamed, nf, fps, ids)
    if len(sp) < 2 or len(sp) != len(truth):
        return None
    SP.span_costs(doc, sp, ids)
    path, margins = SP.solve(doc, sp, ids)
    pairs: list[tuple[float, float]] = []
    n = ok = 0
    for g, t, m, sp_i in zip(path, truth, margins, tspans):
        if t is None:
            continue
        # An identity nobody saw is not ground truth. p0003's 21.27-26.33 s
        # holder was worked out by elimination - and part of that argument was
        # which slots the TRACKER loses, so grading the solver against it grades
        # the solver partly against its own upstream. The brief's second trap:
        # never feed the solver's own output back as a constraint. It stays in
        # the file, where it closes a real hole in the display; it does not
        # count here.
        if sp_i.inferred:
            continue
        n += 1
        ok += (g == t)
        if np.isfinite(m):
            pairs.append((float(m), 1.0 if g == t else 0.0))
    return (ok, n, pairs, f"{work.name} {ok}/{n}")


def check_disc(works: list[Path]) -> dict:
    """Grade the span solver wherever a human has named who held the disc."""
    out: dict = {"possession": "disc / holder inference", "checks": []}
    graded, correct, pairs = 0, 0, []
    per = []
    for work in works:
        ev_p = work / "events.json"
        if not (work / "possession.json").exists() or not ev_p.exists():
            continue
        ev = json.loads(ev_p.read_text(encoding="utf-8"))
        doc = json.loads((work / "possession.json").read_text(encoding="utf-8"))
        r = grade_spans(work, doc, ev)
        if r is None:
            continue
        ok, n, prs, note = r
        correct += ok
        graded += n
        pairs += prs
        per.append(note)

    acc = correct / graded if graded else None
    out["checks"].append(C.gate(
        "span identity accuracy",
        graded >= MIN_GRADED_SPANS and acc is not None and acc >= SPAN_ACCURACY,
        (f"{correct}/{graded}" + (f" = {acc:.0%}" if acc is not None else "")
         + (f"  [{', '.join(per)}]" if per else "")),
        f">= {SPAN_ACCURACY:.0%} over at least {MIN_GRADED_SPANS} spans",
        "needs identity tags: select the player, then press `c`"))

    corr = None
    if len(pairs) >= MIN_GRADED_SPANS and len({p[1] for p in pairs}) > 1:
        corr = float(np.corrcoef([p[0] for p in pairs], [p[1] for p in pairs])[0, 1])
    out["checks"].append(C.gate(
        "margin predicts correctness",
        corr is not None and corr >= MARGIN_CORRELATION,
        "not enough graded spans" if corr is None else f"r = {corr:+.2f}",
        f"r >= {MARGIN_CORRELATION}",
        "docs/27 step 4 asks for the next tag where the margin is thinnest; "
        "that is only a strategy if the margin means something"))
    return out


def check_site() -> dict:
    """The published site, which is the only thing anybody actually sees.

    Every other gate here reads `work/`. A site can be stale, can publish tags it
    then ignores, and can carry one possession's numbers on another's page while
    all of them stay green - which is how clicking through the live site on
    2026-09-15 found two defects the suite could not see. `tools/audit_site.py`
    carries the checks and the reasoning.
    """
    from tools import audit_site as A
    out: dict = {"possession": "the published site", "checks": []}
    try:
        ids = sorted({"p0001"} | {q.name for q in A.SITE.iterdir()
                                  if q.is_dir() and _PID.fullmatch(q.name)})
    except FileNotFoundError:
        out["checks"].append(C.gate("site is built", False, "no docs/",
                                    "tools.build_site has run", "AGENTS rule 7"))
        return out
    for pid in ids:
        for c in A.audit(pid):
            out["checks"].append({**c, "name": f"{pid}: {c['name']}"})
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="tools.gates")
    p.add_argument("work", nargs="*", default=None)
    a = p.parse_args(argv)
    works = ([Path(w) for w in a.work] if a.work
             else sorted(q for q in Path("work").iterdir()
                         if (q / "possession.json").exists()))
    reports = [check_possession(w) for w in works]
    reports.append(check_directions(works))
    reports.append(HP.check(works))
    reports.append(check_site())
    reports.append(check_disc(works))

    open_by: dict[int, int] = {}
    for r in reports:
        print(f"\n=== {r['possession']}")
        for c in r["checks"]:
            # A measurement has no verdict, so it owns no ticket here and shows
            # no number: a ticket beside a row that cannot fail would be a
            # definition of done that can never be met (docs/31).
            failing = C.is_gate(c) and not c["pass"]
            n = _issue(c["name"]) if failing else None
            if n:
                open_by[n] = open_by.get(n, 0) + 1
            print(C.render(c) + (f"  #{n}" if n else ""))
            if failing and c["note"]:
                print(f"         {c['note']}")

    t = C.tally(reports)
    print(C.totals(t))
    if open_by:
        print("")
        print("by ticket - each closes when its checks all pass:")
        for n in sorted(open_by):
            print(f"  {ISSUE_URL}/{n}   {open_by[n]} failing check(s)")
    orphan = t.failed - sum(open_by.values())
    if orphan:
        print(f"  {orphan} failing check(s) with no ticket - open one, or record "
              "in docs/30 why the failure is permanent.")
    return t.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
