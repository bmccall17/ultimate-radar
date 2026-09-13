"""M3 — a deliberately crude stand-in for the tracker, so the clip can be watched.

    python -m ur.standin work/p0001        # -> possession.json

**This is not a tracker and must never be mistaken for one.** It is greedy
nearest-neighbour matching in field space, team-gated and speed-gated, with no
motion model, no Kalman filter, no global assignment and no re-identification.
It exists for one reason: to put real data on the screen at the end of M3 so the
viewer can be built and looked at before M4 starts. Every output it writes says
so, in a `stand_in` flag and a `notice` string, the same way
`fixtures/possession_demo.json` carries `synthetic: true`.

What that means in practice, and it is worth being blunt: **the slot identities
here are close to meaningless over more than a second or two.** Two players of
the same team who pass within a yard will swap and nothing will notice. A player
who leaves frame and returns will come back in whatever slot happens to be free.
M4 exists to fix exactly this, and `docs/04-milestones.md` M4 sets the gate -
at most two identity switches over the possession, every one caught by M5's swap
detector. Nothing here is measured against that gate, because it would fail it.

**No `predicted`, no `interpolated`.** `docs/05-uncertainty.md` is explicit: those
states mean a motion model stood behind the estimate, and none does yet. A slot
with a match is `observed`; a slot without one is `unknown`. That is the whole
state machine at this milestone.

An `unknown` sample carries `xy: null` rather than a held-over position. The
contract in docs/03 wants a sample for every slot in every frame - no gaps,
because a gap is a decision the viewer would have to re-make - and this provides
one; what it refuses to provide is a *number*. Holding the last observed position
and letting a sigma grow around it is dead reckoning with the velocity set to
zero, and dead reckoning is what M4 is for. The sigma still grows, so the viewer
can draw the widening ignorance, but it is drawn around nothing.

Detections carrying `weak_team` are excluded from association. Those are the ones
whose torso matches neither kit - `ur/team.py` explains why that is where the
referees it could not catch end up - and putting one in a defender's slot would
be inventing a defender. The cost is real and is reported: excluding them turns
some genuine players into `unknown`.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

SEED = 20260827

# 9.5 yd/s is the implied-speed threshold docs/05 uses for its sanity detector.
# Used here as an association gate: a slot cannot claim a detection further away
# than a player could have run since the slot was last seen.
MAX_SPEED_YD_S = 9.5
GATE_CAP_YD = 12.0          # beyond this the gate stops meaning anything

# docs/05: unknown carries sigma >= 3 yd, capped at 16.
UNKNOWN_SIGMA_MIN = 3.0
UNKNOWN_SIGMA_MAX = 16.0
UNKNOWN_SIGMA_GROWTH = MAX_SPEED_YD_S   # yd per second of ignorance


def _slot_names(n: int, prefix: str) -> list[str]:
    return [f"{prefix}{i + 1}" for i in range(n)]


def associate(frames: list[dict], n_per_team: int, teams: tuple[str, str],
              fps: float) -> dict:
    """Greedy nearest-neighbour, team-gated and speed-gated. A stand-in.

    Per frame and per team: build every (slot, detection) pair whose distance is
    inside the slot's gate, take them shortest-first, and assign. Detections left
    over seed slots that have never been observed - which is how a player the
    camera has not shown yet gets picked up, and is the `docs/04` M4 rule for slot
    initialisation applied one player at a time rather than seven at once.
    """
    dt = 1.0 / fps
    slots: dict[str, dict] = {}
    for team in teams:
        pre = "O" if team == teams[0] else "D"
        for name in _slot_names(n_per_team, pre):
            slots[name] = {"team": team, "last_xy": None, "last_f": None,
                           "samples": [], "n_observed": 0}

    dropped = 0
    ungated = 0
    for fi, fr in enumerate(frames):
        by_team: dict[str, list[tuple[int, np.ndarray, float]]] = {t: [] for t in teams}
        for di, d in enumerate(fr["dets"]):
            if not d.get("in_bounds") or d.get("non_player") or d.get("weak_team"):
                continue
            t, xy = d.get("team"), d.get("field")
            if t in by_team and xy is not None:
                by_team[t].append((di, np.asarray(xy, float),
                                   float(d.get("sigma_yd") or UNKNOWN_SIGMA_MIN)))

        assigned: dict[str, tuple[int, np.ndarray, float]] = {}
        for team in teams:
            cands = list(by_team[team])
            names = [s for s, v in slots.items() if v["team"] == team]
            pairs = []
            for s in names:
                v = slots[s]
                if v["last_xy"] is None:
                    continue
                gap = fi - v["last_f"]
                gate = min(GATE_CAP_YD, MAX_SPEED_YD_S * dt * max(gap, 1))
                for k, (di, xy, sg) in enumerate(cands):
                    dist = float(np.hypot(*(xy - v["last_xy"])))
                    if dist <= gate:
                        pairs.append((dist, s, k))
            pairs.sort(key=lambda p: (p[0], p[1], p[2]))
            used_slots, used_dets = set(), set()
            for dist, s, k in pairs:
                if s in used_slots or k in used_dets:
                    continue
                used_slots.add(s)
                used_dets.add(k)
                assigned[s] = cands[k]

            # Leftovers. A detection that no slot could claim inside its speed
            # gate is a real, measured position of a real player, and dropping it
            # would leave the viewer with a gap where a player is plainly on
            # screen. So it takes a free slot anyway - never-observed slots first
            # (the docs/04 M4 cold-start rule, applied one player at a time), then
            # the slot unseen longest, which is the one whose identity was already
            # the least trustworthy.
            #
            # This is the single worst thing in this module and the clearest
            # reason it is a stand-in: it is where identity gets shuffled. It is
            # counted, and the count is written into possession.json.
            left = [c for k, c in enumerate(cands) if k not in used_dets]
            left.sort(key=lambda c: (round(c[1][0], 3), round(c[1][1], 3)))
            free = [s for s in names if s not in used_slots]
            free.sort(key=lambda s: (slots[s]["last_xy"] is not None,
                                     -(fi - (slots[s]["last_f"] if slots[s]["last_f"]
                                             is not None else -10 ** 6)), s))
            for s, c in zip(free, left):
                assigned[s] = c
                if slots[s]["last_xy"] is not None:
                    ungated += 1
            dropped += max(0, len(left) - len(free))

        for s, v in slots.items():
            if s in assigned:
                di, xy, sg = assigned[s]
                v["samples"].append({"xy": [round(float(xy[0]), 3), round(float(xy[1]), 3)],
                                     "state": "observed", "sigma": round(sg, 3), "det": di})
                v["last_xy"], v["last_f"] = xy, fi
                v["n_observed"] += 1
            else:
                if v["last_f"] is None:
                    sg = UNKNOWN_SIGMA_MAX
                else:
                    sg = min(UNKNOWN_SIGMA_MAX,
                             UNKNOWN_SIGMA_MIN
                             + UNKNOWN_SIGMA_GROWTH * (fi - v["last_f"]) * dt)
                v["samples"].append({"xy": None, "state": "unknown",
                                     "sigma": round(float(sg), 3), "det": None})
    return {"slots": slots, "dropped": dropped, "ungated": ungated}


def build(work: Path, *, verbose: bool = True) -> dict:
    clip = json.loads((work / "clip.json").read_text(encoding="utf-8"))
    det = json.loads((work / "detections.json").read_text(encoding="utf-8"))
    cal = json.loads((work / "calibration.json").read_text(encoding="utf-8"))

    offense, defense = clip["offense"], clip["defense"]
    n_frames = clip["frames"]
    frames = sorted(det["frames"], key=lambda r: r["f"])
    assert len(frames) == n_frames, f"{len(frames)} detection frames vs {n_frames} clip frames"

    res = associate(frames, 7, (offense, defense), clip["fps"])
    slots = res["slots"]

    players = []
    for name, v in slots.items():
        players.append({
            "id": name,
            "team": v["team"],
            "slot": name,
            "jersey": None,
            "role": "cutter" if name.startswith("O") else "defender",
            "est": [s["xy"] for s in v["samples"]],
            "state": [s["state"] for s in v["samples"]],
            "sigma": [s["sigma"] for s in v["samples"]],
            "det": [s["det"] for s in v["samples"]],
            "observed_frames": v["n_observed"],
        })
    players.sort(key=lambda p: (p["id"][0] != "O", p["id"]))

    obs = np.array([[s == "observed" for s in p["state"]] for p in players])
    coverage = obs.sum(axis=0).tolist()

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
        "stand_in": True,
        "notice": (
            "SLOT IDENTITIES ARE A STAND-IN, NOT TRACKING. Positions and team "
            "assignments are real, measured from the broadcast. Which slot a "
            "player occupies is greedy nearest-neighbour matching with no motion "
            "model and no re-identification, and it is close to meaningless over "
            "more than a second or two: two players of the same team passing "
            "within a yard will swap and nothing will notice. Built by ur.standin "
            "so that M3 could be seen on screen; M4 replaces it. Do not quote any "
            "per-player number from this file."
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
                     "Invert it to draw on the video.",
            "per_frame": per_frame,
        },
        "disc": None,
        "events": [],
        "players": players,
        "derived": {
            "coverage": coverage,
            "note": "coverage is the number of the 14 slots observed in that frame. "
                    "No tactical metric is derived here: docs/05 forbids a "
                    "'measured' figure built on slots this file cannot vouch for.",
        },
        "method": {
            "module": "ur.standin",
            "association": "greedy nearest-neighbour in field space, team-gated, "
                           "speed-gated; STAND-IN FOR M4",
            "max_speed_yd_s": MAX_SPEED_YD_S,
            "gate_cap_yd": GATE_CAP_YD,
            "states_emitted": ["observed", "unknown"],
            "states_forbidden_here": ["predicted", "interpolated", "confirmed"],
            "why_forbidden": "docs/05-uncertainty.md: those states presume a motion "
                             "model behind the estimate, and none exists before M4.",
            "unknown_xy": "null. The slot has a sample in every frame, as the "
                          "contract requires, but no position - holding the last "
                          "observed one is dead reckoning at zero velocity.",
            "excluded_from_association": "detections flagged weak_team, whose torso "
                                         "matches neither kit; see ur/team.py",
            "detections_dropped_no_free_slot": res["dropped"],
            "slots_claimed_outside_the_speed_gate": res["ungated"],
            "gate_note": "A detection no slot could claim inside its speed gate is "
                         "still a real measured position, so it takes a free slot "
                         "anyway rather than being thrown away. That is where slot "
                         "identity gets shuffled, and the count above is how often. "
                         "It is the clearest single reason this is a stand-in.",
            "seed": SEED,
        },
    }
    (work / "possession.json").write_text(json.dumps(doc, indent=1) + "\n",
                                          encoding="utf-8")

    if verbose:
        tot = obs.size
        print(f"[standin] {len(players)} slots x {n_frames} frames")
        print(f"[standin] observed fraction {obs.sum() / tot:.1%} "
              f"({obs.sum()} of {tot} samples)")
        print(f"[standin] coverage per frame: median {int(np.median(coverage))}/14, "
              f"min {min(coverage)}, max {max(coverage)}")
        print(f"[standin] slots claimed outside the speed gate: {res['ungated']} "
              f"(identity shuffles)")
        print(f"[standin] detections dropped for want of a free slot: {res['dropped']}")
        for p in players:
            print(f"    {p['id']:>3} {p['team']:>5}  observed {p['observed_frames']:>3}"
                  f"/{n_frames}")
    return doc


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="ur.standin")
    p.add_argument("work")
    a = p.parse_args(argv)
    build(Path(a.work))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
