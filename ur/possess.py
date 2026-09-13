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
are dead reckoning and are allowed to be wrong. What is *not* established is
whether any of it passes M4's gates — none of them are measured at the time of
writing — so the file carries `gates_measured: false` and a notice saying so.
That is the same discipline `ur/standin.py` used with `stand_in: true`: a file
that will be read by something downstream has to say what it is.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np


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
            "observed_frames": s["observed"],
            "state_counts": {k: s[k] for k in
                             ("observed", "interpolated", "predicted", "unknown")},
            "first_observed_f": s.get("first_observed_f"),
        })
    players.sort(key=lambda p: (p["id"][0] != "O", p["id"]))

    obs = np.array([[x == "observed" for x in p["state"]] for p in players])
    coverage = obs.sum(axis=0).tolist()

    # Detections the tracker did not use, kept per frame so the render can show
    # them. Seeing what is standing where a slot is not is the cheapest read
    # available on whether excluding weak_team was the right call.
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
                        "why": "weak_team" if d.get("weak_team") else "unassigned",
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
        "gates_measured": False,
        "notice": (
            "Positions, evidence states and sigmas are the M4 tracker's real "
            "output (ur.track.run). NONE of M4's acceptance gates have been "
            "measured yet, so nothing in this file is established: identity "
            "switches, position error and sigma calibration are all unknown. "
            "`predicted` samples are dead reckoning and are allowed to be wrong "
            "by design - docs/05-uncertainty.md explains why a ghost that drifts "
            "and snaps back is more honest than one frozen in place."
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
            "position_yd": cam["position_yd"],
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
