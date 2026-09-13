# Handoff — M4 in progress, 2026-09-13

Pick this up cold. Read this, then `docs/04-milestones.md` § M4, then AD-1, AD-2, AD-3 and
`docs/05-uncertainty.md`. The spec in `docs/` still governs; where a milestone changed it,
the change is recorded in that milestone's own document and in the commit message.

Working directory: `E:\dev\playertrackerultimate\ultimate-radar`

> **M4 is half-built and none of its gates are measured yet.** The tracker exists and runs;
> the ground truth it must be scored against does not exist. Everything below marked
> *unmeasured* is exactly that. Do not quote any M4 number as a result.

---

## 1. Where the project is

| | Milestone | Status |
|---|---|---|
| **M0** | Ingest + footage report | **Done**, independently reviewed (`docs/11-m0-review.md`) |
| **M1** | Calibration | **Done**, acceptance passed (`docs/12-m1-calibration.md`) |
| **M2** | Detection | **Done.** Recall passed here; its false-positive gate passed in M3 (`docs/13-m2-detection.md`) |
| **M3** | Team assignment + projection | **Done**, both gates passed (`docs/14-m3.md`) |
| **M4** | Tracking | **In progress.** Tracker built and committed; **gates unmeasured** |
| M5 | Identity, events, corrections | Not started |
| M6 | Viewer | Not started; `viewer/prototype.html` is the design target, `viewer/live.html` is M3's working page |
| M7 | Sharing + a second possession | `p0003` is already cut for it |

Numbers that stand (measured, gated, committed):

- **M1** — mean reprojection error **0.0996 yd** (gate 0.75), max **0.4096 yd** (gate 1.5).
  Confidence ≥ 0.5 on **93.9 %** of frames.
- **M2** — recall **0.9873** (gate 0.95) on 236 players in 20 held-out frames.
- **M3** — team accuracy **0.9957** (gate 0.99); foot-point error **0.4345 yd** median
  (gate 0.6); false positives **1.15 → 0.30 per frame** (gate 1.0), zero real players lost.
- The M0–M3 pipeline re-runs byte-identical.

## 2. What M4 has so far

`ur/track/` — a Kalman filter in field yards (AD-1), 14 slots never created or destroyed
(AD-2), per-team gated Hungarian association (AD-3), and the `docs/05` state machine
including the retrospective `interpolated` pass. Writes `tracks.json`.

Current output on p0001, **diagnostics, not results**:

| | |
|---|---|
| observed | 3401 / 5040 slot-frames (**67.5 %**) |
| interpolated | 428 (8.5 %) |
| predicted | 671 (13.3 %) |
| unknown | 540 (10.7 %) |
| unassigned detections | 245 — 9 surplus, 227 outside every gate, **9 lost a contested slot** |

The motion model took three attempts and the failures are recorded in `ur/track/kalman.py`,
because two of them looked like association bugs rather than covariance bugs:

1. **Piecewise white-noise acceleration.** Velocity variance grows as `σ_a²·dt·T` — it
   depends on the frame rate. At 15 fps the filter thought a player unobserved for two
   seconds had a velocity uncertainty of 1.5 yd/s. **736 detections, a median of 13 yd from
   every slot, failed association**; real players went unassigned while their own slots sat
   predicting confidently in the wrong place. Observed fraction 53.2 %.
2. **Undamped covariance** overshot the other way — 7.8 yd/s after 2.2 s, most of the mass
   beyond a sprint.
3. **Integrated Ornstein-Uhlenbeck velocity**, which is what is there now. Mean and
   covariance go through the same damped transition, so the damping is the model rather than
   a cosmetic smoothing, and velocity uncertainty saturates instead of running away.
   Verified two ways: velocity sd saturates at exactly σ_v, and `Q_pp` converges to the
   white-noise-acceleration limit as `dt` falls (ratio 0.981 at 15 fps, 0.997 at 100 fps).

`SIGMA_V_INF` is **measured**, not chosen — `tools/m4_speed.py`, 2.6 yd/s. Single-frame
differencing cannot measure it (0.6 yd of foot noise over 1/15 s implies 9 yd/s), so the
tool differences over a range of baselines, subtracts the foot noise M3 measured, and
inverts the integrated-OU displacement variance. The estimate settles at 2.50 / 2.64 / 2.63
for baselines of 0.8 / 1.3 / 2.0 s. Fed back and re-measured: 2.635 / 2.623. It converged.

## 3. The decision a reviewer should weigh in on

**The `observed` fraction gate is currently failing, and the reason is a choice, not a bug.**

Compared like for like on the 20 hand-labelled frames:

| | per frame |
|---|---|
| Visible players (hand-labelled, M3) | **11.85 / 14 = 84.6 %** |
| Detections offered to the tracker | 11.05 |
| …of those, unassigned | 0.70 |
| `weak_team` excluded before association | **1.10** |
| **Tracker `observed`** | **10.35 / 14 = 73.9 %** |

The gate wants the observed fraction within 5 points of the visible fraction, so 79.6–89.6 %.
It is at **73.9 %**, about **10.7 points short**. Note the detector is not the problem: it
finds 12.15 player-classified detections per frame against 11.85 visible, i.e. slightly more,
because a few non-players survive M3's filters.

Essentially all of the shortfall is the two sinks above, and the larger one is a deliberate
choice: **`ur/track/run.py` excludes `weak_team` detections from association.** Those are the
detections whose torso matches neither kit, which is where M3's three uncaught referees end
up. Admitting them would add up to 1.10 observations per frame — about 7.9 points, enough to
pass the gate — at the cost of letting a referee occupy a defender's slot.

I have not made that trade, for two reasons. It cannot be evaluated without the identity
ground truth, which does not exist yet; and `docs/04` M4 lists "phantom or missing slots:
zero, always" alongside the observed fraction, so buying coverage with referees trades one
gate against another. **This is the open question for the review.** The options are:

- **(a) Keep excluding.** Honest, fails the observed-fraction gate, and the write-up says so.
- **(b) Admit `weak_team` but down-weight it** — inflate R rather than drop the detection, so
  a referee competes weakly instead of not at all. Not tried.
- **(c) Admit them and let the tracklet-level team vote clean up afterwards.** This is what
  `HANDOFF` §6 of the M3 handoff proposed; the vote is not built yet.
- **(d) Re-measure the visible fraction properly.** The gate's "≈ 88 %" comes from three
  hand-counted M0 frames; M3's 20-frame labels say **84.6 %**, which is the better number and
  is what the table above uses.

## 4. What M4 still needs, in order

1. **The 1 Hz identity ground truth. It does not exist and nothing can be scored without it.**
   `tools/m4_label.py` is written and renders the sheets; the labels are not made.
   The approach was measured before being relied on: jersey numbers are readable on **about
   half** the crops (UFA §3.2.3 numbers the back *and* the front, so a side-on player shows
   neither), which is enough, because a switch is a change in which number a slot holds and
   an unlabelled observation simply contributes no evidence.
2. **A fresh foot-point sample for the position and sigma gates**, disjoint from the 50 in
   `eval/m3/foot_labels.json`. Re-using those would be circular: `FOOT_UNCERTAINTY_PX` was
   fitted on them, and the sigma-calibration gate would be scoring a constant against its own
   training data.
3. **Score all five gates**, and expect the `observed` fraction one to fail as above.
4. **The tracklet-level team vote**, which is what closes the last of the referee leak.
5. **Rewire `possession.json` to come from `tracks.json`** instead of `ur/standin.py`, then
   regenerate the viewer. **Right now `viewer/live.html` still shows M3 stand-in data** — the
   tracker's output is not on screen anywhere yet.
6. `ur/standin.py` is then dead and should be deleted.

## 5. Environment

Unchanged since M2. Python **3.11.16** in `.venv` (uv-managed). M4 added no dependencies —
`scipy.optimize.linear_sum_assignment` was already present from M1.

```powershell
$env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
uv venv --python 3.11 .venv
uv pip install --python .venv\Scripts\python.exe -r requirements-m0.txt
uv pip install --python .venv\Scripts\python.exe torch torchvision --index-url https://download.pytorch.org/whl/cu128
uv pip install --python .venv\Scripts\python.exe -r requirements-m2.txt
```

torch **2.11.0+cu128** sees the RTX 4070 Ti SUPER. ffmpeg 9.0.1 gyan **full** build (GPL —
exec'd as a separate process, never linked, never vendored). Seed **20260827** everywhere.
Licence register: `docs/07-licenses.md`; code *and* weights are checked separately, and
**no Ultralytics anywhere**.

## 6. What exists

```
ur/ingest.py            M0. Cuts a possession; source.start_s is measured, not assumed.
ur/ffprobe.py           ffmpeg/ffprobe wrappers.
ur/calibrate/           M1. world, camera, mask, paint, features, fit, run, venue,
                        render, verify, accept.
ur/detect/              M2. model (D-FINE + suppression), run, overlay.
ur/team.py              M3. Kit fit, the stripe test, the crew reject.
ur/standin.py           M3. The greedy stand-in. M4 deletes this once step 5 above is done.
ur/track/               M4. kalman (the motion model), run (slots, association, states).
viewer/live.html        M3. Video + overlay + radar. Not the M6 viewer.
tools/                  survey, sheet, crop, measure, paint, cuts, fpscheck, heights,
                        jerseysheet, teamcolour, regcheck, pancheck, m2_label,
                        m3_label, m3_foot, m3_render, make_view, m4_speed, m4_label.
```

Decisions worth not re-litigating:

- **AD-4 amended** (`docs/02-architecture.md`): the per-frame **3-DOF camera fit is primary**,
  the mosaic is the fallback. Solved centre **C = (0.47, −50.21, 6.98) yd** in the soccer frame.
- **Registration runs on a mask, never a raw frame.** `tools/regcheck.py` reproduces why.
- **The referee test is stripe periodicity, not luminance variance.** The M0 review predicted
  variance; a numbered dark jersey and a two-player box both have high torso variance too.
- **The kits are fitted per possession**, and the fit refuses to report two teams when the
  separation is below 20 L\*.
- **`sigma_yd` is measured** (5.83 px rms), not the 3 px M2 assumed, which put only 46 % of
  truths inside the drawn disc against the ≥ 80 % `docs/05` requires.
- **The venue transform lives in code**, `venue.BREESE_STEVENS_NEAR_SIDELINE_Y`, after M3
  found M2's correction had been hand-edited into `calibration.json` and would have been
  silently reverted by any re-run.

## 7. On disk

```
raw/           5.6 GB   GITIGNORED   the broadcast (format 299+140, 1080p60 avc1)
work/p0001/    24.0 s, 360 frames    clip.json, calibration.json, detections.json,
                                     possession.json (STAND-IN), tracks.json
work/p0002/    18.0 s, 270 frames    the pull; clip.json, calibration.json
work/p0003/    26.0 s, 390 frames    endzone-framed; clip.json, calibration.json
survey/                 GITIGNORED   161 stills
eval/m0..m4/            COMMITTED    evidence, hand labels, acceptance JSON, videos
viewer/live-data.js     GITIGNORED   regenerate with tools.make_view
```

**p0002 and p0003 still carry the pre-M3 calibration**, written before
`BREESE_STEVENS_NEAR_SIDELINE_Y` existed. Re-run `ur.calibrate.run` on them before use.

Hand labels — the most expensive artefacts here and the hardest to regenerate:
`eval/m0/visibility_counts.json`, `eval/m2/labels.json`, `eval/m3/team_labels.json`,
`eval/m3/foot_labels.json`. **M4 adds two more and neither is made yet.**

## 8. Habits this project has earned

Six bugs across M1–M4 shared one shape: **something reported success while being wrong**, and
only a check that could contradict it caught the problem.

- A chamfer objective sampled its distance field with integer indices, so the optimiser saw
  zero gradient, stopped at its seed, and reported success.
- An acceptance test called two well-calibrated frames 10 and 34 yards wrong because its own
  RANSAC had fitted a needle-thin ellipse along the halfway line. *A test that fails for its
  own reasons is worse than no test.*
- A calibration reported `rms 0.0000 yd` at confidence 0.55 on a collapsed fit.
- "Longest straight line = halfway line" was wrong, quietly, because the longest line in a
  wide shot is the *ultimate* sideline.
- **A sigma disc that contained the truth 46 % of the time**, stated as an assumption in M2
  and believed until M3 measured it.
- **A process-noise model that made the tracker certain about players it had not seen for two
  seconds.** It presented as an association failure, not a covariance error.

And two that were cheap only because they were loud: `inv(H)` returns **negative** `w` for
points genuinely in front of the camera here, so the obvious `w > 0` test drew nothing at
all; and `H` disagreeing with its own `venue_transform` by 6.8 yd, which only surfaced because
the viewer was the first thing to use `H` directly.

So: prefer a check that can contradict the thing it is checking. `tools/pancheck.py` compares
the calibration's pan against masked phase correlation sharing no code and no inputs
(correlation 0.946). `tools/m3_render.py` is the only thing that exercises the field→image
direction. `tools/m4_speed.py` measures a constant the tracker would otherwise assume, and
prints zeroes at the baselines where it cannot measure rather than reporting a number.
