"""Audit the published site - the thing a reader actually gets.

    python -m tools.audit_site            # every published possession
    python -m tools.audit_site p0009

`tools/gates.py` checks the pipeline: does the calibration accept, does the
roster hold together, does the solver get the holder right. Every one of those
reads `work/`. **None of them look at `docs/`**, which is the only artefact
anybody sees, and `docs/30` § 2.6 already records three defects that printed
success while being wrong. A site can be stale, can publish evidence it then
ignores, and can carry one possession's numbers on another's page, and the
entire gate suite would stay green.

This was written after clicking through the live site on 2026-09-15 and finding
two of those three. The checks below are the findings turned into tests.

**These read the published JSON, not the rendered page.** A browser audit found
the problems; a string match against rendered HTML is not the test, because the
first version of that flagged the phrase "the huck is on" as a live claim when it
survived only inside a code comment. What a page *asserts* lives in its data.

**One check breaks that rule, and it had to.** Five pages printed `Recall 0 %
and sigma containment 0 %` off fields that were `null`, because
`Math.round(null * 100)` is `0`. The data was right and said "unmeasured"; the
rendering invented the zero. No amount of reading the fields can see that, so
`no unmeasured percentage printed` runs the page's own sentence under node and
reads the string it produces - not a Python copy of the formatting, which would
only ever agree with itself. `tools/gate_sentence.py` carries the machinery.
"""

from __future__ import annotations

import argparse
import functools
import json
import re
import sys
from pathlib import Path

from tools import checks as C
from tools import gate_sentence as GS
from tools import tag_guard as TG
from tools import tag_list as TL

SITE = Path("docs")
WORK = Path("work")

# States the viewer will draw a disc for. Anything else it suppresses, which is
# the behaviour check D locks in.
DRAWN_DISC_STATES = {"observed", "confirmed"}

# How far outside the lines an OBSERVED player may be before it is a defect
# rather than a sideline. Measured: across the six published possessions 374
# observed positions are outside the field and the furthest is 2.5 yd, which is
# where people stand. The boards at Breese Stevens are a few yards further out,
# so 5 yd is past anywhere a player can be and still be on camera as a player.
OFF_FIELD_LIMIT_YD = 5.0

# The longest a drawn flight may last. Every human-tagged flight across p0001,
# p0003 and p0009 runs 0.27-3.20 s (n = 16), so 5 s is past anything real. It
# matters because an unnamed span between two named ones leaves the holder null
# throughout, and the viewer used to bridge the lot into one arc - p0003 drew a
# 7.7 s flight that silently contained a catch and a throw.
MAX_DRAWN_FLIGHT_S = 5.0


def inferred_name_frames(doc: dict) -> tuple[set[int], bool, int]:
    """Which published frames rest on a holder name nobody read, and how sure.

    Returns the frame indices, whether the flag reached the disc stage at all,
    and how many tags carry it.

    Two derivations, deliberately. `disc_meta.name_inferred` is what `ur.disc`
    recorded, and reading only that would make the check a mirror of the fix -
    revert the fix and the array disappears along with every frame it flagged,
    leaving a row that passes by having nothing to look at. So the tags are read
    too: a `throw` or `catch` tag holds the disc on its own frame, whatever the
    disc stage then did with the flag, and `holders` says whether that frame
    still names the tagged player. That half survives a revert and fails.
    """
    meta = doc.get("disc_meta") or {}
    holders = meta.get("holder") or []
    flags = meta.get("name_inferred")
    fps = float((doc.get("possession") or {}).get("fps") or 15.0)
    out = {i for i, v in enumerate(flags or []) if v}
    marked = [e for e in doc.get("events", []) if e.get("player_inferred")]
    for e in marked:
        i = int(round(float(e["t"]) * fps))
        if 0 <= i < len(holders) and holders[i] == e.get("player"):
            out.add(i)
    return out, bool(marked) and flags is None, len(marked)


def site_path(pid: str, name: str) -> Path:
    """Where a published file for `pid` lives. p0001 is the landing page, so its
    folder is `docs/` itself and every other possession gets a subdirectory -
    a rule that was written out twice before it was written down once."""
    return (SITE if pid == "p0001" else SITE / pid) / name


def published(pid: str) -> dict | None:
    """Read a published possession back out of the site, as a reader's browser does."""
    p = site_path(pid, "possession.js")
    if not p.exists():
        return None
    txt = p.read_text(encoding="utf-8")
    # The file carries several assignments (POSSESSION, ISSUES, IDENTITIES), so a
    # greedy match to the last brace swallows all of them. Decode from the start
    # of the object and let the decoder find its own end.
    i = txt.find("POSSESSION")
    if i < 0:
        return None
    i = txt.find("{", i)
    return json.JSONDecoder().raw_decode(txt[i:])[0] if i >= 0 else None


@functools.lru_cache(maxsize=1)
def _direction_table():
    """Resolve `(quarter, team) -> direction` over `work/` once per run."""
    from ur import direction as DIR
    try:
        return DIR.resolve_work(WORK)[0]
    except (OSError, ValueError, KeyError):
        return {}


def _resolved_now(pid: str) -> dict | None:
    """What this possession's page SHOULD be saying about the attacking direction."""
    from ur import direction as DIR
    cp = WORK / pid / "clip.json"
    if not cp.exists():
        return None
    clip = json.loads(cp.read_text(encoding="utf-8"))
    return DIR.for_possession(_direction_table(), clip.get("quarter"),
                              clip["offense"])


def audit(pid: str) -> list[dict]:
    out: list[dict] = []

    def add(name, ok, got, want, note=""):
        """A gate: it can fail, and it counts in the failable total."""
        out.append(C.gate(name, ok, got, want, note))

    def report(name, got, why):
        """A measurement: a number with no threshold to hold it to."""
        out.append(C.measurement(name, got, why))

    doc = published(pid)
    if doc is None:
        add("is published", False, "no possession.js under docs/", "the site carries it")
        return out

    # ---- A. the site is not behind the pipeline ------------------------------
    # Tags live in work/<id>/events.json, NOT in possession.json - make_view reads
    # them from there and injects them. Comparing against possession.json's own
    # `events`, which stays empty until ur.possess is re-run, made this check fail
    # the moment any tag existed. A gate that fires on the wrong thing is worse
    # than no gate: it trains you to ignore it.
    ev_p = WORK / pid / "events.json"
    ev = (json.loads(ev_p.read_text(encoding="utf-8")) if ev_p.exists()
          else {"events": []})
    live_n = len(ev.get("events", []))
    src = WORK / pid / "possession.json"
    if src.exists():
        live = json.loads(src.read_text(encoding="utf-8"))
        # The attacking direction goes stale in a way tags cannot, and checking
        # this possession's own `observed` block would miss it. `make_view`
        # RESOLVES the direction across every possession at build time (AD-10),
        # so a confirmation made in p0008 changes what p0003's page should say
        # while nothing in p0003 changes at all. Compare the resolved answer,
        # which is the thing the reader sees.
        pub_dir = doc["possession"].get("attacking_direction_resolved")
        same = (len(doc.get("events", [])) == live_n
                and doc["possession"]["frames"] == live["possession"]["frames"]
                and pub_dir == _resolved_now(pid))
        add("site is current", same,
            f"{len(doc.get('events', []))} events published, {live_n} in work/"
            + ("; the direction on the page is not the one work/ resolves to"
               if pub_dir != _resolved_now(pid) else ""),
            "the published page matches the pipeline",
            "run tools.build_site - the site is the deliverable (AGENTS rule 7)")

    # ---- B. published evidence is actually used ------------------------------
    # The point of tagging is that the artefact changes. p0003 and p0009 were
    # found publishing 14 and 12 human tags while every disc frame was still
    # `inferred`, because ur.disc had not been re-run since the tags landed. The
    # tags were in the file, visible to nobody, buying nothing.
    tags = [e for e in doc.get("events", [])
            if e.get("source") == "human" and e.get("player")]
    meta = doc.get("disc_meta") or {}
    human_frames = sum(1 for s in (meta.get("source") or []) if s == "human")
    add("published tags are used", not tags or human_frames > 0,
        f"{len(tags)} human tags naming a player -> {human_frames} disc frames from them",
        "tags change the artefact, or they bought nothing",
        "re-run `python -m ur.disc work/<id>` then tools.build_site")

    # ---- C. no page wears another possession's numbers -----------------------
    # The brief is explicit: never quote p0001's numbers over other footage.
    # Every page currently ships p0001's tracker gates in its data. The viewer
    # does not render them today, which makes this a loaded gun rather than a
    # live misstatement - and the fix is the same either way.
    g = doc.get("gates") or {}
    on = g.get("measured_on")
    NUMERIC = ("per_player_recall", "sigma_containment", "identity_switches_caught")
    carried = [k for k in NUMERIC if g.get(k) is not None]
    add("no borrowed gate numbers", on in (None, pid) or not carried,
        f"measured_on = {on!r}; numbers present: {carried or 'none'}",
        "numbers only on the possession they were measured on",
        "another possession's tracker numbers are readable off this page")

    # ---- C2. ...nor prints one for a measurement nobody took -----------------
    # C reads the fields; these read what the page says about them, and they are
    # two different facts. C was green on all five pages that printed a rounded
    # `0 %` for a null, because the fields were right and the formatter was not.
    # docs/30 § 2.7 carries the finding; tools/gate_sentence.py carries the
    # machinery and the argument for rendering rather than re-deriving.
    idx = site_path(pid, "index.html")
    if not idx.exists():
        # Silence here would be the worst outcome: the rows would vanish from
        # the run and the total would shrink by one with nobody the wiser.
        add("no unmeasured percentage printed", False, f"no {idx}",
            "the site carries a page to read",
            "possession.js is published and index.html is not - the build is "
            "half-done, run tools.build_site")
        add("published tags show on load", False, f"no {idx}",
            "the site carries a page to read",
            "possession.js is published and index.html is not - the build is "
            "half-done, run tools.build_site")
        add("a self-pass is always refused", False, f"no {idx}",
            "the site carries a page to read",
            "possession.js is published and index.html is not - the build is "
            "half-done, run tools.build_site")
    else:
        try:
            html = idx.read_text(encoding="utf-8")
            said = GS.render(html, doc)
            loose = GS.invented(html, doc)
            shown = GS.percentages(said)
            add("no unmeasured percentage printed", not loose,
                (f"prints {', '.join(v + ' %' for v in loose[:4])} with every "
                 "measurement removed" if loose else
                 "prints " + ", ".join(v + " %" for v in shown) if shown
                 else "prints no percentage"),
                "every percentage on the page survives only because a field "
                "behind it was measured",
                "a null recall rounds to `0 %`, which states a measurement "
                "nobody took (docs/05)")
            # The other half of the same sentence. A page that prints no number
            # and also says nothing has not told the reader its accuracy is
            # unknown - it has just left a gap where a figure would go, and a
            # gap reads as "fine". #11 asks for both halves.
            if not GS.measured(doc):
                add("an unmeasured page says so", GS.UNMEASURED in said.lower(),
                    f"{'says' if GS.UNMEASURED in said.lower() else 'never says'} "
                    f"'{GS.UNMEASURED}'",
                    f"the word '{GS.UNMEASURED}' appears in the sentence",
                    "silence about an unknown accuracy reads as a good one")
        # Deliberately broad. Everything below this line is a way of failing to
        # READ the page - node missing, gateSentence renamed, node throwing -
        # and every one of them has to land as a red row. A traceback out of
        # here takes down all 114 rows and reports nothing about any of them,
        # which is the failure mode this whole file was written against.
        except Exception as e:
            add("no unmeasured percentage printed", False,
                f"{type(e).__name__}: {e}".strip()[:160],
                "the sentence can be rendered and read",
                "the accuracy sentence is JS, so reading it needs node on PATH "
                "and a `gateSentence` to find - a gate that cannot run has not "
                "passed")

    # ---- C3. ...and it shows the tags somebody was paid to make --------------
    # Same exception to the read-the-data rule, same shape of defect. p0001,
    # p0003 and p0009 publish 6, 14 and 12 human tags, and all three pages opened
    # saying "Nothing tagged yet": the list rendered from the in-session array,
    # which starts empty, while `D.events` reached the metric cards and the
    # download button and never the pane whose whole job is to say what has been
    # tagged. B above asks whether the tags changed the artefact and was green
    # throughout - they did, in the disc stage. This asks whether the reader can
    # see them, and hiding finished work is also how it gets done twice. #12.
    if idx.exists():  # the missing-page row is added above, once
        try:
            lst = TL.read(idx.read_text(encoding="utf-8"), doc)
            add("published tags show on load", lst.ok,
                f"{lst.published} published tag(s), {lst.listed} listed"
                + lst.fault,
                "exactly the tags it was given, before a key is pressed, and "
                "the empty state back once they are taken away",
                "the tags are in events.json and the reader cannot see them - the "
                "list is seeded from the in-session array alone")
        # Broad for the reason the block above is: every way of failing to READ
        # the page has to land as one red row, not as a traceback that takes the
        # other rows down with it.
        except Exception as e:
            add("published tags show on load", False,
                f"{type(e).__name__}: {e}".strip()[:160],
                "the tag list can be rendered and read",
                "the tag list is JS, so reading it needs node on PATH and a "
                "`tagListHtml` to find - a gate that cannot run has not passed")

    # ---- C4. ...and it refuses a tag nobody could have made -----------------
    # The other half of the tagging pane, and the only check here that is about
    # what the page REFUSES rather than what it says. Nobody throws to
    # themselves; `addTag` has said so since p0009's first tagging pass, and it
    # looked for the preceding throw in the tags made in this browser tab, so a
    # throw already in `events.json` was invisible to it. C3 putting the
    # published tags on screen is what made that reachable. #25.
    #
    # **It constructs the failure.** Every events.json in work/ is correct, so no
    # published possession contains a self-pass, so reading the published data
    # would pass today with or without the guard - a definition of done that can
    # never fail to be met (AD-11). Two of the four scenarios exist only to stop
    # the row going green the easy way: a legitimate pass that must not be
    # refused, and the same self-pass with the throw taken away, which must go
    # quiet.
    roster = [q["id"] for q in doc.get("players", [])]
    if idx.exists() and len(roster) >= 2:
        try:
            v = TG.check(idx.read_text(encoding="utf-8"), roster[0], roster[1])
            add("a self-pass is always refused", v.ok,
                f"{roster[0]} throws, {roster[0]} catches" + (v.fault or
                 f" - refused on a published throw and on this session's, and "
                 f"{roster[1]} catching is taken"),
                "the guard reads the published throws as well as this session's, "
                "and still takes a catch naming anybody else",
                "a throw in events.json is a throw; a guard that cannot see one "
                "lets a self-pass into the file it is there to keep out")
        # Broad for the reason the blocks above are: a way of failing to read the
        # page has to land as one red row, not as a traceback.
        except Exception as e:
            add("a self-pass is always refused", False,
                f"{type(e).__name__}: {e}".strip()[:160],
                "the guard can be run and read",
                "the guard is JS, so running it needs node on PATH and a "
                "`selfPassRefusal` to find - a gate that cannot run has not passed")

    # ---- D. nothing is drawn from an inference that failed its gate ----------
    # Behavioural, not textual: count the frames the viewer would draw a disc
    # for, and require every one of them to rest on a human tag rather than on
    # the holder inference, which `docs/27` measures at 33 % held out.
    states = meta.get("state") or []
    sources = meta.get("source") or []
    drawn = [i for i, s in enumerate(states) if s in DRAWN_DISC_STATES]
    bad = [i for i in drawn
           if i < len(sources) and sources[i] not in ("human", "solved")]
    add("no disc drawn from the failed inference", not bad,
        f"{len(drawn)} frames drawn, {len(bad)} of them from inference alone",
        "every drawn disc frame rests on a human tag",
        "docs/27: unaided holder inference scores 33 % held out")

    # ---- E. ...nor on a position nothing saw --------------------------------
    # D checks WHO: does a drawn frame rest on a human tag. This checks WHERE,
    # and they are two different facts about the same frame. A human tag names
    # the holder; it says nothing about where the tracker's marker for that slot
    # had drifted to. On p0003 the tracker lost O2, dead-reckoned it, and
    # re-acquired 26.9 yd away on a match official standing over the sideline -
    # and because `provisional` counted as good enough, the disc was published on
    # the official at state `confirmed`, on the strength of a tag that was right
    # about the catch. Three frames, all wrong, and D was green through every one
    # of them.
    #
    # Distance cannot catch this: the "nobody observed in the stands" check below
    # measures how far outside the lines a position is, worst 2.04 yd against a
    # 5 yd threshold, because a sideline official stands exactly where a sideline
    # player stands. Provenance can.
    by = {q["id"]: q for q in doc.get("players", [])}
    holders = meta.get("holder") or []
    ghost = [i for i in drawn
             if i < len(holders) and holders[i] in by
             and by[holders[i]]["state"][i] not in DRAWN_DISC_STATES]
    add("no disc drawn on a guessed position", not ghost,
        f"{len(drawn)} frames drawn, {len(ghost)} of them on a holder whose own "
        "position was not seen"
        + ("" if not ghost else
           " - " + ", ".join(f"f{i} {holders[i]} {by[holders[i]]['state'][i]}"
                             for i in ghost[:4])),
        "the holder's own position is observed or confirmed on every drawn frame",
        "a tag vouches for WHO held it, not for where that slot's marker is")

    # ---- E2. ...nor from a name nobody read ---------------------------------
    # D asks whether a human spoke for the frame and E asks whether the tracker
    # saw the slot. Neither asks how the human arrived at the name. A tag may
    # carry `player_inferred`: the moment is a person's and so is the reasoning,
    # but the name was settled by elimination rather than read off a jersey.
    # p0003's 21.27-26.33 s span is the case, docs/27 sets out the elimination,
    # and `tools/gates.py` already refuses to grade the solver against it - yet
    # it reached the site at `confirmed`, because the disc stage asked only
    # whether a human had spoken and whether the coordinates were seen, and both
    # were true. The card then read MEASURED about a holder nobody named.
    # Evidence about WHO and evidence about WHERE are different claims and the
    # weaker one governs. #15.
    flagged, dropped, marked = inferred_name_frames(doc)
    guessed = sorted(i for i in flagged if i < len(states)
                     and states[i] == "confirmed")
    add("no confirmed disc from an inferred name", not guessed and not dropped,
        (f"{marked} tag(s) carry `player_inferred` and the published disc "
         "stage records none of it" if dropped else
         f"{len(flagged)} frame(s) rest on an inferred name, {len(guessed)} of "
         "them confirmed"
         + ("" if not guessed else
            " - " + ", ".join(f"f{i} {holders[i]}" for i in guessed[:4]))),
        "an inferred name never renders a confirmed disc state",
        "a name settled by elimination is no stronger evidence than the solver's "
        "own; it may not render at the strongest state the format has (docs/27)")

    # ---- E. nobody is observed somewhere there is no field --------------------
    # Ultimate is played with people standing just out of bounds, so being outside
    # the lines is not by itself wrong, and the measurement says so: across all six
    # published possessions, 374 `observed` positions sit outside the field and the
    # furthest is 2.5 yd. That is a player on the sideline, not a defect. So this
    # is not a finding - it is a floor, set where the stands begin. Dead reckoning
    # is exempt: docs/05 argues a ghost that drifts is more honest than one frozen,
    # and `predicted` is allowed to wander.
    fld = doc.get("field") or {}
    L, W = fld.get("length_yd", 120.0), fld.get("width_yd", 53.333)
    worst, n_bad = 0.0, 0
    for pl in doc.get("players", []):
        for st, e in zip(pl.get("state", []), pl.get("est", [])):
            if not e or st not in ("observed", "confirmed"):
                continue
            d = max(0.0, -e[0], e[0] - L) ** 2 + max(0.0, -e[1], e[1] - W) ** 2
            d = d ** 0.5
            worst = max(worst, d)
            n_bad += d > OFF_FIELD_LIMIT_YD
    add("nobody observed in the stands", n_bad == 0,
        f"{n_bad} observed positions over {OFF_FIELD_LIMIT_YD} yd out, worst {worst:.1f} yd",
        f"0 beyond {OFF_FIELD_LIMIT_YD} yd outside the field",
        "an observed position that far out is a calibration failure, not a sideline")

    # ---- F. no flight longer than a disc can stay in the air ------------------
    fps = float((doc.get("possession") or {}).get("fps") or 15.0)
    run, worst = 0, 0.0
    holders = meta.get("holder") or []
    for i, st in enumerate(states):
        if st == "interpolated" and i < len(holders) and not holders[i]:
            run += 1
            worst = max(worst, run / fps)
        else:
            run = 0
    # The viewer now refuses to draw a run this long, so the page no longer
    # ASSERTS a seven-second hang time - it shows nothing there instead. What is
    # left is a real hole in the possession, and the honest name for the check is
    # the hole, not the drawing bug that used to paper over it.
    add("disc not lost for long", worst <= MAX_DRAWN_FLIGHT_S,
        f"longest stretch with no holder {worst:.1f} s",
        f"<= {MAX_DRAWN_FLIGHT_S} s",
        "an unnamed span between two named ones leaves the disc unattributed "
        "across all three; name the holder and the hole closes")

    # Reported, not gated: the longest stretch INSIDE the tagged region where a
    # reader sees no disc at all. The check above bounds an impossible flight on
    # physics; this one has no principled threshold, and picking a number that
    # happened to fail p0003 would be the tuning trap in reverse. It is here
    # because it is the quantity the reader actually experiences, and because
    # naming a holder does not supply it - knowing WHO has the disc does not say
    # WHERE it is. p0003's 21.27-26.33 s span is named O2 and still mostly blank,
    # because the tracker observes O2 on 6 of its 77 frames.
    tagged = [e for e in doc.get("events", []) if e.get("source") == "human"]
    if tagged:
        a = int(round(min(e["t"] for e in tagged) * fps))
        b = min(int(round(max(e["t"] for e in tagged) * fps)), len(states))
        run = blind = 0
        names = meta.get("name_inferred") or []
        for i in range(a, b):
            # Mirrors the viewer's `discTrusted`: a `predicted` frame draws when
            # the identity is weak but the moment is a human's - solved from the
            # timing, or named by elimination and on a slot the tracker actually
            # saw. Reading only `confirmed` here would report p0003's
            # 21.27-26.33 s span as blank the moment #15 stopped it being
            # `confirmed`, which would be this measurement disagreeing with the
            # page it measures.
            seen = (i < len(holders) and holders[i] in by
                    and by[holders[i]]["state"][i] in DRAWN_DISC_STATES)
            drawn = states[i] in ("confirmed", "interpolated") or (
                states[i] == "predicted"
                and ((i < len(sources) and sources[i] == "solved")
                     or (i < len(names) and names[i] and seen)))
            run = 0 if drawn else run + 1
            blind = max(blind, run)
        report("...longest blind stretch", f"{blind / fps:.1f} s",
               "no principled threshold - one picked to fail p0003 is tuning, #8")

    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="tools.audit_site")
    p.add_argument("possession", nargs="*")
    a = p.parse_args(argv)
    ids = a.possession or sorted(
        {"p0001"} | {q.name for q in SITE.iterdir()
                     if q.is_dir() and re.fullmatch(r"p\d{4}", q.name)})
    reports = []
    for pid in ids:
        print(f"\n=== {pid} (as published)")
        rows = audit(pid)
        reports.append({"checks": rows})
        for c in rows:
            print(C.render(c))
            if C.is_gate(c) and not c["pass"] and c["note"]:
                print(f"         {c['note']}")
    t = C.tally(reports)
    print(C.totals(t))
    return t.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
