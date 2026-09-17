"""What carried a tagged identity, and so whether it may grade the tracker.

A tag is a human statement about the game (AD-7, CONTEXT.md). Its *moment* is
the half a person can see, and it is not in doubt. Its *name* is not: a tagger
selects somebody in the viewer and the name that comes back is the **tracker's**
name for that person, so where the tracker's slot is on the wrong body the tag is
wrong and the tagger made no mistake. 32 of 32 tags in this corpus are named.

`provenance` is the tagger's own statement of what carried the identity from a
moment it was unambiguous to the tagged moment:

- `footage` - a person followed it in the picture.
- `tracker` - the viewer's label supplied it.

A `tracker` name does not grade the tracker. That is the whole of #4.

## Why this is not `player_inferred`

They answer different questions and both are needed. `player_inferred` says
**nobody read the jersey**; provenance says **what the reasoning ran over**.
p0001's names were reached by elimination over the throws the tagger watched, and
p0003's O2 by elimination over the tracker's own coverage counts. Both are
inferences and only the second is contaminated. So `player_inferred` keeps its
display job - such a frame never renders `confirmed` - and stops being the
grading filter.

## When a jersey read is provenance, and when it is not

CONTEXT.md is blunt: a jersey number cannot be turned into a slot without
tracking continuity to carry it. So a number read at f212 and a tag at f319 are
joined by the *tracker*, and trusting that join is this module's own subject one
step further back. p0003 showed it the hard way, where the tagger read #28 off
the kit and still could not name the slot.

A reading **inside the span the tag bounds** is different, and it is the one case
that settles a name. There is nothing to carry: the person holding the disc and
the person whose shirt was read are one person at one moment. `derive` is that
rule, and it is why a declaration pass is a matter of reading numbers during the
spans you want graded rather than remembering a tagging session.

## Blinding strips the name, not the tag

The moment stays. A span whose name is stripped is an unnamed span, which
`ur.spans` already leaves `fixed=None` and every grader already drops, so the
exclusion reuses the path that is there rather than adding one beside it.

**Absent provenance is not clean.** The whole corpus predates this field, so a
tag that says nothing is treated as `tracker` and excluded. Assuming otherwise
would grade the solver against exactly the tags this exists to hold out.
"""

from __future__ import annotations

# What carried the identity.
FOOTAGE = "footage"
TRACKER = "tracker"
CARRIERS = (FOOTAGE, TRACKER)

KEY = "provenance"

# When a person supplied the provenance. Provenance recalled from memory is not
# provenance, and the difference has to survive into the file or a declaration
# pass over an old corpus reads as if somebody had been watching at the time.
AT_TAGGING = "at_tagging"
RECONSTRUCTED = "reconstructed"
WHENS = (AT_TAGGING, RECONSTRUCTED)
WHEN_KEY = "provenance_stated"

# What went wrong with a tag that has been corrected, named for the **source**
# of the error, because CONTEXT.md's tag-versus-correction split already turns on
# what a fact is about.
#
#   tagger   - a person picked the wrong body in the picture.
#   tracker  - the slot's label was on the wrong person (p0003's 8.73 s, where
#              the tracker lost O1 and called the same body O5).
#   roster   - no slot names this person at all (p0003's jersey #28, and #26's
#              match official). AD-2 fixes fourteen slots and the field has
#              somebody on it who is not one of them.
#
# `tagger` is carried at zero occurrences on purpose. A vocabulary with no word
# for tagger error blames the tracker by default, which is the mirror of the
# defect this module exists for.
FAULTS = ("tagger", "tracker", "roster")
SUPERSEDED = "superseded"


def fault(block: dict) -> str:
    """The fault named by a `superseded` block, refusing one it does not know.

    An unknown value raises rather than passing through, in the same spirit as
    `ur.resolve` refusing an unknown correction op: a word nothing understands is
    a word that means nothing, and silently ignoring it would let a typo read as
    "no fault recorded".
    """
    v = block.get("fault")
    if v not in FAULTS:
        raise ValueError(f"unknown fault {v!r}")
    return v


def stated(tag: dict) -> str | None:
    """When the provenance was stated, or None where the tag does not say."""
    v = tag.get(WHEN_KEY)
    if v is None:
        return None
    if v not in WHENS:
        raise ValueError(f"unknown {WHEN_KEY} {v!r}")
    return v


def carried(tag: dict) -> str:
    """What carried this tag's identity. `tracker` when nothing says otherwise."""
    v = tag.get(KEY)
    if v is None:
        return TRACKER
    if v not in CARRIERS:
        raise ValueError(f"unknown {KEY} {v!r}")
    return v


def grades(tag: dict) -> bool:
    """May this tag's name be scored against? Only a name off the footage."""
    return tag.get("player") is not None and carried(tag) == FOOTAGE


def derive(events: dict, identities: dict, fps: float) -> dict:
    """Declare provenance from the jersey numbers somebody read off shirts.

    **A reading only settles the tag whose span it falls inside.** `CONTEXT.md`
    says a jersey cannot become a slot without tracking continuity to carry it,
    so a number read at f212 and a tag at f319 are joined by the tracker, and
    trusting that is this ticket's own defect one step further back. Inside the
    span there is nothing to carry: the person holding the disc and the person
    whose shirt was read are one person at one moment.

    Everything else comes back `tracker` and drops out of the graded sample.
    That is not a defeat, it is an instruction: read a number *during* the span
    you want graded.

    The result is marked `reconstructed`, because it was worked out afterwards
    from a file rather than stated by somebody looking at the picture. A
    declaration already in the file is left alone - a person who said it at the
    time outranks anything derived here.
    """
    from ur import spans as SP

    marks = [e for e in events.get("events") or ()
             if e.get("source") == "human" and e.get("type") in ("throw", "catch")]
    if not marks:
        return events
    nf = int(max(float(e["t"]) for e in marks) * fps) + 2
    ids = sorted({e["player"] for e in marks if e.get("player")})
    read = {}
    for r in identities.get("readings") or ():
        read.setdefault(r["slot"], set()).add(int(r["f"]))

    # Which frames each slot's spans cover, from the timings alone. The timings
    # are the half a person can see and are not in doubt, so building spans from
    # them borrows nothing from the tracker.
    covered: dict[str, list[tuple[int, int]]] = {}
    for sp in SP.spans_from_events({"events": marks}, nf, fps, ids):
        if sp.fixed is not None:
            covered.setdefault(ids[sp.fixed], []).append((sp.a, sp.b))

    def carried_by_a_reading(slot: str) -> bool:
        return any(a <= f <= b
                   for a, b in covered.get(slot, ())
                   for f in read.get(slot, ()))

    out = dict(events)
    out["events"] = []
    for e in events.get("events") or ():
        slot = e.get("player")
        if slot is None or KEY in e:
            out["events"].append(e)
            continue
        out["events"].append({
            **e,
            KEY: FOOTAGE if carried_by_a_reading(slot) else TRACKER,
            WHEN_KEY: RECONSTRUCTED})
    return out


def check(events: dict) -> dict:
    """Read every provenance word in the file, refusing one nothing understands.

    Called on the way into the grading view, so a malformed `events.json` stops
    at the read rather than becoming a number quietly computed around it. A typo
    in `provenance` would otherwise read as "nothing said", which excludes the
    span - the safe direction, and still wrong, because nobody would ever find
    out. `ur.resolve` refuses an unknown correction op for the same reason.
    """
    for e in events.get("events") or ():
        carried(e)
        stated(e)
        if SUPERSEDED in e:
            fault(e[SUPERSEDED])
    return events


def blind(events: dict) -> dict:
    """The same tags with every name the tracker supplied taken back out.

    A grading view, and never a publishing one: the page should show the name a
    person settled on, and `docs/27` is explicit that suppressing p0003's span
    would reopen the display hole naming it closed. Only the grade is blind.
    """
    check(events)
    out = dict(events)
    out["events"] = [e if grades(e) or e.get("player") is None
                     else {**e, "player": None}
                     for e in events.get("events") or ()]
    return out


def main(argv: list[str] | None = None) -> int:
    """Declare provenance across a working directory from its jersey readings.

        python -m ur.provenance work/p0003
        python -m ur.provenance work/p0003 --dry-run

    Re-runnable. A tag that already carries a declaration is never overwritten,
    so reading more numbers and running this again only ever adds.
    """
    import argparse
    import json
    from pathlib import Path

    from ur import grading as GV

    ap = argparse.ArgumentParser(prog="ur.provenance", description=main.__doc__)
    ap.add_argument("work", nargs="+", type=Path)
    ap.add_argument("--dry-run", action="store_true",
                    help="say what would change and write nothing")
    a = ap.parse_args(argv)

    for work in a.work:
        if not GV.has_events(work):
            print(f"[provenance] {work.name}: no tags")
            continue
        ev = GV.read_events(work)
        idp = work / "identities.json"
        idn = (json.loads(idp.read_text(encoding="utf-8")) if idp.exists()
               else {"readings": []})
        fps = float(GV.read_for_publishing(work)["possession"]["fps"])
        out = derive(ev, idn, fps)
        named = [e for e in out["events"] if e.get("player")]
        foot = sum(1 for e in named if e.get(KEY) == FOOTAGE)
        print(f"[provenance] {work.name}: {len(named)} named tag(s), "
              f"{foot} carried by a jersey read inside its own span, "
              f"{len(named) - foot} by the tracker"
              + (" (dry run)" if a.dry_run else ""))
        if not idn.get("readings"):
            print(f"             no identities.json - nothing has been read "
                  f"off a shirt here, so every name is the tracker's")
        if not a.dry_run:
            (work / GV.EVENTS).write_text(
                json.dumps(out, indent=1) + chr(10), encoding="utf-8")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
