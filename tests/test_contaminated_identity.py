"""The probe that a tracker-supplied name cannot move a grade.

Run them:

    python -m unittest discover -s tests -t .

AD-13's position probe moves every marker twelve yards and requires the numbers
not to follow. This is the same argument about the other half of what a person
supplies, and it took two goes to aim it correctly.

**It mangles the names that are already excluded.** Putting a wrong name on a tag
that *grades* takes that tag out of the sample, so the number moves for a
perfectly good reason and the probe reports a leak that is not one. Putting one
on a tag that is already excluded must change nothing at all, because that tag
was never in the sample — which is exactly what #4 claims, tested head on.

Four runs, and the fourth is what stops this being a row that cannot fail: the
mangled names must move the *unblinded* grade, or the probe reached nothing and
the agreement between the blinded runs says nothing (AD-11).
"""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest import mock

from tools import human_positions as HP
from ur import grading as GV
from ur import provenance as PV


def tag(t, kind, player, **kw):
    return {"t": t, "type": kind, "player": player, "source": "human", **kw}


class Contaminating(unittest.TestCase):
    def test_a_name_the_tracker_supplied_comes_back_wrong(self):
        ev = {"events": [tag(1.0, "catch", "O2", provenance=PV.TRACKER)]}
        got = HP.contaminated(ev, ["O1", "O2", "O3"])["events"][0]
        self.assertNotEqual(got["player"], "O2")
        self.assertEqual(got["t"], 1.0)

    def test_a_tag_with_no_provenance_is_mangled_too(self):
        # Silence reads as `tracker`, so these are excluded and therefore the
        # ones worth probing. Today that is all 32 of them.
        ev = {"events": [tag(1.0, "catch", "O2")]}
        self.assertNotEqual(
            HP.contaminated(ev, ["O1", "O2"])["events"][0]["player"], "O2")

    def test_a_tag_that_grades_is_left_exactly_alone(self):
        # Mangling this one would shrink the denominator, and the probe would
        # read its own damage as a leak.
        ev = {"events": [tag(1.0, "catch", "O2", provenance=PV.FOOTAGE)]}
        self.assertEqual(HP.contaminated(ev, ["O1", "O2"]), ev)

    def test_a_timing_only_tag_passes_through(self):
        ev = {"events": [tag(1.0, "catch", None)]}
        self.assertEqual(HP.contaminated(ev, ["O1", "O2"]), ev)

    def test_the_contamination_is_the_same_on_every_run(self):
        # AGENTS rule 6: a number that moves between runs is not a measurement,
        # and neither is a probe.
        ev = {"events": [tag(1.0, "catch", "O2")]}
        ids = ["O1", "O2", "O3"]
        self.assertEqual(HP.contaminated(ev, ids), HP.contaminated(ev, ids))

    def test_a_mangled_name_does_not_survive_the_view(self):
        ev = {"events": [tag(1.0, "catch", "O2")]}
        out = PV.blind(HP.contaminated(ev, ["O1", "O2", "O3"]))
        self.assertIsNone(out["events"][0]["player"])


class Verdicts(unittest.TestCase):
    """The probe's answers on a possession the graders actually run over.

    p0003 rather than an invented dict, because `grade_spans` solves real spans
    over real positions and a hand-built document would be testing the fixture.
    The tags are varied in memory; nothing on disk is touched.
    """

    WORK = Path("work/p0003")

    def declared(self, carrier):
        ev = GV.read_events(self.WORK)
        return {**ev, "events": [{**e, PV.KEY: carrier} if e.get("player") else e
                                 for e in ev["events"]]}

    def doc(self):
        return GV.load(self.WORK, blinded=False)[0]

    def verdict(self, ev):
        return HP.identity_verdict(self.WORK, self.doc(), ev)[0]

    def test_the_corpus_as_it_stands_demonstrates_the_exclusion(self):
        # No tag carries provenance, so every one is excluded and every one gets
        # a wrong name. The blinded grade must not move and the unblinded one
        # must. That is the exclusion working, and it is what the gate asserts.
        self.assertEqual(self.verdict(GV.read_events(self.WORK)), "excluded")

    def test_names_declared_off_the_tracker_are_the_same_case(self):
        self.assertEqual(self.verdict(self.declared(PV.TRACKER)), "excluded")

    def test_names_all_off_the_footage_leave_nothing_to_probe(self):
        # Nothing is excluded, so there is no contamination to test for, and
        # saying "excluded" here would be a pass that tested nothing (AD-11).
        self.assertEqual(self.verdict(self.declared(PV.FOOTAGE)), "unreachable")

    def test_taking_the_exclusion_away_turns_the_row_red(self):
        # The property the prior art insists on: a check earns its place by
        # failing when the fix is gone. With `ur.provenance.blind` neutered, the
        # mangled names reach the grade and the probe must say so.
        with mock.patch.object(PV, "blind", side_effect=lambda ev: ev):
            self.assertEqual(self.verdict(GV.read_events(self.WORK)), "leaked")
