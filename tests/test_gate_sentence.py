"""The accuracy sentence a reader gets, rendered rather than inferred.

`tools/audit_site.py` reads the published JSON on purpose: what a page asserts
lives in its data, and matching strings against HTML once flagged a phrase that
survived only inside a code comment. This module is the one exception, and the
defect it exists to catch is the argument for it.

Five published pages printed a rounded `0 %` for recall and for sigma
containment. The fields behind those numbers were `null` - nobody measured
recall on those possessions - and `Math.round(null*100)` is `0`. Every check
that read the data was green, because the data was right. The sentence was the
lie. `docs/30` § 2.7 carries the finding.

So the seam under test runs the viewer's own `gateSentence` under node and hands
back the string, and the test for a number nobody measured is to render the page
a second time with every measurement taken away and see what still prints.

Run them:

    python -m unittest discover -s tests -t .
"""

from __future__ import annotations

import pathlib
import unittest

from tools import gate_sentence as GS

VIEWER = pathlib.Path("viewer/index.html")


def doc(**gates) -> dict:
    """The least possession document `gateSentence` needs: gates and a roster.

    The denominators are here because AD-13 made them load-bearing: a figure
    prints its value AND its sample size or it prints neither, so a fixture
    carrying only `per_player_recall` renders no percentage at all. They default
    to the real ones - 234 labelled players, 40 sigma samples - and a test that
    wants them gone takes them away itself.
    """
    g = {"document": "docs/17-m4-tracking.md", "measured_on": "p0001",
         "per_player_recall": None, "per_player_recall_n": 234,
         "sigma_containment": None, "sigma_containment_n": 40,
         "identity_switches_caught": None, **gates}
    return {"gates_measured": True, "gates": g,
            "possession": {"id": "p0003"},
            "players": [{"id": "O1", "state": ["observed", "provisional"]},
                        {"id": "O2", "state": ["observed", "observed"]}]}


class Extract(unittest.TestCase):
    def test_finds_the_function_in_the_viewer(self):
        src = GS.extract(VIEWER.read_text(encoding="utf-8"), GS.FUNC)
        self.assertTrue(src.startswith("function gateSentence"))
        self.assertTrue(src.rstrip().endswith("}"))

    def test_says_so_when_the_page_has_no_sentence(self):
        # audit_site turns this into one red row rather than a traceback, so it
        # has to be an exception and not a silent empty string.
        with self.assertRaises(ValueError):
            GS.extract("<html><body>nothing here</body></html>", GS.FUNC)


class Percentages(unittest.TestCase):
    def test_reads_through_markup(self):
        self.assertEqual(GS.percentages("<b>Recall</b> 97 % and <i>83 %</i>"),
                         ["97", "83"])

    def test_ignores_a_percent_hidden_in_a_tag(self):
        self.assertEqual(GS.percentages('<a href="?x=50%">none here</a>'), [])


class Blanking(unittest.TestCase):
    def test_removes_every_measurement_and_nothing_else(self):
        d = doc(per_player_recall=0.9744, sigma_containment=0.829)
        b = GS.blanked(d)
        self.assertEqual([b["gates"][k] for k in GS.MEASURED_FIELDS], [None, None])
        self.assertEqual(b["gates"]["measured_on"], "p0001")
        self.assertEqual(b["players"], d["players"])

    def test_leaves_the_original_alone(self):
        d = doc(per_player_recall=0.9744)
        GS.blanked(d)
        self.assertEqual(d["gates"]["per_player_recall"], 0.9744)

    def test_measured_names_the_fields_that_carry_a_number(self):
        self.assertEqual(GS.measured(doc()), [])
        self.assertEqual(GS.measured(doc(per_player_recall=0.0)),
                         ["per_player_recall"])

    def test_a_measured_zero_is_a_measurement(self):
        # The distinction the defect lost: 0.0 was measured, None was not.
        self.assertEqual(GS.measured(doc(sigma_containment=0.0)),
                         ["sigma_containment"])


@unittest.skipUnless(GS.node(), "node is not on PATH")
class Render(unittest.TestCase):
    """Against the real viewer, because the point is what the viewer does."""

    @classmethod
    def setUpClass(cls):
        cls.html = VIEWER.read_text(encoding="utf-8")

    def test_an_unmeasured_possession_prints_no_number(self):
        d = doc()
        self.assertEqual(GS.percentages(GS.render(self.html, d)), [])

    def test_an_unmeasured_possession_says_it_is_unmeasured(self):
        # Printing no number is only half of it. A gap where a figure would go
        # reads as "fine"; the page has to say the accuracy is unknown.
        self.assertIn(GS.UNMEASURED, GS.render(self.html, doc()).lower())

    def test_an_unmeasured_possession_names_where_the_numbers_came_from(self):
        self.assertIn("p0001", GS.render(self.html, doc()))

    def test_a_measured_possession_still_quotes_its_numbers(self):
        d = doc(measured_on="p0003", per_player_recall=0.9744,
                sigma_containment=0.829)
        self.assertEqual(GS.percentages(GS.render(self.html, d)), ["97", "83"])

    def test_the_unreviewed_re_acquisitions_are_still_counted(self):
        # docs/25 R4: silence here would read as "the queue is empty".
        self.assertIn("1 re-acquisition", GS.render(self.html, doc()))

    def test_a_page_that_predates_the_measurements_has_no_sentence(self):
        d = doc()
        d["gates_measured"] = False
        self.assertEqual(GS.render(self.html, d), "")

    def test_nothing_is_printed_off_nothing(self):
        d = doc(measured_on="p0003", per_player_recall=0.9744,
                sigma_containment=0.829)
        self.assertEqual(GS.invented(self.html, d), [])

    def test_the_defect_itself_would_be_caught(self):
        """The viewer as it was before #11, rendered against the same document.

        This is the test that would have gone red, and it goes red for the
        *measured* possession too - p0001 printed `97 %` honestly while the code
        behind it was one null away from printing `0 %`. Taking the measurement
        away is what exposes that, and comparing printed values against expected
        ones never would.
        """
        # The guard moved with AD-13 and the patch moves with it. Breaking
        # `num` alone no longer reintroduces the defect - `pct` still compares
        # `=== null` and catches it - so the breakage goes where the decision
        # now lives, which is `pct` itself. It reopens both wounds at once: a
        # null rounded to 0 %, and a figure printed with no sample behind it.
        broken = self.html.replace(
            'const pct = (v, n) => (num(v)===null || num(n)===null)\n'
            '      ? null : `${Math.round(v*100)} % of ${n}`;',
            'const pct = (v, n) => `${Math.round(v*100)} % of ${n}`;')
        self.assertNotEqual(broken, self.html, "the guard has moved; fix the patch")
        self.assertEqual(GS.invented(broken, doc()), ["0", "0"])


if __name__ == "__main__":
    unittest.main()
