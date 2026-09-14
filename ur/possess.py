"""Assemble possession.json — the one file the viewer reads — from tracks.json.

    python -m ur.possess work/p0001

This replaces `ur/standin.py` as the source of `possession.json`. The stand-in
stays on disk until M4's gates are measured, because its output is the only
thing the viewer has shown so far and deleting it before the replacement is
checked would leave nothing to compare against.

`tracks.json` is never modified here. AD-6 makes it immutable: this reads it,
reshapes it into the columnar form `docs/03-data-contracts.md` specifies for the
viewer, and writes a separate file. Human edits belong in `corrections.json` and
are applied by `ur/resolve.py`, which does not exist yet.

**What is honest about this file and what is not.** The positions and the
evidence states are the tracker's real output, including `predicted` samples that
are dead reckoning and are allowed to be wrong. M4's five gates have since been
measured (`docs/17-m4-tracking.md`), so the file now carries the numbers rather
than a warning that there are none — including the one that falls short, because
a file that will be read by something downstream has to say what it is. Anything
reading this should quote `gates.note` before quoting a position.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np


def _to_ultimate(C, vt):
    """The camera centre in the ultimate frame, the one everything else uses."""
    if not vt:
        return C
    return [round(C[0] * vt["x_sign"] + vt["x_offset"], 4),
            round(C[1] * vt["y_sign"] + vt["y_offset"], 4),
            round(C[2], 4)]


def build(work: Path, *, verbose: bool = True) -> dict:
    clip = json.loads((work / "clip.json").read_text(encoding="utf-8"))
    cal = json.loads((work / "calibration.json").read_text(encoding="utf-8"))
    trk = json.loads((work / "tracks.json").read_text(encoding="utf-8"))
    det = json.loads((work / "detections.json").read_text(encoding="utf-8"))

    n_frames = int(clip["frames"])
    offense, defense = clip["offense"], clip["defense"]
    by_frame = {d["f"]: d["dets"] for d in det["frames"]}

    players = []
    for s in trk["slots"]:
        smp = sorted(s["samples"], key=lambda r: r["f"])
        assert len(smp) == n_frames, f"{s['slot']}: {len(smp)} samples, {n_frames} frames"
        players.append({
            "id": s["slot"],
            "team": s["team"],
            "slot": s["slot"],
            "jersey": None,                 # M5
            "role": "cutter" if s["slot"].startswith("O") else "defender",
            "est": [r["xy"] for r in smp],
            "state": [r["state"] for r in smp],
            "sigma": [r["sigma"] for r in smp],
            "det": [r["det"] for r in smp],
            "assoc": [r.get("assoc") for r in smp],
            "reacquire": [r.get("reacquire") for r in smp],
            # Per-frame flags the viewer needs and cannot recompute cheaply:
            # `falsified` - the camera looked at the estimate and found nobody;
            # `covered` - it can see everywhere this player could be. Both come
            # from the tracker, which has the homography and the detections.
            "falsified": [bool(r.get("falsified")) for r in smp],
            "covered": [bool(r.get("covered")) for r in smp],
            "observed_frames": s["observed"],
            "state_counts": {k: s.get(k, 0) for k in
                             ("observed", "provisional", "interpolated",
                              "predicted", "unknown")},
            "first_observed_f": s.get("first_observed_f"),
        })
    players.sort(key=lambda p: (p["id"][0] != "O", p["id"]))

    # Coverage counts slots with a matched detection, which is `provisional` as
    # well as `observed` - a re-acquisition is an observation of somebody, and the
    # doubt it carries is about identity, not about whether anyone was seen.
    obs = np.array([[x in ("observed", "provisional") for x in p["state"]]
                    for p in players])
    coverage = obs.sum(axis=0).tolist()

    # Detections the tracker did not use, kept per frame so the render can show
    # them. Seeing what is standing where a slot is not is the cheapest read
    # available on whether the kit gate is letting real players through.
    used = {(f, di) for p in players
            for f, di in enumerate(p["det"]) if di is not None}
    leftovers = []
    for f in range(n_frames):
        row = []
        for i, d in enumerate(by_frame.get(f, [])):
            if not d.get("in_bounds") or d.get("non_player"):
                continue
            if d.get("field") is None or (f, i) in used:
                continue
            row.append({"xy": d["field"], "team": d.get("team"),
                        "team_p": d.get("team_p"),
                        "why": "weak_kit" if d.get("weak_team") else "unassigned",
                        "box": d["box"]})
        leftovers.append(row)

    cam = cal["camera"]
    per_frame = []
    for rec in cal["frames"]:
        c = rec.get("camera")
        per_frame.append(None if rec.get("H") is None else {
            "H": rec["H"],
            "pan_deg": c["pan_deg"], "tilt_deg": c["tilt_deg"],
            "roll_deg": c["roll_deg"], "focal_px": c["focal_px"],
            "confidence": rec.get("confidence", 0.0),
        })

    doc = {
        "schema": "ultimate-radar/possession@0.2",
        "stand_in": False,
        "gates_measured": True,
        "gates": {
            "document": "docs/17-m4-tracking.md",
            # These are literals, measured once, on p0001, against hand labels
            # that exist only for p0001. Every possession used to emit them as
            # its own - so p0003's viewer announced "tracker recall 88 %, sigma
            # containment 80 %" over footage on which neither has ever been
            # measured. Naming the possession they came from is what lets a
            # reader, and the viewer, tell the difference.
            "measured_on": "p0001",
            "per_player_recall": 0.9060,
            "identity_switches_caught": None,
            "sigma_containment": 0.784,
            "note": "Per-player recall is 0.9060 against a threshold left "
                    "deliberately unset, because the statistic is chaotically "
                    "sensitive at this sample size - it moves non-monotonically "
                    "between 0.880 and 0.919 under association changes that should "
                    "not matter, which is about one standard error on 234 labelled "
                    "players. Sigma containment is 29 of 37, below the 80 % gate and "
                    "inside its own 95 % interval of 62.8-88.6 %; it needs a larger "
                    "sample, not a fix. `identity_switches_caught` is null rather "
                    "than the '2 of 2' it used to claim: that number was the swap "
                    "detector agreeing with the analysis that produced it, and no "
                    "re-acquisition on this possession has been labelled by a human. "
                    "The re-acquisitions are emitted for review instead - see "
                    "issues.json and docs/25.",
        },
        "notice": (
            "Positions, evidence states and sigmas are the M4 tracker's real "
            "output (ur.track.run), and M4's gates are measured - see `gates` "
            "above and docs/17. `predicted` samples are dead reckoning and are "
            "allowed to be wrong by design: docs/05-uncertainty.md explains why a "
            "ghost that drifts and snaps back is more honest than one frozen in "
            "place. No per-player number here is better than the recall in "
            "`gates`."
        ),
        "possession": {
            "id": clip["possession_id"],
            "label": f"{clip['teams'][offense]['name']} on offence vs "
                     f"{clip['teams'][defense]['name']}",
            "source_video": {
                "platform": clip["source"]["platform"],
                "id": clip["source"]["id"],
                "start_s": clip["source"]["start_s"],
                "end_s": clip["source"]["end_s"],
                "note": "Personal film study. The clip is not redistributed with this file.",
            },
            "fps": clip["fps"],
            "frames": n_frames,
            "duration_s": clip["duration_s"],
            "offense": offense,
            "defense": defense,
            "attacking_direction": clip["attacking_direction"],
            "clip_frames_sync": {**clip["source"]["clip_frames_sync"],
                                 "video_fps": clip["source"]["video_fps"]},
        },
        "field": clip["field"],
        "teams": clip["teams"],
        "camera": {
            "model": "pinhole, fixed position, per-frame pan/tilt/roll/focal (M1)",
            "image_w": cam["image_w"],
            "image_h": cam["image_h"],
            # Every other coordinate in this file is ultimate-frame yards, so the
            # camera centre is converted to match. calibration.json keeps it in
            # the soccer frame because that is where the venue was solved; a file
            # that mixes the two frames under one key is a trap.
            "position_yd": _to_ultimate(cam["position_yd"], cal.get("venue_transform")),
            "position_yd_soccer": cam["position_yd"],
            "frame": "H maps image pixel -> ultimate field yard, homogeneous. "
                     "Invert it to draw on the video; the inverse's w is NEGATIVE "
                     "in front of the camera on this footage, so take the sign "
                     "from a point known to be in front.",
            "per_frame": per_frame,
        },
        "disc": None,
        "events": [],
        "players": players,
        "unused_detections": leftovers,
        "derived": {
            "coverage": coverage,
            "note": "coverage is the number of the 14 slots observed in that frame. "
                    "No tactical metric is derived here: docs/05 forbids a "
                    "'measured' figure built on slots nothing has yet vouched for.",
        },
        "method": {
            "module": "ur.possess",
            "source": "tracks.json, written by ur.track.run",
            "tracker": trk["method"],
            "tracker_diagnostics": trk["diagnostics"],
        },
    }
    (work / "possession.json").write_text(json.dumps(doc, indent=1) + chr(10),
                                          encoding="utf-8")
    if verbose:
        import collections
        st = collections.Counter(x for p in players for x in p["state"])
        lo = collections.Counter(r["why"] for row in leftovers for r in row)
        print(f"[possess] {len(players)} slots x {n_frames} frames from tracks.json")
        print(f"[possess] states: " + ", ".join(f"{k} {v}" for k, v in st.most_common()))
        print(f"[possess] coverage per frame: median {int(np.median(coverage))}/14, "
              f"min {min(coverage)}, max {max(coverage)}")
        print(f"[possess] detections the tracker did not use: " +
              ", ".join(f"{k} {v}" for k, v in lo.most_common()))
    return doc


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="ur.possess")
    p.add_argument("work")
    a = p.parse_args(argv)
    build(Path(a.work))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
