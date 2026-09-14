# 05 — Evidence, uncertainty, and correction

This is the part of the product that is not like other tracking demos. Read it before
`04-milestones.md`.

## The problem, in numbers

**Measured in M0** on 40 seeded-random frames from the real broadcast, hand-counted at full
resolution (`docs/00-footage-report.md` Q6):

| Subset | n frames | Mean visible | Min | Max |
|---|---|---|---|---|
| **Wide live-play field shots** | 14 | **10.4 / 14 (74 %)** | 5 | 14 |
| Medium / tight live-play shots | 7 | 4.1 / 14 (30 %) | 1 | 6 |
| **All live-play frames** | 21 | **8.3 / 14 (59 %)** | 1 | 14 |

The synthetic fixture models a wide shot and averages **10.1 of 14**, which the measurement
**confirms** — 10.4 against 10.1 is as close as this kind of count gets. What the fixture
understates is the *variance*: its worst frame is 3, the real worst observed is **1**, and
that is not a freak. The broadcast cuts tight on a catch several times a point, and roughly
48 % of its running time is not a usable field shot at all. A possession containing one of
those tight cut-ins will have seconds at a stretch where twelve of fourteen players are pure
dead reckoning.

> **For p0001 specifically, the visible fraction is 84.6 %, not 88 %.** *Corrected 2026-09-13.*
> The 88 % came from three frames hand-counted during M0 (11/14/12 at frames 0/180/345). M3
> later labelled every box on 20 held-out frames of the same possession, which gives 11.85
> visible of 14 — 234 players found and labelled plus the 3 M2 measured as missed. Twenty
> frames beat three, so 84.6 % is the number to use, and `docs/04-milestones.md` M4 now does.
> The broadcast-wide figures in the table above are unaffected; this is one possession.

> Still modelled, not measured: the per-role breakdown — handler set visible 83–89 % of the
> time, deep cutters and their defenders 35–54 %. Measuring it needs tracking output, so it
> cannot be settled before M4. The *claim* it supports is sound in direction — the camera
> follows the disc, so it misses whoever is furthest from it — but do not quote the numbers
> as measurements. The deep defenders are precisely the players whose position decides
> whether the huck at the end of the possession was a good decision.

So: partial observability is the normal operating condition, not an edge case. Every layer
has to carry it.

**Which figure to design against: 8.3, not 10.4.** When sizing how much of the viewer's time
is spent showing estimates rather than observations, use the all-live-play number. The 10.4
applies only while the camera is wide, and it is wide for about a third of the broadcast.

> **The state machine below is M4's, not M3's.** Walking `observed → interpolated →
> predicted → unknown` by elapsed time presumes a motion model standing behind the estimate.
> Until the M4 tracker exists there is none, so an earlier stage that loses a detection must
> emit **`unknown`**, never `predicted` or `interpolated`. Producing plausible-looking dead
> reckoning out of a greedy matcher is precisely the failure this project exists to avoid.

## The evidence state machine

Each slot, each frame, carries exactly one state.

| State | Meaning | Positional sigma | How it is drawn |
|---|---|---|---|
| `observed` | A detection was matched to this slot in this frame, through a frame whose calibration residual was acceptable. | ~0.3 yd | Solid filled dot |
| `provisional` | A detection was matched, but the slot had been estimating for ≥ 1.0 s beforehand, so **which** player this is has not been established. | as `observed` | Solid dot inside a broken ring |
| `weak` | A detection was matched, but the **frame** is weakly placed: its calibration is below the 0.5 that `docs/03` requires for an observation, because the paint on it could not solve it and `ur/calibrate/mosaic.py` registered it against frames that could. The player was seen; where the camera was pointing is the uncertain part. | the calibration's own measured error, 0.2–2.4 yd by gap | Solid dot inside the sigma it has earned — a wide ring on a player who was plainly seen |
| `interpolated` | No detection, but observations exist within ±0.5 s on both sides. Straight-line fill. | 0.4–1.0 yd | Dashed outline dot |
| `predicted` | No detection for ≤ 2.2 s. Dead reckoning from the last observed position and velocity, damped. | 0.6–3.5 yd, growing | Dashed dot inside a translucent uncertainty disc |
| `unknown` | No detection for > 2.2 s, or never observed. Position is **held at the last observation**, not dead-reckoned. | ≥ 3 yd, capped at 16 | The disc alone — **no dot at all** |
| `confirmed` | A human placed this player here. Outranks everything. | 0.3 yd | Solid dot with a distinct ring |

> **`weak` is new, 2026-09-14** (`docs/29-scouting-possessions.md`). It exists because
> "below the confidence threshold" stopped meaning "no pose at all". It is deliberately
> **not** in the viewer's `MEASURABLE` set, so every card built on one reads `inferred`,
> and it is deliberately **in** `coverage`, because the player really was seen. The
> distinction it draws is the one this project keeps needing: *which* part of a position
> is uncertain. For `provisional` it is who; for `weak` it is where the camera was.
>
> **Two changes, 2026-09-14, from the round-2 ghost audit (`docs/25`).**
>
> **`provisional` is new.** M4 measured both of the swap detectors specified below catching
> **0 of 2** real identity switches, because both happened across a dropout rather than as a
> single-frame crossing. The honest response is not a better detector — nobody has labels to
> tune one against — but a state that says what is actually known: a detection was matched,
> so somebody is there, and the identity is unverified. It counts toward coverage and is
> excluded from `measured` and `partial` in the propagation table below, which is the whole
> point of having it.
>
> **`unknown` no longer dead-reckons.** The section "Why dead reckoning must be allowed to be
> wrong", below, is right *while the velocity estimate still means something*. Past 2.2 s it
> does not: the OU model has damped velocity to near zero, so the marker no longer tracks a
> plausible run, it creeps a fraction of a yard per frame through grass nobody has looked at.
> The argument against freezing was that a frozen dot reads as information — but so does a
> creeping one, and the creeping one also implies a direction the filter no longer has any
> evidence for. So an `unknown` sample reports the last position anyone actually saw, with a
> growing sigma and an `anchor_f` saying when that was, **and the viewer draws no marker at
> all** — only the disc. The filter keeps dead-reckoning internally, because that is still
> the best prior for re-association; it is the *reported* position that stops moving.

## Seeing nothing is evidence

*Added 2026-09-14. This is the rule that stops a ghost standing in plain sight, and it was
missing from the original spec.*

A detector finding nothing is a measurement. If the camera is pointed at the patch of field
where a slot thinks its player is, and returns no detection within about 3 yd of it, then
the estimate has been **contradicted** — not merely left unrefreshed. Before this rule the
tracker treated the two identically, and measured on p0001 it was asserting a player stood
in searched, empty grass on **295 slot-frames**.

The likelihood of "no detection here" is near zero inside a searched region, so the
posterior is the prior with a hole punched in it. A Gaussian cannot represent a hole. It can
represent what the hole implies, and that is all the tracker claims:

1. **The covariance grows.** Negative evidence makes the estimate worse, not better.
2. **The state becomes `unknown` immediately**, whatever the elapsed time. `predicted`
   asserts a position; this one has been falsified, and it may not keep being asserted.
3. **The sigma is at least the distance to the nearest ground the camera cannot see.** If
   every point the disc covers has been searched, the disc is smaller than the evidence
   allows. This matters practically as well as philosophically: it is what stops the clipped
   disc below from being empty.
4. **The mean does not move.** Pushing it away from the searched region would invent a
   direction the evidence does not contain.

**In the viewer, an unobserved slot's uncertainty is drawn only where the camera cannot
see** — the frustum is already on screen for the scrim, and reusing it as a clip path is the
difference between "could be anywhere in this circle" and "is somewhere out of shot". A slot
whose whole disc is inside the searched region has no honest place on the field at all: the
viewer draws nothing and the roster says *"nothing drawn — the camera can see everywhere
they could be"*, which is the same never-silently-blank treatment a slot with no position
gets.

**And an unobserved slot asserts nothing derived.** It owns no cell in the space-control
layer, and a matchup with an unseen end has no range rather than a range computed from a
guess. Hatching was the old concession and it is not enough once the system can say the
player is provably not there — a Voronoi cell handed to a ghost gives ground to somebody who
is demonstrably not standing on it, and subtracting a ghost's position from a real one
produces a defensive breakdown that did not happen.

> **The sigma column is a containment radius, not a per-axis standard deviation.**
> *Clarified 2026-09-13.* The gate below asks that ≥ 80 % of truths fall inside the drawn
> disc, which fixes the meaning: a per-axis σ would contain 39.3 % and could never pass.
> `docs/03-data-contracts.md` records which producer uses which level. **The figures in the
> table are the spec's original estimates and M4 measured higher** — an `observed` sample's
> radius comes out at 0.75 yd against the ~0.3 quoted, because the measured position error is
> 0.37 yd median and most of that is a systematic foot-point offset a Kalman filter cannot
> model. The table should be re-based on measurement rather than left as written.

Transitions are mechanical: `observed` on a match; on a miss, walk `interpolated →
predicted → unknown` by elapsed time; a human anchor writes `confirmed` and re-fits the
surrounding span. The one subtlety is that `interpolated` can only be assigned
retrospectively — the pipeline must buffer, since you do not know a gap was short until it
closes. Do this in a second pass over the possession, not online.

### Why dead reckoning must be allowed to be wrong

`predicted` positions use constant velocity with an exponential damp (time constant ~2.6 s).
A player who cuts while off camera will be badly misplaced, and the fixture deliberately
reproduces this: ghosts drift away from truth and snap back when the player re-enters frame.
This is correct behaviour. The alternative — freezing the player at their last seen position
— looks more stable and is more misleading, because a frozen dot reads as information. The
growing sigma disc is what stops the drift from lying.

## The camera frustum is a first-class object

The single most effective way to communicate missing information to a non-technical viewer
is not a legend: it is drawing, on the overhead view, the quadrilateral of field the camera
is actually pointed at, and scrimming everything outside it.

Compute it by inverse-projecting the four image corners onto the ground plane (rays above
the horizon are clamped to a far cap), then clipping the resulting polygon to the field
rectangle. Once that shape is on screen, "why is that player a ghost?" answers itself, and
every uncertainty convention below becomes legible rather than decorative.

## Uncertainty conventions used in the viewer

Uncertainty is encoded in **form**, never in hue — hue is reserved for team identity, and
semantic colour is reserved for warnings.

- **Fill vs outline** — observed is filled; everything estimated is outlined.
- **Dash** — any dashed stroke means "not measured in this frame". Trails switch between
  solid and dashed segment by segment, so a trail shows at a glance which parts of a run
  were watched and which were inferred.
- **Translucent disc** — radius is the positional sigma at true field scale, so it shrinks
  and grows meaningfully rather than decoratively.
- **Hatching** — used on the space-control layer for cells owned by a player whose position
  is a guess. A Voronoi map built from ghosts is worse than no map unless it says so.
- **Edge chevrons** — a player the camera cannot see still gets a marker on the video pane:
  a chevron at the frame edge, pointing where the system thinks they are, labelled with the
  sigma. It keeps the overlay honest about off-frame players instead of pretending they left
  the game.

## Provenance propagation into metrics

A derived number inherits the **weakest** evidence state among its inputs, mapped to three
labels the viewer shows next to it:

| Label | Condition |
|---|---|
| `measured` | All contributing players `observed` or `confirmed`, and frame coverage ≥ 11/14. |
| `partial` | All contributing players observed, but coverage below that. |
| `inferred` | Any contributing player `predicted`, `unknown` or `provisional`. The card is dimmed and the copy says explicitly that the number should not be quoted. |

> `provisional` joins `inferred` deliberately, and it is the uncomfortable one: the position
> *is* measured, to the same precision as any observation. What is not established is whose
> position it is, and a separation number attached to the wrong player is not a worse
> measurement of the right thing — it is a measurement of something else. Coverage counts it,
> because somebody really was seen; metrics do not, because they name a player.

This is what earns the tool's credibility. A separation-at-release figure computed from a
receiver the camera never saw is not a worse measurement, it is not a measurement, and
showing it plainly is the difference between a coach trusting the tool and dismissing it.

## The correction model

### What a human can change

1. **Place a player** — drag a ghost on the overhead view to where they actually were.
   Writes an anchor.
2. **Swap two identities from a frame onward** — fixes the classic same-team ID exchange.
3. **Confirm** — affirm that an estimated position is right. Cheap, and it collapses sigma.

That is the whole vocabulary. Resist adding more.

### How an anchor is applied

`ur/resolve.py`, given anchor `(slot, frame f, x, y)`:

1. Find `lo` = the last frame ≤ f that is `observed`/`confirmed`, and `hi` = the first frame
   ≥ f that is. These bracket the estimated span the anchor belongs to.
2. Compute the offset `(dx, dy)` between the anchor and the current estimate at `f`.
3. Apply it across `[lo, hi]` with a weight that ramps 0→1 from `lo` to `f` and 1→0 from `f`
   to `hi`, so the corrected path still meets the real observations at both ends.
4. Scale sigma down by the same weight. Set frame `f` to `confirmed`, sigma 0.3.

The result is a track that honours both the machine's observations and the human's knowledge,
with no discontinuity at the joins. The prototype implements exactly this; port it.

### Auto-detected issues, offered to the human

The system finds its own likely mistakes and puts them in a queue. Three detectors earn
their place:

> **The queue changed shape in round 2.** These three detectors all try to *pick* which
> slots are wrong. M4 measured the first two picking nothing real, and the round-2 audit
> then measured its own replacement feature — displacement from the dead-reckoned position —
> failing to separate its four nominated cases from sixteen others it had not nominated. Any
> threshold that caught the smallest admitted most of the set, and **none of the twenty was
> ever labelled**. So `contested_reacquisition` stopped picking: it now emits *every*
> re-acquisition after a gap of 1.0 s or more, ranked by displacement from the prediction,
> each carrying the runner-up it beat and the kit probability it was taken on. Twenty to
> thirty clips is a bounded review; a detector tuned against an unlabelled guess is a
> preference wearing a threshold. Set the threshold from the human labels, once they exist.

- **Identity exchange.** Two same-team slots where `|A(f) − B(f−1)| < 1.6 yd` and
  `|B(f) − A(f−1)| < 1.6 yd` while both moved more than 3 yd in that frame. This finds the
  swap the fixture injects, and it finds real ones. One-click fix: swap back from frame f.
- **Long blind stretch.** Any slot `unknown` for more than 1.5 s. Offer "place them".
- **Cold start.** Slots never observed before their first appearance — on a tight opening
  shot this is often four players at once. Group them into a single item; their opening
  positions are a formation assumption, and saying so is the honest move.

An implied-speed detector (a slot moving faster than 9.5 yd/s between consecutive frames)
is a useful fourth, but the tracker's own speed gate should prevent most of these; add it
as a sanity check on resolved output rather than on raw tracks.

### Corrections as a dataset

`corrections.json` accumulates human-verified field positions on real broadcast frames.
After a few possessions this is the only labelled ultimate tracking data that exists
anywhere. Design the format so it can be exported as detection/position training data
without rework — keep the source frame index, the image-space box if one existed, and the
field-space truth together.
