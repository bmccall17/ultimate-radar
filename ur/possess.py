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
                             ("observed", "provisional", "weak", "interpolated",
                              "predicted", "unknown")},
            "first_observed_f": s.get("first_observed_f"),
        })
    players.sort(key=lambda p: (p["id"][0] != "O", p["id"]))

    # Coverage counts slots with a matched detection, which is `provisional` and
    # `weak` as well as `observed` - a re-acquisition is an observation of
    # somebody and the doubt is about identity, and a `weak` sample is a player
    # who was seen on a frame that is weakly placed. Both were seen. What they
    # are not is `observed`, and docs/05 is what stops a metric treating them
    # as such.
    obs = np.array([[x in ("observed", "provisional", "weak") for x in p["state"]]
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

    # The disc, if ur.disc has run. Two shapes: `disc` is the [x, y, z] triple the
    # viewer already draws, and `disc_meta` is the provenance beside it. They are
    # separate because the triple is geometry and the provenance is the reason
    # anything may or may not be computed from it - a viewer that reads only the
    # triple gets a position, and a viewer that reads both knows whether to trust
    # it. Nothing in this pipeline has seen a disc; see ur/disc.py.
    disc, disc_meta = None, None
    dpath = work / "disc.json"
    if dpath.exists():
        dd = json.loads(dpath.read_text(encoding="utf-8"))
        smp = sorted(dd["samples"], key=lambda r: r["f"])
        disc = [([*r["xy"], r["z"]] if r["xy"] is not None else None) for r in smp]
        disc_meta = {
            "state": [r["state"] for r in smp],
            "basis": [r["basis"] for r in smp],
            "holder": [r["holder"] for r in smp],
            "sigma": [r["sigma"] for r in smp],
            "source": [r["source"] for r in smp],
            "trustworthy": dd["diagnostics"]["inference_trustworthy"],
            "plausibility": dd["diagnostics"]["plausibility"],
            "note": dd["method"]["nothing_has_seen_the_disc"],
        }

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
            # Naming the possession stopped the viewer *announcing* them as its
            # own, but it left the numbers sitting in every page's data, where
            # anything reading possession.js still gets 0.9744 for p0003. Clicking
            # through the published site on 2026-09-15 is what made that concrete.
            # So the values now travel only on the possession they were measured
            # on; everywhere else the keys are null and the pointer remains.
            # tools/audit_site.py enforces it.
            "measured_on": "p0001",
            "per_player_recall": (0.9744 if clip["possession_id"] == "p0001"
                                  else None),
            "identity_switches_caught": None,
            "sigma_containment": (0.829 if clip["possession_id"] == "p0001"
                                  else None),
            "measured_here": clip["possession_id"] == "p0001",
            "note": "Per-player recall is 0.9744 against a threshold left "
                    "deliberately unset, because the statistic is chaotically "
                    "sensitive at this sample size - it moves non-monotonically "
                    "between 0.880 and 0.919 under association changes that should "
                    "not matter, which is about one standard error on 234 labelled "
                    "players. Sigma containment is 33 of 40, above the 80 % gate but "
                    "inside a Wilson 95 % interval of 68.1-91.3 %, so it needs a "
                    "larger sample to call properly. `identity_switches_caught` is null rather "
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
            # The quarter is what attacking direction belongs to (AD-10), so it
            # travels with the possession rather than staying behind in
            # clip.json where only the pipeline can see it.
            "quarter": clip.get("quarter"),
            # A DECLARATION, typed at cut time, and named as one. It is not the
            # source of the direction any more - `ur.direction` resolves that
            # from what a human confirmed, across possessions - and
            # `tools.gates` checks this against it rather than the other way
            # round. `tools.make_view` adds `attacking_direction_resolved`
            # beside it, because resolving needs every possession at once and
            # this module only ever sees one.
            "attacking_direction": clip["attacking_direction"],
            "attacking_direction_source": "declared",
            # Named for what it measures. It was `attacking_direction_check`,
            # beside `attacking_direction`, and three near-identical names for a
            # declaration, a drift and a fact is how the drift got mistaken for
            # the direction in the first place (docs/30 section 2.0).
            "offence_drift_check": _direction_check(
                players, offense, clip["attacking_direction"],
                clip["field"]["length_yd"], clip["field"]["endzone_yd"]),
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
        "disc": disc,
        "disc_meta": disc_meta,
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
        # The drift, and only the drift. Which end is being attacked is not
        # decided here any more (AD-10) - `python -m ur.direction` is.
        dc = doc["possession"]["offence_drift_check"]
        if dc["agrees"] is False:
            print(f"[possess] !! the drift disagrees with the declaration: "
                  f"{dc['why']}")
        elif dc["agrees"] is None:
            print(f"[possess] the drift says nothing here: {dc['why']}")
        else:
            print(f"[possess] the offence drifted {dc['drift_yd']:+.1f} yd, the "
                  f"way clip.json declares ({dc['declared']}). That is agreement "
                  "between two guesses, not a measured direction - docs/30 "
                  "section 2.0.")
    return doc


MIN_DIRECTION_DRIFT_YD = 5.0


def _direction_check(players: list[dict], offense: str, declared: str,
                     length_yd: float, endzone_yd: float) -> dict:
    """Which way did the offence actually go, against what `clip.json` claims?

    **This is not the attacking direction, and it was once mistaken for it.**
    `docs/30` section 2.0: the drift of the offence was recorded as the
    direction, and across quarters it does not survive - in three of the four
    quarters cut, both teams' offences drift the same way. Direction now comes
    from `ur.direction`, resolved from what a human confirmed. What is left here
    is a flag on the *declaration*: `attacking_direction` is the one field in
    `clip.json` a person types from memory, and it is inherited by copy-paste
    from the previous possession more easily than anything else there.

    **The obvious check does not work here, and it is worth saying why.** "Does
    the offence finish inside the endzone it was attacking" would be decisive,
    and it needs an absolute field x. `venue_transform.x_offset` is
    `field_length / 2` with `field_length` itself unresolved
    (`docs/08-risks.md` #5, `docs/28` "what it does not fix"), so along-pitch
    positions carry an unmeasured offset. On p0003 - a possession that ends in a
    goal - the leading receiver finishes at x = 87.4 with the endzone nominally
    at 100. The endzone test would have called that no goal, and it would have
    been the offset lying, not the tracker.

    So this measures the **drift**, which the offset cancels out of: where the
    offence centroid ends against where it started. It abstains below
    `MIN_DIRECTION_DRIFT_YD`, and a disagreement is a flag rather than a verdict
    - a possession can genuinely move backwards, and p0001 does, 81.9 -> 66.3 yd
    while legitimately attacking +x.
    """
    offs = [p for p in players if p["team"] == offense]
    if not offs:
        return {"agrees": None, "why": "no offensive slot in the tracks"}
    n = len(offs[0]["est"])

    # A straight line through the whole possession rather than first minus last:
    # the camera loses the offence for stretches at a time (p0003 has no
    # offensive position at all in its first 55 frames), and an endpoint that
    # happens to be missing should cost precision, not the whole measurement.
    fs, cs = [], []
    for f in range(n):
        xs = [p["est"][f][0] for p in offs if p["est"][f] is not None]
        if xs:
            fs.append(f)
            cs.append(float(np.mean(xs)))
    if len(fs) < max(10, n // 10):
        return {"agrees": None,
                "why": f"the offence has a position on only {len(fs)} of {n} "
                       "frames, too few to fit a direction"}
    slope, intercept = np.polyfit(np.asarray(fs, float), np.asarray(cs), 1)
    a = float(intercept)
    b = float(intercept + slope * (n - 1))
    drift = b - a
    out = {"offence_centroid_x_start_yd": round(a, 1),
           "offence_centroid_x_end_yd": round(b, 1),
           "frames_with_an_offence": len(fs),
           "drift_yd": round(drift, 1), "declared": declared,
           "basis": "least-squares drift of the offence centroid over the "
                    "possession. The unresolved along-pitch offset (docs/08 #5) "
                    "cancels out of a difference"}
    if abs(drift) < MIN_DIRECTION_DRIFT_YD:
        out["agrees"] = None
        out["why"] = (f"the offence moved {drift:+.1f} yd along the pitch, which "
                      "is not enough to say which way they were attacking")
        return out
    measured = "+x" if drift > 0 else "-x"
    out["measured"] = measured
    out["agrees"] = measured == declared
    if not out["agrees"]:
        out["why"] = (
            f"the offence moved {drift:+.1f} yd but clip.json declares {declared}. "
            "Neither of those is the attacking direction (docs/30 section 2.0) - "
            "a possession can go backwards, and the drift was measured not to "
            "predict the end being attacked at all. To settle it, confirm the "
            "direction against the footage: `python -m ur.direction confirm "
            f"<work> --direction +x|-x`. To correct the declaration alone, re-run "
            f"ur.ingest with --attacking-direction {measured} (the cut is "
            "deterministic, so clip.mp4 and frames/ come back identical - check "
            "clip_sha256 - and nothing downstream needs redoing), then "
            "ur.possess.")
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="ur.possess")
    p.add_argument("work")
    a = p.parse_args(argv)
    build(Path(a.work))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
