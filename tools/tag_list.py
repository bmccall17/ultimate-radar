"""Render the viewer's tag list the way a browser does, and read it back.

    from tools import tag_list as TL
    html = pathlib.Path("docs/p0003/index.html").read_text(encoding="utf-8")
    TL.read(html, doc).fault      # why the page is not showing its tags, or ""

`tools/audit_site.py` reads published JSON on purpose, and its docstring says
why: what a page *asserts* lives in its data. This is the second exception to
that rule, and it is the same exception `tools/gate_sentence.py` is - a defect
that lives entirely between a correct file and the screen. `tools/page_js.py`
carries the mechanics both of them share.

p0001, p0003 and p0009 publish 6, 14 and 12 human tags. All three pages opened
saying **Nothing tagged yet**, because the list rendered from `TAGS`, the array
of tags made in this browser tab, which starts empty. `D.events` - the tags
somebody was paid to make - reached the metric cards and the download button and
never the list. Every data-side check was green and correctly so; the data was
right. Only a render shows you that.

So, as with the accuracy sentence, this does **not** re-implement the list in
Python. It lifts the page's own `tagListHtml` out and runs it under node against
a published document. And the proof that the list is reading the published tags
is not a comparison against expected text - it is `read`'s **second render, with
those tags taken away**. A list that prints the same rows either way was never
reading them, and one that only happens to print the right number of rows cannot
survive having them removed.
"""

from __future__ import annotations

import re
from typing import NamedTuple

from tools.page_js import NoNode, extract, node, run, strip_markup  # noqa: F401

FUNC = "tagListHtml"

# The one phrase this matches by hand, because its absence is half the check: a
# page with nothing tagged has to say so, and a page with fourteen tags has to
# stop saying so. The viewer may word the rest of the empty state however it
# likes; this much is the contract, and `tests/test_tag_list.py` fails the day
# the page stops honouring it.
EMPTY = "Nothing tagged yet"

# What marks a tag that exists only in this browser tab. Closing the tab loses
# it, and a reader who cannot tell it apart from one already in `events.json`
# does not know what that costs.
UNSAVED = "this session"

_TIME = re.compile(r"(\d+\.\d{2})\s*s\b")

# `tagListHtml` is pure - two arrays and the clip's frame rate and length in, a
# string out - so the harness needs no `window`, no DOM and no possession beyond
# the events. That purity is the point of the seam: the DOM write stays in
# `renderTags`, where nothing can test it and nothing needs to.
_HARNESS = """\
const IN = require(process.argv[2]);
__FN__
process.stdout.write(tagListHtml(IN.published, IN.session, IN.fps, IN.nf));
"""


def render(page_html: str, doc: dict, session=()) -> str:
    """Run the page's own tag list against `doc`, return its HTML.

    `session` defaults to empty, which is the state the ticket is about: what a
    reader gets on load, before touching a key.
    """
    poss = doc.get("possession") or {}
    return run(page_html, FUNC, _HARNESS,
               {"published": list(doc.get("events") or []),
                "session": list(session),
                "fps": float(poss.get("fps") or 15.0),
                "nf": int(poss.get("frames") or 0)})


def says_empty(rendered: str) -> bool:
    return EMPTY.lower() in strip_markup(rendered).lower()


def printed_times(rendered: str) -> list[str]:
    """Every tag time the list prints, in the order it prints them.

    Counting these rather than matching formatted strings keeps the Python side
    out of the business of reproducing `toFixed(2)`: a second copy of the
    formatting would only ever agree with itself. A row the page drops is a
    timestamp that does not appear, whatever it would have looked like.
    """
    return _TIME.findall(strip_markup(rendered))


class Listing(NamedTuple):
    """What the tagging pane does with a published document, on load."""

    published: int   # tags the page was handed
    listed: int      # rows it printed
    empty: bool      # it said there was nothing tagged
    empty_without: bool  # ...and says it once the published tags are taken away

    @property
    def fault(self) -> str:
        """The one thing wrong, as a clause for the gate's `got`, or empty.

        Ordered by how badly each misleads a reader. Listing too few hides
        finished work, which is the defect this exists for; listing too many
        would be a page counting the same tag twice, which is what seeding the
        in-session array instead of the render would do and is the obvious next
        way to break this.
        """
        if self.listed < self.published:
            return "; the rest are not on the page"
        if self.listed > self.published:
            return f"; {self.listed - self.published} row(s) more than it was given"
        if self.empty and self.published:
            return "; says there is nothing tagged over them anyway"
        if not self.empty and not self.published:
            return "; never says a page with nothing tagged has nothing"
        if not self.empty_without:
            return ("; still lists rows with the published tags taken away, so "
                    "they are not what it is reading")
        return ""

    @property
    def ok(self) -> bool:
        return not self.fault


def read(page_html: str, doc: dict) -> Listing:
    """What a reader gets on load, and whether it rests on the published tags.

    Two renders, deliberately, and the second is the half that cannot be faked:
    hand the page the same document with `events` emptied and it has to fall
    back to the empty state. See the module docstring.
    """
    shown = render(page_html, doc)
    without = render(page_html, {**doc, "events": []})
    return Listing(published=len(doc.get("events") or []),
                   listed=len(printed_times(shown)),
                   empty=says_empty(shown),
                   empty_without=says_empty(without))
