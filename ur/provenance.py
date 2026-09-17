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

## Why a jersey read is not provenance

CONTEXT.md is blunt: a jersey number cannot be turned into a slot without
tracking continuity to carry it. p0003 proves it, where the tagger read #28 off
the kit and still could not name the slot. Provenance is about the chain, not the
number.

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
