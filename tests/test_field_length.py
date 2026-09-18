"""Which of two things the lines across the field are, and whether a reader is told.

#7 was read as "every field coordinate depends on this", and it does not.
`ur/calibrate/world.py` registers to the soccer centre circle and the halfway
line, both FIFA dimensions, so the length of a yard comes from the circle. What
`length_yd` decides is where `goal_lines` puts the ultimate goal lines inside
that frame, and therefore every claim measured against an endzone.

Across thirteen cuts, no possession's paint shows a line within a yard of where
either a 120 yd or a 110 yd field would put a goal line, so the published goal
lines are declared from the rulebook. The tests here are about saying so: the
page has to print which of the two it is, and the printing has to rest on the
data rather than on prose somebody typed.

    python -m unittest discover -s tests -t .
"""

from __future__ import annotations

import copy
import pathlib
import unittest

from tools import audit_site as AS
from tools import field_length as FL
from tools import page_js as PJ

VIEWER = pathlib.Path("viewer/index.html")
HTML = VIEWER.read_text(encoding="utf-8")

needs_node = unittest.skipIf(PJ.node() is None, "node is not on PATH")

# The shape `ur/calibrate/venue.py::decide_field_length` writes. Invented here
# rather than read out of `work/`, which is gitignored broadcast footage and so
# is a thing only one machine can run a test against.
UNRESOLVED = {
    "field_length": {
        "field_length_yd": None,
        "verdict": "unresolved",
        "why": "no line of constant x was found at a plausible goal-line distance",
        "all_x_peaks": [
            {"x_yd": -0.05, "count": 48900.7, "prominence": 19.49},   # halfway
            {"x_yd": +38.15, "count": 737.3, "prominence": 4.72},
            {"x_yd": +43.15, "count": 649.7, "prominence": 4.42},
        ],
    },
    "frames": [{"confidence": 0.9}] * 100 + [{"confidence": 0.1}] * 20,
}

RESOLVED = {
    "field_length": {
        "field_length_yd": 120.0,
        "verdict": "120",
        "why": "a line at 40.05 yd from the halfway line",
        "all_x_peaks": [
            {"x_yd": -0.05, "count": 48900.7, "prominence": 19.49},
            {"x_yd": +40.05, "count": 9000.0, "prominence": 9.0},
        ],
        "sample": {"frames": 169, "paint_points": 413529, "bin_yd": 0.1},
    },
    "frames": [{"confidence": 0.9}] * 100,
}


def field(cal: dict) -> dict:
    """What `tools/make_view.py` bakes onto the page."""
    return {"length_yd": 120.0, "width_yd": 53.333, "endzone_yd": 20.0,
            "brick_yd": 20.0, "length_source": FL.provenance(cal),
            "length_evidence": FL.evidence(cal)}


class WhichOfTwoThingsItIs(unittest.TestCase):
    def test_a_verdict_nobody_reached_is_declared(self):
        self.assertEqual(FL.provenance(UNRESOLVED), FL.DECLARED)

    def test_a_measured_length_is_observed(self):
        self.assertEqual(FL.provenance(RESOLVED), FL.OBSERVED)

    def test_a_calibration_with_no_field_length_block_is_declared(self):
        # "Nobody has looked" and "somebody looked and found nothing" are both
        # short of an observation, and only one of them may print a goal line
        # as though it were seen.
        self.assertEqual(FL.provenance({}), FL.DECLARED)


class WhatThePeaksSay(unittest.TestCase):
    def test_the_halfway_line_is_not_a_candidate(self):
        xs = [p["x_yd"] for p in FL.peaks(UNRESOLVED)]
        self.assertEqual(xs, [38.15, 43.15])

    def test_each_peak_carries_its_distance_from_both_hypotheses(self):
        p = FL.peaks(UNRESOLVED)[0]
        self.assertAlmostEqual(p["err_if_120_yd"], 1.85)
        self.assertAlmostEqual(p["err_if_110_yd"], 3.15)
        self.assertIsNone(p["votes"], "1.85 yd is outside the 1.0 yd tolerance")

    def test_a_peak_on_the_line_votes(self):
        self.assertEqual(FL.peaks(RESOLVED)[0]["votes"], "120")

    def test_a_rejected_peak_is_still_reported(self):
        # `decide_field_length` drops a peak carrying under 5 % of the halfway
        # line's support, correctly. Reporting only what survived that rule
        # would have hidden the pair at 38 and 42.5 that recurs across eight
        # possessions, which is the finding in docs/30 section 2.21.
        share = FL.peaks(UNRESOLVED)[0]["share_of_halfway"]
        self.assertLess(share, 0.05)
        self.assertIn(38.15, [p["x_yd"] for p in FL.peaks(UNRESOLVED)])


class TheDenominator(unittest.TestCase):
    """#7's caution: the endzone-framed footage is where calibration is weakest,
    so a verdict without its sample is not a measurement."""

    def test_an_old_calibration_admits_the_sample_is_not_recorded(self):
        s = FL.sample(UNRESOLVED)
        self.assertFalse(s["recorded"])
        self.assertIsNone(s["frames"])
        # An upper bound is offered instead, and never as the number: the map
        # takes every second confident frame that has paint in it.
        self.assertEqual(s["confident_frames"], 100)
        self.assertEqual(s["upper_bound_frames"], 50)

    def test_a_new_calibration_carries_the_real_one(self):
        s = FL.sample(RESOLVED)
        self.assertTrue(s["recorded"])
        self.assertEqual((s["frames"], s["paint_points"]), (169, 413529))


class TheRows(unittest.TestCase):
    def test_a_declared_page_passes_and_an_unlabelled_one_does_not(self):
        ok = {r["name"]: r for r in FL.rows("p0003", field(UNRESOLVED))}
        self.assertTrue(ok["goal lines say which they are"]["pass"])
        bare = {k: v for k, v in field(UNRESOLVED).items()
                if k != "length_source"}
        bad = {r["name"]: r for r in FL.rows("p0003", bare)}
        self.assertFalse(bad["goal lines say which they are"]["pass"])

    def test_observed_without_a_measurement_is_refused(self):
        # The label is the whole of what this ticket delivers, so the one way to
        # cheat it is to type the stronger word.
        f = field(UNRESOLVED)
        f["length_source"] = FL.OBSERVED
        r = {c["name"]: c for c in FL.rows("p0003", f)}
        self.assertFalse(r["goal lines say which they are"]["pass"])

    def test_the_paint_row_reports_and_never_judges(self):
        r = {c["name"]: c for c in FL.rows("p0003", field(UNRESOLVED))}
        row = r["...goal lines found in the paint"]
        self.assertNotIn("pass", row, "no threshold exists, so it cannot be a gate")
        self.assertIn("0 of 2", row["got"])


@needs_node
class WhatThePageSays(unittest.TestCase):
    def test_a_declared_page_says_declared_and_says_why(self):
        said = PJ.strip_markup(FL.render(HTML, field(UNRESOLVED)))
        self.assertIn("declared", said.lower())
        self.assertIn("dashed", said.lower())
        # The denominator travels with the claim. A reader told nobody saw a
        # goal line, with no sample, cannot tell one frame from four hundred.
        self.assertIn("50", said)

    def test_an_observed_page_says_observed(self):
        said = PJ.strip_markup(FL.render(HTML, field(RESOLVED)))
        self.assertIn("observed", said.lower())
        self.assertNotIn("declared", said.lower())

    def test_it_says_nothing_without_the_data(self):
        # The ablation, and the whole reason this runs the page rather than
        # reading the field. A sentence that survives its data being removed is
        # prose somebody typed that happens to be true today.
        bare = {k: v for k, v in field(UNRESOLVED).items()
                if k != "length_source"}
        self.assertEqual(FL.render(HTML, bare).strip(), "")

    def test_the_row_reads_the_rendered_sentence(self):
        r = {c["name"]: c for c in FL.rows("p0003", field(UNRESOLVED), HTML)}
        self.assertTrue(r["the page says which they are"]["pass"])

    def test_a_page_that_has_lost_the_sentence_fails_loudly(self):
        r = {c["name"]: c
             for c in FL.rows("p0003", field(UNRESOLVED), "<html>nothing</html>")}
        self.assertFalse(r["the page says which they are"]["pass"])


@needs_node
class OnTheRealSite(unittest.TestCase):
    """The published pages, because the site is the deliverable (AGENTS rule 7)."""

    def test_every_published_page_says_which_they_are(self):
        pages = [p for p in ("p0001", "p0003", "p0004", "p0005", "p0009", "p0015")
                 if AS.published(p)]
        self.assertTrue(pages, "docs/ is not built")
        for pid in pages:
            with self.subTest(pid):
                doc = AS.published(pid)
                idx = AS.site_path(pid, "index.html")
                rows = FL.rows(pid, doc.get("field"),
                               idx.read_text(encoding="utf-8"))
                for c in rows:
                    if "pass" in c:
                        self.assertTrue(c["pass"], f"{pid}: {c['name']}: {c['got']}")

    def test_no_published_page_claims_it_observed_a_goal_line(self):
        # Not a requirement, a record. The day footage exists that settles it,
        # this test is the one that has to change, and changing it is how
        # somebody notices the claim on the page got stronger.
        for pid in ("p0001", "p0003", "p0004", "p0005", "p0009", "p0015"):
            doc = AS.published(pid)
            if not doc:
                continue
            with self.subTest(pid):
                self.assertEqual((doc.get("field") or {}).get("length_source"),
                                 FL.DECLARED)


if __name__ == "__main__":
    unittest.main()
