# 13 — M2, detection

**Status: recall passes, false positives do not — and the reason is structural, not
a threshold that needs tuning.**

| M2 gate | Required | Measured | |
|---|---|---|---|
| Recall on held-out frames | ≥ 0.95 | **0.9873** (233 of 236) | pass |
| False positives per frame, after the out-of-bounds filter | ≤ 1.0 | **1.35** | **fail** |

20 held-out frames, seeded, from those with calibration confidence ≥ 0.5. 236 on-field
players in truth. Labels and the arithmetic are in `eval/m2/labels.json` and
`eval/m2/m2_acceptance.json`; the frames they were read off are `eval/m2/label_*.jpg`.

**No fine-tune was needed to pass recall, so none was done.** `docs/04-milestones.md` M2
plans a bootstrap — COCO weights over ~300 frames, a human fixes boxes, retrain. Off-the-shelf
COCO weights reach 0.987 recall on this footage, so that hour of labelling has nothing to buy
yet. It is still the right move if the remaining misses start to matter; see below for what
they are.

**No SAHI either.** M0 measured players at 50–130 px rather than the 25–45 px the
architecture assumed, and whole-frame inference finds them. Tiling stays unused and
uninstalled.

---

## What the false positives actually are

Every one is a real person. None is a hallucination, and none is a duplicate box any more.
Two classes, and only one of them is fixable by geometry:

**Referees — about a third of them — stand on the field.** No bounds test can reject a
person who is inside the field, because they *are* inside the field. This is exactly what
AD-3 anticipates: it specifies the reject as position **and** appearance, not position
alone, and the M0 review pointed at the mechanism — referee stripes give a torso high
luminance *variance*, a flat kit gives low, and that works precisely where the geometric
filter does not. **That test belongs to M3 and is not built yet.**

**Camera crew near the far boards — the rest.** Photographers and operators sitting or
standing just beyond the far touchline. Most are now rejected; the survivors are the ones
standing upright close enough to the line that both the position and the size test pass.

So the gate as written — "≤ 1 false positive per frame after the out-of-bounds filter" —
assumes the out-of-bounds filter can do the whole job. On this footage it cannot, and the
missing half of AD-3's reject is a later milestone. **Recommendation: re-measure the false
positive rate at the end of M3, once appearance is available, rather than tuning a
geometric threshold now to hit a number it cannot honestly hit.**

## What the misses are, all three of them

Every miss in 20 frames was **two overlapping players sharing one box**. Frame 327 was
checked at source resolution: a Sol thrower and the Wind Chill defender marking them, and at
*no* score threshold did the detector emit a separate box for the defender. It is a
detection failure, not a suppression one.

That is also the answer to the question the gate exists to ask — is a whole class of player
being missed? No. Not the small distant ones, not the far-side ones, not one kit or the
other. Only players who overlap another player in the image, which is the case a fine-tune on
this footage would most plausibly improve.

## Three filters, and why each exists

Each was added because something concrete went wrong, and each is visible in
`eval/m2/p0001_detections.mp4` — kept boxes green, rejected red with the reason.

**1. NMS plus containment suppression.** DETR-family detectors are described as NMS-free,
and at a high score threshold they are. At 0.25 on this footage a single player came back
four times — the whole body, the torso, and two part-boxes, all sharing a top edge — giving
**0.86 duplicate pairs per frame**, most of the false-positive budget spent on one person.
Plain IoU NMS does not catch a torso box inside a body box, because their IoU can be ~0.5
while they are plainly the same person; so a box is also suppressed when 80 % of *it* lies
inside a better-scoring one. Duplicates fell to **0.075 per frame**.

**2. A size-consistency test.** The bounds test alone waved every far-side camera operator
through, because a foot point at the advertising boards back-projects to y = 21–29 yd and
lands inside the field. But those people are further away than that position implies, so
their boxes are far too short for it. Comparing the observed box height against the height a
standing person at that spot would subtend separates them cleanly: real players cluster at
**0.95–1.10**, crouching crew at 0.49.

That clustering is worth noting for its own sake. The ratio is an absolute-scale prediction —
it depends on the camera height, the focal length and the ground-plane geometry all being
right at once — and it comes out at 1.00 across thousands of detections. It is independent
evidence that M1's calibration is correct in scale, not just self-consistent.

**3. A per-detection sigma.** Every positioned detection carries `yd_per_px`, the local
ground-plane scale, and `sigma_yd` = that times an assumed 3 px of foot-point error. It grows
with distance the way the real uncertainty does, and it is what M3 and M4 inherit rather than
a constant. M3 measures the foot-point term properly.

## The venue transform was wrong, and detection is what caught it

M1 chose between two candidate near-side paint peaks — soccer y = −32.75 and −25.95 — by
taking the one nearest where a field centred across the pitch would put its sideline. That
picked −25.95 and put the far sideline at +27.38.

Detection showed it was the wrong pick. Plotting where confident, player-shaped detections
actually go: they run from −18 and **taper out at +17**, then there is an empty gap, then a
**stationary cluster of 202 detections at +24 to +26** — camera crew, in the same spot frame
after frame. The far sideline has to lie in that gap. Taking −32.75 as the near sideline puts
it at **+20.58**, inside the gap; −25.95 would put the crew on the field of play.

So the transform is now `y_offset = 32.75`, chosen on that evidence and recorded with it in
`calibration.json`. The along-pitch offset is still the centred assumption — that is open
question 5 and it is unchanged.

The general point is worth keeping: **the calibration could not distinguish two
interpretations of its own paint, and the detector could**, because players are a
measurement the calibration does not have access to. Expect more of this. It is also a
reminder that M1's residual was never wrong here — the camera model was right and the
*labelling* of which line was which was not, and a residual cannot see that.

## Reproducing

```bash
python -m ur.detect.run work/p0001                 # writes detections.json
python -m ur.detect.overlay work/p0001             # the video
python -m tools.m2_label render work/p0001 -n 20   # frames to label
python -m tools.m2_label score work/p0001          # the gate
```

Detector: `ustc-community/dfine-medium-coco`, Apache-2.0 code and Apache-2.0 weights, both
checked separately (`docs/07-licenses.md`). Whole-frame, person class only, score threshold
0.25, seeded and run with cuDNN deterministic — the same frame gives the same boxes, twice
verified. 6801 detections over 360 frames, 4201 kept as on-field players (11.7 per frame).
Inference runs at about 30 fps batched on the RTX 4070 Ti SUPER.

## Honest limits

- **The labels are the agent's own, not an independent human's.** Recall is measured against
  one judgement of what counts as an on-field player, and per-frame counts carry about ±1 on
  crowded frames. The systematic conclusion — that the only misses are overlapping pairs —
  does not rest on that precision, but the headline number does, to a degree.
- These 20 frames are all from one possession, one camera, one lighting condition. Nothing
  here says the detector generalises to the tight shots that make up a sixth of the
  broadcast, where M0 measured players at up to 460 px and only 1–5 in frame.
- The false-positive gate is deferred to M3 rather than met. That is a real gap in the M2
  acceptance, not a technicality, and it should be closed before M4 builds a tracker on top
  of detections that still contain a referee about a third of the time.
