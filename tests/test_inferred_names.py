"""Which published frames rest on a holder name nobody read.

Run them:

    python -m unittest discover -s tests -t .

A tag can carry `player_inferred`: the moment is a person's and so is the
reasoning, but the name was settled by elimination rather than read off a jersey
(docs/27, p0003's 21.27-26.33 s span). `tools/audit_site.py` fails the site if
such a frame renders at `confirmed`, and the interesting property of that check
is not that it passes now - it is that it still fails when the fix is taken away.
These are the cases that pin that down, on invented dicts.
"""

from __future__ import annotations

import unittest

from tools.audit_site import inferred_name_frames


def doc(events, *, holders, name_inferred=None, fps=1.0):
    meta = {"holder": holders}
    if name_inferred is not None:
        meta["name_inferred"] = name_inferred
    return {"possession": {"fps": fps}, "events": events, "disc_meta": meta}


TAG = {"t": 2.0, "type": "catch", "player": "O2", "source": "human",
       "player_inferred": True}


class NothingFlagged(unittest.TestCase):
    def test_a_possession_with_no_inferred_tag_flags_nothing(self):
        d = doc([{"t": 2.0, "type": "catch", "player": "O2", "source": "human"}],
                holders=["O2"] * 5, name_inferred=[False] * 5)
        self.assertEqual(inferred_name_frames(d), (set(), False, 0))

    def test_a_page_with_no_disc_at_all_is_not_a_defect(self):
        self.assertEqual(inferred_name_frames({"possession": {"fps": 15.0}}),
                         (set(), False, 0))


class FlagRecorded(unittest.TestCase):
    def test_the_recorded_span_is_read_back(self):
        d = doc([TAG], holders=["O2"] * 5,
                name_inferred=[False, False, True, True, True])
        self.assertEqual(inferred_name_frames(d), ({2, 3, 4}, False, 1))

    def test_the_tag_and_the_array_are_one_set(self):
        # The array covers the span from frame 3 on; the tag itself lands on 2.
        d = doc([TAG], holders=["O2"] * 5,
                name_inferred=[False, False, False, True, True])
        self.assertEqual(inferred_name_frames(d)[0], {2, 3, 4})


class SurvivesARevert(unittest.TestCase):
    """The half that makes this a check rather than a mirror of the fix."""

    def test_a_dropped_flag_is_itself_the_failure(self):
        # No `name_inferred` key at all: the site was built before the disc
        # stage carried the flag, or after somebody took it back out.
        d = doc([TAG], holders=["O2"] * 5)
        self.assertEqual(inferred_name_frames(d), ({2}, True, 1))

    def test_an_array_of_all_false_still_flags_the_tagged_frame(self):
        # The subtler revert: the key survives and nothing sets it.
        d = doc([TAG], holders=["O2"] * 5, name_inferred=[False] * 5)
        self.assertEqual(inferred_name_frames(d), ({2}, False, 1))

    def test_a_frame_the_tag_no_longer_holds_is_not_attributed_to_it(self):
        # A tag naming somebody the disc stage did not end up holding says
        # nothing about that frame, and guessing would make the check fire on
        # the wrong row - worse than not firing at all.
        d = doc([TAG], holders=["O5"] * 5)
        self.assertEqual(inferred_name_frames(d), (set(), True, 1))


if __name__ == "__main__":
    unittest.main()
