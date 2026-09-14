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

**AD-3 gates team, and round 2 changed how.** Association across a confidently
classified kit is still forbidden outright — that is the cross-team identity swap
AD-3 exists to prevent, and it stays at zero. What changed is that a detection
whose kit call is *weak* is no longer deleted. It used to be: `weak_team` meant
"excluded entirely", justified in `docs/17` on the grounds that those detections
were mostly referees. Measured against `eval/m3/team_labels.json` they are 64 %
real players, and that exclusion was the single largest cause of slots going
blind — 218 slot-frames on p0001 where a usable detection sat within 1.5 yd of a
slot that was dead-reckoning. Now an uncertain kit is a price in the assignment
cost rather than a veto. See `docs/25-round-2-ghost-audit.md`.

Because a kit-ambiguous detection is a candidate for slots on both teams, the
assignment is solved **once over all fourteen slots** rather than once per team.
Two per-team solves would each be free to take the same detection, which is how a
person becomes two players.

**The state machine is `docs/05-uncertainty.md`'s, and M4 is the first stage
allowed to run it.** `observed` on a match. On a miss, `predicted` while the gap
is under 2.2 s, then `unknown`. Then a second, retrospective pass marks a miss
`interpolated` when observations exist within ±0.5 s on *both* sides — which can
only be decided after the fact, because you do not know a gap was short until it
closes.

Two states were added in round 2. A match that re-acquires a slot after a long
gap is `provisional` rather than `observed` — an observation of somebody, where
whether it is the same somebody is the open question — and an `unknown` sample
reports the last position anyone actually saw, with a growing sigma, instead of
creeping through grass nobody has looked at.

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
# ...and a physical bound on top of it, because after a long gap the covariance
# grows until the statistical gate alone would accept most of the field. AD-1: a
# sprint is about 9.5 yd/s.
MAX_SPEED_YD_S = 9.5

# The physical bound limits how far the PLAYER can have moved. What the gate
# actually compares it against is the distance between two *measured* points -
# the slot's last observed position and the candidate detection - and both of
# those carry noise. Allowing k sigma of combined endpoint noise on top of the
# displacement bound is what makes the comparison type-correct.
#
# The first version instead used `max(2.0, speed * elapsed)`. The 2.0 yd floor
# was meant as a backstop for long gaps; at a gap of one or two frames it is
# *tighter* than the statistical gate, so it overrode the covariance exactly when
# the covariance was small and right. It cost 70 associations that chi-square
# scored at 4.4 against a threshold of 9.21 - see docs/16-m4-watching.md, which
# found it by watching the render rather than by reading any statistic.
GATE_NOISE_SIGMAS = 3.0
GATE_FLOOR_YD = 0.5       # degenerate case only: no sigma available at all

# --- round 2: the two gates are a union, not an intersection (audit R2) ----- #
#
# The reach bound and the chi-square gate were both required. `docs/25` worked out
# what that means in yards: with sigma reported at 1.794x the per-axis value and a
# chi-square radius of sqrt(9.21) = 3.035 per-axis sigmas, the statistical reach is
# 1.692 x the reported sigma - and that is *tighter* than the physical reach at
# every elapsed time past half a second, by a factor of 1.7-2.
#
# That is backwards. The longer a slot has been unobserved, the less its stale
# covariance deserves to be the binding constraint and the more the physics should
# be. So a candidate is admissible if it is inside EITHER gate.
#
# The physical branch is deliberately narrow, because on its own it is very wide -
# 28 yd at a three-second gap. It only opens for a slot that has actually been
# waiting, and only for a detection no other slot has already been assigned. That
# second condition is what keeps it from stealing: if the chi-square branch placed
# the detection, it was doing its job and the physical branch has no business
# bidding against it.
#
# **What it buys, measured, and what it costs.** On p0001 it makes 24 assignments
# and lifts the observed fraction from 0.6946 to 0.7135. Thirteen of the 24 are
# jumps of 12-22 yd after gaps of 1.1-1.9 s, which is the branch doing exactly
# what it is for and is also where it will be wrong when it is wrong. Every one of
# them is emitted as `provisional` and queued for review - that pairing is what
# makes the branch safe to have, and the branch would not be defensible without it.
#
# The setting is 0.5 s because that is where `docs/25` measures the chi-square
# reach crossing below the physical one, not because 0.5 scored best. Sweeping it
# over 0.5 / 0.8 / 1.0 / 1.5 / 2.0 / off gives per-player recall of 0.8932,
# 0.8803, 0.8803, 0.9188, 0.8803, 0.8974 - non-monotone, and the whole spread is
# about one standard error on a 234-player label set. One flipped assignment early
# in a possession changes every assignment after it, so all of these statistics
# are chaotic at this sample size. **Do not tune on them.** Pick the value the
# argument gives and report what it measured.
REACH_BRANCH_MIN_GAP_S = 0.5

# --- round 2: team is priced, not vetoed (audit R1) ------------------------ #
#
# AD-3 made team a hard gate and gave the reason: a cross-team identity swap
# corrupts every matchup and every separation number at once. That reason still
# holds and the protection is still here - what changed is which detections it
# applies to.
#
# The old rule forbade association across the *label*, and deleted outright any
# detection whose label was weak. Measured against eval/m3/team_labels.json, that
# deleted roughly two real players for every non-player it caught, and it is the
# single largest cause of slots going blind on p0001: 218 slot-frames where a
# usable detection sat within 1.5 yd of a slot that was dead-reckoning.
#
# The new rule forbids association when the kit evidence leans to the other team
# by 3:1 or more. Between there and certainty the detection is admissible and pays
# for the doubt:
#
#     kit penalty = -2 ln P(detection's kit = slot's team)
#
# in the same units as the squared Mahalanobis distance, because both are twice a
# negative log likelihood. At the block threshold the penalty is 2.8, about a
# third of the chi-square gate - enough to lose any contest that is close on
# geometry, not enough to override a detection sitting on top of the slot.
#
# **0.25 was chosen from a sweep, and from the shape of the sweep rather than its
# peak.** Blocking at 0.10, 0.15, 0.20, 0.25, 0.30, 0.40 and 0.50 gives an
# observed fraction of 0.7044, 0.7139, 0.7137, 0.7135, 0.7133, 0.7129, 0.7107 -
# a plateau everywhere except the loosest setting - while assignments taking a
# detection whose nearer label is the other team fall monotonically: 21, 15, 14,
# 13, 11, 6, 0. Coverage is flat and cross-label risk is not, so the setting is
# picked from the strict end of the plateau.
#
# The near-miss recovery count over the same sweep is 149, 164, 163, 157, 147,
# 151, 133 - not a function of the threshold in any useful sense. One flipped
# assignment early in a possession diverges everything after it, so that statistic
# is chaotic at this sample size and was deliberately not used to choose. It is
# reported, not optimised.
#
# What the criterion AD-3 actually states is unaffected at any of these values:
# a detection classified confidently (P >= 0.9) as one kit is never admissible to
# the other, and that is measured at zero on p0001 before and after.
KIT_BLOCK_P = 0.25
KIT_MAX_PENALTY = float(-2.0 * np.log(KIT_BLOCK_P))

# A slot that has never been observed is seeded from a leftover detection. That
# one still requires a confident kit: a cold start has no motion model, no history
# and no competing claim to sanity-check it, so it is the one place where an
# uncertain kit has nothing to lose against.
KIT_SEED_MIN_P = 0.90

# --- round 2: re-acquisition after a gap is provisional (audit R4) --------- #
#
# A slot that re-acquires after a long gap may have re-acquired the wrong person,
# and `docs/17` measured both of M5's specified detectors missing both real
# switches. The audit's own four candidates turned out not to separate under the
# better feature, and nobody has labels - so the tracker's job here is to *emit
# the whole reviewable set*, not to guess which are swaps.
#
# Every re-acquisition after this gap is marked `provisional` and carries what a
# human needs to judge it: how long the gap was, how far the observation is from
# the dead reckoning, and the runner-up it beat.
REACQ_MIN_GAP_S = 1.0

# docs/05 state machine, in seconds.
PREDICT_MAX_S = 2.2       # beyond this a slot is `unknown`, not `predicted`
INTERP_MAX_S = 0.5        # observations within this on BOTH sides -> interpolated

UNKNOWN_SIGMA_MIN = 3.0   # docs/05
UNKNOWN_SIGMA_MAX = 16.0

# What the `sigma` written into tracks.json MEANS.
#
# docs/05-uncertainty.md says the viewer draws a disc of this radius and gates on
# ">= 80 % of truths inside" it. Those two statements are only consistent if sigma
# is a containment radius, not a per-axis standard deviation: for a 2-D Gaussian
# with per-axis sigma_p, the disc of radius sigma_p contains just 39.3 %, so a
# per-axis value cannot reach 80 % however well calibrated it is.
#
# M3 already settled this for detections - `sigma_yd` is the rms of the measured
# 2-D offset, which contains 94 % - and the tracker was the inconsistent one.
# Measured before this change: 57.5 % containment, which is *better* than a
# perfectly calibrated per-axis sigma would give, because the filter's covariance
# is conservative by about 31 %. The gate was failing on a definition, not on the
# filter being wrong.
#
# 1.794 = sqrt(-2 ln 0.2), the radius in per-axis sigmas that contains 80 % of a
# 2-D Gaussian. The filter's internal covariance is untouched; only the number
# reported downstream changes.
SIGMA_CONTAINMENT_K = 1.7941


# The playing proper, in field yards. Not the same as the detector's in-bounds
# test, which deliberately carries a 2 yd apron so a thrower pivoting on the line
# and a defender chasing a throw are both kept - both are out of play and both
# matter (see ur/team.py).
FIELD_L, FIELD_W = 120.0, 160.0 / 3.0


def _on_field(xy, z) -> np.ndarray:
    """Keep an anchored estimate inside the field when its own evidence is.

    The failure this fixes is small and specific. A slot whose prior sits outside
    the sideline and whose detection sits inside it lands, after the Kalman blend,
    a fraction of a yard *outside* - the filter placing a player where nothing
    saw one. Two samples on p0001, both about 0.16 yd out, both from detections
    comfortably in play.

    The constraint is conditional on purpose. A blanket clamp would also drag a
    genuinely out-of-bounds player onto the field, and in ultimate that player is
    often the interesting one. So the estimate is only pulled back when the
    detection it was built from is itself in play: the rule is "do not place a
    player outside the field on the strength of evidence that is inside it",
    which is a statement about consistency rather than about where players may
    stand. Figures that really are off the field are `ur.team`'s problem, and the
    crew test is where that is handled.
    """
    zx, zy = float(z[0]), float(z[1])
    if not (0.0 <= zx <= FIELD_L and 0.0 <= zy <= FIELD_W):
        return xy
    return np.array([min(max(float(xy[0]), 0.0), FIELD_L),
                     min(max(float(xy[1]), 0.0), FIELD_W)])


def reported_sigma(track: Track) -> float:
    """The radius docs/05 wants drawn, from the filter's per-axis covariance.

    Association never uses this - it uses the covariance directly, where a
    per-axis sigma is the correct quantity. Only what is written out is scaled.
    """
    return SIGMA_CONTAINMENT_K * track.position_sigma()


class Slot:
    def __init__(self, name: str, team: str):
        self.name = name
        self.team = team
        self.track = Track()
        self.last_obs_f: int | None = None
        # The position sigma at the moment this slot was last *updated*, not the
        # grown one. The physical bound applies from where the player actually
        # was, and that was known this well - using the grown sigma instead would
        # widen the physical bound by the very uncertainty it exists to contain.
        self.last_obs_sigma: float | None = None
        # Where the slot was when it was last actually seen. `unknown` samples
        # report this rather than the dead-reckoned position - see audit R5.
        self.last_obs_xy: list[float] | None = None
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


def kit_probability(det: dict, team: str) -> float:
    """P(this detection's kit is `team`). Two kits, so the other is the complement.

    Falls back to the hard label for detections written before `team_p` existed,
    so an old detections.json still tracks rather than silently losing every
    candidate.
    """
    p = det.get("team_p")
    if p is None:
        return 1.0 if det.get("team") == team else 0.0
    p = float(p)
    return p if det.get("team") == team else 1.0 - p


def associate(slots: list[Slot], dets: list[dict], gap_frames: dict[str, int],
              dt: float) -> tuple[dict[str, int], np.ndarray, dict[str, dict]]:
    """Gated Hungarian assignment over all fourteen slots at once.

    **This used to be solved once per team, and is now solved once.** That is a
    consequence of AD-3 becoming a price rather than a veto: a detection whose kit
    is genuinely ambiguous is a candidate for slots on *both* teams, and two
    separate per-team solves would each be free to take it. One solve over all
    fourteen slots is what keeps a detection from being two players at once. The
    protection AD-3 was written for is unchanged and is enforced in the cost
    matrix - a confident cross-team pairing is never admissible at all.

    Cost is the squared Mahalanobis distance of the innovation plus the kit
    penalty. Mahalanobis weighs a candidate by how surprising it is given the
    slot's own uncertainty rather than by raw yards, so a slot unobserved for a
    second accepts a more distant detection than one seen last frame; the kit term
    is in the same units, being twice a negative log likelihood, so adding them is
    arithmetic rather than a weighting choice.
    """
    live = [s for s in slots if s.live]
    if not live or not dets:
        return {}, np.zeros(len(dets), bool), {}

    BIG = 1e6
    n, m = len(live), len(dets)
    chi2 = np.full((n, m), np.inf)
    stat_ok = np.zeros((n, m), bool)
    reach_ok = np.zeros((n, m), bool)
    kit_pen = np.zeros((n, m))
    kit_p = np.zeros((n, m))

    for i, s in enumerate(live):
        gap = max(1, gap_frames.get(s.name, 1))
        travel = MAX_SPEED_YD_S * dt * gap
        s_last = s.last_obs_sigma if s.last_obs_sigma is not None else GATE_FLOOR_YD
        stale_enough = gap * dt >= REACH_BRANCH_MIN_GAP_S
        for j, (_, z, R, det) in enumerate(dets):
            p = kit_probability(det, s.team)
            kit_p[i, j] = p
            if p < KIT_BLOCK_P:
                continue                  # AD-3: a confident other kit, never
            kit_pen[i, j] = float(-2.0 * np.log(max(p, 1e-9)))

            s_det = float(np.sqrt(R[0, 0]))
            reach = max(GATE_FLOOR_YD,
                        travel + GATE_NOISE_SIGMAS * float(np.hypot(s_last, s_det)))
            within_reach = float(np.hypot(*(z - s.track.position))) <= reach

            y, S = s.track.innovation(z, R)
            d2 = mahalanobis2(y, S)
            chi2[i, j] = d2
            stat_ok[i, j] = within_reach and d2 <= GATE_CHI2
            reach_ok[i, j] = within_reach and stale_enough

    # Two passes, and the order is the whole point of the union.
    #
    # Pass one is the statistical gate alone - unchanged behaviour, and it gets
    # first refusal on everything. Pass two offers what is *left over* to the
    # slots that are still empty and have been waiting at least
    # REACH_BRANCH_MIN_GAP_S, under the physical bound only.
    #
    # The audit phrased the restriction as "no competing slot inside their own
    # chi-square gate". Applying that literally to the matrix closes the branch
    # far too often: the common case is a detection that *is* inside some slot's
    # chi-square gate but loses to a better one, and then nobody can have it. What
    # the restriction is protecting is the assignment, not the gate - so the test
    # is run against the assignment, after pass one has actually been solved.
    cost = np.where(stat_ok, chi2 + kit_pen, BIG)
    rows, cols = linear_sum_assignment(cost)
    taken_slot = {int(i): int(j) for i, j in zip(rows, cols) if cost[i, j] < BIG}

    free_i = [i for i in range(n) if i not in taken_slot]
    free_j = [j for j in range(m) if j not in set(taken_slot.values())]
    reach_taken: dict[int, int] = {}
    if free_i and free_j:
        sub = np.where(reach_ok[np.ix_(free_i, free_j)],
                       (chi2 + kit_pen)[np.ix_(free_i, free_j)], BIG)
        r2, c2 = linear_sum_assignment(sub)
        for a, b in zip(r2, c2):
            if sub[a, b] < BIG:
                reach_taken[free_i[a]] = free_j[b]

    assign = dict(taken_slot)
    assign.update(reach_taken)
    admissible = stat_ok.copy()
    for i, j in reach_taken.items():
        admissible[i, j] = True
    cost = np.where(admissible, chi2 + kit_pen, BIG)
    branch = np.where(stat_ok, "chi2", "reach")

    out, amb = {}, {}
    for i, j in sorted(assign.items()):
        if cost[i, j] >= BIG:
            continue
        out[live[i].name] = j
        # How contested was this assignment? A swap after a dropout is not
        # statistically *surprising* - M5 measured the largest re-acquisition at
        # 1.73 sigma, because an honest covariance after two seconds admits half
        # the field. What distinguishes a swap is that more than one candidate was
        # plausible. That is only knowable here, so it is recorded here.
        #
        # **`margin` is never null any more (audit R2a).** It used to be omitted
        # whenever a slot had exactly one candidate, which was the majority of
        # every slot's records - D5 had zero non-null margins out of 253 - so any
        # statistic over it was mostly reading absent data, and a helper that read
        # the absence as zero concluded the least contested slot was the most.
        # The fix is to notice that "no rival" is not "no information": the
        # implicit rival is the gate edge, the cost at which the least attractive
        # admissible candidate would sit. Measuring against that makes alone-in-
        # the-gate read as a large margin, which is what it is.
        row = np.sort(cost[i][cost[i] < BIG])
        rival = row[1] if len(row) > 1 else GATE_CEILING
        amb[live[i].name] = {
            "alts": int(len(row)),
            "margin": round(float(max(0.0, min(rival, GATE_CEILING) - row[0])), 3),
            "chi2": round(float(chi2[i, j]), 3),
            "kit_p": round(float(kit_p[i, j]), 3),
            "kit_penalty": round(float(kit_pen[i, j]), 3),
            "branch": str(branch[i, j]),
            "runner_up": (None if len(row) < 2 else
                          _runner_up(cost[i], dets, j)),
        }
    # Which detections were admissible to *some* slot, whether or not they won it.
    in_gate = admissible.any(axis=0)
    return out, in_gate, amb


# The worst cost a candidate could carry and still be admitted: at the chi-square
# gate edge with the weakest kit call the block threshold allows. It is the
# reference `margin` is measured against when a slot has no rival.
GATE_CEILING = GATE_CHI2 + KIT_MAX_PENALTY


def _runner_up(row: np.ndarray, dets: list[dict], taken: int) -> dict | None:
    """The detection that came second, so a human can see both sides of a swap."""
    order = [k for k in np.argsort(row) if row[k] < 1e6 and k != taken]
    if not order:
        return None
    k = int(order[0])
    return {"det": int(dets[k][0]), "xy": [round(float(v), 2) for v in dets[k][1]],
            "cost": round(float(row[k]), 3)}


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

    stats = {"unassigned_detections": 0, "non_player_skipped": 0,
             "weak_kit_admitted": 0, "weak_kit_assigned": 0,
             "reach_branch_assignments": 0, "provisional": 0,
             "seeded": {}, "frames_with_surplus": 0,
             "unassigned_surplus": 0, "unassigned_lost_contest": 0,
             "unassigned_no_slot_in_gate": 0}

    for f in range(n_frames):
        for s in slots:
            if s.live:
                s.track.predict(dt)

        # One candidate list, not one per team. A detection whose kit is genuinely
        # ambiguous belongs to both teams' problems, and only a single assignment
        # can stop it from being taken by one slot on each.
        cands: list[tuple[int, np.ndarray, np.ndarray, dict]] = []
        for i, d in enumerate(by_frame.get(f, [])):
            if not d.get("in_bounds"):
                continue
            if d.get("non_player"):
                stats["non_player_skipped"] += 1
                continue
            xy = d.get("field")
            if d.get("team") is None or xy is None:
                continue
            if d.get("weak_team"):
                stats["weak_kit_admitted"] += 1
            cands.append((i, np.asarray(xy, float),
                          _measurement_noise(d, residuals.get(f)), d))

        gaps = {s.name: (f - s.last_obs_f) if s.last_obs_f is not None else 1
                for s in slots}
        assigned, in_gate, ambiguity = associate(slots, cands, gaps, dt)

        # Leftovers seed slots that have NEVER been observed - the cold start in
        # docs/04 M4, one player at a time. They never take a live slot: that is
        # the whole difference between this and the M3 stand-in. A seed still
        # needs a confident kit (KIT_SEED_MIN_P): a cold start has no history and
        # no competing claim, so there is nothing to catch a bad one.
        taken = set(assigned.values())
        left = [k for k in range(len(cands)) if k not in taken]
        left.sort(key=lambda k: (round(float(cands[k][1][0]), 3),
                                 round(float(cands[k][1][1]), 3)))
        used_for_seed: set[int] = set()
        for team in (offense, defense):
            free = [s for s in by_team[team] if not s.live]
            pool = [k for k in left
                    if k not in used_for_seed
                    and kit_probability(cands[k][3], team) >= KIT_SEED_MIN_P]
            for s, k in zip(free, pool):
                _, z, R, _ = cands[k]
                s.track.start(z, float(np.sqrt(R[0, 0])))
                assigned[s.name] = k
                used_for_seed.add(k)
                stats["seeded"].setdefault(s.name, f)

        # Anything still unplaced, classified. The three reasons mean very
        # different things and lumping them hides which one is a problem.
        still = [k for k in left if k not in used_for_seed]
        if still:
            stats["frames_with_surplus"] += 1
        n_live = sum(1 for s in slots if s.live)
        for k in still:
            stats["unassigned_detections"] += 1
            if len(cands) > n_live:
                stats["unassigned_surplus"] += 1
            elif k < len(in_gate) and in_gate[k]:
                stats["unassigned_lost_contest"] += 1
            else:
                stats["unassigned_no_slot_in_gate"] += 1

        for s in slots:
            j = assigned.get(s.name)
            if j is not None:
                di, z, R, d = cands[j]
                seeded_now = stats["seeded"].get(s.name) == f
                # A slot seeded this frame already has the measurement in it,
                # via start(); updating again would count it twice.
                if not seeded_now:
                    s.track.update(z, R)
                gap_s = ((f - s.last_obs_f) * dt
                         if s.last_obs_f is not None else 0.0)
                a = ambiguity.get(s.name)
                if a is not None:
                    if a["branch"] == "reach":
                        stats["reach_branch_assignments"] += 1
                    if a["kit_p"] < KIT_SEED_MIN_P:
                        stats["weak_kit_assigned"] += 1

                # A re-acquisition after a long gap is an observation of
                # *somebody*; whether it is the same somebody is exactly what
                # nobody can currently tell. It is recorded as `provisional`
                # rather than `observed` so a metric can refuse to use it until a
                # human has looked - see audit R4 and ur/issues.py.
                xy = _on_field(s.track.position, z)
                reacq = (not seeded_now and s.last_obs_f is not None
                         and gap_s >= REACQ_MIN_GAP_S)
                state = "observed"
                extra: dict = {}
                if reacq:
                    predicted = s.samples[-1]["xy"] if s.samples else None
                    jump = (None if predicted is None else
                            round(float(np.hypot(*(z - np.asarray(predicted,
                                                                  float)))), 3))
                    state = "provisional"
                    stats["provisional"] += 1
                    extra["reacquire"] = {
                        "gap_frames": int(f - s.last_obs_f),
                        "gap_s": round(gap_s, 3),
                        "jump_from_prediction_yd": jump,
                    }

                s.last_obs_f = f
                s.last_obs_sigma = s.track.position_sigma()
                s.last_obs_xy = [round(float(v), 3) for v in xy]
                s.samples.append({
                    "f": f, "xy": [round(float(v), 3) for v in xy],
                    "state": state,
                    "sigma": round(reported_sigma(s.track), 3),
                    "det": di,
                    "v": [round(float(v), 3) for v in s.track.velocity],
                    **({"assoc": a} if a is not None else {}),
                    **extra,
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
                        "sigma": round(reported_sigma(s.track), 3),
                        "det": None,
                        "v": [round(float(v), 3) for v in s.track.velocity],
                    })
                else:
                    # docs/05 argues a ghost that drifts is more honest than one
                    # frozen in place, and that is right *while the velocity
                    # estimate still means something*. Past PREDICT_MAX_S it does
                    # not: the OU model has damped the velocity to near zero, so
                    # the position creeps rather than tracks, and what it creeps
                    # into is open grass nobody has looked at. The reported
                    # position is therefore held at the last real observation and
                    # the sigma keeps growing - the honest statement being "they
                    # were here, this long ago, and could be anywhere in this
                    # disc by now". The filter itself keeps dead-reckoning, since
                    # that is still the best guess for re-association. See audit
                    # R5.
                    sig = min(UNKNOWN_SIGMA_MAX,
                              max(UNKNOWN_SIGMA_MIN, reported_sigma(s.track)))
                    s.samples.append({
                        "f": f, "xy": list(s.last_obs_xy) if s.last_obs_xy
                        else [round(float(v), 3) for v in s.track.position],
                        "state": "unknown", "sigma": round(sig, 3), "det": None,
                        "v": None, "anchor_f": s.last_obs_f})

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
        obs = [k for k, smp in enumerate(s.samples)
               if smp["state"] in ("observed", "provisional")]
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
        kits = [by_frame[smp["f"]][smp["det"]].get("team_p")
                for smp in s.samples if smp["det"] is not None]
        kits = [x for x in kits if x is not None]
        out_slots.append({
            "slot": s.name,
            "team": s.team,
            "samples": [{"f": smp["f"], "xy": smp["xy"], "state": smp["state"],
                         "sigma": smp["sigma"], "det": smp["det"],
                         **({"assoc": smp["assoc"]} if "assoc" in smp else {}),
                         **({"reacquire": smp["reacquire"]}
                            if "reacquire" in smp else {}),
                         **({"anchor_f": smp["anchor_f"]}
                            if "anchor_f" in smp else {})}
                        for smp in s.samples],
            "observed": states.count("observed"),
            "provisional": states.count("provisional"),
            "interpolated": states.count("interpolated"),
            "predicted": states.count("predicted"),
            "unknown": states.count("unknown"),
            "first_observed_f": stats["seeded"].get(s.name),
            "team_score_median": (round(float(np.median(scores)), 3) if scores
                                  else None),
            "team_p_median": (round(float(np.median(kits)), 3) if kits else None),
        })

    n_obs = sum(r["observed"] for r in out_slots)
    n_prov = sum(r["provisional"] for r in out_slots)
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
            "association": ("one gated Hungarian over all fourteen slots, on "
                            "squared Mahalanobis distance plus a kit penalty. It "
                            "was solved once per team until round 2; a kit-"
                            "ambiguous detection is a candidate for both teams, "
                            "and two separate solves would each be free to take "
                            "it."),
            "gate_chi2_2dof": GATE_CHI2,
            "gate_max_speed_yd_s": MAX_SPEED_YD_S,
            "gate_reach": ("max speed x elapsed, plus "
                           f"{GATE_NOISE_SIGMAS} sigma of combined endpoint noise "
                           "(the slot's sigma when last observed, and the "
                           "detection's). The physical bound limits how far the "
                           "player moved; the distance being compared is between "
                           "two measured points, so the noise of both belongs in "
                           "the comparison."),
            "gate_union": ("a candidate is admissible inside EITHER the chi-square "
                           "gate or the physical reach, not both. The chi-square "
                           "reach in yards is 1.692 x the reported sigma, which is "
                           "tighter than the physical bound at every gap past 0.5 s "
                           "- so requiring both made a stale covariance the binding "
                           "constraint exactly when physics should have been. The "
                           "reach branch opens only for a slot stale at least "
                           f"{REACH_BRANCH_MIN_GAP_S} s and only for a detection no "
                           "slot can claim statistically. See docs/25 R2."),
            "team_gate": ("AD-3, amended in round 2: association across a "
                          "*confidently* classified kit is forbidden outright "
                          f"(P < {KIT_BLOCK_P:.2f} for the slot's team is never "
                          "admissible). Between the confident bands the detection "
                          "is admissible to either team and pays "
                          "-2 ln P(kit = slot team) in the assignment cost."),
            "kit_block_p": KIT_BLOCK_P,
            "kit_max_penalty": round(KIT_MAX_PENALTY, 3),
            "kit_seed_min_p": KIT_SEED_MIN_P,
            "weak_team": ("admitted and priced, not excluded. Before round 2 these "
                          "were dropped entirely on the grounds that they were "
                          "mostly referees; measured against eval/m3/"
                          "team_labels.json they are 64 % real players, and the "
                          "exclusion was the largest single cause of slots going "
                          "blind. See docs/25 R1 and R6."),
            "slots": "exactly 14, never created or destroyed (AD-2). A leftover "
                     "detection may seed a never-observed slot but never takes a "
                     "live one, and a seed needs a confident kit.",
            "measurement_noise": "sigma_yd (measured foot-point term) and the "
                                 "frame's calibration residual, in quadrature (AD-1)",
            "assoc_means": ("per observed sample: `alts` is how many candidate "
                            "detections were admissible to that slot, `chi2` the "
                            "geometric cost of the one taken, `kit_p` the kit "
                            "probability it was taken on, `kit_penalty` what that "
                            "cost it, `branch` which gate admitted it, and "
                            "`runner_up` the candidate it beat. `margin` is the "
                            "cost gap to the best alternative, where a slot with no "
                            f"alternative is measured against the gate ceiling "
                            f"({GATE_CEILING:.2f}) - the cost at which the least "
                            "attractive admissible rival would have sat. It used to "
                            "be null in that case, which is most records, so any "
                            "statistic over it was reading absent data. See "
                            "docs/25 R2a."),
            "gate_ceiling": round(GATE_CEILING, 3),
            "sigma_means": ("the radius of a disc intended to contain the truth "
                            "about 80 % of the time (docs/05), not a per-axis "
                            f"standard deviation. It is {SIGMA_CONTAINMENT_K} x the "
                            "filter's per-axis position sigma. Association uses the "
                            "covariance directly and is unaffected."),
            "states": "docs/05-uncertainty.md. predicted while the gap is under "
                      f"{PREDICT_MAX_S} s, then unknown; interpolated assigned "
                      f"retrospectively when observations sit within {INTERP_MAX_S} s "
                      "on both sides; provisional for an observation that "
                      f"re-acquires a slot after a gap of {REACQ_MIN_GAP_S} s or "
                      "more",
            "provisional_means": (
                "a detection was matched, so this is an observation of somebody - "
                "but the slot had been estimating long enough that whether it is "
                "the same somebody is exactly what nobody can tell. Renders like an "
                "observation; excluded from measured metrics until a human confirms "
                "or swaps it. docs/17 measured both specified swap detectors "
                "catching 0 of 2 real switches, and the audit's replacement "
                "candidates did not separate under a better feature, so the "
                "tracker emits the whole reviewable set rather than guessing which "
                "are swaps. See docs/25 R4."),
            "unknown_is_frozen": (
                "docs/05 argues a ghost that drifts beats one frozen in place, and "
                "that holds while the velocity estimate means something. Past "
                f"{PREDICT_MAX_S} s it does not - the OU model has damped velocity "
                "to near zero, so the marker creeps through grass nobody has "
                "looked at. An unknown sample reports the last observed position "
                "with a growing sigma, and `anchor_f` says when that was. The "
                "filter keeps dead-reckoning internally, because that is still the "
                "best guess for re-association. See docs/25 R5."),
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
            "provisional_fraction": round(n_prov / (n_frames * len(slots)), 4),
            "anchored_fraction": round((n_obs + n_prov) / (n_frames * len(slots)), 4),
            "anchored_note": "observed plus provisional. Both are frames in which a "
                             "detection was matched to the slot; they differ in "
                             "whether anyone can vouch that it is the same player.",
            "interpolated_samples": n_interp,
            "non_player_detections_skipped": stats["non_player_skipped"],
            "weak_kit_detections_admitted": stats["weak_kit_admitted"],
            "weak_kit_assignments": stats["weak_kit_assigned"],
            "reach_branch_assignments": stats["reach_branch_assignments"],
            "provisional_samples": stats["provisional"],
            "exclusion_note": "Non-player exclusions (referee, crew) and "
                              "low-confidence player detections are counted "
                              "separately, because docs/17 conflated them and drew "
                              "the wrong conclusion from the total. See docs/25 R6.",
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
        print(f"[track] observed {d['observed_fraction']:.1%} + provisional "
              f"{d['provisional_fraction']:.1%} = anchored "
              f"{d['anchored_fraction']:.1%}, interpolated {n_interp}")
        print(f"[track] non-players skipped {d['non_player_detections_skipped']}, "
              f"weak-kit admitted {d['weak_kit_detections_admitted']} of which "
              f"{d['weak_kit_assignments']} won a slot; "
              f"{d['reach_branch_assignments']} via the reach branch")
        print(f"[track] unassigned {d['detections_unassigned']}: "
              f"{d['unassigned_more_than_seven_of_a_team']} surplus, "
              f"{d['unassigned_no_slot_within_gate']} outside every gate, "
              f"{d['unassigned_lost_a_contested_slot']} lost a contested slot")
        for r in out_slots:
            print(f"    {r['slot']:>3} {r['team']:>5}  obs {r['observed']:>3} "
                  f"prov {r['provisional']:>3} interp {r['interpolated']:>3} "
                  f"pred {r['predicted']:>3} unk {r['unknown']:>3}   "
                  f"first seen f{r['first_observed_f']}")
    return doc


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="ur.track.run")
    p.add_argument("work")
    a = p.parse_args(argv)
    track(Path(a.work))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
