# 02 — Architecture

```
video ──> ingest ──> frames + clip.json
                          │
          ┌───────────────┴────────────────┐
          ▼                                ▼
     calibrate                          detect
   shots, mosaic,                 RT-DETRv2/D-FINE + SAHI
   human anchors                   boxes per frame
   -> calibration.json                    │
          │                               ▼
          │                          team assign
          │                     torso colour, 2 clusters
          │                               │
          └──────────► project ◄──────────┘
                 boxes -> field coordinates (yd)
                           │
                           ▼
                      track  (the core)
            field-space Kalman, team-gated association,
            14 locked roster slots, evidence states
                           │
                           ▼
                      identify
              jersey OCR per tracklet + voting
                           │
      events.json ────────►├◄──────── corrections.json
      (human tagged)       │          (human edits, append-only)
                           ▼
                        resolve  ──►  derive  ──►  possession.json
                                                        │
                                                        ▼
                                                     viewer
```

Nine decisions define this system. Each is here with the reason, because a coding agent
that knows the reason makes better local choices than one following a diagram.

---

## AD-1 — Track on the field, not on the screen

Detections are converted to field coordinates **before** association. The Kalman filter
runs in yards on the ground plane, not in pixels.

*Why.* A panning, zooming broadcast camera makes pixel-space motion meaningless: a
stationary player has large screen velocity during a pan. The standard fix is global motion
compensation (BoT-SORT's ORB/ECC module), which fits an affine model per frame and degrades
exactly when the camera zooms hard — which is when ultimate is most interesting. But we are
already computing a homography for the radar view. Using it one stage earlier makes the
motion model physical: a person accelerates at most ~6 yd/s² and sprints at most ~9.5 yd/s,
so the gate on association is a real constraint rather than a tuned pixel threshold. It also
means the tracker's state **is** the thing the radar draws — no second coordinate system to
keep in sync.

*Consequence.* Calibration quality becomes the upstream dependency for everything. A frame
whose homography residual is poor must down-weight its detections, not silently corrupt the
tracks. Carry `calibration.confidence` per frame into the tracker's measurement noise.

*Measured in M4: the sport constant the motion model needs.* Tracking on the ground plane
makes the motion model physical, which means it needs a physical number. That number is
**σ_v = 2.6 yd/s**, the stationary 1-sigma of one velocity component for an ultimate player
during a point. **It is not a tuning knob and should not be adjusted to make a tracker behave.**

It is not a sprint speed either — a sprint is ~9.5 yd/s, quoted above. It is the spread of a
velocity *component* over a whole point, most of which is spent moving moderately or standing,
and it sets how fast positional uncertainty grows while a player is unobserved.

Method (`tools/m4_speed.py`, `eval/m4/m4_speed.json`): single-frame differencing cannot measure
it, because 0.6 yd of foot-point noise over 1/15 s implies 9 yd/s — larger than the quantity
itself, and the tool prints zeroes at those baselines rather than a number. So displacement is
differenced over a range of baselines, the foot-point noise M3 *measured* is subtracted in
quadrature, and the integrated-Ornstein-Uhlenbeck displacement variance is inverted rather
than assuming velocity is constant over the baseline. The estimate rises out of the noise and
settles: **2.50, 2.64, 2.63 yd/s** at baselines of 0.8, 1.3 and 2.0 s. Fed back into the
filter and re-measured, it returns 2.635 and 2.623 — it converged.

One caveat, stated because the next person will want it: the noise subtracted (1.183 yd rms
over two frames) is about 10 % larger than M3's foot-point rms implies (1.076). Part of that
is genuine conservatism and part is population difference — M3's foot sample was restricted to
boxes ≥ 40 px tall, which are nearer players with smaller `yd_per_px`. Either way it biases
σ_v slightly low rather than high.

## AD-2 — Fourteen locked roster slots, not free-running track IDs

Per point there are exactly 7 offensive and 7 defensive players. The tracker's state is 14
slot trajectories that exist for the whole possession. Detections are assigned to slots. A
slot whose detection is missing is **not** deleted — it degrades to `predicted`, then
`unknown`. There is never a 15th slot and never a 13-player possession.

*Why.* Generic MOT creates and destroys tracks, which produces the two failure modes a coach
will never forgive: a player who blinks out of existence, and a phantom extra defender. The
roster constraint is free, exact information about ultimate that generic trackers do not
have. It also turns identity into a bounded assignment problem — 7 candidates, not N — and
makes human correction cheap: there is always exactly one right answer to "which slot is
this?".

*Consequence.* Substitutions only happen between points, so a possession never changes its
roster. A new point means a new possession file.

## AD-3 — Team colour is a hard gate

> **Amended 2026-09-14, after the round-2 ghost audit.** The decision's *reason* is
> unchanged and is still the important part: **a cross-team identity swap corrupts every
> matchup, every separation number and the scheme classifier at once, so it is forbidden
> outright.** That prohibition is intact and is measured at zero on p0001 before and after.
> What changed is what the prohibition applies to.
>
> **(a) The gate is on a confident kit call, not on a hard three-way label.** `ur/team.py`
> emits `team_p`, the probability that a detection's torso is the team it is labelled. A
> detection the classifier puts at P ≥ 0.9 for one kit can never be associated to a slot of
> the other — that is AD-3, unchanged. Below that the detection is admissible to either team
> and pays `−2 ln P(kit = slot's team)` in the assignment cost, in the same units as the
> squared Mahalanobis distance because both are twice a negative log likelihood. Association
> is blocked outright once the kit evidence leans 3:1 to the other team (`KIT_BLOCK_P`).
>
> **(b) A weak kit call is no longer a deletion.** This is the substantive change. The old
> code did not merely refuse to cross teams on a `weak_team` detection, it **excluded that
> detection from association entirely**, on the grounds recorded in `docs/17` that such
> detections were "over half referees and camera crew". Measured against
> `eval/m3/team_labels.json`, which labels every in-bounds box on 20 held-out frames, the
> `weak_team` set is **14 real players, 5 non-players and 3 boxes spanning two players** —
> 64 % players, not the majority non-players the exclusion assumed. It was the single largest
> cause of slots going blind: 218 slot-frames on p0001 where a usable detection sat within
> 1.5 yd of a slot that was dead-reckoning instead.
>
> **(c) The assignment is solved once, not once per team.** A kit-ambiguous detection is a
> candidate for slots on both teams, and two separate per-team solves would each be free to
> take it — which is how one person becomes two players. One Hungarian over all fourteen
> slots is what makes the one-to-one constraint mean anything now that the teams' candidate
> sets overlap. `tools/m4_structure.py` checks for shared detections and measures zero.
>
> **What still protects against a cross-team swap, now that the gate is not on the label.**
> Four things, in order of how much work they do:
>
> 1. **The confident-kit prohibition itself.** The kits are ΔE 36.6 apart in CIELAB and only
>    1 of 234 hand-labelled players is misclassified by luminance alone. The overwhelming
>    majority of detections are confident, and for those nothing changed at all.
> 2. **The 3:1 block.** Measured across block thresholds of 0.10 to 0.50, the observed
>    fraction is flat (0.714 ± 0.001) while assignments taking a detection whose nearer label
>    is the other team fall from 21 to 0. Coverage does not pay for the strictness, so the
>    setting is taken from the strict end of the plateau.
> 3. **The cost, not just the gate.** An ambiguous detection carries a penalty of up to 2.8
>    against a chi-square gate of 9.21, so it loses every contest that is close on geometry.
>    A confident same-team candidate beats it every time.
> 4. **Cold starts still require a confident kit.** A slot that has never been observed has
>    no motion model and no competing claim to catch a bad seed, so it may only be seeded
>    from a detection at P ≥ 0.9.
>
> **What this gives up, stated plainly.** 13 of 3568 assignments on p0001 take a detection
> whose nearer label is the other team, all at P 0.25–0.49 — never confident. Under the old
> rule those 13 would have been dropped rather than crossed, and some of them are probably
> wrong. The trade is 13 uncertain crossings against 218 slot-frames of blindness, and the
> crossings are visible in `tracks.json` as `assoc.kit_p` rather than silent.
>
> The original decision, which still governs where the amendment is silent:

Torso-crop colour, clustered into two groups per point, assigns team. Association across
teams is forbidden outright.

*Why.* The Sol wear light kit and the Wind Chill dark; the separation is close to trivial and
far more reliable than any learned re-ID embedding. Cross-team identity swaps are the single
most damaging error for a defensive-analysis tool — they corrupt every matchup, every
separation number, and the scheme classifier at once. Forbidding them removes that whole
class of error and halves the assignment problem.

*Consequence.* Handle the third cluster: referees, sideline players, and coaches inside the
frame. Reject detections whose position falls outside the field bounds by more than ~2 yd,
and whose colour matches neither cluster tightly.

*Measured in M0: the colour half of this is safe, the reject half is harder than assumed.*
Torso separation is ΔE = 36.6 in CIELAB (L\* 31.8 dark vs 66.6 light), with the clusters
barely touching at the 5th/95th percentiles — colour will not be the failure mode. But two
reject cases are worse than this doc implies: **referees wear black-and-grey vertical stripes
and stand on the field**, landing squarely in the Wind Chill cluster in most live frames; and
**Wind Chill have a light-blue alternate kit** worn on the sideline, which lands in the *Sol*
cluster. So the out-of-bounds filter is doing more work than the colour gate. Build and
measure it first. See `docs/00-footage-report.md` Q5.

## AD-4 — Register to known world geometry, not to a neighbouring frame

> **Amended 2026-09-12, after M0 and its review.** The decision's *reason* is unchanged and is
> the important part: **never chain frame-to-frame, because the error accumulates monotonically
> and nothing signals it.** Two measurements changed the preferred means.
>
> **(a) Registration must run on a mask, never the whole frame.** The rendered score bug and
> sponsor banner occupy 12.6 % of this broadcast's frame, move 0 px, and dominate phase
> correlation (peak 0.973 and 0.867, against 0.054 for the playing surface). Whole-frame
> registration reported **a static camera on 10 of 11 frame pairs** while the camera was
> actually panning 38–360 px. The mask excludes the rendered graphics, everything above the
> horizon (the stands are off the ground plane, so their motion is parallax, not camera
> motion), and — once M2 exists — the players. Derive the horizon from the calibration rather
> than hard-coding a row, and find the graphic regions by low temporal variance plus high
> texture rather than fixed boxes. `tools/regcheck.py` reproduces the failure.
>
> **(b) The per-frame camera fit is now primary and the mosaic is the fallback.** Peak
> response on the *masked* playing surface is only 0.008–0.468: mown turf is close to
> featureless, and its stripes give an aperture problem along their own direction. A mosaic
> built by dense correspondence over that is marginal. But the camera is a fixed broadcast
> hard camera — it pans, tilts and zooms, and does not translate — so each frame is **three
> unknowns (pan, tilt, focal), not eight**, solvable directly against world geometry that is
> exactly specified: the soccer centre circle (radius 9.15 m), the halfway line, and the
> penalty area when in shot. Fitting every frame independently to known world geometry
> accumulates no drift at all, which is what AD-4 was protecting. `docs/03-data-contracts.md`
> already anticipates storing pan/tilt/focal per frame, and `docs/08-risks.md` already listed
> this as a mitigation. Keep the mosaic for stretches where too little paint is visible.

The original decision, which still governs where the amendment is silent:

Split the clip at camera cuts. Within a shot, build a background mosaic (players masked
out), register every frame to that mosaic, and register the mosaic **once** to field
coordinates using human-clicked correspondences.

*Why.* Chaining frame-to-frame homographies accumulates drift monotonically; after twenty
seconds of panning the radar is visibly wrong and there is no signal saying so. Registering
every frame to a single reference makes the error bounded rather than accumulating, and it
reduces the human's job from "click points on many keyframes" to "click points once per
shot". A possession typically contains one to three shots.

*Consequence.* Zoom range within a shot can be large; the mosaic must be built at the widest
zoom available in that shot, and matching should use a scale-robust matcher. Use LoFTR
(Apache-2.0) or LightGlue with **DISK or ALIKED** features — *not* SuperPoint, whose weights
are non-commercial research-only.

### The world geometry available at this venue

Even with no gridiron paint, a UFA field on a soccer pitch is a well-conditioned target.
Exact positions, from the rulebook (§2.2.1, §2.3.1, §2.3.2) and the FIFA laws:

- **Seven centreline marks**, at X = 10 (reverse brick), 20 (goal-line centre), 40 (brick),
  60 (midfield), 80 (brick), 100 (goal-line centre), 110 (reverse brick), all at Y = 26.667.
- **Ten pylons** — the four endzone back corners, the four goal-line ends, and the centre of
  each back line.
- **Soccer centre circle**, radius 9.15 m = 10.006 yd, and the **halfway line** through its
  centre perpendicular to the touchlines. These are the two features visible in the most
  frames, and the circle is a conic, so it constrains five degrees of freedom by itself.
- **Penalty area** (16.5 m deep, 40.32 m wide), **goal area** (5.5 m, 18.32 m), **penalty
  spot** (11 m) and **penalty arc** (9.15 m) when the camera is near an end.

*Measured in M0, and it changes the shape of this problem.* A possession contains **typically
one shot, not one to three**: every live-play frame sampled sat inside a shot of 36–174 s
(median 96 s), and none was shorter than a possession. The human cost of AD-4 is therefore
one set of clicks per possession. But the zoom warning above is now the live risk rather than
a theoretical one — at t ≈ 7326 s the camera whips from a wide field shot to a tight catch
and back *within a single detected shot*, which no cut detector will flag and which will
break naive frame-to-frame registration. Build the mosaic at the widest zoom and verify
against that case. See `docs/00-footage-report.md` Q7.

*Also measured in M0:* this venue has **no football yard lines or hash marks** — it is a
soccer pitch. The richest available geometry is the soccer centre circle and halfway line,
which are visible in far more frames than the ultimate paint is. The plan that follows is to
calibrate to the *soccer* frame, whose dimensions are exactly specified, and apply one fixed
venue transform into the ultimate frame, established once. See `docs/00-footage-report.md` Q2.

## AD-5 — Evidence states, not confidence scores

Every position sample carries a discrete provenance state (`observed`, `provisional`,
`interpolated`, `predicted`, `unknown`, `confirmed`) plus a positional sigma in yards. See
`docs/05-uncertainty.md` for the full state machine.

> **`provisional` added 2026-09-14.** A sixth state, for a match that re-acquires a slot
> after a long gap. It is an observation of *somebody*; whether it is the same somebody is
> the open question. It renders like an observation and counts for coverage, and it is
> excluded from every metric until a human confirms or swaps it. The reason it needs its own
> state rather than a flag is AD-5's own argument: a small set of named states can be
> rendered distinctly and reasoned about in `if` statements, and "we saw a person here, we
> are not sure it is this person" is a distinct thing to say.

*Why.* A float confidence is uninterpretable to a coach and easy for the code to ignore. A
small set of named states can be rendered distinctly, reasoned about in `if` statements, and
explained in one sentence in the UI. It also lets derived metrics refuse to answer: a
separation number computed from a `predicted` receiver is not a measurement and must not be
displayed as one.

## AD-6 — Corrections are an append-only layer over immutable output

`tracks.json` is never edited. Human edits land in `corrections.json` as anchors (a
position, pinned at a frame) and identity operations (swap two slots from frame N onward).
`ur/resolve.py` produces the corrected track by re-fitting the estimate between the
surrounding observations with anchors as hard constraints.

*Why.* Reversibility and auditability — a coach who cannot undo will not correct at all. And
the correction log is the highest-value training data this project can produce: every anchor
is a human-verified field position on real broadcast footage, and there is no public dataset
of those for ultimate.

## AD-7 — Events are tagged by hand; disc detection is a stretch goal

A small tagging pass: scrub, press `t` on a throw, `c` on a catch. Roughly 20 keystrokes per
possession. Heuristics may *suggest* events (the thrower is the near-stationary player with a
defender inside 2 yd while others cut) but the human confirms.

*Why.* Throw and catch timestamps unlock the metrics that matter and cost a minute of
attention. A disc detector good enough to replace them is a research project with a poor
success probability at this resolution.

## AD-8 — The possession is the unit of work

Ingest cuts one possession. Every artefact, metric, share link and comparison is scoped to
it. Nothing in the pipeline needs whole-game state.

*Why.* It bounds every algorithm to about 20 seconds and 300 frames — cheap to run, cheap to
re-run after a correction, cheap to reason about. It also matches how film study actually
happens.

## AD-9 — No server, ever

The viewer is static HTML/CSS/JS reading `possession.json`. Sharing is a folder, a zip, or a
push to GitHub Pages.

*Why.* "Free" has to include not paying for hosting, and a coach should be able to open the
thing in five years without a service being alive.

---

## Stage notes

**ingest.** `yt-dlp` for the source, `ffmpeg` to cut `[start,end]` and emit frames at 15 fps
(tracking rate) plus the clip at native rate for the viewer. Record the source timestamp of
frame 0 in `clip.json` so any moment maps back to the original broadcast.

**detect.** Start from COCO-pretrained **D-FINE** or **RT-DETRv2** (both Apache-2.0). Then
bootstrap a fine-tune: run the COCO detector, have a human fix boxes on ~300 frames sampled
across the game, retrain. Expect this to be the single largest accuracy win available.

*On tiling.* This doc used to require **SAHI** (MIT) tiled inference on the grounds that "a
downfield player is 25–45 px tall". **M0 measured 50–70 px at the widest live framing and
80–130 px in a typical wide play shot**, with ~50 px the smallest on-field player seen
anywhere. The reason is structural: the broadcast camera never frames the whole field, so
players never recede far enough to get small — which is the same fact as the partial
visibility in AD-5, seen from the other side. So **run whole-frame first and measure against
the M2 gate; add SAHI only if recall asks for it.** See `docs/00-footage-report.md` Q3.

**project.** The foot point is the bottom-centre of the box, which is wrong when the player
is occluded at the ankles or is airborne. Prefer the pose-free heuristic first (bottom-centre,
with a fixed downward offset when the box aspect ratio is unusually short); add RTMPose
(Apache-2.0) ankle keypoints only if M4 measurements show foot-point error dominating.

**track.** Constant-velocity Kalman in yards. Association: Hungarian on Mahalanobis distance,
gated by team (AD-3) and by a max-speed constraint. Slot-locked (AD-2). Emit an evidence state
per slot per frame.

**identify.** Crop the jersey region, run **PaddleOCR** or **PARSeq** (both Apache-2.0), and
vote **per tracklet, not per frame** — this is what the SoccerNet jersey-number challenge
winners do, and it turns 40–60 % frame accuracy into 80–90 % track accuracy. Where voting is
ambiguous, leave the slot numbered `?` and let the human assign it once.

**derive.** Computes the readouts in `docs/06-viewer.md`, each carrying the weakest evidence
state of its inputs. A metric whose inputs include an `unknown` position is emitted with
`confidence: "inferred"` and the viewer dims it.
