"""When the score bug actually changed, over the frames it was measured on.

`_refine` looked for the first frame close to the box's final state and **more
than 200 away** from its first. An 8 becoming a 9 is two short strokes at this
crop and moves about 90, so on a clean goal nothing ever cleared 200 and the
answer was whatever a graphic wipe happened to do. Measured against the
committed `eval/m9/goals.json`, the code reproduced **1 of 52** of its own
`goal_t` values, and **49 of 52** of them sat outside the `[after_t, before_t]`
bracket the same file says contains the change. docs/30 section 2.24.

`fixtures/score_flip.json` carries, per frame, how far the box sits from the
score it showed before the change and from the one it showed after - numbers
rather than pixels, because `docs/10` says the broadcast is not redistributed.
The two expected times in `WhatTheStillsShowed` were read off the frames by eye
before this rule existed, which is the only reason they are worth asserting.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from tools import scout as S

FIX = json.loads(Path("fixtures/score_flip.json").read_text(encoding="utf-8"))
GOALS = {g["old_goal_t"]: g for g in FIX["goals"]}


def flip_t(old_goal_t: float) -> float | None:
    g = GOALS[old_goal_t]
    i = S.flip_index(g["d_old"], g["d_new"])
    return None if i is None else round(g["t0"] + i / g["fps"], 2)


class InsideItsOwnBracket(unittest.TestCase):
    def test_the_first_goal_of_the_game(self):
        # `goal_t` for this one was 819.22, two seconds past the 817.17 keyframe
        # that already showed the new score - a change that happened after the
        # frame proving it had happened. The box goes 0-0 to 0-1 at 794.97.
        g = GOALS[819.22]
        t = flip_t(819.22)
        self.assertEqual(t, 794.97)
        self.assertTrue(g["after_t"] <= t <= g["before_t"],
                        f"{t} outside [{g['after_t']}, {g['before_t']}]")


class WhatTheStillsShowed(unittest.TestCase):
    """The two goals whose frames were watched one at a time.

    Both had a clock that was still ticking when the freeze window closed, and
    both were read the same way: pull the score box at 1 fps either side and look
    at it. The digits change between 3152 and 3153 on one and between 5810 and
    5811 on the other, in both cases just after a "GOAL!" graphic crosses the
    box. The committed `goal_t` said 3149.63 and 5803.21. These two expectations
    come from that reading, not from this rule.
    """

    def test_the_clock_stopped_before_the_bug_moved(self):
        self.assertEqual(flip_t(3149.63), 3152.38)

    def test_and_the_other_one(self):
        self.assertEqual(flip_t(5803.21), 5810.71)


class EveryFlipIsInsideItsOwnBracket(unittest.TestCase):
    def test_all_ten(self):
        # `after_t` is the last keyframe showing the old score and `before_t` the
        # first showing the new, so the change is between them by construction.
        # The allowance is one 4 fps sample: `before_t` is a keyframe time and
        # the search runs on a quarter-second grid that need not land on it.
        for old, g in GOALS.items():
            with self.subTest(old_goal_t=old):
                t = flip_t(old)
                self.assertIsNotNone(t)
                self.assertGreaterEqual(t, g["after_t"])
                self.assertLessEqual(t, g["before_t"] + 1.0 / g["fps"])
