"""The one view a grader is allowed to see, and the confession beside it.

Run them:

    python -m unittest discover -s tests -t .

Two exclusions used to live apart: hand-placed positions came out in one grader
via `ur.human.blind` (AD-13), and a name nobody read came out in another via a
`continue` inside the span grader. Neither reached `tools/disc_score.py`, which
read both files raw.

`ur.grading` is the single way in. It hands back the possession with hand-placed
frames blinded and the events with tracker-supplied names stripped, so a grader
takes the view and nothing else. The unblinded path keeps a name that reads as a
confession, because a publisher legitimately needs it and a grader does not, and
that one identifier is what the registration gate looks for.

Same standard as `test_inferred_names.py`: invented dicts, and the property worth
having is that these fail when an exclusion is taken away.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ur import grading as GV
from ur import provenance as PV


def doc(*, human=None, n=3):
    """A one-slot possession, optionally with a hand-placed frame."""
    p = {"id": "O2", "team": "offense",
         "est": [[10.0, 10.0]] * n, "state": ["observed"] * n}
    if human is not None:
        p[GV.HU.KEY] = list(human)
    return {"possession": {"id": "p9999", "frames": n, "fps": 1.0,
                           "offense": "offense"},
            "players": [p]}


def events(**kw):
    return {"events": [{"t": 1.0, "type": "catch", "player": "O2",
                        "source": "human", **kw}]}


class OneCall(unittest.TestCase):
    def test_the_view_blinds_the_positions_and_the_names_together(self):
        d, ev = GV.blind(doc(human=[1]), events())
        self.assertEqual(d["players"][0]["state"][1], "unknown")
        self.assertIsNone(d["players"][0]["est"][1])
        self.assertIsNone(ev["events"][0]["player"])

    def test_a_name_off_the_footage_survives_a_blinded_position(self):
        # The two exclusions are about different facts and must not be fused:
        # a repaired position says nothing about who the tagger watched.
        d, ev = GV.blind(doc(human=[1]), events(provenance=PV.FOOTAGE))
        self.assertEqual(d["players"][0]["state"][1], "unknown")
        self.assertEqual(ev["events"][0]["player"], "O2")

    def test_the_publishing_read_is_not_blinded(self):
        # A reader should see the repaired path - that is the whole point of
        # AD-6. Only the score is blind.
        with tempfile.TemporaryDirectory() as tmp:
            w = Path(tmp)
            (w / GV.POSSESSION).write_text(json.dumps(doc(human=[1])),
                                           encoding="utf-8")
            d = GV.read_for_publishing(w)
        self.assertEqual(d["players"][0]["state"][1], "observed")
        self.assertEqual(d["players"][0]["est"][1], [10.0, 10.0])

    def test_loading_a_possession_with_no_tags_is_not_a_failure(self):
        # Most of work/ has no events.json. A grader asking for the view there
        # should get an empty tag list, not an exception.
        with tempfile.TemporaryDirectory() as tmp:
            w = Path(tmp)
            (w / GV.POSSESSION).write_text(json.dumps(doc()), encoding="utf-8")
            _, ev = GV.load(w)
        self.assertEqual(ev["events"], [])
