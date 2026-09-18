"""The audit's two edits, reproduced, and the row that has to see them.

On 2026-09-16 an outside audit took a published `possession.js`, moved one
event's time by a second and changed one event's player **in memory**, and ran
the site audit against it. All eight site checks passed. `site is current`
compared three counts - events, frames, and the resolved attacking direction -
and none of them move when a value changes underneath them.

These tests do the same two edits, on the real published p0003, and require the
row to fail. The third test is the one that makes the first two worth having: an
unchanged page must still pass, or the check is a tripwire nobody can build past.

    python -m unittest discover -s tests -t .
"""

from __future__ import annotations

import copy
import json
import pathlib
import unittest
from unittest import mock

from tools import audit_site as AS
from tools import site_digest as SD

SITE = pathlib.Path("docs")


def published(pid: str) -> dict | None:
    """The page as a reader's browser holds it. Reads `docs/`, never `work/`.

    `work/` is gitignored - it holds broadcast footage - so a test that needed it
    would be a test nobody but this machine can run. `docs/` is committed, which
    is the other half of AGENTS rule 7: the published site is the artefact, so it
    is the thing a test is allowed to assume exists.
    """
    return AS.published(pid)


PID = "p0003"
DOC = published(PID)
needs_site = unittest.skipIf(DOC is None, f"docs/{PID}/possession.js is not built")


def row(pub: dict, now: dict) -> dict:
    """Drive the real gate row with a composed document of our choosing."""
    with mock.patch("tools.make_view.compose", return_value=(now, None, None)):
        return AS.site_is_current(PID, pub)


@needs_site
class TheAuditsEdits(unittest.TestCase):
    """The two changes that walked past the old check."""

    def test_a_no_op_rebuild_still_passes(self):
        # First, because the other two mean nothing without it. A check that
        # fails on an unchanged site is a check somebody turns off.
        r = row(copy.deepcopy(DOC), copy.deepcopy(DOC))
        self.assertTrue(r["pass"], r["got"])

    def test_one_event_moved_by_a_second_fails(self):
        pub = copy.deepcopy(DOC)
        self.assertTrue(pub.get("events"), "p0003 publishes tags; this needs one")
        pub["events"][0]["t"] = float(pub["events"][0]["t"]) + 1.0
        r = row(pub, copy.deepcopy(DOC))
        self.assertFalse(r["pass"])
        # "The failure message says what differs, not just that something does."
        self.assertIn("event 0 t", r["got"])

    def test_one_event_given_another_player_fails(self):
        pub = copy.deepcopy(DOC)
        was = pub["events"][0].get("player")
        pub["events"][0]["player"] = "O7" if was != "O7" else "O4"
        r = row(pub, copy.deepcopy(DOC))
        self.assertFalse(r["pass"])
        self.assertIn("event 0 player", r["got"])
        self.assertIn(str(was), r["got"])

    def test_the_counts_the_old_check_read_do_not_move(self):
        # The point of the two above: the page the audit built is identical to
        # the real one by every measure the old row had. If this ever fails, the
        # edits have grown teeth of their own and the tests above stopped
        # testing what they were written for.
        pub = copy.deepcopy(DOC)
        pub["events"][0]["t"] = float(pub["events"][0]["t"]) + 1.0
        pub["events"][0]["player"] = "O7"
        self.assertEqual(len(pub["events"]), len(DOC["events"]))
        self.assertEqual(pub["possession"]["frames"], DOC["possession"]["frames"])
        self.assertEqual(pub["possession"].get("attacking_direction_resolved"),
                         DOC["possession"].get("attacking_direction_resolved"))


@needs_site
class TheDigest(unittest.TestCase):
    def test_the_video_path_is_the_one_thing_excluded(self):
        # viewer/live-data.js says ../work/p0003/clip.mp4 and docs/p0003/ says
        # clip.mp4 for the same page. Hashing it would make every published page
        # permanently stale against a viewer build.
        a = copy.deepcopy(DOC)
        a["video_src"] = "somewhere/else/clip.mp4"
        self.assertEqual(SD.digest(a), SD.digest(DOC))

    def test_a_field_nobody_named_is_still_covered(self):
        # `rest` exists so that a field added to the document tomorrow is
        # checked the day it lands, not the day somebody remembers this file.
        a = copy.deepcopy(DOC)
        a["a_field_invented_by_this_test"] = 1
        self.assertNotEqual(SD.digest(a)["rest"], SD.digest(DOC)["rest"])
        self.assertIn("rest differs", SD.differences(a, DOC))

    def test_a_moved_player_is_named_by_slot(self):
        # The ticket asks for event values and resolved claims. The positions
        # are in too, because a pipeline re-run that moves every player and no
        # event is the same staleness in a bigger place.
        a = copy.deepcopy(DOC)
        p = a["players"][0]
        p["est"][0] = [(p["est"][0] or [0, 0])[0] + 3.0,
                       (p["est"][0] or [0, 0])[1]]
        diffs = SD.differences(a, DOC)
        self.assertTrue(any(str(p["slot"]) in d for d in diffs), diffs)

    def test_the_resolved_direction_is_covered(self):
        # p0003 resolves to null today - nobody has confirmed Q1 for its team -
        # so the edit that tests this row has to be the one that would matter:
        # a direction appearing on the page that work/ does not resolve to.
        a = copy.deepcopy(DOC)
        was = a["possession"].get("attacking_direction_resolved")
        a["possession"]["attacking_direction_resolved"] = (
            None if was else {"sign": +1, "source": "invented by a test"})
        self.assertTrue(any("attacking_direction_resolved" in d
                            for d in SD.differences(a, DOC)))

    def test_summarise_says_nothing_is_wrong_when_nothing_is(self):
        self.assertEqual(SD.differences(DOC, copy.deepcopy(DOC)), [])
        self.assertIn("rebuild would emit", SD.summarise([]))


@needs_site
class WhenTheWorkDirectoryIsBroken(unittest.TestCase):
    def test_a_directory_that_will_not_compose_is_a_failure_not_a_skip(self):
        with mock.patch("tools.make_view.compose",
                        side_effect=ValueError("possession.json is truncated")):
            r = AS.site_is_current(PID, copy.deepcopy(DOC))
        self.assertFalse(r["pass"])
        self.assertIn("truncated", r["got"])


if __name__ == "__main__":
    unittest.main()
