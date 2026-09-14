# 28 — Calibration confidence, and the two possessions that were silently wrong

**The headline, because it is worse than the title suggests: p0002 and p0003 have never had
a working calibration, and p0003 has been published on the live site throughout.** Measured
by M1's own acceptance test — reprojecting two points whose field position is known exactly —
they were out by **6.8 and 4.6 yards**. Every in-possession signal looked healthy the whole
time.

| | p0001 | p0002 | p0003 |
|---|---|---|---|
| M1 acceptance, mean reprojection error | 0.10 yd **pass** | **6.79 yd fail** | **4.55 yd fail** |
| per-frame residual (in-sample) | 0.149 | 0.217 | 0.208 |
| pose agreement with neighbours | 0.06 | 0.05 | 0.05 |

**The test existed and was never run on them.** `ur/calibrate/accept.py` has implemented M1's
gate since the first milestone; `docs/12-m1-calibration.md` records it passing on p0001 and
nobody ever pointed it at another possession. A test that is only ever run on the possession
it was written for is a test of that possession.

Everything below is what that led to, in the order it was found.

---

## Part 1 — the confidence gate, which was the visible problem and not the real one

Bringing a second and third possession up to p0001's state looked like it was blocked by
calibration succeeding and then being disbelieved.

`docs/03` gates the whole pipeline on one number — *"`confidence` ∈ [0,1] derives from the
residual… Frames below 0.5 must not produce `observed` samples"* — and `ur.detect.run`
enforces it by refusing to write a `field` position at all. On p0002 and p0003 that gate was
rejecting about half of every possession.

| | p0001 | p0002 | p0003 |
|---|---|---|---|
| frames | 360 | 270 | 555 |
| accepted (confidence ≥ 0.5) | 94 % | **51 %** | **53 %** |
| of the rejected: no fit attempted | 0 | 99 (37 %) | 51 (9 %) |
| of the rejected: fit collapsed or degenerate | 0 | 0 | 71 (13 %) |
| **of the rejected: a sound fit, gated out** | **22 (6 %)** | **33 (12 %)** | **138 (25 %)** |

---

## The measurement that started it

The rejected frames had **better residuals than the accepted ones**.

| | accepted, median residual | rejected, median residual |
|---|---|---|
| p0002 | 0.223 yd | **0.159 yd** |
| p0003 | 0.221 yd | **0.197 yd** |

A gate that is anti-correlated with the quantity it exists to measure is not a threshold in
the wrong place; it is measuring something else. Two terms were doing it.

## The paint-count ramp

```python
support = clip((n_circle + n_line) / 500, 0, 1)
confidence = quality * support * geometry
```

A frame seeing 200 px of paint could not score above 0.40 however precisely it fitted, so
`docs/03`'s gate of 0.5 discarded it. The 500 has no measurement behind it.

And the direction is backwards. A frame that sees a small, sharply-imaged arc of the centre
circle fits it *precisely*; a frame that sees a great deal of paint spread to the far side of
the pitch, where a pixel is worth several inches, fits more of it less well. Paint count
tracks how much of the pitch is in shot, not how accurately the frame is placed.

**Replaced by a floor.** Below `MIN_SUPPORT_PX = 120` an rms is not a statistic and the frame
scores zero; above it, the residual sets the value, which is what `docs/03` says the number
is.

## The halfway-line penalty, and why the proxy was the problem

```python
geometry = 1.0 if n_line >= 40 else 0.55
```

The argument is geometrically sound — a circle alone pins the ground plane but leaves
rotation about its normal weakly observed — and applied against a fixed 0.5 gate it is a
**veto**: a circle-only frame would need an rms below 0.043 yd to survive, which nothing
achieves. So it silently deleted every frame that could not see the halfway line.

Whether that is right turns out to depend on the possession, which is the tell that the proxy
is wrong. Scored against how far each frame's pose sits from what its neighbours predict:

| | circle-only frames | | | line-bearing frames | | |
|---|---|---|---|---|---|---|
| | pan | tilt | focal | pan | tilt | focal |
| p0001 | 0.169° | 0.017° | **23.2 px** | 0.044° | 0.007° | 2.1 px |
| p0002 | 0.090° | 0.046° | 19.5 px | 0.070° | 0.019° | 5.7 px |
| **p0003** | 0.086° | 0.005° | **1.1 px** | 0.052° | 0.006° | 2.0 px |

On p0001 the penalty earns its keep — an 11× worse focal estimate is a real 0.5 yd of
positional error at typical range. On p0003 the circle-only frames are **better** than the
line-bearing ones on focal and equal on tilt, and the penalty was discarding a quarter of the
possession for nothing.

"Is the halfway line present" was never the question. The question is whether the pose is
well conditioned — and that can be measured rather than predicted.

## Measuring conditioning instead of guessing at it

`residual_yd` is computed on the very pixels the frame was fitted to. It is **in-sample**, so
it cannot detect over-fitting, which is exactly the failure a sparse view produces.

The camera supplies the out-of-sample check for free. AD-4's amendment establishes that this
is a fixed broadcast hard camera: it pans, tilts and zooms and does not translate, so pan,
tilt and focal are smooth functions of time. Fit a line through each over ±5 frames
**excluding the frame itself**, and the frame's distance from that line is an out-of-sample
error. A frame that fits its own pixels beautifully and sits half a degree off the pan curve
is over-fitted, and says so.

### The curve has to be a quadratic, and that is not a detail

The first version fitted a straight line, and it was measuring the wrong thing. A third of a
second of a real pan is not straight, and the curvature lands in the "disagreement" as if it
were error. Measured as the correlation between a frame's disagreement and how fast the
camera was panning:

| | straight line | quadratic |
|---|---|---|
| p0001 (pans 16°) | +0.19 | +0.14 |
| p0002 (pans 50°) | **+0.66** | **−0.04** |
| p0003 (pans 100°) | **+0.89** | +0.25 |

At +0.66 the check is not detecting bad fits, it is detecting the camera accelerating — and
rejecting frames for it, worst on exactly the fast, hard-to-calibrate possessions it exists
to help. A quadratic absorbs constant angular acceleration, which is what an operator's hands
produce. Accepted frames on p0002 go 100 → 141 and on p0003 338 → 402; p0001 goes 321 → 340,
so the well-behaved possession does not pay for it either.

The residual correlation on p0003 is still +0.25 and is an honest limit: over a 100° pan even
a quadratic leaves some curvature, so that possession's fastest frames are still scored a
little harshly.

Converted to yards so it adds to the residual rather than competing with it: an angular error
θ displaces a point at range R by `R·θ`, and a fractional focal error `δf/f` scales the range
by the same fraction. With `R = 60 yd`:

```
total_error = residual ⊕ (R · Δangle) ⊕ (R · Δfocal / f)
confidence  = exp(−total_error / 0.45)
```

The same rule now produces the right answer in all four cases that mattered, without a
threshold chosen to make it do so:

| | residual | pose disagreement | total | confidence | |
|---|---|---|---|---|---|
| p0001, line present | 0.150 | 0.07 | 0.16 | 0.69 | accepted |
| p0001, circle only | 0.153 | **0.56** | 0.58 | 0.28 | rejected |
| p0003, circle only | 0.196 | **0.10** | 0.22 | 0.62 | **accepted** |
| p0002, circle only | 0.159 | 0.45 | 0.48 | 0.35 | rejected |

The two halves are written out separately — `residual_yd` and `pose_disagreement_yd` — so
anything downstream can see which one cost a frame its confidence.

## Part 2 — what none of it caught

After all of the above, p0002 still failed M1 acceptance at **8.7 yd** and p0003 at 4.6.
Pinning the camera centre to the venue's measured value (below) did not fix it either. The
montage the test writes is what explains why, and `accept.py`'s docstring says to look at it
before quoting any number from it.

**p0002 is not uniformly wrong. It is right in some frames and badly wrong in others** —
0.17 and 0.06 yd on frames 267 and 268, 12.7 and 10.0 yd on frames 113 and 118, which sit
immediately after a 105-frame block where no fit was possible at all. The pose is carried
forward through that block, locks onto the wrong pixels coming out of it, and then drifts
*smoothly* from there.

That is the failure neither of the two confidence inputs can see:

- **`residual_yd` is in-sample.** It is measured on the pixels the frame was fitted to, so a
  fit that locked onto the wrong pixels scores beautifully. Those bad frames have a *better*
  median residual than p0001's good ones.
- **Pose agreement with neighbours is out-of-sample but not independent.** The sequential pass
  initialises each frame from its neighbour, so a drifting stretch drifts smoothly. Being
  consistent with your neighbours is no defence when your neighbours are wrong the same way.

### The fix: check every frame against geometry that is known exactly

The two points whose field position is known exactly and which appear in most frames are
where the halfway line crosses the centre circle — soccer-frame `(0, ±10.0066)`. Find them in
**image space only**, back-project through the frame's own camera model, and measure how far
the answer lands from where it must be. That is a number in yards, independent of the solve,
and it is exactly the quantity `docs/03` says confidence is about.

`ur/calibrate/groundtruth.py` now runs it on **every frame** and folds the error into
confidence, so a frame that is wrong stops producing positions instead of producing wrong
ones. It only ever lowers confidence, and it abstains when it cannot find both features —
`accept.py` records an earlier version of this same test calling two good frames 10 and 34
yards wrong because its own RANSAC locked onto a spurious conic, and a check that fires
wrongly costs you the signal you were relying on.

| | before | after |
|---|---|---|
| **p0002 M1 acceptance** | **6.79 yd fail** | **0.145 yd pass** |
| p0002 frames accepted | 138 (many of them wrong) | 134 (measured right) |

The frame count barely moves. What changed is that the frames that survive are the ones whose
positions are true, rather than the ones whose fit was self-consistent.

## The camera centre is a venue fact too

Chasing p0002 turned up a third instance of a mistake this module has now made three times.
The camera centre was solved per possession and chosen between two candidates on **mean
per-frame confidence** — an in-sample score, which a self-consistently wrong camera satisfies
happily:

| | camera centre (soccer yd) |
|---|---|
| p0001 | (0.47, −50.21, 6.98) |
| p0002 | (−19.50, −60.00, 8.67) |
| p0003 | (−19.50, −41.25, 6.00) |

AD-4's amendment says this camera *"pans, tilts and zooms, and does not translate"*. It does
not translate between possessions either — one fixed hard camera cannot be in three places
twenty yards apart. `BREESE_STEVENS_CAMERA_C` now pins it to p0001's, the only one ever
checked against known geometry, and `--fit-camera-centre` re-enables the per-possession solve
for a new venue.

**The pattern, stated once because it has now cost three defects:** the venue transform, the
near sideline, and the camera centre are all facts about the venue. Measure each once on the
possession with the best evidence and reuse it. Do not let a possession with worse evidence
re-derive it and silently win on an in-sample score.

## What it does not fix

- **A frame with no fit at all stays rejected**, and on p0002 that is 99 frames (37 %) in one
  contiguous block at the start, where the camera is panned somewhere with no paint in shot.
  AD-4's amendment already names the answer — *"keep the mosaic for stretches where too
  little paint is visible"* — and the mosaic fallback is still not built. That, not the
  confidence formula, is what caps p0002.
- **The out-of-sample check fails open inside a long bad block.** It needs four scoring
  neighbours; where there are none it contributes zero and the frame is scored on its
  residual alone, as before. That is the conservative direction — it cannot reject a frame it
  has no evidence about — but it means the check is weakest exactly where the calibration is.
- **The along-pitch offset is still assumed.** `venue_transform.x_offset` is
  `field_length / 2`, and `field_length` is unresolved on all three possessions
  (`docs/08-risks.md` #5). Across the pitch it is measured; along it, it is not.

## The stale possession, and the re-run that fixes it

p0002's `calibration.json` was written on 12 September, before `BREESE_STEVENS_NEAR_SIDELINE_Y`
existed. Its venue transform therefore reads:

> *"ultimate sidelines not found in the paint map; assuming the field is centred on the
> pitch. **UNMEASURED**."*

with `y_offset = 26.667` against the measured 32.75 — **every cross-field position in that
possession was 6 yd out, on a field 53 yd wide.** Nothing was wrong with the code; the file
predated the fix. `ur/calibrate/venue.py` already warns that a number a re-run destroys is a
note rather than a measurement, and this is the same lesson from the other side: a number a
re-run would *create* is one somebody has to re-run.

`tools/pipeline.py` now exists so that bringing a possession up to date is one command rather
than a reading exercise across three documents.
