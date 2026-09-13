# 04 — Build plan

Work in order. Each milestone has an acceptance test that must pass before the next starts.
Estimates assume one competent engineer with a consumer NVIDIA GPU; they are for sequencing,
not for promising.

A note on order: **M6 (the viewer) can be built at any time**, because
`fixtures/possession_demo.json` is a valid `possession.json`. If you want early feedback
from the person this is for, build M6 second and let them react to the prototype while the
pipeline catches up.

---

## M0 — Ingest, and check the assumptions against real frames ·  half a day

Nobody has yet looked at a single real frame of this broadcast at pixel level. Everything
downstream depends on things M0 measures.

Build `ur/ingest.py`: `yt-dlp` the source, `ffmpeg` a clip, emit 15 fps frames plus the
native clip, write `clip.json`.

Then produce `docs/00-footage-report.md` answering, with numbers and example crops:

1. Native resolution and framerate; whether 60 fps is real or interpolated.
2. **Does the venue carry football yard lines and hash marks?** Breese Stevens Field is a
   stadium pitch; if the ultimate lines are painted over football markings, calibration gets
   dramatically easier. This single question changes the M1 plan.
3. Player height in pixels at the near sideline, mid-field, and the far endzone. Take the
   minimum seriously — it sets whether tiled inference is optional or mandatory.
4. Jersey number legibility: at what distance do digits become unreadable? Sample 20 crops.
5. Team colour separability: sample torso crops from both teams plus referees and sideline,
   and show that a 2-cluster split is clean (AD-3 depends on this).
6. How much of the field is in frame? Sample 30 random frames, and estimate what fraction of
   14 players are visible. The fixture assumes ~10/14; confirm or correct that number.
7. How often does the camera cut? Count cuts per minute — it sets how much M1 human work a
   possession costs.
8. Pick the possession for round one. Want: a clear defensive structure, at least one
   scheme change or poach, 15–30 s, and ideally a camera cut so M1 handles the multi-shot
   case from the start. Record start/end timestamps.

**Accept when:** the report exists with real crops, and `clip.json` + frames for the chosen
possession are on disk.

> If YouTube egress is blocked on the build machine, download once by hand and point
> `ingest` at a local file. Do not build around the block.

**Done, 2026-09-12.** `docs/00-footage-report.md`; `work/p0001/` (24.0 s, 360 frames,
deterministic). All eight questions answered with measurements. The three findings that move
other milestones: **no gridiron markings** (it is a soccer pitch — changes M1), **players are
50–130 px, not 25–45** (changes M2), **a possession contains one shot, not three** (makes M1
cheaper). Criterion 8's "at least one scheme change or poach" is the one thing not confirmed —
the report says so rather than claiming it.

## M1 — Calibration ·  two to three days

`ur/calibrate/`:

- Shot boundary detection (histogram / feature-match discontinuity is sufficient).
- A correspondence tool: show a frame beside a field diagram, click matching points, store
  them. Keyboard-driven, ugly is fine.
- Per shot: mask players (use M2's detector once it exists; a crude motion mask first),
  build a background mosaic, register every frame to it, compose with the mosaic→field
  homography.
- Per frame: emit `H`, `residual_yd`, `confidence`. Smooth pan/tilt/focal, not `H` directly.
- A verification render: project the field lines back onto the video. This is the only
  honest way to see whether calibration is working, and you will use it constantly.

**Accept when:** on 10 held-out frames spread across the possession, clicked field points
reproject with **mean error < 0.75 yd and max < 1.5 yd**; the line-overlay render sits on the
painted lines through a full pan; and a cut is handled without manual intervention beyond
one set of clicks per shot.

*Added after the M0 review:*

- **Also accept only when whole-frame and masked registration have been compared on at least
  ten frame pairs, and the masked result recovers pans the whole-frame result misses.** Ten
  minutes of work. Without it, the failure in `docs/08-risks.md` open question 10 reaches M4
  disguised as a tracking problem. `tools/regcheck.py` is the check.
- **Report two error budgets, not one.** On a soccer-marked pitch the points that can be
  located precisely are *soccer* points, whose geometry is exact. Ultimate-frame error is that
  plus the error in the one venue transform tying the soccer frame to the ultimate frame. A
  single blended number hides which half is bad.

## M2 — Detection ·  two days

`ur/detect/`: D-FINE or RT-DETRv2 (Apache-2.0). Person class only.

*Revised by M0.* SAHI tiling was specified as required on the assumption that downfield
players are 25–45 px. Measured, they are **50–70 px at the widest live framing and 80–130 px
in a typical wide play shot**, because the camera never frames the whole field. **Run
whole-frame first, measure against the gate below, and add SAHI only if recall asks for it.**

Bootstrap the fine-tune: run COCO weights over ~300 frames sampled across the whole game,
have a human fix boxes (an hour of work), retrain, re-measure.

**Accept when:** on 20 hand-labelled held-out frames (~280 boxes), **recall ≥ 0.95 at
IoU 0.5 for players inside the field bounds**, with ≤ 1 false positive per frame after the
out-of-bounds filter. Recall matters far more than precision here — a missed deep defender
is the error that costs the product its point.

## M3 — Team assignment and projection ·  one day

`ur/team.py` and `ur/project.py`. Torso-crop colour, 2-means per point, with a reject class
for referees/sideline. Foot point → field coordinates via `calibration.json`.

**Accept when:** team accuracy **≥ 99 %** on the M2 label set (it should be near-perfect
given light vs dark kit — if it is not, stop and find out why before building the tracker on
top of it), and foot-point field error **< 0.6 yd** on 50 hand-checked detections.

**Done, 2026-09-13.** `docs/14-m3.md`. Team accuracy **0.9957** (233/234); foot-point error
**0.4345 yd** median. **M2's deferred false-positive gate closes here: 1.15 → 0.30 per frame
with zero real players lost.** Three things moved other milestones:

- The referee test is **not** the luminance *variance* the M0 review predicted — a numbered
  dark jersey and a two-player box both have high torso variance. Stripes are separable
  because they are *periodic and vertically coherent*. It is high-precision, moderate-recall:
  5 of 8 referees, 0 of 234 players. **The rest survive as dark-kit players carrying
  `weak_team`, and M4 must vote team over a tracklet rather than trust a frame.**
- `sigma_yd` was measured and found to be **46 % honest** — M2's assumed 3 px of foot error
  is really 5.83 px rms. docs/05 wants ≥ 80 % of truths inside the drawn disc. Corrected to
  94 %. M4 inherits the corrected number.
- `H` in calibration.json had been left behind by M2's venue correction, and
  `ur.calibrate.run` would have silently reverted that correction on re-run. Both fixed in
  code.

## M4 — Tracking ·  three to four days.  The hard one.

`ur/track/`: field-space Kalman, team-gated Hungarian association, 14 locked slots, evidence
states, and the retrospective `interpolated` pass. Read AD-1, AD-2, AD-3 and
`docs/05-uncertainty.md` first.

Slot initialisation: the first frame where 7 of a team are visible seeds the slots; players
never yet seen start `unknown` and get picked up on first observation. Do not guess opening
positions — that is what the cold-start issue in M5 is for.

**Accept when, on the round-one possession hand-labelled at 1 Hz (21 frames × 14 players):**

| Metric | Gate |
|---|---|
| Identity switches over the possession | ≤ 2, and every one detected by the M5 swap detector |
| Field position error, `observed` samples | median < 0.8 yd, p95 < 1.8 yd |
| `observed` fraction | within 5 points of the visible fraction measured in M0 **for this possession** — hand-counted at **≈ 88 % (11/14/12 at frames 0/180/345)**, not the broadcast-wide 74 % |
| Phantom or missing slots | zero, always |
| Sigma calibration | ≥ 80 % of truths fall inside the drawn sigma disc |

That last row is the one people skip. A sigma that does not contain the truth is worse than
no sigma, because the viewer's entire honesty argument rests on it.

## M5 — Identity, events, corrections ·  two days

- `ur/identify/`: PaddleOCR or PARSeq on jersey crops, voting **per tracklet**. Emit `null`
  freely rather than guessing.
- `ur/events.py`: keyboard tagging pass + suggested events.
- `ur/resolve.py`: anchors and swaps applied per `docs/05-uncertainty.md`. The three issue
  detectors.

**Accept when:** the swap detector finds the injected swap in `fixtures/possession_demo.json`
at the right frame and the right pair; `resolve.py` applied to an anchor produces a path
continuous at both ends; `revert` restores byte-identical output; and jersey numbers are
correct for **≥ 5 of 7** players on at least one team, with the rest honestly `null`.

## M6 — Viewer ·  three days ·  buildable now

Static page reading `possession.json`. Spec in `docs/06-viewer.md`. The published prototype
is the behavioural reference — match what it does, write better code than it has.

For real footage, swap the synthetic camera render for `<video>` plus an overlay canvas
driven by `calibration.json`. The projection math does not change.

**Accept when:** it runs from `file://` with no build step; it renders the fixture correctly;
and it passes the comprehension test in `docs/01-brief.md` with a real person.

## M7 — Sharing and a second possession ·  one day

Export a possession as a self-contained folder (page + JSON + clip) that opens anywhere.
Deep-link to a timestamp. Then run a **second, different possession** end to end — a zone
look if the first was person. The second possession is what tells you whether you built a
pipeline or a one-off.

---

## Evaluation, standing

Keep `eval/` with the hand labels and a `make eval` that prints the M2/M3/M4 table. Re-run
it after any model or parameter change. Numbers that are not re-measured are not numbers.

The comprehension test from `docs/01-brief.md` is the real gate and should be run with a
different person each time, since nobody is naive twice.
