"""What the tagging pane says on load, rendered rather than assumed.

`tools/audit_site.py` reads published JSON on purpose, and says why: what a page
asserts lives in its data. The tag list is one of the two places that rule does
not reach, for the same reason the accuracy sentence is the other. p0001, p0003
and p0009 published 6, 14 and 12 human tags, and every one of those pages opened
saying **Nothing tagged yet**: the list rendered from an in-session array that
starts empty, and `D.events` - the tags a person was paid to make - were read by
the metric cards and by the download button and never by the list itself. The
data was right on all three pages. The rendering was the lie, which is the shape
of defect only a render can show you (docs/30 section 2.7).

So the seam is `tagListHtml(published, session, fps)`: a pure function from the
two arrays to the block of HTML, extracted out of the page and run under node.
The test that the list rests on the published events is to render it a second
time with those events taken away and require the page to change its mind.

Run them:

    python -m unittest discover -s tests -t .
"""

from __future__ import annotations

import pathlib
import unittest

from tools import page_js as PJ
from tools import tag_list as TL

VIEWER = pathlib.Path("viewer/index.html")
HTML = VIEWER.read_text(encoding="utf-8")

PUBLISHED = [
    {"t": 7.6, "type": "throw", "player": "O7", "source": "human"},
    {"t": 8.467, "type": "catch", "player": "O4", "source": "human"},
]
INFERRED = {"t": 21.267, "type": "catch", "player": "O2", "source": "human",
            "player_inferred": True}


def doc(events):
    return {"possession": {"id": "p0003", "fps": 15.0, "frames": 555},
            "events": events}


needs_node = unittest.skipIf(PJ.node() is None, "node is not on PATH")


class Extract(unittest.TestCase):
    def test_the_viewer_carries_the_function(self):
        src = PJ.extract(HTML, TL.FUNC)
        self.assertTrue(src.startswith(f"function {TL.FUNC}"))

    def test_a_page_without_it_fails_loudly(self):
        # audit_site turns this into one red row. Silence would drop the row
        # out of the run and shrink the total with nobody the wiser.
        with self.assertRaises(ValueError):
            PJ.extract("<html>nothing here</html>", TL.FUNC)


@needs_node
class OnLoad(unittest.TestCase):
    """What a reader gets before touching a key."""

    def test_published_tags_are_listed(self):
        out = TL.render(HTML, doc(PUBLISHED))
        self.assertFalse(TL.says_empty(out))
        self.assertEqual(len(TL.printed_times(out)), 2)
        self.assertIn("O7", out)
        self.assertIn("O4", out)

    def test_a_possession_with_none_says_so(self):
        out = TL.render(HTML, doc([]))
        self.assertTrue(TL.says_empty(out))
        self.assertEqual(TL.printed_times(out), [])

    def test_the_list_rests_on_the_events_and_not_on_something_else(self):
        # The half that survives a revert. Take the published events away and a
        # list that was really reading them has to change its mind; one seeded
        # from an empty array prints the same thing either way, which is the
        # defect this file exists for.
        self.assertNotEqual(TL.render(HTML, doc(PUBLISHED)),
                            TL.render(HTML, doc([])))

    def test_a_published_tag_carries_no_frame_and_still_gets_one(self):
        # events.json holds `t` only; `f` is a viewer-side convenience the
        # in-session tags happen to have. A row that printed `fundefined` would
        # be listing the tag and still reading as broken.
        self.assertNotIn("undefined", TL.render(HTML, doc(PUBLISHED)))

    def test_a_name_nobody_read_is_not_printed_as_one_somebody_did(self):
        out = TL.render(HTML, doc([INFERRED]))
        self.assertIn("elimination", out)
        self.assertNotIn("elimination", TL.render(HTML, doc(PUBLISHED)))


@needs_node
class WithSessionTags(unittest.TestCase):
    """Tagging still works on top of the seeded list."""

    NEW = [{"t": 3.0, "type": "throw", "player": None, "f": 45,
            "source": "human"}]

    def test_a_new_tag_joins_the_published_ones(self):
        out = TL.render(HTML, doc(PUBLISHED), session=self.NEW)
        self.assertEqual(len(TL.printed_times(out)), 3)
        self.assertFalse(TL.says_empty(out))

    def test_they_are_listed_in_time_order_not_by_which_array_they_came_from(self):
        out = TL.render(HTML, doc(PUBLISHED), session=self.NEW)
        self.assertEqual(TL.printed_times(out), ["3.00", "7.60", "8.47"])

    def test_a_timing_only_tag_is_still_counted_as_one(self):
        out = TL.render(HTML, doc(PUBLISHED), session=self.NEW)
        self.assertIn("timing-only", out)
        self.assertNotIn("timing-only", TL.render(HTML, doc(PUBLISHED)))

    def test_the_session_tags_are_marked_as_unsaved(self):
        # The published ones are in a file and this one is in a browser tab. A
        # reader who cannot tell which is which does not know what closing the
        # tab costs them.
        out = TL.render(HTML, doc(PUBLISHED), session=self.NEW)
        self.assertIn(TL.UNSAVED, out)
        self.assertNotIn(TL.UNSAVED, TL.render(HTML, doc(PUBLISHED)))


@needs_node
class TheGateItself(unittest.TestCase):
    """`published tags show on load`, in both directions it can fail."""

    SIG = f"function {TL.FUNC}(published, session, fps, nf){{"

    def test_a_page_that_lists_its_tags_passes(self):
        lst = TL.read(HTML, doc(PUBLISHED))
        self.assertEqual((lst.published, lst.listed), (2, 2))
        self.assertTrue(lst.ok, lst.fault)

    def test_a_page_with_no_tags_to_list_passes(self):
        lst = TL.read(HTML, doc([]))
        self.assertEqual((lst.published, lst.listed), (0, 0))
        self.assertTrue(lst.ok, lst.fault)

    def test_a_list_seeded_from_nothing_fails(self):
        # The defect, reconstructed: a renderer that ignores `published`.
        broken = HTML.replace(self.SIG, self.SIG + " published = [];", 1)
        self.assertNotEqual(broken, HTML)
        lst = TL.read(broken, doc(PUBLISHED))
        self.assertFalse(lst.ok)
        self.assertEqual(lst.listed, 0)
        self.assertTrue(TL.says_empty(TL.render(broken, doc(PUBLISHED))))

    def test_a_list_that_prints_every_tag_twice_fails(self):
        # The obvious next way to break this: seed the in-session array from
        # `D.events` as well and every tag renders once from each. Counting only
        # what is missing would call that page clean.
        broken = HTML.replace(self.SIG, self.SIG + " session = published;", 1)
        self.assertNotEqual(broken, HTML)
        lst = TL.read(broken, doc(PUBLISHED))
        self.assertEqual((lst.published, lst.listed), (2, 4))
        self.assertFalse(lst.ok)
        self.assertIn("more than it was given", lst.fault)

    def test_a_list_that_prints_rows_from_somewhere_else_fails(self):
        # The second render is the only thing that catches this: a page hard-
        # coding rows lists the right number and survives having its events
        # taken away, because it was never reading them.
        rows = ("return "
                "'<div>throw O7 @ f114 · 7.60s</div>"
                "<div>catch O4 @ f127 · 8.47s</div>';")
        broken = HTML.replace(self.SIG, self.SIG + rows, 1)
        self.assertNotEqual(broken, HTML)
        lst = TL.read(broken, doc(PUBLISHED))
        self.assertEqual((lst.published, lst.listed), (2, 2))
        self.assertFalse(lst.empty)
        self.assertFalse(lst.empty_without)
        self.assertFalse(lst.ok)
        self.assertIn("taken away", lst.fault)


if __name__ == "__main__":
    unittest.main()
