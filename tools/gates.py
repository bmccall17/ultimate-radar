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
from tools import grading_view as GVG
from tools import human_positions as HP
from ur import grading as GV
from ur import human as HU
from ur import provenance as PV

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
# What a person can physically do, and the allowance for the fact that we are
# measuring them with a camera. #28.
#
# 12 yd/s is roughly a world-class sprinter's top speed on a track; nobody in
# cleats on turf, changing direction, exceeds it. It is a property of people
# rather than of this footage, which is what makes it a threshold and not a
# tuned constant.
#
# The 2.5 yd is measured: tools/m4_foot puts the tracker's p95 position error at
# 1.14 yd, so two independent frames differ by about 1.6 yd at p95 before
# anybody has moved. Without it this fires on jitter - 1 yd of foot-point noise
# over one frame at 15 fps reads as 15 yd/s, and a plain speed bound flags 178
# transitions across the corpus, almost all of them sub-yard wobble. With it the
# corpus contains three violations and they are all on p0003.
SPRINT_YD_S = 12.0
FOOT_NOISE_YD = 2.5
# Both ends had a detection matched and neither frame was flagged `weak`. A
# `weak` sample is a real player on a frame the CAMERA is badly placed on, so a
# jump into or out of one is a calibration failure and this check would be
# blaming the tracker for it. docs/05.
MATCHED_STATES = {"observed", "provisional", "confirmed"}

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
    # The whole-broadcast index. Passing today and here to stay passing: it is
    # what catches a re-scan or a re-labelled cluster table.
    "goals reconcile with the final score": 16,
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
    # The unnamed span is the jersey-#28 player, who has no correct slot
    # anywhere in p0003 - the same root cause as #4, not a separate problem.
    "disc not lost for long": 4,
    # Likewise: a disc drawn on a slot whose marker has wandered onto somebody
    # else is the tracker losing the player, which is #4. The disc stage only
    # decides whether to publish the mistake.
    "no disc drawn on a guessed position": 4,
    # AD-13: a figure with no sample size behind it, and a figure over a
    # repaired possession that does not admit it is a ceiling.
    "every percentage names its sample": 27,
    "a bounded number says it is one": 27,
    # A measurement today, so it never fails and never shows a number here -
    # the mapping is so the ticket is findable the day it gets a threshold.
    "...longest blind stretch": 8,
    # A measurement today; mapped so the ticket is findable the day it is gated.
    "...slots on somebody off the field": 29,
    # The first calibration ground truth this project has ever had.
    "...paint is where the model says": 30,
    # The sixth rendered-page check. `corrections reached the page` above asks
    # whether possession.json replayed the log; this asks whether the reader is
    # told, and p0003 said "0" over 181 hand-placed positions. docs/30 s 2.22.
    "the page counts the hand in it": 31,
    # #7. Neither can fail while the goal lines are honest about being declared;
    # they are mapped so that a page that starts claiming an observation, or
    # stops saying anything at all, lands on the ticket that argued it out.
    "goal lines say which they are": 7,
    "the page says which they are": 7,
    "...goal lines found in the paint": 7,
    # Counting events, frames and a direction could not see a value change, and
    # the audit walked a doctored page past all eight site checks. #13 gave the
    # row a content digest; mapped so the next drift has a ticket to land on.
    "site is current": 13,
    # Repair mode's own gate: the one thing that has to be true before a person
    # is invited to hand-place fourteen markers and a disc.
    "no human position in a metric": 8,
    # The same argument about the other half of what a person supplies: a name
    # read off the viewer is the tracker's name, so it cannot grade the tracker.
    "no contaminated identity in a metric": 4,
    "every possession read goes through the view": 4,
    "every named tag says what carried it": 4,
    # ...and the one that says their work actually arrived.
    "corrections reached the page": 8,
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
    # The fifth. A separation is a minimum over the defensive set, and the card
    # badged it `measured` off the two players it named while a seventh sat
    # dead-reckoned and unmentioned. AD-15, docs/30 § 2.19.
    "no measured claim over an unseen defender": 14,
    "median roster in shot": 6,
    "frames with nothing at all": 6,
    "camera motion is possible": 6,
    # Found on the live page by somebody watching a slot jump between two
    # players. The camera has been asked this since M1; the players never were.
    "player motion is possible": 28,
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

    cal_p = work / "calibration.json"
    if not GV.has(work):
        add("pipeline has run", False, "no possession.json", "the pipeline run")
        return out
    cal = json.loads(cal_p.read_text(encoding="utf-8"))
    # The publishing read on purpose: every row below is about the document a
    # reader is shown, not a score of the tracker against ground truth. An
    # anchor produces `confirmed` and these ask for `observed`, so a repair pass
    # cannot walk into them.
    doc = GV.read_for_publishing(work)

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

    # Where the calibration is wrong, as opposed to how confident it says it is.
    #
    # Not a gate and #30 says why not: there is no threshold yet because there is
    # barely a measurement yet. `confidence` is one number for a whole frame,
    # scored by ur/calibrate/groundtruth.py at the two known points where the
    # halfway line crosses the centre circle - both at the CENTRE of the image -
    # so a fit good centrally and wrong at the edges reports a good frame. A
    # person dragging the viewer's paint landmarks onto the real paint is the
    # only thing that has ever measured the difference.
    #
    # Split by whether the page stands behind the frame, because a reading on a
    # frame the page already disclaims says nothing about #30 and would drag any
    # average toward a conclusion nobody claimed.
    truth_p = work / "calibration_truth.json"
    if truth_p.exists():
        truth = json.loads(truth_p.read_text(encoding="utf-8"))
        byf = {r["f"]: r for r in cal["frames"]}
        vouched, other = [], []
        for o in truth.get("observations", []):
            rec = byf.get(o["f"]) or {}
            H = rec.get("H")
            if not H:
                continue
            q = np.asarray(H, float) @ np.array([*o["image"], 1.0])
            if abs(q[2]) < 1e-12:
                continue
            err = float(np.hypot(*(q[:2] / q[2] - np.asarray(o["field"], float))))
            (vouched if (rec.get("confidence") or 0) >= 0.5 else other).append(err)
        if vouched or other:
            report("...paint is where the model says",
                   (f"{len(vouched)} reading(s) on a frame the page stands behind"
                    + (f", worst {max(vouched):.1f} yd" if vouched else "")
                    + f"; {len(other)} on frames it does not"
                    + (f", worst {max(other):.1f} yd" if other else "")),
                   "no threshold: the sample is a handful of hand-drags and only "
                   "the first group bears on #30")

    # How much of the roster is standing in the crowd.
    #
    # Not a gate, and #29 says why it is not one yet. AD-3 puts a two-yard margin
    # outside the sidelines because a thrower plants a pivot foot on the line and
    # a defender chases a disc out - so "outside the lines" is not by itself
    # wrong, and there is no fraction of it that is defensibly the limit. What
    # this row exists to stop is the `coverage` readout being believed: p0003 at
    # 28.67 s says `14/14` over a frame with ten players on it, because the bench
    # and the camera crew at Breese Stevens stand inside AD-3's margin and get
    # slots assigned to them like anybody else.
    outside = matched = 0
    try:
        dets = json.loads((work / "detections.json").read_text(encoding="utf-8"))
        byf = {r["f"]: r["dets"] for r in dets["frames"]}
        fld = doc.get("field") or {}
        L, W = fld.get("length_yd", 120.0), fld.get("width_yd", 53.333)
        for p_ in doc["players"]:
            for f, di in enumerate(p_.get("det") or []):
                if di is None or f not in byf or di >= len(byf[f]):
                    continue
                xy = byf[f][di].get("field")
                if not xy:
                    continue
                matched += 1
                outside += not (0 <= xy[0] <= L and 0 <= xy[1] <= W)
    except (FileNotFoundError, KeyError):
        matched = 0
    if matched:
        report("...slots on somebody off the field",
               f"{outside} of {matched} matched slot-frames ({outside/matched:.0%})",
               "AD-3 allows 2 yd outside the lines on purpose, so no fraction of "
               "this is defensibly wrong yet - #29")

    # Could a person have moved like that?
    #
    # The counterpart to `camera motion is possible` above, which has gated the
    # camera since M1. Until 2026-09-17 this project asked whether the CAMERA
    # could physically have moved that way and never once asked it of a PERSON -
    # so p0003's O2 slot crossing 55 yd in a single frame, `observed` at both
    # ends, went through every gate green. A person watching the live page found
    # it in about a minute. #28.
    # Blind, and this module got it wrong first. The check was written against
    # the raw document and immediately reported p0003's O2 crossing 55 yd in one
    # frame - which was not the tracker moving anybody. It was a hand-placed
    # anchor being compared against the tracker's own observation of a DIFFERENT
    # person, and the gap between them read as a teleport. Excluding what a hand
    # put there leaves zero impossible moves in the whole corpus: `MAX_SPEED_YD_S`
    # in ur/track/run.py has been doing its job all along.
    #
    # That the first new gate written after ur/human.py existed still forgot to
    # call it is the argument for `no human position in a metric` being a gate
    # rather than a convention.
    fps = float(doc["possession"]["fps"])
    impossible, worst, worst_at = [], 0.0, ""
    for pl in HU.blind(doc)["players"]:
        prev = None
        for f, (e, st) in enumerate(zip(pl["est"], pl["state"])):
            if not e or st not in MATCHED_STATES:
                continue
            if prev is not None:
                dt = (f - prev[0]) / fps
                gap = float(np.hypot(e[0] - prev[1][0], e[1] - prev[1][1]))
                over = gap - (SPRINT_YD_S * dt + FOOT_NOISE_YD)
                if over > worst:
                    worst, worst_at = over, (f"{pl['id']} f{prev[0]}->f{f}, "
                                             f"{gap:.1f} yd in {dt:.2f}s")
                if over > 0:
                    impossible.append(f"{pl['id']} f{prev[0]}->f{f}")
            prev = (f, e)
    add("player motion is possible", not impossible,
        f"{len(impossible)} impossible" + (f", worst {worst_at}" if impossible else ""),
        f"0 moves over {SPRINT_YD_S} yd/s + {FOOT_NOISE_YD} yd of noise",
        "both ends had a detection matched, so this is the slot changing person "
        "rather than the estimate drifting - the label is on two people")

    # Did the corrections in the log actually reach the file the viewer reads?
    #
    # Seen once on 2026-09-17 and not reproduced since: p0003 came out of a
    # pipeline run with `disc_meta` confirmed from twelve hand-placed positions
    # and `corrections_applied` empty - the disc stage had been handed the
    # corrected positions and the pass after it had rebuilt the players without
    # them. The published page then drew the disc on a holder its own data said
    # nobody had seen, which is what turned the row red.
    #
    # A correction that sits in a file nobody replayed is the failure #8 exists
    # to prevent, and it is silent: the log looks right, the page looks
    # plausible, and only the two counts disagreeing says otherwise. Counting is
    # cheap and this is the only place both numbers are in the same room.
    from ur import resolve as RS
    log = RS.load_log(work)
    want_n = len(RS.active(log))
    got_n = len(doc.get("corrections_applied", []))
    add("corrections reached the page", want_n == got_n,
        f"{got_n} applied, {want_n} active in the log",
        "every active correction is replayed into possession.json",
        "re-run `python -m tools.pipeline <work> --from correct`; the log is "
        "intact, the file built from it is not")

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
        if cp.exists() and GV.has(w):
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

    # `blind=False` means the caller has already been through ur.grading -
    # check_disc has, and tools/human_positions passes it to run each grader
    # with its exclusions off. Blinding is idempotent, so a second pass here
    # would be harmless; skipping it keeps one obvious owner per call.
    if blind:
        doc, ev = GV.blind(doc, ev)
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
        # A name the tracker supplied is not ground truth: grading the solver
        # against it grades the solver against its own upstream, which is the
        # brief's second trap. That exclusion used to sit here as a `continue` on
        # `player_inferred`, which asked the wrong question - it says nobody read
        # the jersey, not what the reasoning ran over. `ur.provenance` strips the
        # name instead, upstream of the span, so such a span arrives here unnamed
        # and falls out on the line above with every other unnamed span. #4.
        if t is None:
            continue
        n += 1
        ok += (g == t)
        if np.isfinite(m):
            pairs.append((float(m), 1.0 if g == t else 0.0))
    return (ok, n, pairs, f"{work.name} {ok}/{n}")


def check_declared(works: list[Path]) -> dict:
    """Does every named tag say what carried its name? #4.

    Not a percentage. A tag that stays silent reads as `tracker` and drops out
    of the graded sample, so partial declaration shrinks the denominator without
    telling anybody what left it - which is the same silence AD-11 is about, one
    file over.

    It counts **declarations, not truth**. Nothing can check that `footage` is
    honest and a check claiming to would be worth less than none;
    `provenance_stated` is what lets a reader see which were stated while
    looking and which were worked out afterwards.
    """
    named = declared = 0
    per = []
    for work in works:
        if not GV.has_events(work):
            continue
        n = d = 0
        for e in GV.read_events(work).get("events") or ():
            if e.get("player"):
                n += 1
                d += PV.KEY in e
        if n:
            named += n
            declared += d
            per.append(f"{work.name} {d}/{n}")
    return {"possession": "tagged identity provenance", "checks": [C.gate(
        "every named tag says what carried it",
        named > 0 and declared == named,
        f"{declared}/{named}" + (f"  [{', '.join(per)}]" if per else ""),
        "every tag naming a slot declares footage or tracker",
        "run `python -m ur.provenance <work>` to declare from the jersey "
        "numbers already read, then read a number during any span you want "
        "graded - a reading only settles the span it falls inside")]}


def check_disc(works: list[Path]) -> dict:
    """Grade the span solver wherever a human has named who held the disc."""
    out: dict = {"possession": "disc / holder inference", "checks": []}
    graded, correct, pairs = 0, 0, []
    per = []
    for work in works:
        ev_p = work / "events.json"
        if not GV.has(work) or not ev_p.exists():
            continue
        # Through the view, and graded with `blind=False` because it arrives
        # blinded. `ur.grading.blind` is idempotent, so this is the same answer
        # by a route the registration gate can see.
        doc, ev = GV.load(work)
        r = grade_spans(work, doc, ev, blind=False)
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
         # Say which half of the threshold failed. A reader seeing `0/0` beside
         # `>= 75%` reads it as the solver scoring nothing, when what happened is
         # that nothing was gradeable. Two different failures and only one of
         # them is about the solver.
         + (f" - under the {MIN_GRADED_SPANS}-span minimum, so this fails on "
            f"sample size and says nothing about the solver"
            if graded < MIN_GRADED_SPANS else "")
         + (f"  [{', '.join(per)}]" if per else "")),
        f">= {SPAN_ACCURACY:.0%} over at least {MIN_GRADED_SPANS} spans",
        # The tags exist - 32 of 32 name somebody. What is missing is the
        # statement of what carried each name, and until a tag says `footage`
        # it cannot be scored against. 0/0 is the honest reading, and it fails
        # on sample size rather than on the solver. #4.
        # Every tag is declared now (#4). What is scarce is independent truth:
        # only a jersey read INSIDE a span settles that span's name, because
        # anything else is the tracker carrying the identity between the two
        # moments. So the denominator grows by reading numbers, not by tagging.
        "read a jersey number during each span you want graded - a reading only "
        "settles the span it falls inside, and everything else is the tracker "
        "carrying the name there. #4 declares them; this needs more of them"))

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


GOALS_JSON = Path("eval/m9/goals.json")


def check_goals(path: Path = GOALS_JSON) -> dict:
    """The whole-broadcast goal index, read off the committed file.

    **This never opens the broadcast.** Not for portability - `work/` is
    gitignored too, so the gates already need local state - but for runtime, and
    because a check that re-derives its answer from the footage every run is
    comparing the measurement to itself. It is worth something precisely because
    `eval/m9/goals.json` is committed: that is what catches a re-scan, a
    re-labelled cluster table, or a collision repair that broke. #16.
    """
    out: dict = {"possession": "the game's goal index", "checks": []}
    if not path.exists():
        out["checks"].append(C.gate(
            "goals reconcile with the final score", False, f"no {path}",
            "the scan has run", "python -m tools.scout goals"))
        return out
    doc = json.loads(path.read_text(encoding="utf-8"))
    goals, final = doc["goals"], doc["final_score"]
    total = sum(final.values())
    steps = [(g["to"][0] - g["from"][0]) + (g["to"][1] - g["from"][1])
             for g in goals]
    odd = [g for g, s in zip(goals, steps) if s != 1]
    out["checks"].append(C.gate(
        "goals reconcile with the final score",
        len(goals) == total and not odd,
        f"{len(goals)} changes, final {'-'.join(str(v) for v in final.values())}"
        + (f" = {total}" if len(goals) != total else "")
        + (f", {len(odd)} moving a team by something other than one"
           f" ({', '.join(str(g['from']) + '->' + str(g['to']) for g in odd[:3])})"
           if odd else ""),
        f"one change per point scored, and each moves one team by one",
        "a count that disagrees with the scoreline is a change the scan missed "
        "or invented; re-run `python -m tools.scout goals` and look at the "
        "contact sheet before touching the labels"))
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
                         if GV.has(q)))
    reports = [check_possession(w) for w in works]
    reports.append(check_directions(works))
    reports.append(HP.check(works))
    reports.append(GVG.check())
    reports.append(check_declared(works))
    reports.append(check_site())
    reports.append(check_goals())
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
