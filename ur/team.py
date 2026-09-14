"""M3 — team assignment by torso colour, and the reject class AD-3 asks for.

    python -m ur.team work/p0001          # fills team / team_score in detections.json

Three things happen here, and the order matters.

**1. The two kits are fitted, not hard-coded.** Torso luminance is collected over
every in-bounds detection in the possession and split by a deterministic 2-means,
seeded at the extremes so the answer does not depend on a random draw. `docs/04`
calls for "2-means per point"; per possession is the same idea with more support
per fit, and it means a different venue, a different time of day or a different
pair of kits needs no constant edited here. What *is* assumed is that the two kits
differ in lightness, which M0 measured at delta-E 36.6 for this pair and which the
fit re-checks every run through `separation_ok`.

**2. Referees are rejected on appearance.** This is the half of AD-3 that M2 could
not build, and the reason M2's false-positive gate was deferred: a referee stands
*on* the field, so no geometric bounds test can reject one.

The M0 review predicted the mechanism would be torso luminance **variance** -
stripes have it, a flat kit does not. Measured on the 20 held-out frames, that is
not the discriminator. Variance does separate referees from a *clean* kit, but not
from the two cases that actually occur: a Chill jersey carries a large light number
on the back, and a box drawn round two overlapping players contains one dark torso
and one light one. Both have high variance.

What does separate them is that referee stripes are **periodic and vertically
coherent**, and neither a number nor a neighbour is. Averaging luminance down the
torso preserves vertical stripes and washes out everything else; high-passing that
column profile removes the low-frequency ramp a neighbouring player creates; what
survives is counted as bright runs. Three or more runs caught 5 of the 8 referees
in the label set and **zero** of the 234 players and 15 crew. It is a
high-precision, moderate-recall test, and it is reported that way rather than
tuned until it claims all eight.

**3. Camera crew are rejected on position *and* appearance, exactly as AD-3 says.**
Neither half alone is safe. Position alone would mean shrinking the out-of-bounds
margin, which would throw away real players - in ultimate a defender chasing a
throw and a thrower with a pivot on the line are both out of play and both matter.
Appearance alone would risk a mid-grey reading on a real player. Together: a figure
whose torso matches neither kit *and* whose feet are beyond the far sideline is
crew. On this possession that is 12 of 15, and no labelled player is anywhere near
- the six players whose torsos do land between the kits are all at soccer
y = -2 to 0, in the middle of the pitch.

Everything else gets the nearer kit and a `team_score` from how clear the call was.
A detection whose torso cannot be sampled at all gets `team: null` and a reason,
never a guess.

**4. The kit call is a probability (round 2).** `team_p` is P(the kit is the one
in `team`); the other kit is the complement, because there are exactly two. This
replaced a three-way hard label whose middle band was swallowing real players -
see the block comment on `WEAK_TEAM_P` for the measurement that forced it, and
`docs/25-round-2-ghost-audit.md` for what it cost the tracker. The probability is
calibrated to agree with the old hard label at its decision point, so `weak_team`
still flags the same detections; what changed is that the flag now carries a
number, and the tracker prices it instead of deleting it.

Both reject tests take their kit half from that probability rather than from band
membership. The hard band made them brittle in a way M4 watched twice: a figure
0.39 L* outside it escaped the test entirely and was tracked as a player for a
second and a half.

**Not done here:** nothing in this module uses more than one frame. A tracker can
vote a team over a tracklet and fix the occasional bad frame; M4 is where that
belongs, and `docs/05-uncertainty.md` governs how it is recorded.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np

SEED = 20260827

# Two bands, because they answer different questions. The colour band is wider
# vertically to gather enough kit pixels on a small or side-on figure; the stripe
# band is tighter on the panel the stripes actually occupy. Both trim the same
# amount off each side: at CX = 0.18 a neighbouring player's torso is mostly
# outside the sample, and trimming harder starts cutting into the kit itself.
COLOUR_BAND = (0.17, 0.48, 0.18)      # (top, bottom, side trim) as fractions of the box
STRIPE_BAND = (0.18, 0.46, 0.18)

MIN_TORSO_PX = 10          # below this there is no colour to speak of
STRIPE_W = 32              # column profile resampled to this, so runs are scale-free
STRIPE_SMOOTH = 9          # moving-average width for the high-pass
STRIPE_MIN_RUNS = 3        # measured: 5/8 referees, 0 of 249 non-referees
STRIPE_MIN_AMP = 3.5       # L units; referees that fire sit at 4.2-5.9

# How far from the midpoint between the two kits a torso must be before it counts
# as one of them. This is no longer a hard band - it is the point at which the kit
# probability below is calibrated to WEAK_TEAM_P. See KIT_LOGIT_K.
NEITHER_KIT_FRAC = 0.25

# --- the kit call is a probability, not a three-way hard label ------------- #
#
# **Why this changed (round 2).** The hard band this constant used to define ran
# L* 51.4-72.3 on p0001 - half the 41.8 L* separation between the two kits - and
# every detection inside it was flagged `weak_team` and then *excluded entirely*
# from association by ur.track.run. 341 detections landed there, and the tracker
# went blind on 218 slot-frames where one of them was sitting within 1.5 yd of the
# slot it belonged to.
#
# `docs/17-m4-tracking.md` justified that exclusion on the grounds that the
# excluded detections were "over half referees and camera crew". Measured against
# eval/m3/team_labels.json, which labels every in-bounds box on 20 held-out
# frames, that is not true. Of the 22 `weak_team` detections in the labelled set:
#
#     9 chill players, 5 sol players   -> 14 real players   (64 %)
#     3 referees, 2 camera crew        ->  5 non-players    (23 %)
#     3 boxes spanning two players     ->  3 unsure         (14 %)
#
# So the band was mostly discarding players. A hard three-way label was the wrong
# shape for the answer: the honest statement about an L* of 58 on this footage is
# "probably the dark kit, but not confidently", and that is a number, not a class.
#
# The logistic below says exactly that, and it is calibrated so it does not move
# the boundary anyone has already measured against: P = WEAK_TEAM_P at exactly the
# old band edge. Everything the old code called confident is still P >= 0.9, and
# `weak_team` still flags the same set of detections. What changes is that the
# flag now travels with a probability the tracker can price, instead of acting as
# a silent delete.
WEAK_TEAM_P = 0.90

# The reject tests (referee, crew) used to require `is_neither(L)` - the hard band
# - as a precondition. That made them brittle in a way M4 watched happen twice: a
# camera operator at L* 51.0 missed the band edge at 51.39 by 0.39 L* and was
# handed to slot D6 with full confidence (docs/16-m4-watching.md), and the figure
# D5 held at the sideline for 1.5 s sits at L* 49.8-51.4 - just outside the band,
# every frame. A probability threshold degrades instead of snapping.
#
# 0.95 rather than WEAK_TEAM_P because the reject tests already carry a second,
# independent condition (stripes, or feet beyond the far sideline); the kit term
# only has to say "not a confident kit". Measured on the labelled frames: moving
# the crew test to this threshold catches all 13 labelled crew and zero players,
# and moving the referee test to it adds 2 detections, neither of them labelled.
REJECT_MAX_P = 0.95

CLASSES = ("sol", "chill", "ref", "crew")


# --------------------------------------------------------------------------- #
# torso sampling


def _mask_and_L(patch: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Luminance in L*, and a mask of pixels that are not grass.

    Grass is the only thing excluded. Masking skin as well was tried and changed
    nothing measurable, so it is not carried: a rule that does not move a number
    is a rule nobody can check.
    """
    hsv = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV)
    H = hsv[..., 0].astype(np.int16)
    S = hsv[..., 1].astype(np.int16)
    V = hsv[..., 2].astype(np.int16)
    grass = (H >= 30) & (H <= 90) & (S >= 60) & (V >= 40)
    L = cv2.cvtColor(patch, cv2.COLOR_BGR2LAB)[..., 0].astype(np.float64) * 100.0 / 255.0
    return L, ~grass


def _crop(img: np.ndarray, box, band) -> np.ndarray | None:
    t0, t1, cx = band
    x0, y0, x1, y1 = box
    h, w = y1 - y0, x1 - x0
    a = max(0, int(round(y0 + t0 * h)))
    b = min(img.shape[0], int(round(y0 + t1 * h)))
    c = max(0, int(round(x0 + cx * w)))
    d = min(img.shape[1], int(round(x1 - cx * w)))
    if b - a < 3 or d - c < 3:
        return None
    return img[a:b, c:d]


def torso_luminance(img: np.ndarray, box) -> tuple[float, int] | None:
    """Median L* of the torso, grass excluded. None when there is too little of it."""
    patch = _crop(img, box, COLOUR_BAND)
    if patch is None:
        return None
    L, keep = _mask_and_L(patch)
    if int(keep.sum()) < MIN_TORSO_PX:
        return None
    return float(np.median(L[keep])), int(keep.sum())


def stripe_evidence(img: np.ndarray, box) -> dict | None:
    """How much of a referee's vertical stripe pattern is in this torso.

    Average L down the torso: vertical stripes are coherent down the body and
    survive it, a number on the back and a neighbour's shoulder largely do not.
    Then subtract a moving average - a neighbouring light player is a ramp across
    the patch, stripes are high-frequency - and count the runs that stay bright.
    """
    patch = _crop(img, box, STRIPE_BAND)
    if patch is None or patch.shape[1] < 5:
        return None
    L, keep = _mask_and_L(patch)
    wsum = keep.sum(axis=0)
    cols = np.where(wsum >= max(2, 0.6 * keep.shape[0]))[0]
    if len(cols) < 6:
        return None
    prof = np.where(keep, L, 0.0).sum(axis=0)[cols] / wsum[cols]
    prof = np.interp(np.linspace(0, len(prof) - 1, STRIPE_W), np.arange(len(prof)), prof)
    k = STRIPE_SMOOTH
    trend = np.convolve(np.pad(prof, k // 2, mode="edge"), np.ones(k) / k,
                        mode="valid")[:STRIPE_W]
    hp = prof - trend
    amp = float(hp.std())
    above = hp > max(4.0, 0.8 * amp)
    runs = int(np.sum(above[1:] & ~above[:-1]) + (1 if above[0] else 0))
    return {"runs": runs, "amp": round(amp, 2)}


def looks_striped(ev: dict | None) -> bool:
    return bool(ev and ev["runs"] >= STRIPE_MIN_RUNS and ev["amp"] >= STRIPE_MIN_AMP)


# --------------------------------------------------------------------------- #
# fitting the two kits


def kmeans2_1d(x: np.ndarray, iters: int = 100) -> np.ndarray:
    """Deterministic 2-means on a 1-D sample, seeded at the extremes.

    Same seeding idea as tools/teamcolour.py: no random draw, so two runs on the
    same possession give the same two centres, which AD is what "deterministic,
    seed everything" means for a fit that has no other randomness in it.
    """
    centres = np.array([x.min(), x.max()], dtype=np.float64)
    labels = np.zeros(len(x), dtype=int)
    for _ in range(iters):
        new = (np.abs(x[:, None] - centres[None, :])).argmin(axis=1)
        if (new == labels).all():
            break
        labels = new
        for k in (0, 1):
            if (labels == k).any():
                centres[k] = x[labels == k].mean()
    return np.sort(centres)


class KitModel:
    """The two kit luminances for a possession, and the band that is neither."""

    def __init__(self, dark: float, light: float, n: int):
        self.dark = float(dark)
        self.light = float(light)
        self.n = int(n)
        self.separation = self.light - self.dark
        self.midpoint = 0.5 * (self.light + self.dark)
        half = NEITHER_KIT_FRAC * self.separation
        self.neither = (self.midpoint - half, self.midpoint + half)

    # M0 measured delta-E 36.6 between these kits. A fit that comes back with the
    # two centres close together means the assumption this module rests on -
    # that the kits differ in lightness - does not hold for that footage, and the
    # honest response is to say so rather than to split a single cluster in half.
    MIN_SEPARATION = 20.0

    @property
    def separation_ok(self) -> bool:
        return self.separation >= self.MIN_SEPARATION

    def is_neither(self, L: float) -> bool:
        """Kept for reporting. Nothing decides on it any more - see `p_light`."""
        return self.neither[0] <= L <= self.neither[1]

    def t(self, L: float) -> float:
        """Torso luminance on the kit axis: -1 at the dark centre, +1 at the light."""
        return (L - self.midpoint) / max(0.5 * self.separation, 1e-6)

    # Slope of the logistic, derived rather than picked. `t` is +/-1 at the two kit
    # centres and the old hard band ended at |t| = 2 * NEITHER_KIT_FRAC, so setting
    # P = WEAK_TEAM_P there fixes the slope:
    #
    #     k = ln(P / (1 - P)) / (2 * NEITHER_KIT_FRAC) = ln 9 / 0.5 = 4.394
    #
    # That is the whole calibration. It is one constant, tied to a boundary that was
    # already measured against, so the soft model reproduces the hard one at its
    # decision point and only differs in what it says about the cases in between.
    LOGIT_K = float(np.log(WEAK_TEAM_P / (1.0 - WEAK_TEAM_P)) / (2.0 * NEITHER_KIT_FRAC))

    def p_light(self, L: float) -> float:
        """P(this torso is the light kit). The dark kit is the complement."""
        return float(1.0 / (1.0 + np.exp(-self.LOGIT_K * self.t(L))))

    def team_of(self, L: float, light_team: str, dark_team: str
                ) -> tuple[str, float, float]:
        """The nearer kit, the probability it is right, and the old margin score.

        `team_score` is kept unchanged so nothing that already reads it shifts
        meaning underneath. `team_p` is the new number and the one to use: it is a
        probability, so `1 - team_p` is the probability of the *other* kit, which
        is what the tracker needs to price a cross-team association.
        """
        p_l = self.p_light(L)
        team = light_team if p_l >= 0.5 else dark_team
        p = max(p_l, 1.0 - p_l)
        d_light, d_dark = abs(L - self.light), abs(L - self.dark)
        margin = abs(d_light - d_dark) / max(0.5 * self.separation, 1e-6)
        return team, float(p), float(np.clip(margin, 0.0, 1.0))

    def as_dict(self) -> dict:
        return {"dark_L": round(self.dark, 2), "light_L": round(self.light, 2),
                "separation_L": round(self.separation, 2),
                "midpoint_L": round(self.midpoint, 2),
                "neither_kit_band_L": [round(self.neither[0], 2), round(self.neither[1], 2)],
                "fitted_on_detections": self.n,
                "separation_ok": self.separation_ok,
                "min_separation_L": self.MIN_SEPARATION,
                "logit_k": round(self.LOGIT_K, 4),
                "p_calibration": (f"P = {WEAK_TEAM_P} at the old hard band edge "
                                  f"(|t| = {2 * NEITHER_KIT_FRAC}), so the soft model "
                                  "agrees with the hard one at its decision point")}


def fit_kits(work: Path, *, verbose: bool = True) -> KitModel:
    det = json.loads((work / "detections.json").read_text(encoding="utf-8"))
    paths = sorted((work / "frames").glob("*.jpg"))
    vals = []
    for fr in det["frames"]:
        dets = [d for d in fr["dets"] if d.get("in_bounds")]
        if not dets:
            continue
        img = cv2.imread(str(paths[fr["f"]]))
        for d in dets:
            r = torso_luminance(img, [int(round(v)) for v in d["box"]])
            if r is not None:
                vals.append(r[0])
    if len(vals) < 20:
        raise SystemExit(f"[team] only {len(vals)} torso samples; cannot fit the kits")
    dark, light = kmeans2_1d(np.asarray(vals, dtype=np.float64))
    km = KitModel(dark, light, len(vals))
    if verbose:
        print(f"[team] kits fitted on {km.n} torsos: dark L* {km.dark:.1f}, "
              f"light L* {km.light:.1f}, separation {km.separation:.1f}")
        print(f"[team] neither-kit band L* {km.neither[0]:.1f} .. {km.neither[1]:.1f}")
        if not km.separation_ok:
            print(f"[team] !! separation {km.separation:.1f} is below "
                  f"{km.MIN_SEPARATION}; the two kits are not separable by lightness "
                  "on this footage and every team call below is unsafe")
    return km


# --------------------------------------------------------------------------- #
# classifying


def classify(img, box, *, kit: KitModel, soccer_y: float | None,
             far_sideline_y: float | None, light_team: str, dark_team: str) -> dict:
    lum = torso_luminance(img, box)
    if lum is None:
        return {"team": None, "team_score": None,
                "team_note": "torso could not be sampled - too small, or all grass"}
    L, npx = lum
    team, p, score = kit.team_of(L, light_team, dark_team)
    out = {"torso_L": round(L, 1), "torso_px": npx}

    ev = stripe_evidence(img, box)
    if ev:
        out["stripe_runs"] = ev["runs"]
        out["stripe_amp"] = ev["amp"]

    # The two reject tests. Each is a weak kit call AND one independent piece of
    # evidence; neither half is safe alone, which is the argument in this module's
    # docstring and is unchanged. What changed in round 2 is that the kit half is
    # now a threshold on a probability rather than membership of a hard band, so a
    # figure sitting 0.4 L* outside the band no longer escapes the test entirely.
    weak_for_reject = p < REJECT_MAX_P

    if weak_for_reject and looks_striped(ev):
        out.update({"team": None, "team_score": None, "team_p": None,
                    "non_player": "ref",
                    "team_note": f"kit call is only P {p:.2f} (L* {L:.0f}) and the "
                                 f"torso carries {ev['runs']} vertical bright runs "
                                 "- referee"})
        return out

    if (weak_for_reject and far_sideline_y is not None and soccer_y is not None
            and soccer_y > far_sideline_y):
        out.update({"team": None, "team_score": None, "team_p": None,
                    "non_player": "crew",
                    "team_note": f"kit call is only P {p:.2f} (L* {L:.0f}) and the "
                                 f"feet are {soccer_y - far_sideline_y:.1f} yd beyond "
                                 "the far sideline - camera crew"})
        return out

    out.update({"team": team, "team_score": round(score, 3),
                "team_p": round(p, 4)})
    if p < WEAK_TEAM_P:
        # Kept as a player, but the kit call is not confident. Before round 2 this
        # flag meant "delete": ur.track.run dropped these detections entirely, and
        # measured against eval/m3/team_labels.json that threw away roughly two
        # real players for every non-player it caught. It is now a *price*, not a
        # veto - the tracker adds -2 ln P to the association cost, so an uncertain
        # kit 0.2 yd away can win a slot and a confident wrong kit still cannot.
        out["weak_team"] = True
        out["team_note"] = (f"torso sits between the two kits; P {p:.2f} for {team}. "
                            "The call is the nearer kit but it is weak, and this may "
                            "not be a player at all - the tracker prices it rather "
                            "than trusting or discarding it")
    return out


def assign_frame(img, dets: list[dict], *, kit: KitModel | None = None,
                 far_sideline_y: float | None = None,
                 light_team: str = "sol", dark_team: str = "chill") -> list[dict]:
    """Classify every detection in one frame. Out-of-bounds boxes are left alone."""
    if kit is None:
        kit = assign_frame.default_kit                       # set by run(); see below
    out = []
    for d in dets:
        if not d.get("in_bounds"):
            out.append({"team": None, "team_score": None, "team_p": None,
                        "team_note": "not in bounds; no team assigned"})
            continue
        sy = (d.get("soccer") or [None, None])[1]
        out.append(classify(img, [int(round(v)) for v in d["box"]], kit=kit,
                            soccer_y=sy, far_sideline_y=far_sideline_y,
                            light_team=light_team, dark_team=dark_team))
    return out


assign_frame.default_kit = None


# --------------------------------------------------------------------------- #


def run(work: Path, *, verbose: bool = True) -> dict:
    det_path = work / "detections.json"
    det = json.loads(det_path.read_text(encoding="utf-8"))
    clip = json.loads((work / "clip.json").read_text(encoding="utf-8"))
    cal = json.loads((work / "calibration.json").read_text(encoding="utf-8"))
    paths = sorted((work / "frames").glob("*.jpg"))

    teams = clip["teams"]
    light_team = next((k for k, v in teams.items() if v.get("kit") == "light"), "sol")
    dark_team = next((k for k, v in teams.items() if v.get("kit") == "dark"), "chill")

    vt = cal.get("venue_transform", {})
    far_sideline_y = -float(vt["y_offset"]) + 160.0 / 3.0 if "y_offset" in vt else None

    kit = fit_kits(work, verbose=verbose)
    assign_frame.default_kit = kit

    counts = {"sol": 0, "chill": 0, "ref": 0, "crew": 0, "none": 0, "weak": 0}
    for fr in det["frames"]:
        dets = [d for d in fr["dets"] if d.get("in_bounds")]
        if not dets:
            continue
        img = cv2.imread(str(paths[fr["f"]]))
        for d in fr["dets"]:
            if not d.get("in_bounds"):
                d["team"], d["team_score"], d["team_p"] = None, None, None
                continue
            sy = (d.get("soccer") or [None, None])[1]
            r = classify(img, [int(round(v)) for v in d["box"]], kit=kit, soccer_y=sy,
                         far_sideline_y=far_sideline_y,
                         light_team=light_team, dark_team=dark_team)
            # A re-run must not leave last run's verdict behind. `non_player` and
            # `weak_team` are only ever *set*, so a detection that was rejected
            # under the old hard band and is kept under the new probability would
            # otherwise keep a stale reject flag and stay invisible downstream.
            for stale in ("non_player", "weak_team"):
                d.pop(stale, None)
            d.update(r)
            np_cls = r.get("non_player")
            if r.get("weak_team"):
                counts["weak"] += 1
            if np_cls:
                counts[np_cls] += 1
                # A rejected detection is no longer an on-field player. in_bounds
                # stays true - it is a statement about geometry and it was correct -
                # and `non_player` is what everything downstream must read.
            elif r["team"]:
                counts[r["team"]] += 1
            else:
                counts["none"] += 1

    det["method"]["team_assignment"] = {
        "module": "ur.team",
        "kits": kit.as_dict(),
        "light_team": light_team,
        "dark_team": dark_team,
        "colour_band": list(COLOUR_BAND),
        "stripe_band": list(STRIPE_BAND),
        "stripe_min_runs": STRIPE_MIN_RUNS,
        "stripe_min_amp": STRIPE_MIN_AMP,
        "neither_kit_frac": NEITHER_KIT_FRAC,
        "weak_team_p": WEAK_TEAM_P,
        "reject_max_p": REJECT_MAX_P,
        "team_p_means": ("P(this detection's kit is the team in `team`). The other "
                         "kit is the complement - there are exactly two. Calibrated "
                         "so P = weak_team_p at the old hard band edge, so nothing "
                         "measured against the hard label shifts meaning."),
        "far_sideline_soccer_y": (round(far_sideline_y, 2)
                                  if far_sideline_y is not None else None),
        "reject_note": "non_player is 'ref' (torso matches neither kit and carries "
                       "vertical bright runs) or 'crew' (matches neither kit and the "
                       "feet are beyond the far sideline). Downstream must drop any "
                       "detection carrying non_player; in_bounds is left as the "
                       "geometric statement it always was.",
        "measured": "5 of 8 referees and 12 of 15 crew rejected on the M2 held-out "
                    "frames, with 0 real players lost: 1.15 -> 0.30 false positives "
                    "per frame. See docs/14-m3.md.",
        "known_leak": "The stripe test is high-precision, moderate-recall. A referee "
                      "whose stripes do not survive one frame's pose is kept and given "
                      "the nearer kit - usually the dark one - with weak_team set and a "
                      "low team_p. Downstream must not treat a weak_team detection "
                      "as a confirmed player.",
        "round_2_change": {
            "what": "the three-way hard label became a probability; weak_team is a "
                    "price the tracker pays, not a detection it deletes",
            "why": "measured on eval/m3/team_labels.json, the weak_team set is 14 "
                   "real players, 5 non-players and 3 boxes spanning two players - "
                   "not the 'over half referees and camera crew' docs/17 asserted "
                   "when it justified excluding them",
            "reject_tests": "the kit precondition on the referee and crew tests is "
                            "now P < reject_max_p rather than membership of the hard "
                            "band, because M4 watched two non-players escape the band "
                            "by under 0.4 L* and be tracked as players",
            "see": "docs/25-round-2-ghost-audit.md R1 and R6",
        },
        "seed": SEED,
    }
    det_path.write_text(json.dumps(det, indent=1) + "\n", encoding="utf-8")
    if verbose:
        tot = sum(counts[k] for k in ("sol", "chill", "ref", "crew", "none"))
        print(f"[team] {tot} in-bounds detections: {counts['sol']} {light_team}, "
              f"{counts['chill']} {dark_team}, {counts['ref']} referee, "
              f"{counts['crew']} crew, {counts['none']} unassigned")
        print(f"[team] {counts['weak']} kept with a weak kit call "
              f"(P < {WEAK_TEAM_P}); the tracker prices these, it does not drop them")
    return det


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="ur.team")
    p.add_argument("work")
    a = p.parse_args(argv)
    run(Path(a.work))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
