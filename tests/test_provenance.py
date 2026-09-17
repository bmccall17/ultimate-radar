"""Which tagged names a grader is allowed to see.

Run them:

    python -m unittest discover -s tests -t .

A tag's name comes back from the viewer, so it is the *tracker's* name for that
person (CONTEXT.md, Slot). Where the tracker's slot is on the wrong body the tag
is wrong and the tagger made no mistake, and grading the solver against it grades
the solver against its own upstream. `provenance` is the tagger's statement of
what carried the identity from a moment it was unambiguous to the tagged moment:
the footage, or the tracker.

Blinding strips the **name** and keeps the **moment**, because the moment is the
half a person can see (CONTEXT.md, Timing-only tag) and is not in doubt. A span
whose name is stripped is an unnamed span, which `ur.spans` already leaves
`fixed=None` and every grader already drops.

Like `test_inferred_names.py`, these run on invented dicts, and the interesting
property is not that they pass now - it is that they still fail when the
exclusion is taken away.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from ur import grading as GV
from ur import provenance as PV


def tag(t, player="O2", **kw):
    return {"t": t, "type": "catch", "player": player, "source": "human", **kw}


class BlindingEvents(unittest.TestCase):
    def test_a_name_the_tracker_supplied_does_not_reach_a_grader(self):
        ev = {"events": [tag(2.0, provenance=PV.TRACKER)]}
        out = PV.blind(ev)
        self.assertIsNone(out["events"][0]["player"])
        self.assertEqual(out["events"][0]["t"], 2.0)

    def test_a_tag_that_says_nothing_is_not_assumed_clean(self):
        # The whole corpus predates the field. Reading silence as `footage`
        # would grade the solver against the tags this exists to hold out.
        ev = {"events": [tag(2.0)]}
        self.assertIsNone(PV.blind(ev)["events"][0]["player"])

    def test_a_name_off_the_footage_survives(self):
        ev = {"events": [tag(2.0, provenance=PV.FOOTAGE)]}
        self.assertEqual(PV.blind(ev)["events"][0]["player"], "O2")

    def test_a_timing_only_tag_passes_through_untouched(self):
        ev = {"events": [tag(2.0, player=None)]}
        self.assertEqual(PV.blind(ev)["events"][0], tag(2.0, player=None))

    def test_an_unknown_carrier_is_refused_rather_than_ignored(self):
        with self.assertRaises(ValueError):
            PV.carried(tag(2.0, provenance="vibes"))


class Fault(unittest.TestCase):
    def test_the_three_faults_are_named_for_their_source(self):
        self.assertEqual(set(PV.FAULTS), {"tagger", "tracker", "roster"})

    def test_an_unknown_fault_is_refused(self):
        with self.assertRaises(ValueError):
            PV.fault({"was": "O5", "now": "O1", "fault": "gremlins"})

    def test_a_superseded_tag_grades_on_the_name_it_now_carries(self):
        # The block records what it was. What it *is* is the `player` field, and
        # nothing reads the old value back into a grade.
        t = tag(2.0, player="O1", provenance=PV.FOOTAGE,
                superseded={"was": "O5", "now": "O1", "at": "2026-09-15",
                            "fault": "tracker", "why": "the tracker lost O1"})
        self.assertTrue(PV.grades(t))
        self.assertEqual(PV.blind({"events": [t]})["events"][0]["player"], "O1")


class ReadOnTheWayIn(unittest.TestCase):
    """Every provenance word in the file is read when a grader loads it.

    A typo reads as "nothing said", which excludes the span — the safe direction
    and still wrong, because nobody would find out. `ur.resolve` refuses an
    unknown correction op for the same reason.
    """

    def test_a_misspelt_carrier_stops_the_read(self):
        with self.assertRaises(ValueError):
            PV.blind({"events": [tag(2.0, provenance="fotage")]})

    def test_a_misspelt_fault_stops_the_read(self):
        with self.assertRaises(ValueError):
            PV.blind({"events": [tag(2.0, provenance=PV.FOOTAGE,
                                     superseded={"was": "O5", "fault": "trackr"})]})

    def test_a_misspelt_stated_stops_the_read(self):
        with self.assertRaises(ValueError):
            PV.blind({"events": [tag(2.0, provenance_stated="later")]})

    def test_the_corpus_as_it_stands_reads_clean(self):
        for pid in ("p0001", "p0003", "p0009"):
            PV.check(GV.read_events(Path("work") / pid))
