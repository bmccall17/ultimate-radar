# Round 2 — ghost audit, tracker rule changes, and disc tracking

Date: 2026-09-14. Written from `live-data.js` (p0001, 360 frames @ 15 fps, M4 tracker real
output) — `players[].state`, `players[].sigma`, `players[].assoc`, `unused_detections[]`
and `method.tracker`. **Written without access to the repo.** Every causal claim below is
an inference from the tracker's output, not from reading the code.

---

## Corrections — read this first

The coding session checked this audit against `ur/team.py`, `detections.json` and the
assoc records and found three claims wrong. They are corrected in place below; this is the
summary so nothing stale gets acted on.

| audit claim | verdict | what's true |
|---|---|---|
| The **hard team gate** is losing the observations | **partly wrong** | The losses are overwhelmingly *upstream* of association. Of ~202 near-miss slot-frames, **195 are `weak_team`** and only 7 are cross-team labels. The knob is `ur/team.py`'s `NEITHER_KIT_FRAC = 0.25`, not the Hungarian gate. |
| D5 tracks **off the field** (y to 55.1, "out of bounds") | **wrong** | The bound is 53.333 + a deliberate 2 yd margin = **55.333**. D5's worst sample is **55.27** — inside it. R3 as originally written is a no-op. |
| D5's association **margin of 0.0** shows maximal ambiguity | **wrong, and backwards** | `margin` is `null` whenever `alts == 1`. D5 has **0 non-null margins out of 253**. It was never ambiguous; it always had exactly one candidate. My analysis coerced null to 0 and read "no data" as "worst possible". |
| The four re-acquisitions are swaps and must appear in the issue list | **not established** | They were selected by displacement-from-last-observed. Under the better metric (displacement from the dead-reckoned prediction) they do not separate — see R4. Nobody has labels. |

What survives unchanged: the scale of the loss (Part 1), the χ²/speed gate mismatch
(root cause 2), and Part 3.

---

## Part 1 — What the two ghosts are

| screenshot | frame | slot | team | state | σ | stale for | parked at |
|---|---|---|---|---|---|---|---|
| first | f0103 (6.87 s) | **D3** | Wind Chill (blue) | `unknown` | 8.5 yd | 38 fr / 2.5 s | [75.2, 37.9] |
| second | f0212 (14.13 s) | **O7** | Austin Sol (white) | `unknown` | 10.3 yd | 48 fr / 3.2 s | [64.9, 24.8] |

Neither is a phantom *slot*. AD-2 locks the roster at 14, so the tracker cannot invent a
player. Both are **real slots whose player was lost**, dead-reckoned into open space and
still drawn, per docs/05's choice that "a ghost that drifts and snaps back is more honest
than one frozen in place."

The rendering is working as designed. The problem is upstream: D3 and O7 lose their players
so often that the honest ghost becomes the dominant visual.

Frames lost to gaps ≥ 1.0 s, of 360:

| slot | gaps | frames lost | % of possession |
|---|---|---|---|
| **D3** | 5 | 184 | **51%** |
| **O7** | 2 | 140 | 39% |
| **D6** | 2 | 140 | 39% |
| **O6** | 1 | 120 | 33% |
| O3 | 2 | 88 | 24% |
| O1 | 2 | 74 | 21% |

D3 is observed in only 107 of 360 frames and dead-reckoned through 191.

### Root cause 1 — detections are being discarded before association ever sees them

*(corrected — original framing blamed the association gate)*

For every slot-frame with no observation, the nearest spare detection was:

| nearest spare detection | slot-frames |
|---|---|
| `weak_team` (matched neither kit) | **693** |
| same-team, `unassigned` | 243 |
| other team, `unassigned` | 125 |
| nothing in frame | 390 |

**My count definition, so it can be reconciled:** for each frame where a slot was not
`observed`/`confirmed`, take the single **nearest** entry in `unused_detections[f]` to the
slot's dead-reckoned `est[f]`, and count it if ≤ 1.5 yd. That gives **202**: 195
`weak_team`, 7 cross-team, 0 same-team-eligible.

The coding session counts **175** — 151 `weak_team`, 24 eligible-and-lost. **Its
decomposition is the better one.** Taking only the single nearest detection per slot-frame
hides an eligible same-team detection whenever a `weak_team` one happened to be closer, so
my method systematically undercounts the eligible-but-lost cases — exactly the 24 that
matter for the gate question.

Either way the shape is the same and the conclusion flips from where I put it: this is
**a team-classification problem, not an association problem.** `ur/team.py`'s
`NEITHER_KIT_FRAC = 0.25` opens a neither-kit band of L\* 51.4–72.3 — roughly half the 41.8
L\* separation between the two kits — and 341 detections fall into it. Only 6 have ≥ 3
stripe runs; median height ratio 1.007; spread across the full field width. They are
players.

Some are absurd: O6 lost at f147 with a detection **0.2 yd** away; O1 at 10.5 s, 17.5 s and
17.7 s with `weak_team` detections **0.2 yd** away.

**`docs/17`'s justification for the 0.8846 recall does not hold.** It asserts the excluded
detections are "over half referees and camera crew". Their y-distribution (p10 29.8, median
37.6, p90 48.4 on a 53.3-yd field) is the middle of the playing area, and 91 of them sit
within 2 yd of an already-tracked player.

### Root cause 2 — the two association gates contradict each other

*(unchanged — still believed, still worth checking against the code)*

`method.tracker` documents a physical reach (`9.5 yd/s × elapsed`, plus 3σ of combined
endpoint noise) and a statistical gate (`chi2_2dof = 9.21`), and states the physical bound
is what limits how far the player moved.

It never does. With `sigma_yd = 1.7941 × sigma_axis` and a χ² radius of `√9.21 = 3.035
sigma_axis`, the statistical reach in yards is `1.692 × sigma_yd`:

| elapsed | median σ_yd | χ² reach | speed reach | binding |
|---|---|---|---|---|
| 0.5 s | 1.7 | 2.9 yd | 4.8 yd | **χ²** |
| 1.0 s | 3.3 | 5.6 yd | 9.5 yd | **χ²** |
| 2.0 s | 6.4 | 10.9 yd | 19.0 yd | **χ²** |
| 2.5 s | 8.0 | 13.5 yd | 23.8 yd | **χ²** |
| 3.0 s | 9.6 | 16.2 yd | 28.5 yd | **χ²** |
| 4.0 s | 12.5 | 21.1 yd | 38.0 yd | **χ²** |

χ² binds at every elapsed time past 0.5 s, by 1.7–2×. The longer the gap, the more the
physics should govern re-acquisition and the less the stale covariance should; this has it
backwards.

Worked example, D3 at f103: parked at [75.2, 37.9], σ 8.5, χ² reach 14.4 yd. An unassigned
`chill` detection sat at [59.4, 30.6] — **17.4 yd away**. Physics allowed 24 yd. χ²
rejected it.

Caveat given root cause 1: fixing the classifier may make most of these moot by supplying a
nearer candidate. Measure R1 first and re-check whether R2 still buys anything.

### Root cause 3 — a slot is holding a figure near the sideline

*(corrected — the original "off field" claim was wrong)*

**D5** has 17–19 `observed` samples between 18.8 s and 20.0 s at y up to **55.27**, worst at
f300. The field is 53.333 wide and `detections.json` carries a deliberate ±2 yd margin
(soccer-frame `y_max = 22.583` → field y 55.333), so **these samples are legitimately in
bounds** and tightening the bound would discard real players pivoting on the line — which
`ur/team.py` argues against explicitly.

The observation that stands: D5 is holding a lone figure loitering at the sideline for well
over a second, with nothing competing for it. Position alone does not discriminate that
from a real player on the line. The open question — which I can't answer from the output
alone — is what does: sustained residence outside the playing proper, absence of
player-like motion, or a competing claim that never arrives.

### Root cause 4 — re-acquisition after long gaps

*(corrected — the four named cases are candidates, not confirmed swaps)*

I flagged four re-acquisitions by displacement from the **last observed** position. The
coding session correctly replaced that with displacement from the **dead-reckoned
prediction**, which is the right reference. Under it, the four do not separate:

| slot | f | gap | from last-observed | from prediction | rank of 20 |
|---|---|---|---|---|---|
| O7 | 217 | 3.5 s | 14.8 yd | 18.7 yd | 3rd |
| D3 | 170 | 1.8 s | 13.9 yd | 9.2 yd | 11th |
| D6 | 172 | 1.7 s | 11.3 yd | 9.5 yd | 9th |
| O1 | 322 | 2.7 s | 12.1 yd | 5.3 yd | **13th** |

There are **20** re-acquisitions after a gap ≥ 1.0 s in this possession. Ranked by
displacement-from-prediction, my four sit at 3rd, 9th, 11th and 13th, interleaved with six
cases I did not flag (O6@f331 at 25.0 yd, D6@f335 at 20.6, D3@f303 at 14.0, O7@f340 at
13.8, O2@f153 at 12.2, O3@f282 at 11.9). Any threshold catching O1 at 5.3 yd admits 13 of
the 20.

So: displacement-from-prediction is the right *feature* and it may still be the best one
available, but it does not by itself pick out the swaps, and **my four were never ground
truth** — they were the output of a worse metric. See R4 for what to do instead.

---

## Part 2 — Rule changes

These are hypotheses from the tracker's output. The code is the authority. Where a rule
below is wrong, the corrections table at the top is the precedent — say so and take the
better path.

### R1 — Fix the team classifier before touching association *(highest value)*

The `weak_team` band is swallowing players. Narrow or replace `NEITHER_KIT_FRAC`'s dead
zone, and have the classifier emit a **probability per team** rather than a three-way hard
label, so uncertainty is expressed rather than thrown away.

If association still needs to tolerate uncertain kits after that, add a graded term
`−2 · ln P(detection team = slot team)` to the Hungarian cost — same units as the squared
Mahalanobis, capped (~+25) so a confident wrong kit still effectively blocks. A detection
0.2 yd away with an uncertain kit then wins; one 15 yd away with a confident wrong kit
still loses, which is the protection AD-3 was built for.

**Gate:** of the ~175 near-miss slot-frames (your definition), at least 150 become
observations. Cross-team assignment with both kits confident (P > 0.9) stays at zero.

### R2 — Reconcile the two gates

Accept a candidate inside **either** `3.035 · σ_axis` **or** the physical reach
`v_max · Δt + 3σ_endpoint`, rather than requiring both. Keep squared Mahalanobis as the
*ranking* cost — this changes what is admissible, not what is preferred. Restrict the
physical-reach branch to slots stale ≥ 0.5 s with no competing slot inside their own χ²
gate.

**Gate:** observed fraction rises from **0.6786**. Cross-team assignments stay at zero.
D3 acquires the f103 candidate at [59.4, 30.6] — *or* R1 supplies it a nearer one and this
case never arises, which is also a pass.

*(The original version of this rule also required "no slot at a median margin below 2.0".
Drop that — see R2a.)*

### R2a — Make `margin` mean something *(new, from the coding session)*

`margin` is `null` whenever `alts == 1`, which is the majority of every slot's records
(D5: 0 non-null of 253; O6: 1 of 224; O7: 11 of 180). Any statistic over it today is
mostly reading absent data — my own "D5 sits at 0.0" was exactly that error.

Define it for the single-candidate case as the distance to the gate edge, so "alone in the
gate" reads as a *large* margin. Then a median margin per slot is a meaningful diagnostic
and can be used as an acceptance criterion.

**Gate:** no `null` margins on successful associations. D5's median margin is large, not
small.

### R3 — Constrain the tracker's state, not the detection bounds

*(rewritten — the original bound was already in place)*

Leave `detections.json`'s ±2 yd margin alone. The failure is a slot holding a stationary
sideline figure for seconds at a time. Put the constraint where the slot's state is
decided, and pick a discriminator that isn't position alone.

**Gate:** D5 stops holding the f300 figure. No real player pivoting on the sideline is
dropped anywhere in the possession — check this explicitly; it's the failure mode the fix
risks.

### R4 — Label the re-acquisitions before tuning a detector for them

*(rewritten — the original named four cases as acceptance criteria)*

Do not gate on my four. Instead: emit all **20** re-acquisitions after a gap ≥ 1.0 s as
`contested_reacquisition` candidates, ranked by displacement-from-prediction, with the
taken candidate and the runner-up. Then a human watches 20 clips and labels them. Tune
against those labels.

Add the **`provisional`** evidence state either way: renders like `observed`, excluded from
every metric until confirmed or swapped in the viewer. Twenty candidates is a bounded
review; a detector tuned against an unlabelled guess is not.

**Gate:** all 20 appear as reviewable candidates with both alternatives attached.
`identity_switches_caught` in docs/17 is re-derived against the human labels, not
self-reported.

### R5 — Stop dead-reckoning once the state is `unknown`

docs/05 is right that a drifting ghost beats a frozen one **while the velocity estimate
still means something**. Past 2.2 s it does not.

- `predicted` (< 2.2 s): unchanged — drift on the filter's velocity, growing σ.
- `unknown` (≥ 2.2 s): freeze position at the last observation, keep growing σ, render the
  sigma disc only — no centre dot, no trail.

This removes what reads as a phantom player without reversing the docs/05 principle.

**Gate:** at f103 and f212 the viewer shows a bounded uncertainty region and no player
marker. No `unknown` slot is ever the nearest defender in a metric card.

### R6 — Re-derive the M4 recall gate

Confirmed already by the coding session's stripe-run and height-ratio analysis: the
`weak_team` exclusions are not mostly officials. After R1, recount recall and restate the
gate, reporting non-player exclusions separately from low-confidence player detections.

### Order

R1 → re-measure everything → R2 (may be moot) → R2a → R6 → R3 → R4 → R5.

---

## Part 3 — Disc tracking

*(unchanged)*

Without the disc we cannot identify the handler, so Sean's definition of sagging —
"separation between the handler and the handler defender" — is not expressible. AD-7 should
be promoted to a Round 2 milestone.

### Don't build a disc detector first

A disc is ~27 cm, motion-blurred at 60 fps broadcast, and for most of a possession it is
**held** — occluded by a hand and a torso inside the densest cluster of bodies on the field.
That is the hardest version of the problem and the version we don't need to solve.

Model the disc as a state machine over the possession:

```
HELD(player_id)  --release-->  FLIGHT(from, t0)  --catch-->  HELD(player_id')
                                      |
                                      +--incompletion--> LOOSE --pickup--> HELD
```

- **HELD** — disc position ≈ the holder's tracked position plus a small offset. Already in
  `players[].est`; costs nothing.
- **FLIGHT** — the only phase needing pixel detection, and the only one where it's easy:
  the disc is separated from every body, silhouetted, on a smooth arc, over a window
  bounded by two known endpoints.
- **LOOSE** — ground disc after a turn. Static, rare.

Disc position for 100% of frames, carrying the same evidence states the players already do.

### Build order

1. **Holder inference (no new models).** The holder is the offensive player who is
   near-stationary while others cut, with exactly one defender inside ~2 yd sustained over
   several frames. Emit `holder_id` per frame with a confidence, `unknown` when ambiguous.
   Validate against hand-tagged holders on p0001 — target ≥ 90% of frames where a holder
   exists.
2. **Two-click human tagging.** Add `tag_release` and `tag_catch` to the append-only
   correction log (AD-6). Flight is interpolated between two known player positions. This
   alone makes the "Separation at release" card work, and produces the labelled set step 3
   needs.
3. **Flight detection.** D-FINE or RT-DETRv2 with SAHI tiling (licence-approved), run only
   between a tagged release and catch, high tile overlap. Fit a ballistic-with-lift
   trajectory in field coordinates; reject detections off the curve. Seed from step 2.
4. **Automatic release/catch.** Only once 1–3 work. Release is a discontinuity in the
   holder's arm pose; catch is a flight trajectory terminating within a yard of a tracked
   player. RTMPose if pose is needed.

### What the disc unlocks

- **The handler** — Sean's definition becomes expressible for the first time.
- **The mark** — which defender, which side, force direction.
- **Roles derived, not declared.** All 14 slots are currently `role: cutter` / `defender`.
- **Separation at release**, per throw — the most coach-legible number available.
- **Shape lag against the disc** rather than the offensive centroid, which is what Sean
  actually described.
- **Off-disc becomes definable.** Sean's sagging is explicitly about players *off* the disc.

### Ordering

Disc work follows R1. Holder inference reads player positions directly; with D3 lost 51% of
the time, it would inherit those gaps and be built on tracks that are about to change.
