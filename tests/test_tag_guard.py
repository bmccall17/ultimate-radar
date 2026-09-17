"""The tag the viewer refuses to take, rendered rather than assumed.

Nobody throws to themselves. `addTag()` refuses a catch naming the player of the
throw before it, and it found that throw in `TAGS` - the tags made in the current
browser tab - so a throw already in `events.json` was invisible to it. Since #12
put those tags on screen, a reader could select O2, press `c` after p0003's
published `throw O2 @ 26.33s`, and watch a self-pass appear in the list with
nothing said.

This is the third thing `tools/page_js.py` runs out of the published page, after
the accuracy sentence and the tag list, and it is a different KIND of thing: not
a claim the page prints but a refusal the page makes. AD-12 covers it and says
why that is the same exemption rather than a wider one.

**The check has to construct its own failure.** Every `events.json` in `work/` is
correct, so no published possession contains a self-pass, so a check that read the
published data would pass today whether or not the guard was fixed - a definition
of done that can never fail to be met (AD-11). The scenarios below are invented on
purpose, and one of them is a legitimate pass, so a guard that refused everything
would fail here rather than sail through.

Run them:

    python -m unittest discover -s tests -t .
"""

from __future__ import annotations

import pathlib
import unittest

from tools import page_js as PJ
from tools import tag_guard as TG

VIEWER = pathlib.Path("viewer/index.html")
HTML = VIEWER.read_text(encoding="utf-8")

THROW = {"t": 26.333, "type": "throw", "player": "O2", "source": "human"}

needs_node = unittest.skipIf(PJ.node() is None, "node is not on PATH")


class Extract(unittest.TestCase):
    def test_the_viewer_carries_the_function(self):
        self.assertTrue(PJ.extract(HTML, TG.FUNC).startswith(f"function {TG.FUNC}"))

    def test_a_page_without_it_fails_loudly(self):
        # audit_site turns this into one red row rather than a traceback.
        with self.assertRaises(ValueError):
            PJ.extract("<html>nothing here</html>", TG.FUNC)


@needs_node
class WhatIsRefused(unittest.TestCase):
    def test_a_catch_naming_the_published_thrower(self):
        # The defect. Before the fix this returns nothing at all.
        said = TG.refusal(HTML, "catch", "O2", published=[THROW], t=27.133)
        self.assertTrue(said)
        self.assertIn("O2", said)

    def test_a_catch_naming_this_session_s_thrower(self):
        # Today's behaviour, which must not regress.
        said = TG.refusal(HTML, "catch", "O2", session=[THROW], t=27.133)
        self.assertTrue(said)

    def test_the_message_says_which_throw_it_means(self):
        # "The selection is still on the thrower" is advice about a keystroke the
        # reader just made. It is wrong about a throw that came out of a file
        # somebody else tagged, and sends them looking for a mistake they did
        # not make.
        pub = TG.refusal(HTML, "catch", "O2", published=[THROW], t=27.133)
        ses = TG.refusal(HTML, "catch", "O2", session=[THROW], t=27.133)
        self.assertNotEqual(pub, ses)
        self.assertIn("events.json", pub)
        self.assertNotIn("events.json", ses)


@needs_node
class WhatIsNotRefused(unittest.TestCase):
    """The half that stops the row passing on a guard that refuses everything."""

    def test_a_catch_naming_somebody_else(self):
        self.assertEqual(
            TG.refusal(HTML, "catch", "O6", published=[THROW], t=27.133), "")

    def test_a_timing_only_catch(self):
        # A tag that names nobody cannot name the wrong body.
        self.assertEqual(
            TG.refusal(HTML, "catch", None, published=[THROW], t=27.133), "")

    def test_a_throw_after_a_throw(self):
        # Two throws running is a tagging gap, not a self-pass, and `ur.spans`
        # is where that is worked out.
        self.assertEqual(
            TG.refusal(HTML, "throw", "O2", published=[THROW], t=27.133), "")

    def test_a_catch_before_the_throw_it_would_be_refused_after(self):
        # `TAGS` is sorted by `t`, so the old guard's "previous" was the latest
        # tag made, not the latest tag before this one. Tag a throw at 26.3 s,
        # scrub back to 5 s, tag a catch: that catch is not after that throw.
        self.assertEqual(
            TG.refusal(HTML, "catch", "O2", published=[THROW], t=5.0), "")

    def test_a_catch_after_an_intervening_catch(self):
        # O2 throws, somebody catches, and only then is O2 tagged catching. The
        # event before this one is a catch, so there is no self-pass in it.
        evs = [THROW, {"t": 27.133, "type": "catch", "player": "O6",
                       "source": "human"}]
        self.assertEqual(
            TG.refusal(HTML, "catch", "O2", published=evs, t=30.067), "")


@needs_node
class TheGateItself(unittest.TestCase):
    SIG = f"function {TG.FUNC}(type, sel, published, session, t){{"

    def test_the_viewer_as_it_stands_passes(self):
        v = TG.check(HTML, "O2", "O6")
        self.assertTrue(v.ok, v.fault)

    def test_a_guard_that_cannot_see_the_published_throw_fails(self):
        # The defect, reconstructed: the guard reading only this session.
        broken = HTML.replace(self.SIG, self.SIG + " published = [];", 1)
        self.assertNotEqual(broken, HTML)
        v = TG.check(broken, "O2", "O6")
        self.assertFalse(v.ok)
        self.assertIn("published", v.fault)

    def test_a_guard_that_refuses_everything_fails(self):
        broken = HTML.replace(self.SIG, self.SIG + " return 'no.';", 1)
        self.assertNotEqual(broken, HTML)
        v = TG.check(broken, "O2", "O6")
        self.assertFalse(v.ok)
        self.assertIn("anybody else", v.fault)

    def test_a_guard_that_refuses_regardless_of_its_input_fails(self):
        # AD-12's second constraint. A refusal that survives having the throw
        # taken away was never reading it.
        rows = (" if(type==='catch' && sel==='O2') return 'no.';")
        broken = HTML.replace(self.SIG, self.SIG + rows, 1)
        self.assertNotEqual(broken, HTML)
        v = TG.check(broken, "O2", "O6")
        self.assertFalse(v.ok)
        self.assertIn("taken away", v.fault)


if __name__ == "__main__":
    unittest.main()
