"""The one view a grader is allowed to see.

Two rules had grown up apart. AD-13 says no score of the machine's work may be
computed over a fact a person supplied, and `ur.human.blind` takes hand-placed
positions out. #4 says a name the tracker supplied may not grade the tracker, and
`ur.provenance.blind` takes those names out. Both were applied by whoever
remembered: the span grader had one `continue`, `tools/m4_recall` and
`tools/m4_foot` each carried their own `blind` call, and `tools/disc_score` read
both files raw and had neither.

That is the shape AD-13 warned about one level up. `tools/human_positions` can
only probe the graders its registry names, so a grader nobody added is a grader
nobody checks, and its absence prints nothing at all rather than a row admitting
it was not reached.

So this module is the only supported way to get a possession for grading, and the
unblinded path keeps a name that reads as a confession in review. There is no
allowlist and no registry: **any direct read of `possession.json` outside this
module is the defect**, which is one grep with nothing to maintain, and
`tools/grading_view.py` is the gate.

## What it is not

It is not a publishing view, and the distinction is the whole of AD-6. A
correction is supposed to make the artefact better and the reader should see the
repaired path; what it must never do is make the *score* better. Likewise a name
settled by elimination still draws on the page, because `docs/27` is explicit
that suppressing p0003's span would reopen the display hole naming it closed.
Publishers call `read_for_publishing` and see everything.
"""

from __future__ import annotations

import json
from pathlib import Path

from ur import human as HU
from ur import provenance as PV

POSSESSION = "possession.json"
EVENTS = "events.json"


def blind(doc: dict, events: dict | None = None) -> tuple[dict, dict]:
    """The possession and the tags with everything a person supplied removed.

    Positions a hand placed or moved come back as `unknown` with no position
    (AD-13); names the tracker supplied come back as no name at all (#4). A tag
    keeps its moment either way, because the moment is the half a person can see
    and is not in doubt.

    Idempotent on both halves, which is what lets `tools/human_positions` compare
    a grader's answer against the answer over an already-blinded document.
    """
    return HU.blind(doc), PV.blind(events or {"events": []})


def load(work: Path, *, blinded: bool = True) -> tuple[dict, dict]:
    """Read one possession for grading. The only supported way in.

    `blinded=False` is for `tools/human_positions.py` and the graders it drives.
    The probe has to run each grader with its exclusions switched off, or the
    agreement between the two runs says nothing: a grader the probe never reached
    agrees with itself. So the door has a documented switch rather than a second
    door, and the two gates split the work - `tools/grading_view.py` asks whether
    you came through here at all, the probe asks whether you left it locked.
    """
    doc = json.loads((Path(work) / POSSESSION).read_text(encoding="utf-8"))
    ev_p = Path(work) / EVENTS
    ev = (json.loads(ev_p.read_text(encoding="utf-8"))
          if ev_p.exists() else {"events": []})
    return blind(doc, ev) if blinded else (doc, ev)


def read_for_publishing(work: Path) -> dict:
    """The possession as it stands, corrections and all. **Never for a score.**

    Named to be uncomfortable. A pipeline stage building the artefact, a
    renderer, the site builder and the site audit all need the document a reader
    sees, and that is a different job from grading. If you are computing a number
    that ends up beside a `want`, this is the wrong function and the gate will
    say so.
    """
    return json.loads((Path(work) / POSSESSION).read_text(encoding="utf-8"))


def read_events(work: Path) -> dict:
    """The tags as they stand. The publishing half of `load`."""
    p = Path(work) / EVENTS
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"events": []}


def has(work: Path) -> bool:
    """Has this working directory been through the pipeline?

    The guard nine callers used to write as `(work / "possession.json").exists()`.
    It reads nothing, so it was never the defect - but it does name the file, and
    a rule that lets the name out for a guard lets it out for a read one edit
    later. `tools/grading_view.py` learned that the hard way.
    """
    return (Path(work) / POSSESSION).is_file()


def has_events(work: Path) -> bool:
    """Has anybody tagged this possession?"""
    return (Path(work) / EVENTS).is_file()


def write(work: Path, doc: dict) -> Path:
    """Write the possession. The one writer, and it returns where it put it.

    `ur.possess` builds the document and `ur.resolve` replays corrections into
    it; nothing else writes one. Here for the same reason the readers are: the
    filename lives in exactly one module, so the check that nobody reaches round
    the view has one thing to look for rather than a family of spellings.
    """
    p = Path(work) / POSSESSION
    p.write_text(json.dumps(doc, indent=1) + chr(10), encoding="utf-8")
    return p
