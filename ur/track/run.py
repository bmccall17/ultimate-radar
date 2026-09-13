"""M4 — fourteen locked slots, tracked in field space. Writes tracks.json.

    python -m ur.track.run work/p0001        # -> tracks.json

Read AD-1, AD-2, AD-3 and `docs/05-uncertainty.md` before changing anything here.

**AD-2 is the load-bearing decision.** There are exactly 7 offensive and 7
defensive players for the whole possession. Slots are never created and never
destroyed; a slot with no detection degrades through `predicted` to `unknown`
rather than disappearing. That rules out the two failures a coach will never
forgive — a player who blinks out of existence, and a phantom extra defender —
and it turns identity into a bounded assignment problem, 7 candidates rather
than N.

It also does something the M3 stand-in could not. The stand-in had no motion
model, so a detection that no slot could claim had to either be thrown away or
shoved into an occupied slot; it shoved, 467 times, and that is where its
identity shuffles came from. Here a slot that misses a frame keeps predicting,
its covariance grows, and its association gate grows with it — so a player who
leaves frame and comes back is re-claimed by their own slot instead of taking
someone else's. **A leftover detection never takes a live slot.** If more
same-team detections are in frame than there are free slots, the extras are
simply not assigned, and that is the roster constraint telling you something
true: at least one of them is not a player.

**AD-3 makes team a hard gate.** Association across teams is forbidden outright,
so the assignment problem is solved once per team. Detections flagged
`weak_team` are excluded entirely — those are the ones whose torso matches
neither kit, which is where `ur/team.py`'s three uncaught referees end up. In M3
excluding them cost coverage, because a lost detection meant a slot with no
position at all. Here it costs almost nothing: the motion model covers the gap
and the sample is `predicted`, which is the honest description of it anyway.

**The state machine is `docs/05-uncertainty.md`'s, and M4 is the first stage
allowed to run it.** `observed` on a match. On a miss, `predicted` while the gap
is under 2.2 s, then `unknown`. Then a second, retrospective pass marks a miss
`interpolated` when observations exist within ±0.5 s on *both* sides — which can
only be decided after the fact, because you do not know a gap was short until it
closes.

`predicted` positions are left as dead reckoning and are allowed to be wrong.
Running a smoother back through them would produce a tidier path, and it would
be a worse answer: docs/05 argues that a ghost which drifts and then snaps back
when the player reappears is honest, while a smooth interpolation through a gap
nobody watched reads as information. Only `interpolated` spans — short, bracketed
and cheap to be right about — get filled in.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from scipy.optimize import linear_sum_assignment

from .kalman import DAMP_TAU_S, SIGMA_ACCEL, Track, mahalanobis2

SEED = 20260827

N_PER_TEAM = 7

# Association gate. Chi-square with 2 degrees of freedom at p = 0.99.
GATE_CHI2 = 9.21
# ...and a hard physical bound on top of it, because after a long gap the
# covariance grows until the statistical gate would accept most of the field.
# AD-1: a sprint is about 9.5 yd/s.
MAX_SPEED_YD_S = 9.5
GATE_FLOOR_YD = 2.0       # a gate is never tighter than this, whatever P says

# docs/05 state machine, in seconds.
PREDICT_MAX_S = 2.2       # beyond this a slot is `unknown`, not `predicted`
INTERP_MAX_S = 0.5        # observations within this on BOTH sides -> interpolated

UNKNOWN_SIGMA_MIN = 3.0   # docs/05
UNKNOWN_SIGMA_MAX = 16.0


class Slot:
    def __init__(self, name: str, team: str):
        self.name = name
        self.team = team
        self.track = Track()
        self.last_obs_f: int | None = None
        self.samples: list[dict] = []

    @property
    def live(self) -> bool:
        return self.track.started


def _measurement_noise(det: dict, residual_yd: float | None) -> np.ndarray:
    """R for one detection, in yards².

    Two independent contributions, added in quadrature because they are:

    - `sigma_yd`, the foot-point term, which M3 measured rather than assumed
      (5.83 px rms times the local ground-plane scale).
    - the frame's own calibration residual, which AD-1 requires be carried into
      the measurement noise so a poorly-fitted frame down-weights its detections
      instead of silently corrupting the track. Frames below confidence 0.5 never
      get here at all — `ur.detect.run` refuses to state a position on them.
    """
    s = float(det.get("sigma_yd") or 0.6)
    r = float(residual_yd or 0.0)
    v = s * s + r * r
    return np.diag([v, v])


def associate_team(slots: list[Slot], dets: list[tuple[int, np.ndarray, np.ndarray]],
                   gap_frames: dict[str, int], dt: float
                   ) -> tuple[dict[str, int], np.ndarray]:
    """Gated Hungarian assignment for one team. Returns slot name -> det index.

    Cost is the squared Mahalanobis distance of the innovation, which weighs a
    candidate by how surprising it is given the slot's own uncertainty rather
    than by raw yards — a slot that has been unobserved for a second should
    accept a more distant detection than one seen last frame, and this is what
    makes that automatic.
    """
    live = [s for s in slots if s.live]
    if not live or not dets:
        return {}, np.zeros(len(dets), bool)

    BIG = 1e6
    cost = np.full((len(live), len(dets)), BIG)
    for i, s in enumerate(live):
        gap = max(1, gap_frames.get(s.name, 1))
        reach = max(GATE_FLOOR_YD, MAX_SPEED_YD_S * dt * gap)
        for j, (_, z, R) in enumerate(dets):
            if float(np.hypot(*(z - s.track.position))) > reach:
                continue
            y, S = s.track.innovation(z, R)
            d2 = mahalanobis2(y, S)
            if d2 <= GATE_CHI2:
                cost[i, j] = d2
    rows, cols = linear_sum_assignment(cost)
    out = {}
    for i, j in zip(rows, cols):
        if cost[i, j] < BIG:
            out[live[i].name] = j
    # Which detections were in *some* slot's gate, whether or not they won it.
    in_gate = (cost < BIG).any(axis=0)
    return out, in_gate


def track(work: Path, *, verbose: bool = True) -> dict:
    clip = json.loads((work / "clip.json").read_text(encoding="utf-8"))
    det = json.loads((work / "detections.json").read_text(encoding="utf-8"))
    cal = json.loads((work / "calibration.json").read_text(encoding="utf-8"))

    fps = float(clip["fps"])
    dt = 1.0 / fps
    n_frames = int(clip["frames"])
    offense, defense = clip["offense"], clip["defense"]
    residuals = {r["f"]: r.get("residual_yd") for r in cal["frames"]}
    by_frame = {d["f"]: d["dets"] for d in det["frames"]}

    slots: list[Slot] = []
    for team, pre in ((offense, "O"), (defense, "D")):
        for k in range(N_PER_TEAM):
            slots.append(Slot(f"{pre}{k + 1}", team))
    by_team = {t: [s for s in slots if s.team == t] for t in (offense, defense)}

    stats = {"unassigned_detections": 0, "weak_team_skipped": 0,
             "seeded": {}, "frames_with_surplus": 0,
             "unassigned_surplus": 0, "unassigned_lost_contest": 0,
             "unassigned_no_slot_in_gate": 0}

    for f in range(n_frames):
        for s in slots:
            if s.live:
                s.track.predict(dt)

        cands: dict[str, list[tuple[int, np.ndarray, np.ndarray]]] = {
            offense: [], defense: []}
        for i, d in enumerate(by_frame.get(f, [])):
            if not d.get("in_bounds") or d.get("non_player"):
                continue
            if d.get("weak_team"):
                stats["weak_team_skipped"] += 1
                continue
            t, xy = d.get("team"), d.get("field")
            if t in cands and xy is not None:
                cands[t].append((i, np.asarray(xy, float),
                                 _measurement_noise(d, residuals.get(f))))

        assigned: dict[str, int] = {}
        for team in (offense, defense):
            group = by_team[team]
            gaps = {s.name: (f - s.last_obs_f) if s.last_obs_f is not None else 1
                    for s in group}
            hit, in_gate = associate_team(group, cands[team], gaps, dt)
            assigned.update(hit)

            # Leftovers seed slots that have NEVER been observed - the cold start
            # in docs/04 M4, one player at a time. They never take a live slot:
            # that is the whole difference between this and the M3 stand-in.
            taken = set(hit.values())
            free = [s for s in group if not s.live]
            left = [k for k in range(len(cands[team])) if k not in taken]
            left.sort(key=lambda k: (round(float(cands[team][k][1][0]), 3),
                                     round(float(cands[team][k][1][1]), 3)))
            for s, k in zip(free, left):
                _, z, R = cands[team][k]
                s.track.start(z, float(np.sqrt(R[0, 0])))
                assigned[s.name] = k
                stats["seeded"].setdefault(s.name, f)

            # Anything still unplaced, classified. The three reasons mean very
            # different things and lumping them hides which one is a problem.
            still = left[len(free):]
            if still:
                stats["frames_with_surplus"] += 1
            for k in still:
                stats["unassigned_detections"] += 1
                if len(cands[team]) > N_PER_TEAM:
                    stats["unassigned_surplus"] += 1
                elif k < len(in_gate) and in_gate[k]:
                    stats["unassigned_lost_contest"] += 1
                else:
                    stats["unassigned_no_slot_in_gate"] += 1

        for s in slots:
            j = assigned.get(s.name)
            if j is not None:
                di, z, R = cands[s.team][j]
                # A slot seeded this frame already has the measurement in it,
                # via start(); updating again would count it twice.
                if stats["seeded"].get(s.name) != f:
                    s.track.update(z, R)
                s.last_obs_f = f
                s.samples.append({
                    "f": f, "xy": [round(float(v), 3) for v in s.track.position],
                    "state": "observed",
                    "sigma": round(s.track.position_sigma(), 3),
                    "det": di,
                    "v": [round(float(v), 3) for v in s.track.velocity],
                })
            else:
                if not s.live:
                    s.samples.append({"f": f, "xy": None, "state": "unknown",
                                      "sigma": UNKNOWN_SIGMA_MAX, "det": None,
                                      "v": None})
                    continue
                gap_s = (f - s.last_obs_f) * dt if s.last_obs_f is not None else 1e9
                if gap_s <= PREDICT_MAX_S:
                    s.samples.append({
                        "f": f, "xy": [round(float(v), 3) for v in s.track.position],
                        "state": "predicted",
                        "sigma": round(s.track.position_sigma(), 3),
                        "det": None,
                        "v": [round(float(v), 3) for v in s.track.velocity],
                    })
                else:
                    sig = min(UNKNOWN_SIGMA_MAX,
                              max(UNKNOWN_SIGMA_MIN, s.track.position_sigma()))
                    s.samples.append({
                        "f": f, "xy": [round(float(v), 3) for v in s.track.position],
                        "state": "unknown", "sigma": round(sig, 3), "det": None,
                        "v": None})

    n_interp = retrospective_interpolation(slots, dt)
    doc = write_tracks(work, clip, det, slots, stats, n_interp, verbose=verbose)
    return doc


def retrospective_interpolation(slots: list[Slot], dt: float) -> int:
    """The second pass docs/05 asks for.

    A miss becomes `interpolated` only when observations exist within
    INTERP_MAX_S on *both* sides. That cannot be decided online — you do not know
    a gap was short until it closes — so it happens here, over the whole
    possession, exactly as the spec says.

    The fill is a straight line between the bracketing observations, as
    specified. Its sigma is the interpolated endpoint uncertainty plus the
    deviation a Brownian bridge would allow: an unmodelled acceleration of
    SIGMA_ACCEL bends a chord by at most a·t1·t2/2 over a gap split t1 : t2, and
    that term is added in quadrature. It goes to zero at both ends and peaks in
    the middle, which is the right shape for "we know where they were before and
    after, and the doubt is what they did in between".
    """
    n = 0
    for s in slots:
        obs = [k for k, smp in enumerate(s.samples) if smp["state"] == "observed"]
        if len(obs) < 2:
            continue
        for a, b in zip(obs, obs[1:]):
            if b - a < 2:
                continue
            t_total = (b - a) * dt
            pa = np.array(s.samples[a]["xy"], float)
            pb = np.array(s.samples[b]["xy"], float)
            sa, sb = s.samples[a]["sigma"], s.samples[b]["sigma"]
            for k in range(a + 1, b):
                t1, t2 = (k - a) * dt, (b - k) * dt
                if t1 > INTERP_MAX_S or t2 > INTERP_MAX_S:
                    continue
                u = t1 / t_total
                xy = pa + (pb - pa) * u
                s_end = np.sqrt((1 - u) ** 2 * sa ** 2 + u ** 2 * sb ** 2)
                s_bridge = 0.5 * SIGMA_ACCEL * t1 * t2
                s.samples[k].update({
                    "xy": [round(float(v), 3) for v in xy],
                    "state": "interpolated",
                    "sigma": round(float(np.hypot(s_end, s_bridge)), 3),
                    "det": None,
                })
                n += 1
    return n


def write_tracks(work: Path, clip: dict, det: dict, slots: list[Slot],
                 stats: dict, n_interp: int, *, verbose: bool = True) -> dict:
    n_frames = int(clip["frames"])
    by_frame = {d["f"]: d["dets"] for d in det["frames"]}

    out_slots = []
    for s in slots:
        states = [smp["state"] for smp in s.samples]
        # Tracklet-level team evidence. AD-3 already gated association by team,
        # so this cannot change a team - what it reports is how well the slot's
        # own detections agreed, which is the signal M5 and a human need when a
        # slot looks wrong.
        scores = [by_frame[smp["f"]][smp["det"]].get("team_score")
                  for smp in s.samples if smp["det"] is not None]
        scores = [x for x in scores if x is not None]
        out_slots.append({
            "slot": s.name,
            "team": s.team,
            "samples": [{"f": smp["f"], "xy": smp["xy"], "state": smp["state"],
                         "sigma": smp["sigma"], "det": smp["det"]}
                        for smp in s.samples],
            "observed": states.count("observed"),
            "interpolated": states.count("interpolated"),
            "predicted": states.count("predicted"),
            "unknown": states.count("unknown"),
            "first_observed_f": stats["seeded"].get(s.name),
            "team_score_median": (round(float(np.median(scores)), 3) if scores
                                  else None),
        })

    n_obs = sum(r["observed"] for r in out_slots)
    doc = {
        "schema": "ultimate-radar/tracks@1",
        "possession_id": clip["possession_id"],
        "immutable": ("Nothing downstream may write to this file. Human edits go "
                      "to corrections.json and are applied by ur/resolve.py. See "
                      "AD-6."),
        "method": {
            "module": "ur.track.run",
            "frame": "field yards, tracked on the ground plane (AD-1) - never pixels",
            "model": "damped constant velocity Kalman, 4-state [x, y, vx, vy]",
            "sigma_accel_yd_s2": SIGMA_ACCEL,
            "damp_tau_s": DAMP_TAU_S,
            "association": "per-team gated Hungarian on squared Mahalanobis distance",
            "gate_chi2_2dof": GATE_CHI2,
            "gate_max_speed_yd_s": MAX_SPEED_YD_S,
            "team_gate": "hard, AD-3: association across teams is forbidden",
            "weak_team": "excluded from association; those detections match neither "
                         "kit and are where ur.team's uncaught referees end up",
            "slots": "exactly 14, never created or destroyed (AD-2). A leftover "
                     "detection may seed a never-observed slot but never takes a "
                     "live one.",
            "measurement_noise": "sigma_yd (measured foot-point term) and the "
                                 "frame's calibration residual, in quadrature (AD-1)",
            "states": "docs/05-uncertainty.md. predicted while the gap is under "
                      f"{PREDICT_MAX_S} s, then unknown; interpolated assigned "
                      f"retrospectively when observations sit within {INTERP_MAX_S} s "
                      "on both sides",
            "predicted_left_as_dead_reckoning": (
                "docs/05: a ghost that drifts and snaps back when the player "
                "reappears is honest; a smoothed path through a gap nobody watched "
                "reads as information. No smoother is run over predicted spans."),
            "seed": SEED,
        },
        "diagnostics": {
            "frames": n_frames,
            "slot_frames": n_frames * len(slots),
            "observed_fraction": round(n_obs / (n_frames * len(slots)), 4),
            "interpolated_samples": n_interp,
            "weak_team_detections_skipped": stats["weak_team_skipped"],
            "detections_unassigned": stats["unassigned_detections"],
            "unassigned_more_than_seven_of_a_team": stats["unassigned_surplus"],
            "unassigned_no_slot_within_gate": stats["unassigned_no_slot_in_gate"],
            "unassigned_lost_a_contested_slot": stats["unassigned_lost_contest"],
            "frames_with_unassigned": stats["frames_with_surplus"],
            "surplus_note": "Three different things, kept apart. More than seven "
                            "of a team in frame is information, not a loss - under "
                            "AD-2 at least one of them is not a player. No slot "
                            "within the gate means the detection is far from every "
                            "slot the tracker holds, which on this possession means "
                            "a median of 23 yd and is almost always a non-player. "
                            "Losing a contested slot is the one that costs a real "
                            "observation, and it is the number to watch.",
        },
        "slots": out_slots,
    }
    (work / "tracks.json").write_text(json.dumps(doc, indent=1) + "\n",
                                      encoding="utf-8")
    if verbose:
        d = doc["diagnostics"]
        print(f"[track] {len(out_slots)} slots x {n_frames} frames")
        print(f"[track] observed {d['observed_fraction']:.1%}, "
              f"interpolated {n_interp}, "
              f"weak_team skipped {d['weak_team_detections_skipped']}")
        print(f"[track] unassigned {d['detections_unassigned']}: "
              f"{d['unassigned_more_than_seven_of_a_team']} surplus, "
              f"{d['unassigned_no_slot_within_gate']} outside every gate, "
              f"{d['unassigned_lost_a_contested_slot']} lost a contested slot")
        for r in out_slots:
            print(f"    {r['slot']:>3} {r['team']:>5}  obs {r['observed']:>3} "
                  f"interp {r['interpolated']:>3} pred {r['predicted']:>3} "
                  f"unk {r['unknown']:>3}   first seen f{r['first_observed_f']}")
    return doc


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="ur.track.run")
    p.add_argument("work")
    a = p.parse_args(argv)
    track(Path(a.work))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
