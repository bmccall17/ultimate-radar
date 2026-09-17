"""Run the viewer's self-pass guard out of the published page, and read it.

    from tools import tag_guard as TG
    html = pathlib.Path("docs/p0003/index.html").read_text(encoding="utf-8")
    TG.check(html, "O2", "O6").fault    # why the guard is wrong, or ""

Nobody throws to themselves. `addTag()` refuses a catch naming the player of the
throw before it - it happened across the whole back half of the first p0009
tagging pass - and it looked for that throw in `TAGS`, the tags made in the
current browser tab. A throw already in `events.json` was invisible to it, so
after #12 put the published tags on screen a reader could tag a self-pass onto
one and watch it appear in the list with nothing said.

This is the third thing lifted out of the page with `tools/page_js.py`, after the
accuracy sentence and the tag list, and it is a different kind of thing: not a
claim the page prints but a refusal the page makes. AD-12 carries the argument
that this is the same exemption rather than a wider one - both are what a reader
gets from the page, and neither is in the data.

**The check constructs its own failure.** Every `events.json` in `work/` is
correct, so no published possession contains a self-pass, so a check that read the
published data would pass today whether or not the guard was fixed - a definition
of done that can never fail to be met (AD-11). So the scenarios below are
invented, and two of them exist only to stop the row going green the easy way: a
legitimate pass that must NOT be refused, and the same self-pass with the
published throw taken away, which must go quiet.
"""

from __future__ import annotations

from typing import NamedTuple

from tools.page_js import NoNode, extract, node, run, strip_markup  # noqa: F401

FUNC = "selfPassRefusal"

# `selfPassRefusal` is pure - a tag type, a selected player, the two event arrays
# and a time in, a message or the empty string out. It reads no DOM and no
# possession. That purity is the point of the seam: `addTag` keeps the keystroke,
# the flash and the push, none of which can be checked and none of which need to.
_HARNESS = """\
const IN = require(process.argv[2]);
__FN__
process.stdout.write(
  selfPassRefusal(IN.type, IN.sel, IN.published, IN.session, IN.t));
"""


def refusal(page_html: str, type_: str, sel, published=(), session=(), t=0.0) -> str:
    """What the page would say to this tag. Empty string means it takes it."""
    return run(page_html, FUNC, _HARNESS,
               {"type": type_, "sel": sel, "published": list(published),
                "session": list(session), "t": float(t)})


class Verdict(NamedTuple):
    """The four scenarios, and whether the guard got each one right."""

    on_published: bool   # refuses a catch naming the player of a published throw
    on_session: bool     # ...and of a throw made in this browser tab
    on_other: bool       # ...and takes a catch naming anybody else
    without: bool        # ...and goes quiet once the published throw is removed

    @property
    def fault(self) -> str:
        """The one thing wrong, as a clause for the gate's `got`, or empty.

        Ordered by what each failure costs a reader. The first is the defect
        this exists for; the third and fourth are the ways a broken guard could
        otherwise pass, and they matter more than they look - a row that goes
        green by refusing everything has told nobody anything.
        """
        if not self.on_published:
            return "; takes a catch naming the player of a published throw"
        if not self.on_session:
            return "; takes a catch naming the player of a throw made in this tab"
        if not self.on_other:
            return "; refuses a catch naming anybody else, so it refuses everything"
        if not self.without:
            return ("; still refuses with the published throw taken away, so that "
                    "is not what it is reading")
        return ""

    @property
    def ok(self) -> bool:
        return not self.fault


# The scenario. A throw, then a catch 0.8 s later - inside the 0.27-3.20 s every
# human-tagged flight in this project runs, so it is a flight somebody could
# actually have tagged rather than an arrangement of numbers.
THROW_T, CATCH_T = 10.0, 10.8


def check(page_html: str, thrower: str, receiver: str) -> Verdict:
    """Put four tags to the page's guard and record what it refuses.

    `thrower` and `receiver` come from the page's own roster, so the scenario is
    about two slots that possession actually has.
    """
    throw = {"t": THROW_T, "type": "throw", "player": thrower, "source": "human"}
    said = lambda sel, pub, ses: bool(
        refusal(page_html, "catch", sel, published=pub, session=ses, t=CATCH_T))
    return Verdict(on_published=said(thrower, [throw], []),
                   on_session=said(thrower, [], [throw]),
                   on_other=not said(receiver, [throw], []),
                   without=not said(thrower, [], []))
