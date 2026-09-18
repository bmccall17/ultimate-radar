"""The whole-broadcast goal index, checked without opening the broadcast.

`eval/m9/goals.json` is committed, and these read it. That is the point: a check
that re-derives its answer from the footage every run is comparing the
measurement to itself, and nobody will keep running a gate that decodes 2 h 22 m
of video in front of a publish. Reading the committed file is what catches a
re-scan, a re-labelled cluster table or a broken collision repair. #16.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools import checks as C
from tools import gates as G


def written(goals: list[dict], final: tuple[int, int] = (2, 1)) -> Path:
    d = Path(tempfile.mkdtemp())
    p = d / "goals.json"
    p.write_text(json.dumps(
        {"source": "invented.mp4", "final_score": {"ATX": final[0], "MIN": final[1]},
         "reconstruction_consistent": True, "goals": goals}), encoding="utf-8")
    return p


def goal(frm, to, t=100.0) -> dict:
    return {"after_t": t - 8, "before_t": t - 2, "from": list(frm), "to": list(to),
            "scorer": "ATX" if to[0] > frm[0] else "MIN", "goal_t": t,
            "clock_freeze_t": t - 11}


def row(path: Path, name: str) -> dict:
    return next(c for c in G.check_goals(path)["checks"] if c["name"] == name)


class GoalsReconcileWithTheFinalScore(unittest.TestCase):
    NAME = "goals reconcile with the final score"

    def test_a_clean_index_passes(self):
        p = written([goal((0, 0), (1, 0), 100.0), goal((1, 0), (2, 0), 200.0),
                     goal((2, 0), (2, 1), 300.0)], final=(2, 1))
        self.assertIs(row(p, self.NAME)["pass"], True)

    def test_a_missing_goal_fails(self):
        # Three changes recorded, a final score that sums to four. One of them
        # was never seen, and the file cannot say which.
        p = written([goal((0, 0), (1, 0), 100.0), goal((1, 0), (2, 0), 200.0),
                     goal((2, 0), (2, 1), 300.0)], final=(3, 1))
        self.assertIs(row(p, self.NAME)["pass"], False)

    def test_a_change_of_two_fails(self):
        # Nobody scores twice at once. A jump of two is a reading the clusterer
        # got wrong or a change it slept through, not a goal.
        p = written([goal((0, 0), (2, 0), 100.0), goal((2, 0), (2, 1), 200.0)],
                    final=(2, 1))
        self.assertIs(row(p, self.NAME)["pass"], False)

    def test_it_is_a_gate_and_not_a_measurement(self):
        # docs/31: only a gate can close a ticket, and #16 points at this one.
        p = written([goal((0, 0), (1, 0), 100.0)], final=(1, 0))
        self.assertTrue(C.is_gate(row(p, self.NAME)))
