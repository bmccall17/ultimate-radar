"""A keyframe of anchors, and the mark it has to leave behind.

Run them:

    python -m unittest discover -s tests -t .

These are about `ur/resolve.py` and `ur/human.py` over an invented possession,
not about the footage. The property under test is the one #8 calls the trap this
project keeps hitting: a hand-placed position becomes `confirmed` with a tight
sigma and is then indistinguishable from a frame the tracker got right. So every
frame a correction created **or moved** has to come back out of `human`, and the
ramped frames either side count - they keep their evidence state and their
position is now partly a person's.
"""

from __future__ import annotations

import unittest

import shutil
import tempfile
from pathlib import Path

from ur import human as H
from ur import resolve as R


def doc(n=11, ids=("O1", "O2"), team="sol"):
    """A possession where every slot is `predicted` on a straight line."""
    return {
        "possession": {"frames": n, "fps": 10.0, "offense": team,
                       "defense": "chill", "id": "p9999"},
        "players": [{"id": i, "team": team, "slot": i,
                     "est": [[float(f), 10.0] for f in range(n)],
                     "state": ["predicted"] * n,
                     "sigma": [4.0] * n,
                     "human": []} for i in ids],
        "derived": {},
    }


def log(*corrections):
    d = R.empty_log("p9999")
    d["corrections"] = list(corrections)
    return d


class AnchorMarksWhatItMoved(unittest.TestCase):
    def test_the_anchored_frame_is_marked(self):
        d = R.resolve(doc(), log({"id": "c1", "op": "anchor", "slot": "O1",
                                  "f": 5, "xy": [5.0, 30.0]}), verbose=False)
        self.assertIn(5, H.touched(d["players"][0]))

    def test_the_ramp_is_marked_too(self):
        """Nothing brackets the anchor, so the ramp is flat and the whole
        trajectory moves. Every frame it moved is a person's, whatever its
        evidence state still says."""
        d = R.resolve(doc(), log({"id": "c1", "op": "anchor", "slot": "O1",
                                  "f": 5, "xy": [5.0, 30.0]}), verbose=False)
        p = d["players"][0]
        self.assertEqual(H.touched(p), set(range(11)))
        # ...and the mark is not the evidence state wearing a different hat.
        self.assertEqual(p["state"][0], "predicted")
        self.assertEqual(p["state"][5], "confirmed")

    def test_a_bracketed_ramp_stops_at_the_observations(self):
        d0 = doc()
        d0["players"][0]["state"][2] = "observed"
        d0["players"][0]["state"][8] = "observed"
        d = R.resolve(d0, log({"id": "c1", "op": "anchor", "slot": "O1",
                               "f": 5, "xy": [5.0, 30.0]}), verbose=False)
        # The bracketing observations carry weight 0, so they are untouched and
        # stay the tracker's own. That is the whole point of the ramp.
        self.assertEqual(H.touched(d["players"][0]), set(range(3, 8)))

    def test_the_other_slot_is_untouched(self):
        d = R.resolve(doc(), log({"id": "c1", "op": "anchor", "slot": "O1",
                                  "f": 5, "xy": [5.0, 30.0]}), verbose=False)
        self.assertEqual(H.touched(d["players"][1]), set())

    def test_a_reverted_anchor_leaves_no_mark(self):
        d = R.resolve(doc(), log({"id": "c1", "op": "anchor", "slot": "O1",
                                  "f": 5, "xy": [5.0, 30.0]},
                                 {"id": "r1", "op": "revert", "target": "c1"}),
                      verbose=False)
        self.assertEqual(H.touched(d["players"][0]), set())

    def test_confirm_marks_nothing(self):
        """`confirm` affirms an estimate the tracker made; it supplies no
        position. The frame becomes `confirmed` and stays the tracker's."""
        d = R.resolve(doc(), log({"id": "c1", "op": "confirm", "slot": "O1",
                                  "f": 5}), verbose=False)
        self.assertEqual(H.touched(d["players"][0]), set())
        self.assertEqual(d["players"][0]["state"][5], "confirmed")


class SwapCarriesTheMark(unittest.TestCase):
    def test_marks_travel_with_the_trajectory(self):
        d0 = doc()
        for p in d0["players"]:
            p["state"][0] = p["state"][10] = "observed"
        d = R.resolve(d0, log({"id": "c1", "op": "anchor", "slot": "O1",
                               "f": 3, "xy": [3.0, 30.0]},
                              {"id": "c2", "op": "swap", "slots": ["O1", "O2"],
                               "from_f": 2}), verbose=False)
        by = {p["id"]: p for p in d["players"]}
        # Everything from frame 2 on went across, so the anchored frames are
        # O2's now. A mark left behind on O1 would say the tracker's own output
        # was hand-placed, which is the accusation running backwards.
        self.assertEqual(H.touched(by["O1"]), {1})
        self.assertIn(3, H.touched(by["O2"]))


class Keyframes(unittest.TestCase):
    def test_one_keyframe_is_many_anchors_on_one_frame(self):
        d = R.resolve(doc(ids=("O1", "O2")),
                      log({"id": "c1", "keyframe": "k1", "op": "anchor",
                           "slot": "O1", "f": 4, "xy": [1.0, 1.0]},
                          {"id": "c2", "keyframe": "k1", "op": "anchor",
                           "slot": "O2", "f": 4, "xy": [2.0, 2.0]}),
                      verbose=False)
        for p in d["players"]:
            self.assertEqual(p["state"][4], "confirmed")
        self.assertEqual({c["keyframe"] for c in d["corrections_applied"]}, {"k1"})


def synthetic_work(root: Path, n: int = 3) -> Path:
    """The smallest working directory `ur.possess.build` will accept.

    Fourteen slots, three frames, an identity homography, no detections. It is
    not a possession and is not meant to be one - it exists so that a test about
    **whether a function writes to disk** can run on a machine with no footage.

    The first version of `BuildingIsNotWriting` skipped when `work/p0003` was
    absent, which meant the test written to stop docs/30 § 2.13 coming back ran
    on exactly one machine and printed `OK (skipped=2)` everywhere else - a green
    that covered nothing, found by the QA re-run and filed as § 2.16.
    """
    import json
    d = root / "p9999"
    d.mkdir(parents=True, exist_ok=True)
    H = [[0.05, 0, 0], [0, 0.05, 0], [0, 0, 1]]
    files = {
        "clip.json": {
            "possession_id": "p9999", "frames": n, "fps": 15.0,
            "duration_s": n / 15.0, "start_s": 0.0, "end_s": n / 15.0,
            "offense": "sol", "defense": "chill", "quarter": 1,
            "attacking_direction": "+x",
            "field": {"length_yd": 120.0, "width_yd": 53.333,
                      "endzone_yd": 20.0, "brick_yd": 20.0},
            "source": {"platform": "test", "id": "none", "start_s": 0.0,
                       "end_s": n / 15.0, "url": "", "video_fps": 15.0,
                       "clip_frames_sync": {"video_fps": 15.0, "offset_s": 0.0}},
            "teams": {"sol": {"name": "Sol"}, "chill": {"name": "Chill"}}},
        "calibration.json": {
            "camera": {"image_w": 1920, "image_h": 1080,
                       "position_yd": [58, -21, 13],
                       "position_yd_soccer": [0, 0, 13]},
            "venue_transform": {},
            "frames": [{"f": f, "H": H, "confidence": 0.9,
                        "camera": {"pan_deg": 0, "tilt_deg": 0, "roll_deg": 0,
                                   "focal_px": 1200.0}} for f in range(n)]},
        "tracks.json": {
            "method": {}, "diagnostics": {},
            "slots": [{"slot": (f"O{i+1}" if i < 7 else f"D{i-6}"),
                       "team": "sol" if i < 7 else "chill",
                       "observed": n, "first_observed_f": 0,
                       "samples": [{"f": f, "xy": [50.0 + i, 20.0],
                                    "state": "observed", "sigma": 0.3,
                                    "det": None, "assoc": None, "reacquire": None,
                                    "falsified": False, "covered": True}
                                   for f in range(n)]} for i in range(14)]},
        "detections.json": {"possession_id": "p9999",
                            "frames": [{"f": f, "dets": []} for f in range(n)]},
    }
    for name, doc in files.items():
        (d / name).write_text(json.dumps(doc), encoding="utf-8")
    return d


class BuildingIsNotWriting(unittest.TestCase):
    """`ur.possess.build` returns a document and must not put one on disk.

    docs/30 § 2.13. `ur.resolve.load_uncorrected` calls it to get the
    *uncorrected* document to compare against, so a write there means
    `--verify-revert` - whose whole job is to prove it changes nothing - leaves
    an uncorrected possession.json behind every time. Two sessions blamed the
    resulting vanished corrections on a parallel process and could not reproduce
    it; docs/32 § 0 told a QA runner to run it first thing.

    On a synthetic directory rather than p0003, so it runs in a clone. § 2.16.
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.work = synthetic_work(Path(self.tmp))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_build_writes_nothing(self):
        from ur.possess import build
        doc = build(self.work, verbose=False)
        self.assertEqual(len(doc["players"]), 14)
        self.assertFalse((self.work / "possession.json").exists(),
                         "building a document put one on disk")

    def test_load_uncorrected_writes_nothing(self):
        R.load_uncorrected(self.work)
        self.assertFalse((self.work / "possession.json").exists(),
                         "load_uncorrected wrote the document it was reading")

    def test_verify_revert_leaves_the_file_alone(self):
        from ur import grading as GV
        GV.write(self.work, R.resolve(R.load_uncorrected(self.work),
                                      R.empty_log("p9999"), verbose=False))
        p = self.work / "possession.json"
        before = p.read_bytes()
        R.main([str(self.work), "--verify-revert"])
        self.assertEqual(before, p.read_bytes(),
                         "--verify-revert rewrote the document it was checking")


class Detach(unittest.TestCase):
    """#26: saying a slot is on nobody.

    The commonest verdict in a roster pass and the one with no operation until
    now. A slot that has lost its player dead-reckons, and on 11-33 % of frames
    of every published possession it drifts within 1.5 yd of a slot that has a
    real detection - two labels, one person. `swap` cannot say it (that claims a
    real player is mislabelled) and `anchor` cannot (there is nowhere to put
    them). `detach` says the slot states no position here, which is what
    `unknown` already means everywhere else in the pipeline.
    """

    def doc_with_gap(self, n=11):
        d = doc(n)
        p = d["players"][0]
        for k in range(3, 8):
            p["state"][k] = "predicted"
        p["state"][0] = p["state"][10] = "observed"
        return d

    def test_clears_the_span(self):
        d = R.resolve(self.doc_with_gap(),
                      log({"id": "c1", "op": "detach", "slot": "O1",
                           "from_f": 3, "to_f": 7}), verbose=False)
        p = d["players"][0]
        self.assertEqual(p["state"][3:8], ["unknown"] * 5)
        self.assertEqual(p["est"][3:8], [None] * 5)

    def test_leaves_the_rest_alone(self):
        d = R.resolve(self.doc_with_gap(),
                      log({"id": "c1", "op": "detach", "slot": "O1",
                           "from_f": 3, "to_f": 7}), verbose=False)
        p = d["players"][0]
        self.assertEqual(p["state"][2], "predicted")
        self.assertEqual(p["state"][8], "predicted")
        self.assertIsNotNone(p["est"][8])

    def test_the_cleared_frames_are_human(self):
        """A frame a person removed is as human-sourced as one they placed.

        Otherwise the tracker's recall improves every time somebody deletes a
        frame it got wrong, which is #8's trap running backwards.
        """
        d = R.resolve(self.doc_with_gap(),
                      log({"id": "c1", "op": "detach", "slot": "O1",
                           "from_f": 3, "to_f": 7}), verbose=False)
        self.assertEqual(H.touched(d["players"][0]), {3, 4, 5, 6, 7})

    def test_an_open_ended_detach_stops_where_the_slot_re_acquires(self):
        """`from_f` alone runs to the frame before the next observation, so a
        person says *from here* without going to find the other end."""
        d = R.resolve(self.doc_with_gap(),
                      log({"id": "c1", "op": "detach", "slot": "O1",
                           "from_f": 8}), verbose=False)
        p = d["players"][0]
        self.assertEqual(p["state"][8:10], ["unknown", "unknown"])
        self.assertEqual(p["state"][10], "observed")     # untouched
        self.assertEqual(p["state"][7], "predicted")     # untouched

    def test_a_reverted_detach_puts_it_back(self):
        d = R.resolve(self.doc_with_gap(),
                      log({"id": "c1", "op": "detach", "slot": "O1",
                           "from_f": 3, "to_f": 7},
                          {"id": "r1", "op": "revert", "target": "c1"}),
                      verbose=False)
        p = d["players"][0]
        self.assertEqual(p["state"][3], "predicted")
        self.assertEqual(H.touched(p), set())

    def test_refuses_to_delete_an_observation(self):
        """A detach over a frame the camera actually saw somebody on is not a
        correction, it is deleting evidence. AD-6 keeps the tracks; this says
        so out loud rather than quietly dropping them."""
        with self.assertRaises(ValueError):
            R.resolve(self.doc_with_gap(),
                      log({"id": "c1", "op": "detach", "slot": "O1",
                           "from_f": 0, "to_f": 7}), verbose=False)


class DiscAnchor(unittest.TestCase):
    def disc_doc(self, n=11):
        d = doc(n)
        d["disc"] = [[float(f), 10.0, 1.0] for f in range(n)]
        d["disc_meta"] = {"state": ["interpolated"] * n,
                          "basis": ["flight"] * n,
                          "holder": [None] * n,
                          "sigma": [8.0] * n,
                          "source": ["inferred"] * n,
                          "name_inferred": [False] * n,
                          "human": []}
        return d

    def test_places_the_disc_and_marks_it(self):
        d = R.resolve(self.disc_doc(),
                      log({"id": "c1", "op": "anchor", "slot": R.DISC,
                           "f": 5, "xy": [5.0, 40.0]}), verbose=False)
        self.assertEqual(d["disc"][5][:2], [5.0, 40.0])
        self.assertEqual(d["disc_meta"]["state"][5], "confirmed")
        self.assertEqual(d["disc_meta"]["source"][5], "human")
        self.assertIn(5, H.touched(d["disc_meta"]))

    def test_height_is_kept_when_not_stated(self):
        d = R.resolve(self.disc_doc(),
                      log({"id": "c1", "op": "anchor", "slot": R.DISC,
                           "f": 5, "xy": [5.0, 40.0]}), verbose=False)
        self.assertEqual(d["disc"][5][2], 1.0)

    def test_refuses_where_there_is_no_disc(self):
        with self.assertRaises(ValueError):
            R.resolve(doc(), log({"id": "c1", "op": "anchor", "slot": R.DISC,
                                  "f": 5, "xy": [5.0, 40.0]}), verbose=False)


if __name__ == "__main__":
    unittest.main()
