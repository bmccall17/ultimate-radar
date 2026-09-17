"""Which positions a human's hand put there, carried beside every position.

`anchor` produces `confirmed`, and `confirmed` is indistinguishable downstream
from a frame the tracker got right. CONTEXT.md says so plainly: *every*
`confirmed` frame is human-sourced. So a metric that counts `confirmed` frames
scores the tracker **better the more a human fixes it** - per-player recall, the
sigma containment sample and the span solver's grade would all move under a
repair pass, and the direction they move in is up.

That is the same contamination as #4 and as the withdrawn
`identity_switches_caught: "2 of 2"`, and the answer is the same: the provenance
has to survive into every gate it touches, by construction rather than by
everybody remembering.

**The mark is per frame, not per operation.** An anchor does not only change the
frame it was placed on: `docs/05`'s ramp shifts every frame between the
bracketing observations so the corrected path still meets them. Those frames keep
their original evidence state - they are still `predicted`, still an estimate -
but the estimate is now partly a person's. Marking only the anchored frame would
leave the ramp's output looking like the tracker's own work, which is the same
lie one frame over.

## The shape

`possession.json` carries, per player and beside `disc_meta`:

    "human": [312, 313, 314, ...]

A sorted list of frame indices, empty on everything the pipeline produced alone.
A list rather than a per-frame boolean because it is empty in the normal case and
a 555-frame array of `false` would be carried onto every published page for
nothing.

## The one rule for a consumer

Ask `touched(player)` and drop those frames. Never infer it from the evidence
state: `confirmed` is the state an anchor *produces*, but a `predicted` frame
inside a ramp is human-sourced too, and a `confirmed` frame is what the
`confirm` operation produces over an estimate the tracker made on its own.

`tools/human_positions.py` is the check that nobody has forgotten, and it works
by moving a probe keyframe and requiring the numbers not to move.
"""

from __future__ import annotations

KEY = "human"


def touched(obj: dict | None) -> set[int]:
    """The frames of `obj` whose position a human's hand created or moved."""
    if not obj:
        return set()
    return {int(f) for f in obj.get(KEY) or ()}


def is_touched(obj: dict | None, f: int) -> bool:
    return int(f) in touched(obj)


def count(doc: dict) -> int:
    """How many (slot, frame) cells in `doc` a human's hand created or moved.

    The number a **bounded** figure has to print beside it (AD-13). Zero means
    every grader saw the whole possession, so its accuracy is a result rather
    than a ceiling; anything else means `blind()` took frames out of the sample,
    and the frames it took out are the ones the tracker got wrong.

    Counted over the players and the disc together, because both are positions a
    repair pass places and both are scored.
    """
    n = sum(len(touched(p)) for p in doc.get("players") or ())
    return n + len(touched(doc.get("disc_meta")))


def as_flags(obj: dict | None, n: int) -> list[bool]:
    """The same fact as a per-frame array, for code that replays in order."""
    marked = touched(obj)
    return [k in marked for k in range(n)]


def from_flags(flags) -> list[int]:
    """Back to the stored shape: sorted frame indices, and nothing else."""
    return [k for k, v in enumerate(flags) if v]


def blind(doc: dict) -> dict:
    """The same possession with every hand-placed position taken back out.

    **A grading view, and never a publishing one.** A correction is supposed to
    make the artefact better - that is the whole point of AD-6, and the reader
    should see the repaired path. What it must never do is make the *score*
    better, and those two only stay separate if the grader is handed a document
    that cannot see a person's work.

    Marked frames come back as `unknown` with no position, which is the shape the
    rest of the pipeline already handles everywhere: a slot nothing has seen. So
    a hand-placed position cannot match a held-out label, cannot sit inside its
    own collapsed sigma, and cannot lower a span's emission cost. It is not that
    it scores zero - it is not in the sample at all, which is what #8 means by
    "excluded by construction".

    The copy is shallow except along the arrays it rewrites, so this is cheap
    enough to run twice per possession inside a gate.
    """
    out = dict(doc)
    out["players"] = []
    for p in doc["players"]:
        marked = touched(p)
        if not marked:
            out["players"].append(p)
            continue
        q = dict(p)
        q["est"] = [None if k in marked else v for k, v in enumerate(p["est"])]
        q["state"] = ["unknown" if k in marked else v
                      for k, v in enumerate(p["state"])]
        out["players"].append(q)
    meta = doc.get("disc_meta")
    if meta and touched(meta):
        marked = touched(meta)
        out["disc"] = [None if k in marked else v
                       for k, v in enumerate(doc.get("disc") or [])]
        m = dict(meta)
        m["state"] = ["unknown" if k in marked else v
                      for k, v in enumerate(meta["state"])]
        out["disc_meta"] = m
    return out
