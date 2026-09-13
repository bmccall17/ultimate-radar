# Handoff — M4 in progress, reviewed 2026-09-13

Pick this up cold. Read this, then `docs/04-milestones.md` § M4, then AD-1, AD-2, AD-3 and
`docs/05-uncertainty.md`. The spec in `docs/` still governs; where a milestone changed it,
the change is recorded in that milestone's own document and in the commit message.

Working directory: `E:\dev\playertrackerultimate\ultimate-radar`

> **M4 is half-built and none of its gates are measured yet.** The tracker exists and runs;
> the ground truth it must be scored against does not exist. Everything below marked
> *unmeasured* is exactly that. Do not quote any M4 number as a result.
>
> **Reviewed — `docs/15-m4-review.md`.** The motion model was re-derived from first
> principles and holds. The escalated decision in § 3 is **resolved**: keep excluding
> `weak_team`, and re-specify the gate, which was the actual fault. § 4 is re-ordered as a
> result — the render comes first.

---

## 1. Where the project is

| | Milestone | Status |
|---|---|---|
| **M0** | Ingest + footage report | **Done**, independently reviewed (`docs/11-m0-review.md`) |
| **M1** | Calibration | **Done**, acceptance passed (`docs/12-m1-calibration.md`) |
| **M2** | Detection | **Done.** Recall passed here; its false-positive gate passed in M3 (`docs/13-m2-detection.md`) |
| **M3** | Team assignment + projection | **Done**, both gates passed (`docs/14-m3.md`) |
| **M4** | Tracking | **All five gates measured** (`docs/17-m4-tracking.md`). Four pass; the identity gate passes its count (2 switches) and **fails its second clause — 0 of 2 would be caught by M5's specified detectors** |
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

## 3. The decision, resolved

The `observed` fraction gate was failing, and the question was whether to admit `weak_team`
detections — the ones whose torso matches neither kit, where the three uncaught referees
live — to close a 10.7-point gap.

**Answer: keep excluding them. The gate was the fault, not the tracker.** Full reasoning in
`docs/15-m4-review.md`; the short version:

The gate as written compares two *counts* — observed slot-frames against visible players —
and a count comparison can be satisfied by counting the wrong objects. Admitting `weak_team`
adds ~1.10 detections per frame that are mostly referees, buying ~7.9 points of "observed" by
putting non-players into player slots. The number would pass and the product would be worse.
Options (b) and (c) as framed were both ways of paying for a metric.

**The replacement gate is recall on players, position-matched:**

> For each of the 20 labelled frames, take every detection a human labelled `sol` or `chill`.
> Project its foot point to field coordinates. Ask whether a slot **of that team** is
> `observed` within 1.5 yd. Report the fraction over all labelled player-boxes, and also at
> 1.0 and 2.0 yd so the threshold's contribution is visible.

This asks what the old gate was trying to ask — *did the tracker see the players who were
there* — and a referee cannot improve it, because referees are not in the denominator. The
perverse incentive disappears, and "zero phantom slots" stops being traded against it.

**It needs no jersey identity labels.** It is a positional match, not an identity match, and
`eval/m3/team_labels.json` already labels every in-bounds box on those 20 frames. This gate
is unblocked today. The 1 Hz jersey labelling is still required, but only for the ID-switch
gate — a different question that should no longer block this one.

Two things to state when reporting it: the denominator is *detected and labelled* players, so
a player the detector missed entirely is invisible to it — bound that with M2's recall
(0.9873), or report the hand-counted 11.85/frame as a second denominator.

**Expectation, recorded before the measurement.** Given that only 9 of 245 unassigned
detections cost a real observation, per-player recall should come out **at or above 0.90**,
in which case the tracker is fine and the old gate was the whole problem. If it lands near
0.75 there is a real coverage gap, and *then* option (b) — inflate R rather than drop the
detection, so a weak-team detection competes weakly instead of not at all — is worth trying,
because it would be buying real players rather than referees.

Also settled: the visible fraction is **84.6 %** from 20 labelled frames, not the 88 % from
three hand-counted M0 frames. `docs/04` and `docs/05` should carry the measured number.

## 3b. Steps 1 and 2, done

**Step 1 — rendered and watched.** `eval/m4/p0001_tracks.mp4`, written up in
`docs/16-m4-watching.md`. Two findings that no statistic had produced: **D6 holds a camera
operator for the last second of the possession** (it cleared the bounds margin by 0.24 yd, the
height-ratio floor comfortably, and the `weak_team` band by 0.39 L\*), and **the unassigned
detections are real players** — I had called them "almost always a non-player" in this document,
inferring it from a distance statistic without looking at the pixels. 245 of 248 of them occur
while that team still has a *free slot*.

**Step 2 — the re-specified gate is measured: 0.8846** at 1.5 yd
(`eval/m4/m4_recall_acceptance.json`). Greedy and one-to-one agree, so nothing is
double-counted. The 27 misses attribute completely: **14 excluded as `weak_team`**, 10 rejected
by the association gate at a median of 15 yd, 3 where the slot sits 1.6–2.4 yd from a detection
it did consume. The old count-comparison gate is retired in `docs/04` with the reasoning.

**One tracker change, and it did not move the number.** Watching found a type error in the
reach gate: it compared a bound on how far the *player* could have moved against the distance
between two *measured* points, without allowing for the noise of either. The old
`max(2.0 yd, speed × elapsed)` floor was tighter than the statistical gate at short gaps and
rejected 70 associations that chi-square scored at 4.4 against a threshold of 9.21. It is now
`speed × elapsed + 3σ` of combined endpoint noise. Reach-only rejections went **70 → 0** and
recall at 1.5 yd went **0.8846 → 0.8846**. The defect was real, the fix is right, and it bought
nothing on this gate — all three of those are worth saying.

It did surface something for the position gate: three labelled players are now "missed" because
the slot holding them sits 1.6–2.4 yd away. The filter accepted a surprising detection and moved
only part of the way to it, which is correct Bayesian behaviour if its covariance is right and
over-confidence if it is not. Step 3 measures exactly that.

**Not done, deliberately.** The largest single lever on the gate is the 14 `weak_team` misses,
and pulling it means readmitting the detections that keep referees out of player slots. The
review conditioned that on recall landing near 0.75; it landed at 0.885. Changing it now would
be changing the tracker to hit the number. **Whoever sets the gate threshold should decide this
explicitly** — `docs/04` § "The `observed` fraction gate was retired" lays out the trade.

## 3c. Step 3, done

| Gate | Result | |
|---|---|---|
| Zero phantom or missing slots | 14 slots, 5040 samples, 0 problems | **PASS** |
| Position error, `observed` | median **0.3698 yd** (gate 0.8), p95 **1.0337** (gate 1.8) | **PASS** |
| Sigma calibration | **80.0 %** (32/40) inside the disc | **PASS, marginal** |

Measured on 40 observed slot-samples **disjoint from `eval/m3/foot_labels.json`**, because
`FOOT_UNCERTAINTY_PX` was fitted on those and the sigma gate would otherwise be scoring a
constant against its own training data.

**The fresh sample independently reproduces M3's foot-point bias** — dx −1.62 px against M3's
−1.52, dy −2.15 against −1.66, sharing none of the same detections. That makes the bias a
measured fact rather than reading noise, and it is most of what is left: 0.38 yd of pure
offset against a 0.370 yd median total error. A Kalman filter cannot remove it, because it
assumes zero-mean noise and averaging frames does not cancel a shift.

**The sigma gate first failed at 57.5 %, on units rather than on the filter.** `docs/05` draws
a disc of radius `sigma` and wants ≥ 80 % of truths inside; the tracker was emitting a per-axis
standard deviation, and for a 2-D Gaussian that disc contains **39.3 %** — unreachable by
construction. The filter's covariance turned out ~31 % *conservative*, i.e. the number was
right and the units were wrong. It now reports 1.794 × the per-axis sigma, matching the
convention M3 had already adopted for `sigma_yd`. `docs/03` carries the definition and a table
of which producer uses which containment level.

**The pass is marginal and must not be quoted as settled.** 32 of 40 is exactly 80.0 %; the
Wilson 95 % interval on n = 40 runs 65.2 % to 89.5 %. A bigger sample is the only way to call it.

## 4. What M4 still needs, in order

**The order changed after review.** The render moved from fifth to first. A tracker is the
first stage whose failures are *temporal* — a slot that swaps, a ghost that drifts somewhere
absurd, a referee quietly holding a defender's slot for six seconds. None of those appear in
a per-frame statistic, and all are obvious within thirty seconds of watching. Measuring a
tracker nobody has looked at is the wrong order of operations.

1. **Render the tracker.** Rewire `possession.json` to come from `tracks.json` instead of
   `ur/standin.py`, regenerate `viewer/live.html`, and produce an `eval/m4/` video the way
   M1, M2 and M3 each did. Evidence state rendered per `docs/05`: solid observed, dashed
   predicted, sigma disc sized in real yards. Then watch all 24 seconds before doing anything
   else, and write down what you see.
2. **Score the re-specified `observed` gate** (§ 3). No new labels needed; it runs against
   `eval/m3/team_labels.json` today.
3. **A fresh foot-point sample for the position and sigma gates**, disjoint from the 50 in
   `eval/m3/foot_labels.json`. Re-using those would be circular: `FOOT_UNCERTAINTY_PX` was
   fitted on them, and the sigma-calibration gate would be scoring a constant against its own
   training data.
4. **The 1 Hz identity ground truth**, for the ID-switch gate only — it no longer blocks the
   others. `tools/m4_label.py` is written and renders the sheets; the labels are not made.
   The approach was measured before being relied on: jersey numbers are readable on **about
   half** the crops (UFA §3.2.3 numbers the back *and* the front, so a side-on player shows
   neither), which is enough, because a switch is a change in which number a slot holds and
   an unlabelled observation simply contributes no evidence.
5. **Score the remaining gates.**
6. **The tracklet-level team vote**, which closes the last of the referee leak.
7. `ur/standin.py` is then dead and should be deleted.

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
- **`SIGMA_V_INF = 2.6 yd/s` is a measured sport constant, not a tuning knob.** It belongs in
  `docs/02` § AD-1 with its method and baseline curve. Note the foot-noise figure it was
  derived against (1.183 yd displacement rms) is ~10 % above the 1.076 implied by M3's
  measured 0.761 yd per-detection rms, which biases σ_v slightly low — conservative, but say
  so in the code.
- **Overlay drawing must be clipped to the registration mask.** M3's render puts projected
  field lines across the sponsor banner. Cosmetic now; misleading once an overlay element
  lands on a graphic and reads as a detection.
- **Add a `.gitattributes` with `* text=auto eol=lf`.** Running git against this checkout
  from a Linux environment reports all 51 source files modified; the diff is a pure CRLF/LF
  flip and the tree is genuinely clean. Worth removing the phantom.

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
