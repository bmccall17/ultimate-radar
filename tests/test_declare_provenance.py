"""Deriving what carried a name from the jersey somebody read.

Run them:

    python -m unittest discover -s tests -t .

`CONTEXT.md` is blunt that a jersey number cannot be turned into a slot without
tracking continuity to carry it. So a reading at f212 and a tag at f319 do not
make that tag an observation: whatever joins them is the tracker's, which is the
contamination this ticket is about, one step further back.

What does resolve a name is a reading taken **inside the span the tag bounds**.
There the person holding the disc and the person whose shirt was read are the
same person at the same moment, and nothing has to be carried anywhere.

Everything else stays `tracker` and drops out of the graded sample. That is not a
defeat: it says precisely what to do next, which is read a number during the span
you want graded.
"""

from __future__ import annotations

import unittest

from ur import provenance as PV

FPS = 15.0


def ev(*marks):
    return {"events": [{"t": t, "type": k, "player": p, "source": "human"}
                       for t, k, p in marks]}


def ident(*readings):
    return {"readings": [{"slot": s, "f": f, "jersey": j}
                         for s, f, j in readings]}


class Deriving(unittest.TestCase):
    def test_a_reading_inside_the_span_makes_that_tag_footage(self):
        # Caught at 2 s, threw at 6 s, shirt read at 4 s. Same person, same
        # moment, nothing carried.
        out = PV.derive(ev((2.0, "catch", "O4"), (6.0, "throw", "O4")),
                        ident(("O4", 60, 5)), FPS)
        self.assertEqual([e[PV.KEY] for e in out["events"]],
                         [PV.FOOTAGE, PV.FOOTAGE])

    def test_a_reading_outside_every_span_carries_nothing(self):
        # Read at 14 s, tagged at 2-6 s. The tracker is what joins them.
        out = PV.derive(ev((2.0, "catch", "O4"), (6.0, "throw", "O4")),
                        ident(("O4", 210, 5)), FPS)
        self.assertEqual([e[PV.KEY] for e in out["events"]],
                         [PV.TRACKER, PV.TRACKER])

    def test_a_reading_on_another_slot_says_nothing_about_this_one(self):
        out = PV.derive(ev((2.0, "catch", "O4"), (6.0, "throw", "O4")),
                        ident(("O1", 60, 28)), FPS)
        self.assertEqual(out["events"][0][PV.KEY], PV.TRACKER)

    def test_a_derived_declaration_says_it_was_reconstructed(self):
        # It was worked out afterwards from a file, not stated while looking.
        out = PV.derive(ev((2.0, "catch", "O4"), (6.0, "throw", "O4")),
                        ident(("O4", 60, 5)), FPS)
        self.assertEqual(out["events"][0][PV.WHEN_KEY], PV.RECONSTRUCTED)

    def test_a_timing_only_tag_is_left_alone(self):
        out = PV.derive(ev((2.0, "catch", None)), ident(("O4", 30, 5)), FPS)
        self.assertNotIn(PV.KEY, out["events"][0])

    def test_a_declaration_already_in_the_file_is_not_overwritten(self):
        # A person who stated it while looking outranks anything derived here.
        e = ev((2.0, "catch", "O4"), (6.0, "throw", "O4"))
        e["events"][0][PV.KEY] = PV.FOOTAGE
        e["events"][0][PV.WHEN_KEY] = PV.AT_TAGGING
        out = PV.derive(e, ident(("O4", 210, 5)), FPS)
        self.assertEqual(out["events"][0][PV.WHEN_KEY], PV.AT_TAGGING)
