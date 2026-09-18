"""One decision about a slot's number, and the places that show it.

`jerseyOf` resolves the readings and refuses to guess: one number across every
reading is the slot's jersey, two different numbers is not a tie to break but the
finding. What sits on top of it - the published number, and whether an OCR vote
or a person produced it - was written out three times, in `railJersey`,
`railTitle` and `unseenName`, and kept in step by hand.

Nothing had drifted. The argument for pulling it into `jerseyFact` is #22, which
adds a **fourth** source - the seven jerseys per team recorded in the sitting -
to a rule held in three copies, while its own acceptance criteria are that rule:
a jersey or an explicit unknown for every slot, and never a number nobody read.
Four inputs against three copies is how one surface ends up saying `unknown`
while another still shows the vote.

`tests/test_openness.py::WhatTheCardSays` covers the prose presentation and was
written before the extraction, so it passing unchanged is what says the cards did
not move. This file covers the decision itself and the rail's column, which had
no test at all.

A second, smaller rule came out with it. `slotLabel` is `D5 #4` or `D5`, and it
was built by hand in four more places - the overlay label, the relabel dropdown,
the Selected Player header and the rail's hover - each of them testing the number
for truthiness, which is false for **0**. Nobody had seen it because no published
possession carries a jersey 0, and 0 and 00 are both legal numbers.

Run them:

    python -m unittest discover -s tests -t .
"""

from __future__ import annotations

import json
import pathlib
import unittest

from tools import page_js as PJ

VIEWER = pathlib.Path("viewer/index.html")
HTML = VIEWER.read_text(encoding="utf-8")

needs_node = unittest.skipIf(PJ.node() is None, "node is not on PATH")

# What the two functions read. `JERSEY` is seeded the way viewer/index.html seeds
# it at load, from `identity_readings`, rather than invented here.
FUNCS = ("readingsFor", "jerseyOf", "jerseyFact", "railJersey", "slotLabel")

_HARNESS = """\
const IN = require(process.argv[2]);
const JERSEY = (IN.readings || []).slice();
__SRC__
process.stdout.write(JSON.stringify({
  fact: jerseyFact(IN.slot, IN.published),
  rail: railJersey(IN.published),
  label: slotLabel(IN.published),
}));
"""


def ask(slot="D5", readings=(), **published):
    """What the page makes of one slot, given its readings and published fields.

    `published` is spread rather than passed whole so a case reads as the fact it
    is testing: `ask(jersey=4, jersey_source="voted")` is a slot carrying a vote.
    """
    src = "\n".join(PJ.extract(HTML, f) for f in FUNCS)
    return json.loads(PJ.run_source(
        _HARNESS.replace("__SRC__", src),
        {"slot": slot, "readings": list(readings),
         "published": {"id": slot, **published}}, "jerseyFact"))


def reading(slot, jersey, f=0):
    return {"id": f"j{f}", "slot": slot, "f": f, "t": f / 15.0, "jersey": jersey}


@needs_node
class TheDecision(unittest.TestCase):
    """Four answers, and which one is right."""

    def test_nothing_at_all(self):
        self.assertEqual(ask()["fact"], {"kind": "none"})

    def test_a_number_somebody_read_off_a_shirt(self):
        f = ask(readings=[reading("D5", 4)])["fact"]
        self.assertEqual(f, {"kind": "read", "number": 4})

    def test_a_number_an_ocr_vote_proposed(self):
        f = ask(jersey=4, jersey_source="voted")["fact"]
        self.assertEqual(f, {"kind": "voted", "number": 4})

    def test_a_published_number_a_person_read(self):
        f = ask(jersey=4, jersey_source="read")["fact"]
        self.assertEqual(f, {"kind": "read", "number": 4})

    def test_two_different_numbers_is_no_jersey_at_all(self):
        # `jerseyOf`'s refusal, carried up. The slot has no number, and both
        # numbers come with it so a caller with room can show the finding
        # instead of hiding it.
        f = ask(readings=[reading("D5", 28, 0), reading("D5", 77, 3)])["fact"]
        self.assertEqual(f["kind"], "conflict")
        self.assertEqual(sorted(f["numbers"]), [28, 77])
        self.assertNotIn("number", f)

    def test_a_conflict_never_borrows_the_published_number(self):
        # The one that must not regress: falling through to `jersey` here would
        # resolve by taking what the readings declined to pick.
        f = ask(readings=[reading("D5", 28, 0), reading("D5", 77, 3)],
                jersey=4, jersey_source="read")["fact"]
        self.assertEqual(f["kind"], "conflict")

    def test_a_reading_outranks_a_published_vote(self):
        f = ask(readings=[reading("D5", 9)], jersey=4,
                jersey_source="voted")["fact"]
        self.assertEqual(f, {"kind": "read", "number": 9})

    def test_jersey_zero_is_a_number_not_an_absence(self):
        # 0 and 00 are legal, so every test in the cascade is against null and
        # undefined rather than against falsiness. A `?:` here would report the
        # slot as unread and the rail would draw nothing over a real shirt.
        self.assertEqual(ask(jersey=0, jersey_source="read")["fact"],
                         {"kind": "read", "number": 0})
        self.assertEqual(ask(readings=[reading("D5", 0)])["fact"],
                         {"kind": "read", "number": 0})


@needs_node
class TheRailsColumn(unittest.TestCase):
    """...and what five characters of column do with it."""

    def test_nothing_read_draws_nothing(self):
        # Not a dash and not a zero: docs/04 M5, a wrong number is worse than no
        # number, and a dash in this column reads as one.
        self.assertIsNone(ask()["rail"])

    def test_the_kind_is_the_class(self):
        # Solid for a number off a shirt, faint for a vote. The rail has drawn
        # those two weights since docs/06, and the extraction is only honest if
        # `kind` still carries the distinction.
        self.assertEqual(ask(readings=[reading("D5", 4)])["rail"],
                         {"text": "#4", "cls": "read"})
        self.assertEqual(ask(jersey=4, jersey_source="voted")["rail"],
                         {"text": "#4", "cls": "voted"})

    def test_a_conflict_shows_both_numbers_and_no_hash(self):
        # No `#`, because this is not a jersey - it is two of them.
        r = ask(readings=[reading("D5", 28, 0), reading("D5", 77, 3)])["rail"]
        self.assertEqual(r, {"text": "28/77", "cls": "conflict"})

    def test_a_conflict_too_wide_for_the_column_becomes_a_count(self):
        # An ellipsis would turn `28/77/9` into `28/77...`, and a conflict that
        # renders as a number is the one reading of it that must never happen.
        r = ask(readings=[reading("D5", 28, 0), reading("D5", 77, 3),
                          reading("D5", 9, 6)])["rail"]
        self.assertEqual(r["cls"], "conflict")
        self.assertEqual(r["text"], "×3")
        self.assertNotIn("#", r["text"])


@needs_node
class TheNameBesideTheSlot(unittest.TestCase):
    """`slotLabel`, the other thing that was written out four times.

    The overlay label, the relabel dropdown, the Selected Player header and the
    rail's hover each built `D5 #4` by hand, and each tested the number for
    truthiness. This shows the published number as an identifier and makes no
    claim about provenance - that is `jerseyFact`'s job, and these four not
    consulting it is a question for #22 rather than a defect here.
    """

    def test_a_slot_with_a_number(self):
        self.assertEqual(ask(jersey=4)["label"], "D5 #4")

    def test_a_slot_with_none(self):
        self.assertEqual(ask()["label"], "D5")

    def test_jersey_zero_prints(self):
        # The bug all four carried. `p.jersey ? ...` is false for 0, so a real
        # shirt rendered as a bare slot. No published possession has a 0 today;
        # #22 is what makes that a matter of time rather than of luck.
        self.assertEqual(ask(jersey=0)["label"], "D5 #0")

    def test_a_reading_made_in_the_session_does_not_change_it(self):
        # Deliberate, and the line between the two helpers. This is the
        # published number as a name; `jerseyFact` is what a reading outranks.
        self.assertEqual(ask(readings=[reading("D5", 9)], jersey=4)["label"],
                         "D5 #4")


if __name__ == "__main__":
    unittest.main()
