# 26 — Round 2, the tracker

What `docs/25-round-2-ghost-audit.md` asked for, what was built, and what it measured.
Everything here is p0001, 360 frames at 15 fps. Reproduce with:

```bash
python -m ur.team           work/p0001
python -m ur.track.run      work/p0001
python -m ur.possess        work/p0001
python -m ur.issues         work/p0001
python -m tools.m4_ghost    score work/p0001
python -m tools.m4_recall   work/p0001
python -m tools.m4_structure work/p0001
python -m tools.m4_foot     score work/p0001
```

---

## The headline

| | before | after | asked for |
|---|---|---|---|
| `observed_fraction` | 0.6786 | **0.7135** | rises |
| anchored (observed + provisional) | 0.6786 | **0.7198** | — |
| worst slot | D3 0.2972 | **D2 0.3750** | **≥ 0.60 — not met** |
| near-miss slot-frames recovered | — | **157 of 218** (83.5 % of the 188 that are jointly reachable) | ≥ 150 |
| cross-team with both kits confident | 0 | **0** | 0 |
| `margin`: null records | 2977 | **0** | meaningful |
| `margin`: lowest slot median | 1.61 (on 11 of 180 records) | **10.735** (on all records) | no slot at 0.0 |
| `observed` samples off the field of play | 17 | **0** | 0 |
| per-player recall @ 1.5 yd vs hand labels | 0.8846 | **0.8932** | — |
| …misses caused by a kit call | 14 | **2** | — |
| …misses that were referees or crew | — | **0** | reported separately |
| shared detections (one person, two slots) | 0 | **0** | — |
| re-acquisitions emitted for review | 0 | **32**, ranked | all of them |

Two of these need the rest of this document before they mean anything: the worst-slot
number, which is not met and cannot be, and the near-miss count, whose denominator is not
what it looks like.

---

## 1. The blind slots were a classification problem, not an association problem

`ur/team.py` sorted every detection into one of three hard classes, and the middle class —
`weak_team`, meaning "torso matches neither kit" — was **deleted** by the tracker before
association ran. On p0001 that band ran L\* 51.4–72.3, half the entire 41.8 L\* separation
between the two kits, and 341 detections fell into it.

`docs/17` justified the deletion: those detections were "over half referees and camera crew".
`eval/m3/team_labels.json` labels every in-bounds box on 20 held-out frames, and says
otherwise — of the 22 `weak_team` detections in it, **14 are real players, 5 are non-players,
3 are boxes spanning two people.** The full re-derivation is in `docs/17`.

The fix is AD-3's amendment (`docs/02`): the kit call became a probability, the prohibition
moved from "the label" to "a confident label", and a weak call became a price in the
assignment cost instead of a veto. 151 of the 194 `weak_team` near-misses became
observations.

**What was tried and rejected.** Two better-calibrated kit models were fitted and both were
worse for this job, which is worth recording so nobody fits them again:

- A logistic slope fitted by maximum likelihood on the hand labels comes out at 11.8 against
  the 4.394 the boundary convention gives — the kit call is far more informative than the old
  band implied. But it is fitted on labels that exist for one possession, so it does not
  generalise to a possession that has none.
- A two-component Gaussian mixture on torso luminance is label-free, per-possession, and
  better calibrated than either logistic on the labels (nll 1.75 against 3.38 and 7.96). It
  is also confidently wrong about exactly the population that matters: it puts L\* 55 at
  P(dark) = 0.9998, and L\* 55 is where the referees are. A three-component mixture separates
  them and then drives ~5 % of real dark-kit players to P ≈ 0.001, which is deleting players
  again by a new route.

The reason no 1-D model of torso luminance fixes this is that **a shadowed dark-kit player
and a black-and-grey striped referee are the same luminance**. The honest instrument is one
that says "leaning, not certain", which is what the shallow logistic does. The slope stays
derived rather than fitted, and the derivation is written down: P = 0.9 at the old hard band
edge, so nothing measured against the old label shifts meaning underneath.

## 2. The two gates were an intersection and are now a union

The audit's root cause 2 is correct and survives: with sigma reported at 1.794× the per-axis
value, the chi-square reach in yards is 1.692 × the reported sigma, which is *tighter* than
the physical `9.5 yd/s × elapsed` bound at every gap past half a second. Requiring both made
a stale covariance the binding constraint exactly where physics should have been.

A candidate is now admissible inside **either** gate. The physical branch is restricted to
slots stale ≥ 0.5 s and to detections the chi-square pass did not place — and that phrasing
matters. The audit put the restriction as "no competing slot inside their own chi-square
gate"; applied to the matrix that closes the branch almost always, because the common case is
a detection inside some slot's gate that loses to a better one, after which nobody may have
it. The restriction is protecting the *assignment*, not the gate, so it is applied after the
first pass is solved.

It makes 24 assignments and lifts `observed_fraction` from 0.6946 to 0.7135. Thirteen of the
24 are jumps of 12–22 yd after gaps of 1.1–1.9 s. That is the branch doing what it is for and
is also where it will be wrong when it is wrong — every one of them is emitted as
`provisional` and queued. **The branch is only defensible because §4 exists.**

## 3. Two things had to change shape, not value

**The assignment is solved once, over all fourteen slots.** A kit-ambiguous detection is a
candidate for slots on both teams, and two per-team solves would each be free to take it.
`tools/m4_structure.py` now checks for a detection held by two slots and measures zero.

**`margin` is defined for the single-candidate case.** It was null whenever a slot had one
candidate, which is most records, so a helper that read null as zero concluded the least
contested slot was the most — the audit's own D5 error. The implicit rival is the gate
ceiling: the cost at which the least attractive admissible candidate would sit. Alone in the
gate now reads as a large margin, because that is what it is.

## 4. Nobody has labelled a single identity switch, so the detector stopped guessing

M4 measured both specified swap detectors catching 0 of 2 real switches. `docs/17` proposed
re-using the Mahalanobis distance; that cannot work, because every re-acquisition is inside
the gate by construction — the four cases the audit nominated score χ² of 1.19, 6.57, 9.02
and 9.20 against a threshold of 9.21, the full width of the admissible band. Margin does not
separate them either (two are at 5.3 and 7.0, unambiguous). Displacement from the dead
reckoning is the right feature and still does not pick them out.

And the four were never ground truth. So:

- Every re-acquisition after a gap ≥ 1.0 s is marked **`provisional`** — an observation of
  somebody, with the identity unestablished. It counts for coverage and is excluded from
  every metric (`docs/05` propagation).
- `ur.issues` emits **all 32**, ranked by displacement from the prediction, each carrying the
  gap, the margin, the kit probability, which gate admitted it, and the runner-up it beat.
- `possession.json`'s `identity_switches_caught` is now **null** rather than the "2 of 2" it
  claimed. That figure was the detector agreeing with the analysis that produced it.

Set the threshold after someone watches 32 clips. Not before.

## 5. The sideline figure was a brittle AND, not a missing bound

The audit's original claim — that D5 tracked off the field — was wrong, and its correction
is right: the detector's bounds carry a deliberate ±2 yd apron (field y ≤ 55.333) and D5's
worst sample was 55.27, legitimately inside it.

What was actually happening: `ur/team.py`'s crew test required *both* "torso matches neither
kit" (a hard band) *and* "feet beyond the far sideline". The figure D5 held for 1.5 s sits at
L\* 49.8–51.4 — **below the band edge of 51.39, by as little as 0.4 L\***. It missed the
colour half of the test and so escaped it entirely, exactly as the camera operator in
`docs/16` did at 0.39 L\*. The test is now `P(kit) < 0.95` rather than band membership, which
degrades instead of snapping. On the labelled frames it catches all 13 crew and **zero
players**; crew recall goes 12/15 → 13/15, referee recall 5/8 → 5/8 with 2 extra detections
caught, neither of them labelled.

That removed 15 of the 17 off-field `observed` samples. The last two came from somewhere
else: the *detections* were at field y 52.67, inside the field, and the Kalman posterior
landed 0.16 yd outside. So an anchored estimate is now constrained to the field of play
**when the detection it was built from is itself in play** — "do not place a player outside
the field on the strength of evidence that is inside it". The condition is the point: a
blanket clamp would drag a genuinely out-of-bounds player onto the field, and in ultimate
that player is often the interesting one.

## 6. The per-slot floor of 60 % cannot be met, and the reason is the camera

This is the one acceptance number that is not met, so here is the evidence rather than the
excuse.

**The detections set a ceiling.** 22 of the 360 frames have calibration confidence below 0.5
and therefore produce no positioned detection at all — frames 0–11 and 312–321 — which is
308 slot-frames, 6.1 points, that no tracker can recover. Counting the candidates actually
available per frame and per team, capped at 7 a side, the maximum achievable anchored
fraction on this possession is **0.7726**. The tracker reaches 0.7198, or **93.2 % of the
ceiling**, up from 88 % before.

**The remaining blindness is not recoverable by association.** Of the 1412 blind slot-frames,
only **33** have any unused same-team-eligible detection within 5 yd; the median nearest
spare is 17.4 yd away, which is a different person. D2, the worst slot at 0.375, has **zero**
blind frames with a spare within 5 yd. Its player is not being dropped — its player is not on
camera.

| slot | blind frames | of those, no spare detection anywhere | spare within 5 yd |
|---|---|---|---|
| D2 | 225 | 126 | **0** |
| O2 | 174 | 140 | 12 |
| D3 | 151 | 116 | 3 |
| O3 | 143 | 127 | 0 |
| O7 | 132 | 99 | 1 |

A 60 % floor on every slot requires the blindness to be spread evenly across the fourteen.
The camera does not spread it evenly — `docs/05` predicted this from the start, that the
broadcast follows the disc and loses whoever is furthest from it, and this is the first
measurement of it on real tracks. The only way to hit the floor would be to rotate which slot
is blind, which is identity churn dressed up as coverage.

**What would actually move it:** more detections. Either SAHI tiling or a fine-tune to raise
M2 recall, or calibration that survives the 22 dead frames. Both are upstream of the tracker
and neither is in this round's scope.

## 7. Do not tune on these numbers

Worth its own section because it cost half a day to learn.

Sweeping `KIT_BLOCK_P` over 0.10–0.50 moves per-player recall through 0.8889, 0.8932, 0.8932,
0.8932, 0.8932, 0.8932, 0.8846, and near-miss recovery through 149, 164, 163, 157, 147, 151,
133. Sweeping `REACH_BRANCH_MIN_GAP_S` over 0.5/0.8/1.0/1.5/2.0/off moves recall through
0.8932, 0.8803, 0.8803, 0.9188, 0.8803, 0.8974.

Neither is a function of the parameter in any useful sense. One flipped assignment early in a
possession changes every assignment after it, and the whole spread is about one standard
error on a 234-player label set. `observed_fraction` is the one stable statistic here — it
sits on a plateau of 0.714 ± 0.001 across the middle of the block sweep.

So both constants were set from their arguments and the sweeps were used only to confirm
nothing catastrophic: `KIT_BLOCK_P = 0.25` because coverage is flat across the plateau while
cross-label assignments fall monotonically from 21 to 0, so the strict end is free;
`REACH_BRANCH_MIN_GAP_S = 0.5` because that is where the chi-square reach measurably crosses
below the physical one.

---

## 8. Round 2b — seeing nothing is evidence

The round-2 fixes removed the two ghosts that prompted the audit, and the class of
failure survived them. Measured after §1–7: **295 ghost slot-frames sat where the camera
was pointed well inside the frame and no detection of any kind lay within 3 yd.** The
tracker was asserting that a player stood in grass the camera could see was empty — and
those are exactly the ghosts that park in the middle of a formation and corrupt every
shape read taken from it.

The missing idea is that a detector finding nothing is a measurement. The likelihood of
"no detection here" is near zero inside a region the camera has searched, so the posterior
is the prior with a hole punched in it. A Gaussian cannot hold a hole, but it can hold the
two things a hole implies: the estimate is worse than we thought, and its mean is not to be
trusted.

So on a falsified miss the tracker inflates the position covariance, declares the sample
`unknown` at once rather than waiting out `PREDICT_MAX_S`, and records `falsified` — and
deliberately does **not** move the mean, because pushing it away from the searched region
would invent a direction the evidence does not contain. The test is conservative on purpose:
the point must project at least 60 px inside the frame, not at the edge where a player is
half out of shot, and "nothing there" counts detections of *either* team including ones
rejected as referees or crew, since any of them would explain the pixels.

**It improves association, which was not the point but is the strongest evidence it is
right.** A slot that knows it is lost widens its own gate, so it re-acquires its player
instead of sitting on a stale prediction. Per-player recall went **0.8932 → 0.9060**, which
is the first time M4's recall gate has passed, and position error p95 went 1.49 → 1.15 yd.

### The viewer half: a ghost can no longer stand in plain sight

Three changes, each removing a way for an unobserved slot to assert something the camera
contradicts:

- **An `unknown` disc is clipped to the region the camera cannot see.** The frustum is
  already computed for the scrim; reusing it as a clip path turns "this player might be
  anywhere in this circle, including a patch of grass you can plainly see is empty" into
  "this player is somewhere the camera is not looking", which is the true statement.
- **An `unknown` slot owns no ground in the space-control layer.** Hatching a ghost's
  Voronoi cell was the old concession, and it is not enough once the tracker can say the
  player is provably not there: territory was being handed to somebody who is not standing
  on it.
- **A matchup with an unseen end has no range.** `assignments()` returns `range: null` when
  either player is not anchored this frame, and `scheme()` judges only the matchups it can
  judge. This is what produced *"Defenders not tracking anyone closely: D3 at 11.4 yd. That
  is the story of this moment"* about a slot that was a ghost in open grass — a defensive
  breakdown invented by subtracting a guess from a measurement. The card now reads
  "N of M judged" and says how many defenders it could not see.

### The flaw the first version of the clip had, and the fix

Clipping alone made **62 % of `unknown` discs disappear entirely** — their whole disc lay
inside the camera's view, so nothing was left to draw and the slot silently vanished, which
`docs/05` forbids outright.

But an empty clipped disc is not a rendering problem. It is the estimate contradicting
itself: it claims the player is somewhere the camera can see, and the camera has just
reported they are not. The smallest claim consistent with both is that they are at least as
far away as the nearest place they could be hiding — so **that distance becomes the sigma
floor** (`Searched.distance_to_unseen`, measured by marching outward on 16 rays so it reuses
the same projection test as the falsification and cannot disagree with it). Vanishing discs
fell 62 % → 16 %.

The 16 % that remain are slots where the camera can see every place the motion model allows.
There is no honest position to draw, so the viewer draws none and the **roster row says
"nothing drawn — the camera can see everywhere they could be"**. That is 26 slot-frames on
p0001, and it is the same never-silently-blank treatment `docs/05` already specifies for a
slot with no position at all.

### Measured

| | before round 2b | after |
|---|---|---|
| ghost slot-frames asserting a position the camera sees is empty | 295 | **13** |
| slot-frames painting a marker in searched-and-empty ground | 295 | **13** |
| `unknown` discs that would draw nothing at all | — | 26, each flagged in the roster |
| falsified misses recorded by the tracker | — | 340 |
| `predicted` / `unknown` split | 854 / 264 | **577 / 527** |
| per-player recall @ 1.5 yd | 0.8932 | **0.9060 — gate passes** |
| position error p95 | 1.4907 yd | **1.1493 yd** |
| `observed_fraction` | 0.7135 | **0.7173** |
| ghosts at f103 / f205 (the two the review flagged) | 2 / 4 | **0 / 1** |

The one remaining at f205 is a `predicted` sample with a 2.4 yd disc — a slot missing for
under a second, which is the state doing its job.

---

## What the audit got wrong, and one thing it still has

The audit's own corrections table already withdrew three claims. Two further things:

- **"D5 sits at a median margin of 0.0"** was corrected to "margin is null when `alts == 1`",
  which is right, but the remedy needs one more step than the audit gives it: D5's margin was
  null on **all** 253 of its associations, which is itself the finding. A slot that never has
  a rival is a slot nothing is competing for, and on p0001 that is because it was holding a
  stationary figure at the sideline that no other slot wanted. The null was a symptom of §5,
  not an independent defect.
- **The near-miss set is not ground truth**, and the acceptance number should be read with
  that in mind. A near-miss records that a detection sat within 1.5 yd of where a slot was
  *guessing* — not that it was that slot's player. 30 of the 218 entries name a detection
  another slot's entry also names, so at most 188 are jointly reachable. Of the 61 that
  remain unrecovered, 26 went to a slot on the other team whose own kit profile fits the
  detection's torso luminance better than the baseline slot's does — recovering those would
  have been an error, not a win. `tools/m4_ghost.py` reports all three numbers and does not
  fold the last into the denominator, because that denominator would then move with the run.

**Still standing and not acted on:** the audit's root cause 2 worked example — D3 at f103,
where an unassigned `chill` detection sat 17.4 yd away with physics allowing 24. After the
classifier fix that specific case no longer arises in the same form, which the audit
explicitly said would also be a pass.
