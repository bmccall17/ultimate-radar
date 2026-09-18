"""An openness claim, rendered rather than assumed, and who it could not see.

`tools/audit_site.py` reads published JSON on purpose. This is the fourth place
that rule does not reach, after the accuracy sentence, the tag list and the
self-pass guard, and the reason is the same one: the data was right and the claim
built on it was not.

On p0001 at 15.867 s the separation card printed **5.1 yd** and badged it
`measured`. Every field behind that is honest - O4 and D6 are both `observed` on
frame 238, twelve of fourteen slots are anchored - and D5 is `predicted`, which
the file also says plainly. The card searched every defender with an estimate,
named the nearest, took its badge from those two players alone, and never
mentioned that one of the seven was a guess. A nearest-defender number is a
**minimum over the whole defensive set**: D5 could have been nearer, and nothing
on that card would have shown it.

So the seam is `opennessClaim(f, who)`: a frame and an attacker in, and out a
number, the defender it names, every defender outside `observed`/`confirmed`, and
one badge taken over all of them. `opennessCard(f, who)` sits on top of it and
holds the whole of what a reader is shown - the figure, that badge, the tail on
the context line and the sentence accounting for it - and that is what
`tools/openness.py` lifts, because a check on the claim alone stays green over a
card that quietly stops naming anybody. Issue #14; desired outcome 8 of #9.

Run them:

    python -m unittest discover -s tests -t .
"""

from __future__ import annotations

import json
import pathlib
import unittest

from tools import openness as OP
from tools import page_js as PJ

VIEWER = pathlib.Path("viewer/index.html")
HTML = VIEWER.read_text(encoding="utf-8")

needs_node = unittest.skipIf(PJ.node() is None, "node is not on PATH")

# The frame the ticket names. 15.867 s at 15 fps.
P0001_F = 238
P0001_RECEIVER = "O4"


def p0001() -> dict:
    """The published p0001, read back out of the site as a browser gets it."""
    from tools.audit_site import published
    doc = published("p0001")
    if doc is None:
        raise unittest.SkipTest("p0001 is not published")
    return doc


def synthetic(states: dict[str, str], n: int = 3) -> dict:
    """A possession where every slot holds one state and one position throughout.

    O1 sits at (50, 10) and the defence runs along y = 10 from D1 at x = 58 to D7
    at x = 79, three yards apart, so the nearest defender to O1 is D1 at 8 yd and
    each one after it is three further. The arithmetic is something a reader of
    this file can check by eye, which is the point of inventing the possession
    rather than reaching for a published one.
    """
    players = []
    for i in range(1, 8):
        players.append({"id": f"O{i}", "team": "sol", "state": [states.get(f"O{i}", "observed")] * n,
                        "est": [[50.0, 10.0 * i]] * n, "jersey": None})
    for i in range(1, 8):
        players.append({"id": f"D{i}", "team": "chill", "state": [states.get(f"D{i}", "observed")] * n,
                        "est": [[55.0 + 3 * i, 10.0]] * n, "jersey": None})
    return {"possession": {"id": "pTest", "fps": 15.0, "frames": n,
                           "offense": "sol", "defense": "chill"},
            "players": players, "events": []}


class Lifting(unittest.TestCase):
    """The page carries the claim, and its absence is loud."""

    def test_the_viewer_carries_the_function(self):
        self.assertTrue(PJ.extract(HTML, OP.FUNC).startswith(f"function {OP.FUNC}"))

    def test_the_state_sets_are_lifted_not_restated(self):
        # The whole check turns on which states count as seen. A copy of
        # MEASURABLE written here would agree with itself forever while the page
        # changed its mind, so the page's own line is what runs.
        src = OP.source(HTML)
        self.assertIn('const MEASURABLE = new Set(["observed", "confirmed"]);', src)

    def test_a_page_without_it_fails_loudly(self):
        # audit_site turns this into one red row. Silence would drop the row out
        # of the run and shrink the total with nobody the wiser.
        with self.assertRaises(ValueError):
            PJ.extract("<html>nothing here</html>", OP.FUNC)

    def test_a_const_wrapped_onto_a_second_line_fails_loudly(self):
        with self.assertRaises(ValueError):
            PJ.extract_const("const MEASURABLE = new Set([\n'observed']);", "MEASURABLE")


@needs_node
class TheClaim(unittest.TestCase):
    """What the claim says about one frame."""

    def test_every_defender_seen_measures(self):
        c = OP.claim(HTML, synthetic({}), 0, "O1")
        self.assertEqual(c["unseen"], [])
        self.assertEqual(c["nearest"], "D1")
        self.assertAlmostEqual(c["yd"], 8.0, places=6)
        self.assertEqual(c["ev"], "measured")

    def test_one_defender_unseen_is_named_and_downgrades(self):
        c = OP.claim(HTML, synthetic({"D7": "predicted"}), 0, "O1")
        self.assertEqual([u["slot"] for u in c["unseen"]], ["D7"])
        self.assertNotEqual(c["ev"], "measured")

    def test_an_unseen_defender_is_named_even_where_it_is_nowhere_near(self):
        # D7 sits 21 yd further out than D1 and is not the number. It is still
        # part of the set the number is a minimum over, which is why it is named.
        c = OP.claim(HTML, synthetic({"D7": "predicted"}), 0, "O1")
        self.assertEqual(c["nearest"], "D1")
        self.assertAlmostEqual(c["yd"], 8.0, places=6)

    def test_the_number_never_rests_on_a_defender_nobody_saw(self):
        # D1 is the nearest and is a guess. The number becomes the nearest
        # defender anybody SAW - a fact - rather than a distance to a dot the
        # tracker dead-reckoned there.
        c = OP.claim(HTML, synthetic({"D1": "predicted"}), 0, "O1")
        self.assertEqual(c["nearest"], "D2")
        self.assertAlmostEqual(c["yd"], 11.0, places=6)

    def test_no_defender_seen_at_all_is_no_number(self):
        blind = {f"D{i}": "predicted" for i in range(1, 8)}
        c = OP.claim(HTML, synthetic(blind), 0, "O1")
        self.assertIsNone(c["yd"])
        self.assertIsNone(c["nearest"])
        self.assertEqual(len(c["unseen"]), 7)

    def test_a_jersey_is_carried_so_the_card_can_name_a_person(self):
        doc = synthetic({"D7": "predicted"})
        for p in doc["players"]:
            if p["id"] == "D7":
                p["jersey"], p["jersey_source"] = 4, "voted"
        u = OP.claim(HTML, doc, 0, "O1")["unseen"][0]
        self.assertEqual((u["jersey"], u["jersey_source"]), (4, "voted"))


@needs_node
class WhatTheCardSays(unittest.TestCase):
    """The strings, not the numbers under them.

    `opennessClaim` deciding that a defender is unseen buys a reader nothing
    until the card says so, and #14 asks for a check on what *renders*. These
    read `opennessCard`, which is the whole of what the two cards are given.
    """

    def test_an_unseen_slot_is_named_on_the_line_a_reader_scans(self):
        c = OP.claim(HTML, synthetic({"D7": "predicted"}), 0, "O1")
        self.assertIn("D7", c["tail"])
        self.assertIn("unseen", c["tail"])

    def test_and_accounted_for_in_the_sentence_under_it(self):
        c = OP.claim(HTML, synthetic({"D7": "predicted"}), 0, "O1")
        self.assertIn("D7", c["why"])
        self.assertIn("not the nearest defender", c["why"])

    def test_a_defence_seen_whole_says_nothing_about_what_it_missed(self):
        c = OP.claim(HTML, synthetic({}), 0, "O1")
        self.assertEqual((c["tail"], c["why"]), ("", ""))

    def test_the_figure_is_the_card_s_own_formatting(self):
        # Not a Python `round()` of the number beside it: JS rounds half up and
        # Python half to even, and the value a reader gets is the page's.
        self.assertEqual(OP.claim(HTML, synthetic({}), 0, "O1")["value"], "8.0 yd")

    def test_no_number_prints_a_dash_and_says_why(self):
        blind = {f"D{i}": "predicted" for i in range(1, 8)}
        c = OP.claim(HTML, synthetic(blind), 0, "O1")
        self.assertEqual(c["value"], "—")
        self.assertIn("not a", c["why"])
        self.assertIn("place to measure from", c["why"])

    def test_a_voted_jersey_is_not_printed_as_a_reading(self):
        doc = synthetic({"D7": "predicted"})
        for p in doc["players"]:
            if p["id"] == "D7":
                p["jersey"], p["jersey_source"] = 4, "voted"
        self.assertIn("D7 #4 by vote", OP.claim(HTML, doc, 0, "O1")["why"])

    def test_a_jersey_somebody_read_is(self):
        doc = synthetic({"D7": "predicted"})
        for p in doc["players"]:
            if p["id"] == "D7":
                p["jersey"], p["jersey_source"] = 4, "read"
        why = OP.claim(HTML, doc, 0, "O1")["why"]
        self.assertIn("D7 #4", why)
        self.assertNotIn("by vote", why)

    def test_a_slot_read_as_two_numbers_borrows_neither(self):
        # `jerseyOf` refuses to resolve a conflict, and the prose must not
        # resolve it by falling through to the published number. The conflict is
        # the finding: the label is on two people.
        doc = synthetic({"D7": "predicted"})
        for p in doc["players"]:
            if p["id"] == "D7":
                p["jersey"], p["jersey_source"] = 4, "read"
        doc["identity_readings"] = [
            {"id": "j1", "slot": "D7", "f": 0, "t": 0.0, "jersey": 4},
            {"id": "j2", "slot": "D7", "f": 2, "t": 0.13, "jersey": 9},
        ]
        why = OP.claim(HTML, doc, 0, "O1")["why"]
        self.assertIn("read as two different jerseys", why)
        self.assertNotIn("#4", why)
        self.assertNotIn("#9", why)

    def test_a_reading_made_in_the_session_outranks_the_vote(self):
        doc = synthetic({"D7": "predicted"})
        for p in doc["players"]:
            if p["id"] == "D7":
                p["jersey"], p["jersey_source"] = 4, "voted"
        doc["identity_readings"] = [{"id": "j1", "slot": "D7", "f": 0, "t": 0.0,
                                     "jersey": 9}]
        why = OP.claim(HTML, doc, 0, "O1")["why"]
        self.assertIn("D7 #9", why)
        self.assertNotIn("by vote", why)


@needs_node
class TheFrameTheTicketNames(unittest.TestCase):
    """p0001 at 15.867 s: 5.1 yd, badged `measured`, with D5 left out."""

    def test_d5_is_named_as_unseen(self):
        c = OP.claim(HTML, p0001(), P0001_F, P0001_RECEIVER)
        self.assertIn("D5", [u["slot"] for u in c["unseen"]])

    def test_the_separation_is_no_longer_measured(self):
        c = OP.claim(HTML, p0001(), P0001_F, P0001_RECEIVER)
        self.assertNotEqual(c["ev"], "measured")

    def test_the_distance_itself_is_unchanged(self):
        # The number was never the defect. 5.1 yd to D6 is what the camera saw,
        # and it still prints - what changed is the badge on it and the sentence
        # beside it.
        c = OP.claim(HTML, p0001(), P0001_F, P0001_RECEIVER)
        self.assertEqual(c["nearest"], "D6")
        self.assertEqual(round(c["yd"], 1), 5.1)


@needs_node
class TheGateItself(unittest.TestCase):
    """`no measured claim over an unseen defender`, in both directions."""

    def test_a_clean_possession_passes_and_is_not_vacuous(self):
        s = OP.scan(HTML, synthetic({}))
        self.assertTrue(s.ok)
        # AD-11: a row whose pass does not depend on the thing it names is not a
        # check. If nothing measured, the pass above proved nothing.
        self.assertGreater(s.measured, 0)

    def test_blinding_a_defender_takes_every_measured_claim_away(self):
        doc = synthetic({})
        s = OP.scan(HTML, OP.blinded(doc, "D3"))
        self.assertEqual(s.measured, 0)
        self.assertTrue(s.ok)

    def test_the_positive_half_is_constructed_so_it_bites_on_every_page(self):
        # p0005 has one frame in 450 where all seven defenders were seen and it
        # does not clear the coverage bar, so p0005 makes no measured claim of
        # its own. Blinding a slot there takes nothing away from nothing, and a
        # row that passes having covered nothing is the thing AD-11 is about.
        # `sighted` hands the page a defence it can see whole, so both halves
        # have something to say.
        doc = p0001()
        self.assertGreater(OP.scan(HTML, OP.sighted(doc)).measured, 0)

    def test_sighted_moves_nobody(self):
        # It changes which states the page believes and not one position. A
        # probe that also moved the players would be measuring a different
        # possession from the one on the page.
        doc = p0001()
        self.assertEqual([p["est"] for p in OP.sighted(doc)["players"]],
                         [p["est"] for p in doc["players"]])

    def test_blinding_the_probe_takes_every_measured_claim_away(self):
        whole = OP.sighted(p0001())
        s = OP.scan(HTML, OP.blinded(whole, OP.a_seen_defender(whole)))
        self.assertEqual(s.measured, 0)

    def test_the_published_page_makes_no_measured_claim_over_an_unseen_slot(self):
        self.assertTrue(OP.scan(HTML, p0001()).ok)

    def test_a_blinded_slot_has_to_be_one_that_was_seen(self):
        doc = p0001()
        slot = OP.a_seen_defender(doc)
        self.assertIsNotNone(slot)
        self.assertTrue(any(s in ("observed", "confirmed")
                            for p in doc["players"] if p["id"] == slot
                            for s in p["state"]))

    def test_a_card_that_stopped_naming_the_unseen_would_fail_this(self):
        # The half the badge cannot cover. Leave the downgrade exactly as it is
        # and delete the naming, and a reader is told the number is weak without
        # being told who made it weak - which is the omission the ticket is
        # about, one layer up from the one it names.
        doc = synthetic({"D7": "predicted"})
        src = OP.source(HTML).replace("tail: unseenTail(op.unseen),", 'tail: "",')
        src = src.replace("why: unseenSentence(op)};", 'why: ""};')
        self.assertIn('tail: ""', src)          # the substitution took
        out = json.loads(PJ.run_source(
            OP._HARNESS.replace("__SRC__", src), {"doc": doc}, OP.FUNC))
        self.assertFalse(out["bad"])            # the badge is still right...
        self.assertTrue(out["unnamed"])         # ...and the reader is still short

    def test_a_claim_that_ignored_the_unseen_would_fail_this(self):
        # The defect, reconstructed: badge the two players the number names and
        # nobody else, which is what the card did. Frame 0 of this document has
        # D7 out of sight and O1-D1 both observed, so that badge is `measured`
        # and the scan has to call it.
        doc = synthetic({"D7": "predicted"})
        src = OP.source(HTML).replace(
            'const ev = evidence(f, [who, ...defs.map(d => d.id)].filter(Boolean));',
            'const ev = evidence(f, [who, nearest].filter(Boolean));')
        self.assertIn("evidence(f, [who, nearest]", src)   # the substitution took
        out = json.loads(PJ.run_source(
            OP._HARNESS.replace("__SRC__", src), {"doc": doc}, OP.FUNC))
        self.assertTrue(out["bad"])


if __name__ == "__main__":
    unittest.main()
