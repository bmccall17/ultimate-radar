"""Render the viewer's accuracy sentence the way a browser does, and read it.

    from tools import gate_sentence as GS
    html = pathlib.Path("docs/p0003/index.html").read_text(encoding="utf-8")
    GS.invented(html, doc)      # percentages the page prints off nothing

`tools/audit_site.py` reads published JSON and says why in its own docstring:
what a page *asserts* lives in its data, and a string match against rendered
HTML once flagged a phrase that survived only inside a code comment.

This module is the exception, and `docs/30` § 2.7 is the argument for it. Five
published pages printed a rounded `0 %` for recall and for sigma containment.
Nobody had measured either: both fields are `null` in those pages' data, and
`Math.round(null * 100)` is `0`. Every data-side check was green, correctly -
the data said "unmeasured" and meant it. The formatter invented the zero on its
way to the screen, and only the screen can show you that.

It does **not** re-implement the sentence in Python. A second copy of the
formatting would agree with itself and catch nothing, and it would have to
reproduce JS rounding (half-up) rather than Python's (half-to-even) to avoid
disagreeing about `12.5`. Instead:

- `page_js.extract` lifts `gateSentence` out of the page as source;
- `render` executes that source under node against a possession document;
- `invented` renders the page a second time with **every measurement removed**,
  and hands back whatever percentages survive. A number that survives having its
  measurement taken away was never resting on one.

That second render is the whole test, and it is stronger than comparing printed
values against expected ones. It catches a literal typed into the prose, it
catches a null rounded to zero, and on a possession that *was* measured it
catches the same bug latent - p0001 prints `97 %` honestly today, and would fail
here the moment the code behind it would print `0 %` for a null.
"""

from __future__ import annotations

import re

# The mechanics - find the function, run it under node, strip the markup - are
# shared with `tools/tag_list.py`, which checks the other rendered pane for the
# same shape of defect. `extract` and `node` stay reachable as `GS.extract` and
# `GS.node` because that is what this module's callers already say.
from tools.page_js import NoNode, extract, node, run, strip_markup  # noqa: F401

FUNC = "gateSentence"

# The gate fields the sentence turns into percentages. `identity_switches_caught`
# is deliberately not here: it is a count, it prints as a count, and
# `audit_site`'s "no borrowed gate numbers" is the check that cares about it.
MEASURED_FIELDS = ("per_player_recall", "sigma_containment")

# What a page with no measurement of its own has to say, in one word. The page
# may say it however it likes as long as it says this much; the point is that
# silence and a number are both wrong, and only one of those is obvious.
UNMEASURED = "unmeasured"

_PCT = re.compile(r"(-?\d+(?:\.\d+)?)\s*%")


# `window.POSSESSION` is what the published possession.js assigns and what the
# viewer reads; `D` and `PL` are the two names the sentence closes over. The
# branch below is viewer/index.html's own: a file that predates the gate
# measurements carries no sentence at all, and neither does one with no gates.
_HARNESS = """\
globalThis.window = globalThis;
window.POSSESSION = require(process.argv[2]);
const D = window.POSSESSION, PL = D.players;
__FN__
process.stdout.write(
  (D.gates_measured === false || !D.gates)
    ? "" : gateSentence(D.gates, D.possession.id));
"""


def render(page_html: str, doc: dict) -> str:
    """Run the page's own accuracy sentence against `doc`, return its HTML."""
    return run(page_html, FUNC, _HARNESS, doc)


def blanked(doc: dict) -> dict:
    """`doc` with every measurement removed and nothing else touched."""
    g = dict(doc.get("gates") or {})
    for k in MEASURED_FIELDS:
        g[k] = None
    return {**doc, "gates": g}


def measured(doc: dict) -> list[str]:
    """Which measurement fields this page actually carries a number for."""
    g = doc.get("gates") or {}
    return [k for k in MEASURED_FIELDS
            if isinstance(g.get(k), (int, float)) and not isinstance(g.get(k), bool)]


def percentages(sentence: str) -> list[str]:
    """Every percentage a reader can see, in order, with markup stripped."""
    return _PCT.findall(strip_markup(sentence))


def invented(page_html: str, doc: dict) -> list[str]:
    """Percentages the page still prints once every measurement is taken away.

    Each one is a number with nothing behind it, by construction: the fields it
    could have come from are `null` in the document that produced it.
    """
    return percentages(render(page_html, blanked(doc)))
