"""When the game clock stopped, over the frames it was really measured on.

`clock_freeze` returned the **last** qualifying change in its window, which is
not the moment ticking stopped. Anything that changed the clock box after the
clock had already frozen - a graphic wipe turning the crop white, the bug
re-rendering after a replay, a change one pixel over the threshold - won that
comparison and put the answer at the end of the window. On 10 of the game's 52
goals that produced a freeze at or after the score-bug flip, and a freeze that
does not precede the flip cannot be the last tick before it.

`fixtures/clock_freeze.json` carries the per-frame ink and change series for
those ten, plus two controls from inside the documented band, measured off the
broadcast at 4 fps. Numbers rather than pixels: `.gitignore` says derived media
is never committed and `docs/10` says the broadcast is not redistributed. Every
expected time below was read off the series by hand and is written here as a
literal, so the test can disagree with the code.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from tools import scout as S

FIX = json.loads(Path("fixtures/clock_freeze.json").read_text(encoding="utf-8"))
GOALS = {g["bug_t"]: g for g in FIX["goals"]}


def freeze_t(bug_t: float, tail_s: float = 2.0) -> float | None:
    """Run the decision over one goal's measured series, back in seconds.

    The window belongs to `clock_freeze`, not to the decision, so the slice is
    here: the fixture runs 15 s past the flip and production reads 2 s past it.
    `tail_s` is how far past the flip the caller looks, and one of these tests
    is about a clock that stops outside the 2 s production uses.
    """
    g = GOALS[bug_t]
    n = int(round((S.CLOCK_LOOKBACK_S + tail_s) * g["fps"])) + 1
    i = S.freeze_index(g["delta"][:n], g["ink"][:n], fps=g["fps"])
    return None if i is None else round(g["t0"] + i / g["fps"], 2)


class AGraphicWipeIsNotATick(unittest.TestCase):
    def test_a_white_frame_does_not_win(self):
        # The crop goes fully white - ink 3200, every pixel of 80x40 - as a
        # graphic wipes across the bug at 1203.79, and the box is gone for the
        # rest of the window. The clock itself last ticked at 1194.79, nine
        # seconds earlier, and had been ticking at a second's cadence up to it.
        self.assertEqual(freeze_t(1204.29), 1194.79)


class ARerenderIsNotATick(unittest.TestCase):
    def test_two_changes_together_are_not_a_clock(self):
        # Here what lands late is not one frame but two, 0.25 s apart at 1728.67
        # and 1728.92, with ink around 460 - the bug drawing itself back on after
        # the replay, not a white wipe. They keep each other company, so a rule
        # that only discards lonely changes keeps them. A clock ticks; two frames
        # a quarter-second apart after eight seconds of silence do not. The last
        # tick of the run before them is 1720.92.
        self.assertEqual(freeze_t(1728.92), 1720.92)


class TheOnesThatWereAlreadyRight(unittest.TestCase):
    """Two goals from inside the documented 9-15 s band, unchanged.

    The rule above throws work away, and a rule that throws away too much would
    show up here first: these two had nothing wrong with them and must come back
    with the same answer the old code gave.
    """

    def test_the_first_goal_of_the_game(self):
        self.assertEqual(freeze_t(819.22), GOALS[819.22]["old_freeze_t"])

    def test_the_second(self):
        self.assertEqual(freeze_t(909.34), GOALS[909.34]["old_freeze_t"])


class StillTickingAtTheEdge(unittest.TestCase):
    def test_a_run_that_reaches_the_edge_is_not_a_freeze(self):
        # 5803.21 is the case the window gets wrong rather than the rule. The
        # clock is still ticking when the window closes at bug_t + 2, so there
        # is no stop inside it to find, and the last tick before the edge is
        # just where the looking stopped. Returning it reports the window as a
        # measurement. docs/30 section 2.6.
        self.assertIsNone(freeze_t(5803.21))

    def test_and_with_room_to_look_it_is_found(self):
        # Given fifteen seconds instead of two, the ticking runs on past the
        # flip and stops at 5809.21 - six seconds AFTER the score bug is
        # recorded as having flipped, which is the other half of this goal's
        # problem and belongs to `goal_t`, not here.
        self.assertEqual(freeze_t(5803.21, tail_s=15.0), 5809.21)
