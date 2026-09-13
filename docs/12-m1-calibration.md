# 12 — M1, calibration

**Status: acceptance passed, 2026-09-12.** `work/p0001/calibration.json` exists, every frame
has a homography with a residual and a confidence, and the verification render sits on the
paint through a full pan.

| M1 gate | Required | Measured | |
|---|---|---|---|
| Mean reprojection error, held-out | < 0.75 yd | **0.0996 yd** | pass |
| Max reprojection error, held-out | < 1.5 yd | **0.4096 yd** | pass |
| Line overlay sits on the paint through a pan | by eye | `eval/m1/p0001_verification.mp4` | pass |
| Masked vs whole-frame registration compared | ≥ 10 pairs | 11 pairs | pass |
| A cut handled with one set of clicks | — | **not exercised** — this possession is a single shot | n/a |

Held out: 20 seeded-random frames from those with confidence ≥ 0.5; 17 testable, 34
correspondences. The three untestable frames are ones where the *test's* independent
detector could not isolate the conic, not ones where calibration failed — their per-frame
residuals are 0.14–0.16 yd, in line with their neighbours.

Per-frame residual over all 360 frames: **median 0.149 yd, p95 0.190 yd, max 0.249 yd.**
Confidence ≥ 0.5 on **93.9 %** of frames.

---

## What was built, and the one decision that differs from AD-4 as written

`ur/calibrate/` — `world.py` (the geometry and its sources), `camera.py` (the camera model),
`mask.py` (what may influence registration), `paint.py` (finding painted lines),
`features.py` (the circle and the halfway line), `fit.py` (the objective and the solvers),
`run.py` (the pass), `venue.py` (soccer frame → ultimate frame), `verify.py` (the render),
`accept.py` (the gate).

**The model is a fixed camera centre with per-frame pan, tilt, roll and focal length.**
AD-4 as originally written registers each frame to a shot mosaic. The amendment, agreed
before the work started and recorded in `docs/02-architecture.md`, keeps AD-4's reason —
never chain frame to frame, because the error accumulates and nothing signals it — and
changes the means, for two measured reasons:

1. **A free homography has eight degrees of freedom and this footage offers seven
   constraints.** In a typical frame the only exactly-specified geometry in shot is the
   soccer centre circle (a conic, five) and the halfway line (two). Fitting eight unknowns
   to seven constraints leaves a direction free to wander, silently.
2. **The camera does not translate.** It is a hard camera on a platform at the sideline.
   That makes each frame three unknowns against a centre shared by the whole shot, so seven
   constraints are comfortably redundant instead of one short. Fitting every frame
   independently against known world geometry accumulates no drift at all, which is what
   AD-4 was protecting.

The camera centre is bundled over nine frames spread across the pan. One frame cannot pin it
down — any single view trades centre against pose and produces the same picture — but one
centre has to explain nine different pans at once. Solved: **C = (0.47, −50.21, 6.98) yd** in
the soccer frame, i.e. about 50 yd out from the centre circle across the pitch and 7 yd up.

## Five things that went wrong, because they are the useful part

**1. The objective had no gradient.** The chamfer sampled its distance field with integer
indices, making the cost piecewise constant, so the optimiser's finite differences saw
exactly zero slope and terminated at its starting point *reporting success*. Every fit was
just the seed. Fixed with bilinear sampling (`fit.sample_bilinear`).

**2. "Longest straight line = halfway line" was wrong, and quietly so.** In a wide shot the
longest straight run is the *ultimate* far sideline (1344 px) — the halfway line is
foreshortened to a few hundred. So the wrong line was removed before the ellipse fit, and
the ellipse then fitted a patch of boundary noise: axes 151 × 335 px for a circle a thousand
pixels across. Fixed by finding the circle first by RANSAC and then requiring the halfway
line to pass through its centre, which is geometry rather than a guess about which line
happens to be longest.

**3. The paint detector missed a third of the circle.** M0's thresholds were tuned on a
bright, high-contrast frame; the soccer paint at night under a 5.4 Mbps encode is far
fainter, and at `TOPHAT_THRESH = 12` roughly a third of the centre circle went undetected —
whereupon the fit locked onto whatever else was bright. Retuned against the visible circle
(`eval/m1/probe/paintbest.jpg`): threshold 8, kernel 21.

**4. Chamfering the model against the paint was the wrong direction.** The modelled halfway
line extends as far as the pitch is wide, which is not published, so a large share of the
model had no paint to sit on and was charged a large residual however right the camera was.
The anchor frame scored 12 px rms while visibly well aligned. Turned around: back-project
the *detected* pixels and ask how far each lands from where it belongs — a circle pixel from
10.0066 yd, a line pixel from x = 0. Every residual is then a real pixel with a real world
meaning, and the answer comes out in yards.

**5. The acceptance test failed for its own reasons.** Its first version reported two of ten
held-out frames as 10 and 34 yards wrong. They were not: their calibration was smooth,
consistent with their neighbours, residual 0.14 yd. The *test's* per-frame RANSAC had fitted
a vast needle-thin ellipse along the halfway line — thousands of inliers, tiny residual,
complete nonsense. Fixed with an angular-coverage test (`features._angular_coverage`): a
real circle has inliers spread around it, an impostor has them all in one sector. **A test
that fails for its own reasons is worse than no test**, because it costs you the signal you
were relying on to catch real failures.

## Evidence that the calibration is right, not just self-consistent

A residual says the model fits the paint it was fitted to. Three things here say more:

- **The held-out point test.** The two crossings of the halfway line and the centre circle
  are at soccer (0, ±10.0066) exactly. They are located from the image-space line and conic
  only; the camera model merely back-projects them. Mean error 0.0996 yd over 34
  correspondences. Every point is drawn in `eval/m1/m1_acceptance_points.jpg` — the numbers
  are worth what that picture is worth, so look at it.
- **An independent measurement of the camera's motion.** `tools/pancheck.py` compares the
  pan implied by `calibration.json` against masked phase correlation on *grass texture*,
  which shares no code and no inputs with the paint-based fit. **Correlation 0.946, best-fit
  scale 0.939, mean difference 6.9 px** over the six pairs where the turf gave a usable
  correlation peak. A fit that sat on the paint while describing a camera that never moved
  correctly would fail this and pass the residual.
- **The halfway line lands at x = −0.05 yd** in the pooled paint map, built from 413 529
  back-projected pixels across 169 frames. Two inches, accumulated over the whole possession.

**Determinism** (AGENTS rule 6): two full runs produce pose parameters identical to 0.0 in
pan, tilt, roll and focal length across all 360 frames.

## The registration mask

The M0 review's hazard, now handled in code. `tools/regcheck.py`, re-run as part of M1:

| | whole frame | masked to the playing surface |
|---|---|---|
| Pairs reporting \|dx\| < 1 px — "a static camera" | **10 of 11** | 0 of 11 |
| Recovered pan, px | ~0 | 38 – 289 |

The mask excludes the rendered graphics — found by temporal stillness, not hard-coded boxes,
since while the camera pans the only pixels that do not change are the ones drawn on top —
and everything above the horizon, since the stands are off the ground plane and their motion
is parallax rather than camera motion. Players are cut too, by a crude non-grass blob test
until M2's detector exists. **48–55 % of the frame survives.**

Also confirmed, and it matters for M2 and M4: **peak correlation response on the masked turf
is 0.008–0.468.** Mown grass is close to featureless and its stripes give an aperture problem
along their own direction. Dense correspondence on this footage is marginal; the paint is
carrying the information. Any later stage tempted to use grass texture for motion
compensation should read that number first.

---

## Two things this does not settle

**The field is still 120 yd by assumption, not measurement.** `docs/08-risks.md` open
question 5 remains open, and the answer is now better characterised: **it cannot be settled
from p0001 at all.** The pooled paint map's x marginal is a single spike at the halfway line
and noise either side; the camera never looks far enough down the field to see a goal line.
The three bumps it does show (x = +12.05, +38.25, +43.35 yd) each carry under 3 % of the
halfway line's support, and the nearest is 1.75 yd from where a 120 yd field's goal line
would be — against a calibration good to 0.15 yd. They are noise, and the tolerance was
tightened so they cannot vote. **To settle it, calibrate a second possession framed near an
endzone.** `survey/random/010_t1615.7.png` is such a shot.

**The venue transform is half measured.** Across the pitch it is real: one ultimate sideline
shows in the paint map at y = −25.95 yd, which is 0.72 yd from where a field centred across
the pitch would put it. Along the pitch it is still the centred assumption, because that is
the same missing goal line. So in the verification render the **cyan** soccer geometry is
verified against paint, and the **yellow** ultimate field inherits an unmeasured offset —
they are drawn in different colours for exactly that reason.

Practically, for M2 and M3: the possession is played around midfield, positions are measured
in the soccer frame where the calibration is good to 0.1 yd, and the ultimate-frame X
coordinate carries an unknown offset of up to a few yards until a goal line is seen.
**Anything that depends on absolute distance to an endzone — deep cover, the deep-deterrent
boolean — must wait for that.** Relative geometry, which is what person-vs-zone, matchups and
separation-at-release are built from, does not.
