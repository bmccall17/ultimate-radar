"""The check that nobody reads a possession around the view.

Run them:

    python -m unittest discover -s tests -t .

`tools/human_positions.py` can only probe the graders its registry names, and the
registry is a hand-written list. A grader nobody added is a grader nobody checks,
and unlike an `unreachable` row its absence prints nothing at all. That is the
hole this closes, and it closes it without a second registry: there is no
allowlist, so **any** direct read of `possession.json` outside `ur/grading.py` is
the finding.

AD-13 warns that a check reading source would pass on a call that had been
commented out. That warning is about *behaviour*, and the probe still tests
behaviour. This asks a different question - does a bypass exist at all - which
source is the only place to answer. It **fails open**: a file that will not parse
is a finding, not a skip, because a scanner that quietly drops what it cannot
read is the same silence it was built to end.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools import grading_view as GVG


def tree(**files) -> Path:
    tmp = tempfile.mkdtemp()
    for name, body in files.items():
        p = Path(tmp) / name.replace("__", "/")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    return Path(tmp)


class Bypasses(unittest.TestCase):
    def test_a_module_reading_the_possession_raw_is_a_finding(self):
        root = tree(**{"tools__score_it.py":
                       'doc = json.loads((work / "possession.json").read_text())'})
        self.assertEqual([f.name for f in GVG.bypasses(root)], ["score_it.py"])

    def test_a_module_going_through_the_view_is_not(self):
        root = tree(**{"tools__score_it.py": "doc, ev = GV.load(work)"})
        self.assertEqual(GVG.bypasses(root), [])

    def test_the_constant_is_the_same_bypass_as_the_literal(self):
        # The regression that matters. The change adding this check also replaced
        # every literal with `GV.POSSESSION`, so a check matching only the string
        # matched nothing anywhere and passed over three real bypasses.
        root = tree(**{"tools__score_it.py":
                       "poss_path = work / GV.POSSESSION\n"
                       "doc = json.loads(poss_path.read_text())"})
        self.assertEqual([f.name for f in GVG.bypasses(root)], ["score_it.py"])

    def test_writing_the_file_is_a_bypass_too(self):
        root = tree(**{"ur__stage.py":
                       '(work / GV.POSSESSION).write_text(body)'})
        self.assertEqual([f.name for f in GVG.bypasses(root)], ["stage.py"])

    def test_an_exists_guard_is_still_a_bypass(self):
        # It reads nothing, so it was never the defect. But a rule that lets the
        # name out for a guard lets it out for a read one edit later, which is
        # how the constant got everywhere in the first place.
        root = tree(**{"tools__score_it.py": "if (work / GV.POSSESSION).exists(): pass"})
        self.assertEqual([f.name for f in GVG.bypasses(root)], ["score_it.py"])

    def test_naming_the_file_in_prose_is_not_a_bypass(self):
        # A gate is *called* "every active correction is replayed into
        # possession.json". Making that illegal asks prose to route around a
        # check, which is how a check gets disabled.
        root = tree(**{"tools__score_it.py":
                       'C.gate("replayed into possession.json", True, "", "")'})
        self.assertEqual(GVG.bypasses(root), [])

    def test_a_file_that_will_not_parse_is_a_finding(self):
        root = tree(**{"tools__broken.py": "def f(:\n"})
        self.assertEqual([f.name for f in GVG.bypasses(root)], ["broken.py"])
