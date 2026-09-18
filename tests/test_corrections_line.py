"""The page said nobody had touched it, over 181 hand-placed positions.

`docs/p0003/possession.js` carries fifteen applied corrections and 181 positions
a hand placed across 165 of its 555 frames, and the page printed **"0 human
corrections applied"**. `const LOG = []` starts empty in the browser and nothing
seeded it from `D.corrections_applied`.

It is `docs/30` section 2.8 one pane over, and worse in the direction that
matters: hiding published tags wastes work, hiding published corrections
overstates the machine. #31.

The tests below are the two halves the row asserts. The sentence has to name what
the file carries, and it has to stop saying it when the file stops carrying it.
The second is the one that makes the first a test rather than a string match.

    python -m unittest discover -s tests -t .
"""

from __future__ import annotations

import copy
import pathlib
import unittest

from tools import audit_site as AS
from tools import corrections_line as CL
from tools import page_js as PJ

HTML = pathlib.Path("viewer/index.html").read_text(encoding="utf-8")
needs_node = unittest.skipIf(PJ.node() is None, "node is not on PATH")

# Two corrections, one of them rippling over a ramp, and one frame both of them
# reached. Invented rather than read from `work/`, which is gitignored footage.
REPAIRED = {
    "possession": {"id": "pTEST", "fps": 15.0, "frames": 100},
    "corrections_applied": [
        {"id": "c1", "op": "anchor", "slot": "O1", "f": 40},
        {"id": "c2", "op": "anchor", "slot": "O2", "f": 42},
    ],
    "players": [
        {"slot": "O1", "human": [38, 39, 40, 41, 42]},
        {"slot": "O2", "human": [42, 43]},
        {"slot": "O3"},
    ],
    "disc_meta": {"human": [42]},
}

CLEAN = {
    "possession": {"id": "pCLEAN", "fps": 15.0, "frames": 100},
    "corrections_applied": [],
    "players": [{"slot": "O1"}, {"slot": "O2"}],
    "disc_meta": {},
}


class TwoNumbersAndTheyAreDifferent(unittest.TestCase):
    """`ur/human.py::count` keeps positions and frames apart, and so does this.
    Two markers moved on one frame is two cells and one frame, and quoting
    either alone reads as the other."""

    def test_positions_are_slot_frame_pairs(self):
        self.assertEqual(CL.cells(REPAIRED), 5 + 2 + 1)

    def test_frames_are_the_union_and_include_the_disc(self):
        self.assertEqual(CL.touched(REPAIRED), len({38, 39, 40, 41, 42, 43}))

    def test_it_agrees_with_the_grading_view(self):
        from ur import human as HU
        self.assertEqual(CL.cells(REPAIRED), HU.count(REPAIRED))

    def test_a_clean_possession_is_zero_on_both(self):
        self.assertEqual((CL.cells(CLEAN), CL.touched(CLEAN)), (0, 0))


@needs_node
class WhatThePageSays(unittest.TestCase):
    def test_a_repaired_page_names_the_corrections_and_the_frames(self):
        v = CL.read(HTML, REPAIRED)
        self.assertTrue(v.ok, v.fault)
        for n in ("2", "8", "6", "100"):
            self.assertIn(n, v.said)

    def test_a_clean_page_says_none_rather_than_a_number_off_nothing(self):
        v = CL.read(HTML, CLEAN)
        self.assertTrue(v.ok, v.fault)
        self.assertIn("0 human corrections", v.said)
        self.assertNotIn("placing", v.said)

    def test_the_sentence_stops_when_the_corrections_do(self):
        # The ablation. A line hard-coding p0003's numbers passes the first test
        # forever, which is AD-11 in the costume tools/openness.py names.
        v = CL.read(HTML, REPAIRED)
        self.assertNotEqual(v.said, v.empty)
        self.assertIn("0 human corrections", v.empty)

    def test_the_old_behaviour_would_fail_this_row(self):
        # What the page did until 2026-09-18: count the in-session log and
        # nothing else. Reproduced by handing the renderer no published
        # corrections and no hand-placed frames over a document that has both.
        said = PJ.strip_markup(CL.render(HTML, [], [], [{"slot": "O1"}], 100))
        self.assertIn("0 human corrections", said)
        self.assertNotEqual(said.strip(), CL.read(HTML, REPAIRED).said)

    def test_a_page_that_has_lost_the_function_fails_loudly(self):
        # audit_site turns this into one red row. Silence would drop the row out
        # of the run and shrink the total with nobody the wiser.
        with self.assertRaises(ValueError):
            CL.read("<html>nothing here</html>", REPAIRED)


@needs_node
class OnTheRealSite(unittest.TestCase):
    def test_p0003_tells_a_reader_about_its_repair_pass(self):
        doc = AS.published("p0003")
        if doc is None:
            self.skipTest("docs/p0003 is not built")
        v = CL.read(AS.site_path("p0003", "index.html").read_text(encoding="utf-8"),
                    doc)
        self.assertTrue(v.ok, v.fault)
        # The finding itself, kept as a regression: this page is NOT the
        # unrepaired page #24's first acceptance criterion asks for.
        self.assertGreater(CL.cells(doc), 0)
        self.assertIn(str(CL.cells(doc)), v.said)

    def test_every_published_page_passes_the_row(self):
        for pid in ("p0001", "p0003", "p0004", "p0005", "p0009", "p0015"):
            doc = AS.published(pid)
            if doc is None:
                continue
            with self.subTest(pid):
                html = AS.site_path(pid, "index.html").read_text(encoding="utf-8")
                self.assertTrue(CL.read(html, doc).ok)


if __name__ == "__main__":
    unittest.main()
