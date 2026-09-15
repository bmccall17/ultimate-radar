# 30 — What is known, and what has to be true to call it good

Written 2026-09-14 at the end of a long session, as the entry point for the next
one. `docs/29` is how the possessions were found and calibrated; `docs/27` is the
disc. This is the summary and, more usefully, **the list of things that have to
pass**.

```bash
python -m tools.gates            # every gate, every possession, one command
```

It exits non-zero if anything fails. Some things fail on purpose; § 3 says which.

---

## 1. Where it stands

**Six possessions published**, three Sol on offence and three Wind Chill — which
is new, every possession before today was Sol.

| | offence | frames the calibration accepts | median roster in shot | blank | M1 mean | M1 max |
|---|---|---|---|---|---|---|
| p0001 | Sol | 96 % | 11 of 14 | 4 % | 0.118 | 0.446 |
| p0009 | Wind Chill | 86 % | 9 of 14 | 10 % | 0.132 | 0.314 |
| p0003 | Sol | 72 % | 9 of 14 | 22 % | 0.160 | 1.262 |
| p0005 | Wind Chill | 72 % | 8 of 14 | 19 % | 0.208 | 1.277 |
| p0004 | Sol | 65 % | 9 of 14 | 32 % | 0.113 | 0.745 |
| p0015 | Wind Chill | 62 % | 8 of 14 | 34 % | 0.102 | 0.304 |

**Four cut and not published** — p0006, p0007, p0008, p0010. All pass M1
acceptance; p0008 passes at 0.077 yd, better than anything published. None has a
median frame with a located player on it. That gap between "passes M1" and
"worth looking at" is § 2.1.

---

## 2. The findings, in the order they cost the most

### 2.1 An acceptance number is about the frames it sampled

`ur/calibrate/accept.py` draws its held-out frames from the frames that already
cleared the confidence gate. On a possession where the gate rejects most of the
footage, a beautiful mean is a statement about the good quarter. p0006 passed at
0.35 yd on **six testable frames inside a 139-frame span of 450**.

The acceptance JSON now carries `usable_fraction`, and `tools/gates.py` prints it
beside the mean rather than under it. **The fix was not a better number, it was
refusing to report one without its denominator.**

### 2.2 The halfway line is the whole game

Counting which frames fail across every possession: **not one line-bearing frame
fails, anywhere.** p0001 316/316, p0004 289/289, p0006 118/118, p0010 61/61. The
usable fraction *is* the fraction of frames with a halfway line in shot, and
frames without one collapse to a focal length of 10¹⁵.

`docs/28` had already shown circle-only frames are not inherently worse and
removed the confidence penalty on them; the solve still ran away, because a
circle pins the plane and the scale and leaves rotation about its normal
unobserved. `ur/calibrate/mosaic.py` observes that direction from the stands and
the boards, and the paint then refines inside the box its measured accuracy
allows.

### 2.3 Three checks, because each one catches what the others cannot

All three are in `ur/calibrate/mosaic.py` and all three found real defects:

1. **A floor.** A pose implying more than 2 yd of error is not written at all —
   dead reckoning is 0.6–3.5 yd (`docs/05`), so a worse pose says less than
   predicting does. Caught a run of p0004 frames scored **0.0001** that were
   producing twelve player positions each.
2. **Registration cross-check.** Every paint-solved frame is re-derived from the
   others. Median disagreement on p0004 is **0.02 yd**, p90 0.07 — and one frame
   at **4.51**, a circle-only fit 9° out that nothing else could contradict,
   because the known-geometry check abstains without a halfway line.
3. **Impossible motion.** A pose can be self-consistent, agree with its sources
   *and* pass known geometry and still be somewhere the camera cannot have been.
   Threshold 1 yd, from p0001 never exceeding 0.35 across its whole length while
   the offenders run 1–16 yd.

### 2.4 No cheap pre-filter predicts whether a possession will calibrate

Three were tried — conic-and-line on the raw frame, the same masked below the
horizon, and a halfway-line-only screen built on the measured cause. Correlation
across nine known outcomes is **+0.11**, and the single best-scoring candidate of
all 49 calibrates at 35 %. **Screening means running the calibration**: six
minutes, six wide, and the hit rate is about two keepers in nine.

### 2.5 The first ground truth says the holder solver fails completely

Six timing-only tags and four identities on p0001. Full account in `docs/27`
under "The first ground truth".

| span | truth | solved | margin it reported |
|---|---|---|---|
| 0.00–7.60 s | O7 | O5 | 0.93 yd |
| 8.47–9.93 s | O4 | O1 | 1.58 |
| 11.80–15.87 s | O5 | O3 | 1.58 |
| 16.53–23.93 s | O4 | O1 | 1.58 |

**0 of 4.** Three things follow:

- **The emission cost prefers the wrong answer.** True holder ranks 3rd, 3rd, 3rd
  and 1st of seven; the truth totals 28.6 yd against the pick's 20.6. Not noise.
- **The margin is not a confidence.** Four wrong answers at 0.93–1.58 yd, the
  range a right answer would give. `docs/27` step 4 — ask where the margin is
  thinnest — rests on it.
- **Flight speed is a strong signal that was used as a wide gate.** The three
  true throws fly at **11.0, 11.0 and 11.2 yd/s** over a 2.7× range of distance,
  every endpoint observed. The solver's picks imply 11.3, **2.0** and 8.0. n = 3.

### 2.6 Measure the artefact, not the log

Three fixes this session printed success while leaving the defect in place: a
loop bound capped at six iterations reporting "dropped 6" for every possession
alike; an acceptance cliff calibrated on frames whose paint was good, then
applied to frames whose paint was degenerate; and a smoothness check comparing
against neighbours that had already been removed. All three were caught by
re-measuring the output afterwards, and none by reading what the tool said.

---

## 3. The gates, and which of them fail on purpose

`python -m tools.gates`. Sixteen checks currently fail, and every one is either a
known-unpublished possession or a documented open problem.

### Per possession — all six published ones pass

| gate | threshold | where it comes from |
|---|---|---|
| M1 acceptance, mean | < 0.75 yd | `docs/04` M1, unchanged since the first milestone |
| M1 acceptance, max | < 1.5 yd | `docs/04` M1 |
| …measured on | reported, never gated | § 2.1. A mean without its denominator is not a result |
| roster structure | zero problems | `docs/04` M4, AD-2 |
| camera motion is possible | 0 frames over 1 yd | § 2.3 |
| median roster in shot | ≥ 6 of 14 | publishing gate. Below this the median frame is mostly empty |
| frames with nothing at all | ≤ 35 % | publishing gate |
| attacking direction | file and play agree | `ur.possess` drift check |

**Currently failing and expected to:** p0006, p0007, p0008 and p0010 on coverage
and on camera motion — they have not been through the impossible-motion check and
are not published. **p0010's attacking direction is wrong**: declared `+x`, the
play drifts **−60.7 yd**. Re-cut it `-x` before it is ever published.

**Failing and NOT expected to: p0001's attacking direction.** Declared `+x`, play
drifts −8.4 yd. p0001 does not end in a goal so the drift is weak evidence, but
it has never been settled and the overhead now says "disputed" on the landing
page. Settle it.

### The disc — both gates fail, and this is the work

| gate | threshold | why that number |
|---|---|---|
| span identity accuracy | ≥ 75 % over ≥ 8 graded spans | currently **0 / 4**. Eight spans across at least two possessions, so it cannot be fitted to the four it would be tested on |
| margin predicts correctness | r ≥ 0.5 | a loop that asks where the margin is thinnest is only a strategy if the margin means something. Currently unmeasurable — too few graded spans |

**These are the two numbers that decide whether Goal 2 works.** Neither can move
without more identity tags, and both must be measured on a possession the solver
was not built against.

---

## 4. What to do next, in order

1. **Tag a second possession.** p0009 (86 % calibrated, 9 of 14 in shot) is the
   best target. Timings with `t`/`c`, then name the holder on each span. That
   gives `tools/gates.py` the eight graded spans it needs and gives any rewrite
   something it was not fitted to.
2. **Then rebuild the span cost around flight speed** (§ 2.5), not stillness.
   Do it in that order: the current cost is known to be wrong, and a replacement
   tested only on the four spans that disproved the first one would prove
   nothing.
3. **Settle p0001's attacking direction**, which is on the landing page.
4. **Re-cut p0010 as `-x`** if it is ever wanted.

## 5. Parked deliberately

- **`Space`** — `docs/06`'s nearest-player Voronoi. It colours 40-yard cells over
  grass nobody can contest and ignores that players are moving. The version that
  answers a question is time-to-reach; player speed is measured over six
  possessions and 18,246 observed steps at p50 3.52, p90 6.81, p99 10.47 yd/s.
- **p0009 at 25.8 s and p0003 at 32.6 s** — the calibration is smooth there
  (steps 0.22–0.66 yd). Only 5–8 of 14 players are anchored while the camera
  follows the throw, the rest frozen at their last position. A viewer
  presentation problem, not a pipeline one.
- **`docs/` is 222 MB**, and each published possession adds ~35 MB to git history
  permanently.
- **`docs/08` #5, the field length** — still unresolved, still the
  highest-leverage unknown. Six calibrated possessions now exist, several
  endzone-framed, which is what that risk says it needs.
