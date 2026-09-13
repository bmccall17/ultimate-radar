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

> Still modelled, not measured: the per-role breakdown — handler set visible 83–89 % of the
> time, deep cutters and their defenders 35–54 %. Measuring it needs tracking output, so it
> cannot be settled before M4. The *claim* it supports is sound in direction — the camera
> follows the disc, so it misses whoever is furthest from it — but do not quote the numbers
> as measurements. The deep defenders are precisely the players whose position decides
> whether the huck at the end of the possession was a good decision.

So: partial observability is the normal operating condition, not an edge case. Every layer
has to carry it.

## The evidence state machine

Each slot, each frame, carries exactly one state.

| State | Meaning | Positional sigma | How it is drawn |
|---|---|---|---|
| `observed` | A detection was matched to this slot in this frame, through a frame whose calibration residual was acceptable. | ~0.3 yd | Solid filled dot |
| `interpolated` | No detection, but observations exist within ±0.5 s on both sides. Straight-line fill. | 0.4–1.0 yd | Dashed outline dot |
| `predicted` | No detection for ≤ 2.2 s. Dead reckoning from the last observed position and velocity, damped. | 0.6–3.5 yd, growing | Dashed dot inside a translucent uncertainty disc |
| `unknown` | No detection for > 2.2 s, or never observed. | ≥ 3 yd, capped at 16 | Faint hatched disc; the dot is nearly gone |
| `confirmed` | A human placed this player here. Outranks everything. | 0.3 yd | Solid dot with a distinct ring |

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
| `inferred` | Any contributing player `predicted` or `unknown`. The card is dimmed and the copy says explicitly that the number should not be quoted. |

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
