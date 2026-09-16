"""The difference between a gate and a measurement, on invented rows.

Run them:

    python -m unittest discover -s tests -t .

`tools/gates.py` prints 132 rows and 24 of them were built with an unconditional
pass, which counted them into a green total that a reader then trusted. A row
that cannot fail is not a gate (`docs/31`: an issue closes when a named check
flips to PASS, and a row that can never flip has nothing to flip). This module is
the shape the two kinds land in, and these are the tests for it - pure logic over
a handful of dicts, which is the one thing this project unit-tests rather than
grading against the footage.
"""

from __future__ import annotations

import unittest

from tools import checks as C


class Gate(unittest.TestCase):
    def test_carries_a_verdict(self):
        g = C.gate("roster structure", True, "0 problems", "zero, always")
        self.assertIs(g["pass"], True)
        self.assertEqual(g["name"], "roster structure")

    def test_verdict_is_a_real_bool(self):
        # numpy comparisons come back as np.bool_, which is not `is True`.
        import numpy as np
        g = C.gate("median roster in shot", np.median([8, 8, 9]) >= 6, "8", ">= 6")
        self.assertIs(g["pass"], True)
        self.assertIsInstance(g["pass"], bool)

    def test_can_fail(self):
        self.assertIs(C.gate("n", False, "60%", "<= 35%")["pass"], False)


class Measurement(unittest.TestCase):
    def test_has_no_verdict_at_all(self):
        # Not `"pass": True` - absent. A row that cannot fail must not be
        # readable as one that passed, and the absent key is what guarantees it:
        # anything totalling `c["pass"]` raises here instead of counting a 25th
        # green row that nobody measured.
        m = C.measurement("...measured on", "62% of frames", "no threshold")
        self.assertNotIn("pass", m)

    def test_carries_why_it_cannot_be_gated(self):
        m = C.measurement("offence drifts", "+3.1 yd",
                          "drift is not the attacking direction")
        self.assertEqual(m["why"], "drift is not the attacking direction")
        self.assertEqual(m["got"], "+3.1 yd")

    def test_refuses_a_row_with_no_reason(self):
        # The reason is the whole point: docs/30 has to say why each one cannot
        # be made failable today, and a measurement that will not name its reason
        # is a gate somebody could not be bothered to write.
        with self.assertRaises(ValueError):
            C.measurement("...quarters confirmed", "0 of 4", "")


class Kind(unittest.TestCase):
    def test_tells_them_apart(self):
        self.assertTrue(C.is_gate(C.gate("a", True, "", "")))
        self.assertFalse(C.is_gate(C.measurement("b", "", "why")))
        self.assertTrue(C.is_measurement(C.measurement("b", "", "why")))
        self.assertFalse(C.is_measurement(C.gate("a", True, "", "")))

    def test_refuses_a_row_that_is_neither(self):
        with self.assertRaises(ValueError):
            C.is_gate({"name": "hand-rolled", "got": "7"})


class Tally(unittest.TestCase):
    ROWS = [
        C.gate("a", True, "", ""),
        C.gate("b", False, "", ""),
        C.gate("c", True, "", ""),
        C.measurement("d", "62%", "no threshold"),
        C.measurement("e", "0 of 4", "a queue, not a defect"),
    ]

    def test_counts_each_kind(self):
        t = C.tally([{"checks": self.ROWS}])
        self.assertEqual((t.passed, t.failed, t.measured), (2, 1, 2))

    def test_failable_excludes_measurements(self):
        t = C.tally([{"checks": self.ROWS}])
        self.assertEqual(t.failable, 3)
        self.assertEqual(t.failable + t.measured, len(self.ROWS))

    def test_adds_up_across_reports(self):
        t = C.tally([{"checks": self.ROWS}, {"checks": self.ROWS}])
        self.assertEqual((t.passed, t.failed, t.measured), (4, 2, 4))

    def test_a_run_of_measurements_alone_is_not_a_pass(self):
        t = C.tally([{"checks": [C.measurement("d", "62%", "no threshold")]}])
        self.assertEqual((t.passed, t.failed, t.failable), (0, 0, 0))
        self.assertEqual(t.exit_code, 0)

    def test_exit_code_follows_the_failable_only(self):
        self.assertEqual(C.tally([{"checks": self.ROWS}]).exit_code, 1)
        self.assertEqual(C.tally([{"checks": [C.gate("a", True, "", "")],
                                   }]).exit_code, 0)


class Render(unittest.TestCase):
    def test_a_gate_says_its_verdict(self):
        self.assertIn("[PASS]", C.render(C.gate("a", True, "0", "zero")))
        self.assertIn("[FAIL]", C.render(C.gate("a", False, "1", "zero")))

    def test_a_measurement_says_neither(self):
        line = C.render(C.measurement("...measured on", "62% of frames",
                                      "no threshold"))
        self.assertNotIn("PASS", line)
        self.assertNotIn("FAIL", line)

    def test_a_measurement_shows_its_number_and_its_reason(self):
        line = C.render(C.measurement("offence drifts", "+3.1 yd",
                                      "drift is not the attacking direction"))
        self.assertIn("+3.1 yd", line)
        self.assertIn("drift is not the attacking direction", line)

    def test_a_measurement_never_says_want(self):
        # `want` is a threshold, and a row with no threshold must not print one -
        # "want reported, not gated" is how the 24 got read as gates in the first
        # place.
        self.assertNotIn("want", C.render(C.measurement("a", "7", "no threshold")))

    def test_rows_line_up(self):
        a = C.render(C.gate("name here", True, "got", "want"))
        b = C.render(C.measurement("name here", "got", "why"))
        self.assertEqual(a.index("name here"), b.index("name here"))


class Totals(unittest.TestCase):
    def test_reports_both_kinds_separately(self):
        out = C.totals(C.Tally(passed=94, failed=14, measured=24))
        self.assertIn("94 of 108 failable check(s) pass", out)
        self.assertIn("24 informational row(s)", out)
        # Never one number for 132 rows: that total is the thing this replaced.
        self.assertNotIn("132", out)

    def test_a_clean_run_does_not_point_at_deliberate_failures(self):
        out = C.totals(C.Tally(passed=42, failed=0, measured=3))
        self.assertIn("42 of 42 failable check(s) pass.", out)
        self.assertNotIn("deliberate", out)
