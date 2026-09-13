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
# as one of them. Inside this band it is "neither kit", which is a precondition
# for the reject tests - never a rejection on its own.
NEITHER_KIT_FRAC = 0.25

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
        return self.neither[0] <= L <= self.neither[1]

    def team_of(self, L: float, light_team: str, dark_team: str) -> tuple[str, float]:
        d_light, d_dark = abs(L - self.light), abs(L - self.dark)
        team = light_team if d_light < d_dark else dark_team
        margin = abs(d_light - d_dark) / max(0.5 * self.separation, 1e-6)
        return team, float(np.clip(margin, 0.0, 1.0))

    def as_dict(self) -> dict:
        return {"dark_L": round(self.dark, 2), "light_L": round(self.light, 2),
                "separation_L": round(self.separation, 2),
                "midpoint_L": round(self.midpoint, 2),
                "neither_kit_band_L": [round(self.neither[0], 2), round(self.neither[1], 2)],
                "fitted_on_detections": self.n,
                "separation_ok": self.separation_ok,
                "min_separation_L": self.MIN_SEPARATION}


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
    out = {"torso_L": round(L, 1), "torso_px": npx}

    neither = kit.is_neither(L)
    ev = stripe_evidence(img, box)
    if ev:
        out["stripe_runs"] = ev["runs"]
        out["stripe_amp"] = ev["amp"]

    if neither and looks_striped(ev):
        out.update({"team": None, "team_score": None, "non_player": "ref",
                    "team_note": f"torso matches neither kit (L* {L:.0f}) and carries "
                                 f"{ev['runs']} vertical bright runs - referee"})
        return out

    if (neither and far_sideline_y is not None and soccer_y is not None
            and soccer_y > far_sideline_y):
        out.update({"team": None, "team_score": None, "non_player": "crew",
                    "team_note": f"torso matches neither kit (L* {L:.0f}) and the feet "
                                 f"are {soccer_y - far_sideline_y:.1f} yd beyond the far "
                                 "sideline - camera crew"})
        return out

    team, score = kit.team_of(L, light_team, dark_team)
    out.update({"team": team, "team_score": round(score, 3)})
    if neither:
        # The reject tests above did not fire, so this is being kept as a player -
        # but its torso matches neither kit, which is what a referee, a camera
        # operator and a box drawn round two overlapping players all look like.
        # M4 must be able to find these without parsing prose: a referee whose
        # stripes do not survive one frame's pose is still a referee across a
        # tracklet, and voting over a track is how that gets settled.
        out["weak_team"] = True
        out["team_note"] = ("torso sits between the two kits; the team call is the "
                            "nearer one but it is weak, and this may not be a player "
                            "at all - vote it over a tracklet in M4")
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
            out.append({"team": None, "team_score": None,
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

    counts = {"sol": 0, "chill": 0, "ref": 0, "crew": 0, "none": 0}
    for fr in det["frames"]:
        dets = [d for d in fr["dets"] if d.get("in_bounds")]
        if not dets:
            continue
        img = cv2.imread(str(paths[fr["f"]]))
        for d in fr["dets"]:
            if not d.get("in_bounds"):
                d["team"], d["team_score"] = None, None
                continue
            sy = (d.get("soccer") or [None, None])[1]
            r = classify(img, [int(round(v)) for v in d["box"]], kit=kit, soccer_y=sy,
                         far_sideline_y=far_sideline_y,
                         light_team=light_team, dark_team=dark_team)
            d.update(r)
            np_cls = r.get("non_player")
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
                      "low team_score. Downstream must not treat a weak_team detection "
                      "as a confirmed player.",
        "seed": SEED,
    }
    det_path.write_text(json.dumps(det, indent=1) + "\n", encoding="utf-8")
    if verbose:
        tot = sum(counts.values())
        print(f"[team] {tot} in-bounds detections: {counts['sol']} {light_team}, "
              f"{counts['chill']} {dark_team}, {counts['ref']} referee, "
              f"{counts['crew']} crew, {counts['none']} unassigned")
    return det


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="ur.team")
    p.add_argument("work")
    a = p.parse_args(argv)
    run(Path(a.work))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
