"""The sentence saying how much of the page a person put there, rendered and read.

    from tools import corrections_line as CL
    CL.read(html, doc)      # a verdict on what that page tells a reader

Found on 2026-09-18 while writing down what a stranger would see on p0003 for
#24. The page carries fifteen applied corrections and 181 hand-placed frames,
and it printed **"0 human corrections applied"**. `LOG` starts empty in the
browser and nothing ever seeded it from `D.corrections_applied`, so the line
counted this session's edits and nothing else.

That is `docs/30` section 2.8 one pane over: the published tag list rendered from
the in-session array and said "Nothing tagged yet" over fourteen tags. Same root
cause, same shape, opposite consequence. Hiding tags wastes work; hiding
corrections **overstates the machine**, and it does it on the page the sprint's
cold read is about, where question 5 asks a stranger which parts the tool told
them it was guessing at.

## Why it reads the render

`tools/gates.py` already has `corrections reached the page`, and it was green
throughout: it compares `corrections.json` against `possession.json`, which is a
question about the pipeline. Whether the **reader** is told is a different
question, and only the rendered string answers it. The fifth module here to make
that argument; `tools/page_js.py` holds the mechanics the six share.

## The two halves it asserts

`seeded` - the line counts what the file carries, proved by removing the
corrections and requiring the number to fall. `frames` - it reports **frames**
and not operations, because one anchor moves every frame between the bracketing
observations (`ur/human.py`), so p0003's fifteen corrections are 181 frames, a
third of the possession. AD-13 keeps those frames out of every accuracy sample;
a reader weighing what they are looking at needs the same count.
"""

from __future__ import annotations

import re
from typing import NamedTuple

from tools.page_js import NoNode, extract, node, run, strip_markup  # noqa: F401

FUNC = "correctionsLine"

_HARNESS = """\
globalThis.window = globalThis;
const P = require(process.argv[2]);
__FN__
process.stdout.write(correctionsLine(P.published, P.session, P.players,
                                     P.frames, P.disc));
"""

_INT = re.compile(r"\\d+")


def render(page_html: str, published: list, session: list, players: list,
           frames: int, disc: dict | None = None) -> str:
    return run(page_html, FUNC, _HARNESS,
               {"published": published, "session": session, "players": players,
                "frames": frames, "disc": disc or {}})


def _payload(doc: dict) -> tuple[list, list, int, dict]:
    return (doc.get("corrections_applied") or [],
            [{"slot": p.get("slot"), "human": p.get("human") or []}
             for p in doc.get("players") or []],
            int(doc["possession"]["frames"]),
            {"human": (doc.get("disc_meta") or {}).get("human") or []})


def cells(doc: dict) -> int:
    """(slot, frame) pairs a hand created or moved - `ur.human.count`'s number.

    Restated here rather than imported because the page has to compute it from
    what it publishes, and this check has to read what the page computed.
    """
    n = sum(len(p.get("human") or ()) for p in doc.get("players") or ())
    return n + len((doc.get("disc_meta") or {}).get("human") or ())


def touched(doc: dict) -> int:
    """How many FRAMES a hand reached, which is a different number: two markers
    moved on one frame is two cells and one frame."""
    out: set[int] = set()
    for p in doc.get("players") or []:
        out.update(int(f) for f in (p.get("human") or ()))
    out.update(int(f) for f in ((doc.get("disc_meta") or {}).get("human") or ()))
    return len(out)


class Verdict(NamedTuple):
    said: str
    empty: str
    published: int
    frames: int
    fault: str

    @property
    def ok(self) -> bool:
        return not self.fault

    def say(self) -> str:
        return (f"{self.published} published correction(s), {self.frames} "
                f"hand-placed frame(s)" + self.fault)


def read(page_html: str, doc: dict) -> Verdict:
    """What this page tells a reader about the hand in it, and whether it holds.

    Two renders. The first is the page as published. The second takes the
    corrections and the hand-placed frames away and requires the sentence to say
    so - a line that reports the same thing over a document with nothing in it
    is a line nobody seeded.
    """
    published, players, frames, disc = _payload(doc)
    said = strip_markup(render(page_html, published, [], players, frames, disc))
    bare = [{"slot": p["slot"], "human": []} for p in players]
    empty = strip_markup(render(page_html, [], [], bare, frames, {"human": []}))
    n_frames, n_cells = touched(doc), cells(doc)

    fault = ""
    if published and not _mentions(said, len(published)):
        fault += (f"; the page prints {said.strip()!r} over "
                  f"{len(published)} published correction(s)")
    if n_frames and not _mentions(said, n_frames):
        fault += (f"; {n_frames} hand-touched frame(s) are not in what the page "
                  "prints")
    if n_cells and not _mentions(said, n_cells):
        fault += (f"; {n_cells} hand-placed position(s) are not in what the "
                  "page prints")
    # The ablation. Without it a page hard-coding p0003's numbers passes forever,
    # which is AD-11 in the costume `tools/openness.py` names.
    if (published or n_frames) and empty.strip() == said.strip():
        fault += "; it says the same thing with every correction removed"
    return Verdict(said.strip(), empty.strip(), len(published), n_frames, fault)


def _mentions(sentence: str, n: int) -> bool:
    """Is `n` one of the numbers the reader is shown?"""
    return str(n) in re.findall(r"\d+", sentence)
