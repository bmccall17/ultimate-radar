# 17 — M4, tracking

**Status: four of five gates pass. The fifth passes its count and fails its second clause,
and that failure is the most useful thing in this milestone.**

| M4 gate | Required | Measured | |
|---|---|---|---|
| Identity switches | ≤ 2 | **2** | pass |
| …every one detected by the M5 swap detector | all | **0 of 2** | **fail** |
| Field position error, `observed` | median < 0.8 yd, p95 < 1.8 | **0.3698**, **1.0337** | pass |
| Per-player recall, position-matched *(re-specified)* | — | **0.8846** | threshold unset |
| Phantom or missing slots | zero, always | **zero** | pass |
| Sigma calibration | ≥ 80 % inside the disc | **80.0 %** (32/40) | pass, marginal |

Evidence: `eval/m4/`. Acceptance JSON for each gate, four hand-label sets, the render, and
the speed measurement. Write-up of what watching the tracker showed: `docs/16-m4-watching.md`.

---

## The motion model took three attempts

Two of the three failures **presented as association bugs and were covariance bugs**, which
is why they are recorded in `ur/track/kalman.py` rather than quietly fixed.

1. **Piecewise white-noise acceleration**, `Q = G Gᵀ σ_a²`. Velocity variance grows as
   `σ_a²·dt·T` — it depends on the frame rate. At 15 fps the filter believed a player
   unobserved for two seconds had a velocity uncertainty of 1.5 yd/s, when someone last seen
   running at 5 yd/s could by then be doing anything between −5 and +5. The symptom: **736
   detections, a median of 13 yd from every slot, failed association**. Real players went
   unassigned while their own slots sat predicting confidently in the wrong place. The
   obvious response — loosen the gate — would have buried the fault and produced a tracker
   that quietly assigned detections to the wrong people.
2. **Undamped covariance** (damp the mean, not the covariance) overshot the other way:
   7.8 yd/s after 2.2 s, most of the probability mass beyond a flat-out sprint.
3. **Integrated Ornstein-Uhlenbeck velocity**, which is what ships. Velocity reverts to zero
   with the 2.6 s constant `docs/05` already specifies for dead reckoning, and the process
   noise is the exact discretisation of that model. Mean and covariance go through the same
   transition, so the damping *is* the model rather than a smoothing of the mean, and the
   filter never becomes more certain by damping.

Verified two ways that do not share code with the filter: velocity sd saturates at exactly
σ_v, and `Q_pp` converges on the white-noise-acceleration limit `q·dt³/3` as `dt` falls
(ratio 0.981 at 15 fps, 0.997 at 100 fps).

**σ_v = 2.6 yd/s is measured, not chosen** (`tools/m4_speed.py`). Single-frame differencing
cannot measure it — 0.6 yd of foot noise over 1/15 s implies 9 yd/s, larger than the quantity
— and the tool prints zeroes at those baselines rather than a number. Differencing over a
range of baselines, subtracting the foot noise M3 measured, and inverting the integrated-OU
displacement variance gives 2.50 / 2.64 / 2.63 at 0.8 / 1.3 / 2.0 s. Fed back and re-measured:
2.635 / 2.623. It converged. Recorded in `docs/02` AD-1 as a sport constant, not a knob.

## The gate that was wrong, and the gate that replaced it

M4's original `observed` fraction gate compared two **counts** — observed slot-frames against
players visible. A count comparison can be satisfied by counting the wrong objects, and this
one actively rewarded it: admitting the detections `ur/team.py` flags `weak_team` would have
added ~1.1 per frame, over half of them referees and camera crew, and bought ~8 points by
putting non-players into player slots. The number would have passed and the product would
have been worse. It also pulled against "zero phantom slots", so two gates measured the same
coverage from opposite ends.

**Replaced by per-player recall, position-matched.** For each of the 20 hand-labelled frames,
take every box a human called `sol` or `chill`, project its foot point, and ask whether a slot
*of that team* is `observed` within 1.5 yd. A referee cannot improve this, because referees
are not in the denominator.

| threshold | greedy | one-to-one | vs the wider denominator |
|---|---|---|---|
| 1.0 yd | 0.8504 | 0.8504 | 0.8397 |
| **1.5 yd** | **0.8846** | **0.8846** | 0.8734 |
| 2.0 yd | 0.8974 | 0.8932 | 0.8819 |

Greedy and one-to-one agree at 1.0 and 1.5 yd — no observed slot stands in for two players at
once, a failure mode ruled out rather than assumed away. The 27 misses attribute completely:
**14 excluded as `weak_team`**, 10 rejected by the association gate at a median of 15 yd, 3
where the slot sits 1.6–2.4 yd from a detection it did consume.

**The threshold is deliberately unset.** Reaching 0.90 would require readmitting the
detections whose exclusion keeps referees out of player slots — the trap the old gate fell
into. Whoever sets the number should do so explicitly.

> ### Re-derived 2026-09-14. The justification above does not survive its own labels.
>
> The paragraph before this one rests on a claim that was never measured: that the excluded
> `weak_team` detections are the ones "whose exclusion keeps referees out of player slots".
> `eval/m3/team_labels.json` labels every in-bounds box on the same 20 held-out frames.
> Cross-tabulating the 22 `weak_team` detections in it against those labels:
>
> | what the label says | n | share |
> |---|---|---|
> | **chill player** | 9 | |
> | **sol player** | 5 | **64 % real players** |
> | referee | 3 | |
> | camera crew | 2 | **23 % non-players** |
> | box spans two players ("unsure") | 3 | 14 % |
>
> The exclusion was discarding roughly two real players for every non-player it caught. The
> 8 points the old count-based gate would have bought by admitting them were not 8 points of
> referees; most of them were players.
>
> **The error was in reporting, not only in reasoning.** `ur/team.py` already had a separate
> and correct mechanism for non-players — `non_player: "ref" | "crew"` — and those detections
> were *already* excluded, by a different code path, before `weak_team` was consulted. The
> two exclusions were then reported as one number (`weak_team_detections_skipped`), which is
> what let a population that is 64 % players be described as mostly officials. The two are
> now counted and printed separately everywhere: `non_player_detections_skipped` against
> `weak_kit_detections_admitted` in `tracks.json`, and `tools/m4_recall.py` splits its misses
> three ways rather than one.
>
> **The re-derived measurement**, after `weak_team` became a price rather than a veto
> (AD-3 as amended):
>
> | | before | after |
> |---|---|---|
> | per-player recall @ 1.5 yd, one-to-one | 0.8846 | **0.8932** |
> | misses at 1.5 yd | 27 | **25** |
> | …rejected as a referee or crew member | — | **0** |
> | …a real player with a weak kit call | 14 | **2** |
> | …a real player with a confident kit call | 13 | **23** |
>
> The misses are no longer a classification problem. Twelve of the fourteen kit-driven
> misses are gone, and what remains is association: 23 players the tracker had a confident
> detection for and did not put in the right slot.
>
> **The threshold stays unset, for a different and better reason.** The old reason — that
> closing the gap means readmitting referees — is retired; it was not true. The new reason is
> that this statistic is **chaotically sensitive at this sample size**. Sweeping the
> association constants over their plausible ranges moves recall non-monotonically between
> 0.880 and 0.919, and the whole spread is about one standard error on 234 labelled players.
> One flipped assignment early in a possession changes every assignment after it. A
> threshold set against a number that jitters by a standard error under changes that should
> not matter is a threshold that will be met by luck. **Setting it needs more labelled
> frames, or more possessions — not a better argument.**

## Watching found two things no statistic had

`docs/16-m4-watching.md` in full; the two that changed what I believed:

**A camera operator held a defender's slot for the last second.** D6, from f339. He cleared
three filters by a hair: field y 55.09 against a bounds margin ending at 55.33; height ratio
0.779 against a floor of 0.62; and torso L\* 51.0 against a neither-kit band starting at
51.39 — missing the `weak_team` flag by **0.39 L\***, so `ur/team.py` called him `chill` with
full confidence. The two-part crew rule argued for in `docs/14-m3.md` behaves exactly as
designed and is wrong here.

**The unassigned detections are real players, and the handback said the opposite.** 227 of
them sit "outside every gate at a median of 23 yd", which I had called "almost always a
non-player" — inferred from a distance statistic without looking at the pixels. They are
players in full kit, and **245 of 248 occur while that team still has a free slot.**

That led to a type error in the reach gate: it compared a bound on how far the *player* could
have moved against the distance between two *measured* points, with no allowance for either
endpoint's noise. The old `max(2.0 yd, speed × elapsed)` floor was tighter than the
statistical gate at short gaps and rejected **70 associations chi-square scored at 4.4 against
a threshold of 9.21**. Now `speed × elapsed + 3σ` of combined endpoint noise, taken from the
slot's sigma when last *observed* so the physical backstop is not widened by the uncertainty
it exists to contain. Reach-only rejections went 70 → 0 and recall at 1.5 yd went 0.8846 →
0.8846. **The defect was real, the fix is right, and it bought nothing on the headline gate.**

## Sigma failed on units, not on the filter

At first measurement, 57.5 % of truths fell inside the drawn disc against a gate of 80 %.
`docs/05` draws a disc of radius `sigma`; the tracker was emitting a **per-axis standard
deviation**, and for a 2-D Gaussian that disc contains **39.3 %** — unreachable by
construction. Working back from 57.5 % says the covariance is about **31 % conservative**: the
number was right and the units were wrong.

M3 had already settled this for detections (`sigma_yd` is an rms, a containment radius). The
tracker now reports 1.794 × the per-axis sigma. Its internal covariance is untouched and
association is unaffected. `docs/03` carries the definition and a table of which producer uses
which containment level.

**The pass is marginal: 32 of 40 is exactly 80.0 %, and the Wilson 95 % interval on n = 40 runs
65.2 % to 89.5 %.** A larger sample is the only way to call it.

The position sample was drawn **disjoint from `eval/m3/foot_labels.json` by construction** —
`FOOT_UNCERTAINTY_PX` was fitted on those 50, so scoring sigma against them would have asked a
constant whether it fits its own training data. It independently reproduces M3's foot-point
bias: dx −1.62 px against −1.52, dy −2.15 against −1.66, sharing no detections. That makes the
bias a measured fact, and it is most of what remains: **0.38 yd of pure offset against a
0.370 yd median total error.** A Kalman filter cannot remove it — it assumes zero-mean noise,
and averaging frames does not cancel a shift.

## The identity gate, and why M5's detectors would miss

Two switches, both **across a dropout** — the slot stops being observed for 1.8 s and 3.3 s
and re-acquires onto a different person.

`docs/05` specifies two detectors precisely enough to implement from the text, so the gate's
second clause was answered rather than deferred. Both miss both switches:

- **Identity exchange** — two same-team slots where `|A(f) − B(f−1)| < 1.6 yd` and
  `|B(f) − A(f−1)| < 1.6 yd` while both moved more than 3 yd — **fires 0 times over the entire
  possession.** It looks for a single-frame crossing, and a re-acquisition swap has no
  crossing frame.
- **Long blind stretch** (`unknown` for more than 1.5 s) fires 3 times — O6, O7, D6, none of
  which switched. D1 was never `unknown` at all; D2's longest `unknown` run is 1.1 s. Both
  gaps were spent mostly in `predicted`.

**M5's detectors are calibrated for the failure the fixture injects and miss the one real
footage produces.** The fix is nearly free: the tracker already computes the Mahalanobis
distance at re-association, so a *re-acquisition surprise* detector — flag a slot that
re-acquires far from where it was dead-reckoned — needs no new machinery.

> **The proposed fix does not work either, measured 2026-09-14.** Mahalanobis distance
> cannot separate these: every re-acquisition is inside the gate by construction, so the
> four the round-2 audit nominated score χ² of 1.19, 6.57, 9.02 and 9.20 against a threshold
> of 9.21 — the full range of the admissible band. Ambiguity does not separate them either;
> two of the four have margins of 5.3 and 7.0, comfortably unambiguous. Displacement from
> the dead-reckoned position is the right *feature* and still does not pick them out: ranked
> by it, the four sit 3rd, 9th, 11th and 13th of the twenty re-acquisitions in the
> possession, interleaved with six the audit never flagged, and any threshold catching the
> smallest admits thirteen of the twenty.
>
> The deeper problem is that **nobody has labelled any of them**, so there is nothing to tune
> against and every "detector" here is a preference with a number attached. The tracker now
> marks all of them `provisional` and `ur.issues` emits the whole set for review. The
> `identity_switches_caught` figure in `possession.json` was self-reported as "2 of 2" and is
> withdrawn: it counted the detector agreeing with the same analysis that produced it.

### The labels caught themselves twice

Four of 52 readings were withdrawn, none because they were inconvenient:

- Two pairs read as the same number on the same frame while **6.1 and 23.5 yd apart**. Two
  people cannot wear one number. Re-rendered at 9×; neither pair resolved, so all three
  readings involved were withdrawn rather than one of each pair picked.
- D7 appeared to switch #28 → #23 in 1.0 s while observed in all 16 frames and never moving
  more than **0.3 yd** between them. A continuously tracked slot moving sub-yard cannot change
  which person it holds. That argument only chose which crop to re-examine; the decision came
  from the image at 10×, where the second glyph is behind the player's arm. **Withdrawn rather
  than corrected to 28** — inferring 28 would use the tracker's own continuity, which is
  circular for a gate measuring the tracker.

## Honest limits

- **Jersey legibility is 20 %, not the ~50 % a three-frame probe suggested**, and it is not
  uniform: ~50 % where the camera is closest, ~12 % across the wide opening and ending. The
  switch measurement has good sensitivity in the middle third of the possession and poor
  sensitivity at either end. A switch in the opening or closing seconds could go unseen.
- **The implied reading-error rate is about 4 in 52**, and only conflicts that collide on one
  frame are detectable at all, so the switch count carries roughly ±1 of its own.
- **All labels are the agent's own**, not an independent human's — the standing caveat, and it
  binds hardest on a gate whose whole budget is two events.
- **Sigma is only verifiable where it is least interesting.** An `observed` disc can be checked
  against a hand-read foot point; a `predicted` disc covers a player who is off camera, which
  is the entire reason the sample exists and the reason it cannot be checked.
- **One possession, one camera, one lighting condition.** Nothing here says any of it
  generalises.
- **The 120 vs 110 yd field length is still open** (`docs/08-risks.md` #5). It bounds only
  absolute distance along the field.

## Reproducing

```bash
python -m ur.track.run      work/p0001     # -> tracks.json
python -m ur.possess        work/p0001     # -> possession.json
python -m tools.m4_render   work/p0001     # the two-pane video
python -m tools.m4_structure work/p0001    # phantom / missing slots
python -m tools.m4_recall   work/p0001     # per-player recall
python -m tools.m4_foot     score work/p0001   # position + sigma
python -m tools.m4_label    score work/p0001   # identity switches
python -m tools.m4_speed    work/p0001     # re-measures sigma_v
```
