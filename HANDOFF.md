# Handoff — end of M2, 2026-09-13

Pick this up cold. Read this, then the milestone write-ups it points at, then
`docs/04-milestones.md` § M3. The spec in `docs/` still governs; where a milestone changed
it, the change is recorded in that milestone's own document and in the commit message.

Working directory: `E:\dev\playertrackerultimate\ultimate-radar`
Git: five commits, clean tree, `29d2421` at HEAD.

---

## 1. Where the project is

| | Milestone | Status |
|---|---|---|
| **M0** | Ingest + footage report | **Done**, independently reviewed (`docs/11-m0-review.md`) |
| **M1** | Calibration | **Done**, acceptance passed (`docs/12-m1-calibration.md`) |
| **M2** | Detection | **Recall passed; the false-positive gate is deferred to M3** (`docs/13-m2-detection.md`) |
| **M3** | Team assignment + projection | **Next** |
| M4 | Tracking | Not started |
| M5 | Identity, events, corrections | Not started |
| M6 | Viewer | Not started; the design-pass prototype is in `viewer/` |
| M7 | Sharing + a second possession | `p0003` is already cut for it |

Numbers that stand:

- **M1** — mean reprojection error **0.0996 yd** (gate 0.75), max **0.4096 yd** (gate 1.5),
  on 34 held-out correspondences. Per-frame residual median **0.149 yd**, p95 0.190, max
  0.249. Confidence ≥ 0.5 on **93.9 %** of frames. Poses reproduce identically across runs.
- **M2** — recall **0.9873** (gate 0.95) on 236 players in 20 held-out frames. False
  positives **1.35 / frame** (gate 1.0, **fail** — see below).

## 2. The three things carried forward

**1. M2's false-positive gate is open, and M3 is where it closes.** About a third of the
false positives are **referees, who stand on the field** — no geometric bounds test can
reject someone who is inside the field. AD-3 already specifies the reject as position *and*
appearance; the appearance half is the luminance-**variance** test (stripes have high torso
variance, a flat kit does not). Build it in M3 and re-measure the FP rate then. **Do not let
M4 build a tracker on detections that still contain a referee a third of the time.**

**2. The field is still 120 yd by assumption** (`docs/08-risks.md` #5). p0001 cannot settle
it — the camera never looks far enough down the field to see a goal line, and the pooled
paint map's x marginal is one spike at the halfway line with noise either side. p0002 (the
pull) is no better. **p0003 is framed on an endzone** — an ultimate corner with a pylon on it
and two field lines are plainly visible — but the soccer centre circle is not, so the current
calibrator has nothing exactly-specified to fit there. Settling it needs soccer penalty-area
geometry (penalty area, goal area, penalty spot, arc — all exact in Law 1) added to
`ur/calibrate/world.py`, plus the **fixed camera centre as a bridge** between the two frames:
calibrate p0003 in a goal-line-anchored frame, and the offset between its camera centre and
p0001's gives the pitch half-length. That bridge doubles as the check that it is the same
camera.

*What it does and does not block:* only **absolute** distance along the field — deep cover,
the deep-deterrent boolean. Relative geometry — matchups, separation at release, person vs
zone — is unaffected, so M3 and M4 are not blocked.

**3. The along-pitch half of the venue transform is unmeasured**, same root cause. The
across-pitch half *is* measured, and was corrected during M2 (see §4).

## 3. Environment

Unchanged from M0 apart from the M1/M2 additions. Python **3.11.16** in `.venv` (uv-managed).

```powershell
$env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
uv venv --python 3.11 .venv
uv pip install --python .venv\Scripts\python.exe -r requirements-m0.txt
uv pip install --python .venv\Scripts\python.exe torch torchvision --index-url https://download.pytorch.org/whl/cu128
uv pip install --python .venv\Scripts\python.exe -r requirements-m2.txt
```

torch **2.11.0+cu128** sees the RTX 4070 Ti SUPER. Detector runs ~30 fps batched. ffmpeg
9.0.1 gyan **full** build (GPL — exec'd as a separate process, never linked, never vendored).
Seed **20260827** everywhere. Licence register: `docs/07-licenses.md`; code *and* weights are
checked separately, and **no Ultralytics anywhere**.

## 4. What exists, and the decisions embedded in it

```
ur/ingest.py            M0. Cuts a possession; source.start_s is measured, not assumed.
ur/ffprobe.py           ffmpeg/ffprobe wrappers.
ur/calibrate/           M1. world, camera, mask, paint, features, fit, run, venue,
                        render, verify, accept.
ur/detect/              M2. model (D-FINE + suppression), run, overlay.
tools/                  survey, sheet, crop, measure, paint, cuts, fpscheck, heights,
                        jerseysheet, teamcolour, regcheck, pancheck, m2_label.
```

Four decisions worth not re-litigating:

- **AD-4 amended** (agreed before M1 started, recorded in `docs/02-architecture.md`): the
  per-frame **3-DOF camera fit is primary**, the mosaic is the fallback. A free homography
  needs 8 DOF; this footage offers 7 constraints (a conic and a line). The camera does not
  translate, so 3 unknowns per frame against a shared centre makes 7 constraints redundant
  rather than one short. Solved centre: **C = (0.47, −50.21, 6.98) yd**.
- **Registration runs on a mask, never a raw frame.** Whole-frame phase correlation reports a
  static camera on 10 of 11 pairs of this footage. `tools/regcheck.py` reproduces it.
- **Evidence states:** until M4 exists there is no motion model, so a stage that loses a
  detection emits **`unknown`**, never `predicted` or `interpolated`. Noted in
  `docs/05-uncertainty.md`.
- **The venue transform's y offset was corrected by M2's own output.** M1 had picked the near
  sideline as the paint peak nearest a *centred* field (−25.95, far at +27.38). Confident
  player-shaped detections taper out at +17, then there is an empty gap, then a stationary
  cluster of 202 detections at +24..+26 — camera crew. The far sideline must be in that gap,
  so the near sideline is the other peak, **−32.75**, far at **+20.58**. The calibration
  could not distinguish two readings of its own paint; the detector could. Expect more of
  this.

## 5. On disk

```
raw/           5.6 GB   GITIGNORED   the broadcast (format 299+140, 1080p60 avc1)
work/p0001/    24.0 s, 360 frames    clip.json, calibration.json, detections.json
work/p0002/    18.0 s, 270 frames    the pull; clip.json, calibration.json
work/p0003/    26.0 s, 390 frames    endzone-framed; clip.json, calibration.json
survey/                 GITIGNORED   161 stills
eval/m0/ m1/ m2/        COMMITTED    all evidence, hand labels, acceptance JSON, videos
```

`p0001` is the working possession: broadcast 7264.023–7288.014 s, 4th quarter,
ATX 20 – MIN 25, Sol on offence, Wind Chill defending, one camera shot, no cut.
**p0003's calibration is deliberately near-useless** — confidence ≥ 0.5 on 1 % of frames —
because the honesty guards correctly refuse to fit it. That is the intended behaviour, not a
regression.

Hand labels, which are the most expensive thing here and the hardest to regenerate:
`eval/m0/visibility_counts.json`, `eval/m2/labels.json`.

## 6. Where M3 starts

Per `docs/04-milestones.md` § M3, plus what M2 learned:

1. **Team assignment by torso colour.** M0 measured ΔE 36.6 between the kits — colour is not
   the hard part. Build the **referee variance test alongside it**, not after; that is what
   closes M2's FP gate.
2. **Foot-point error on 50 hand-checked detections**, before trusting projection. Detection
   already emits `yd_per_px` and a `sigma_yd` built on an *assumed* 3 px of foot error — M3
   replaces that assumption with a measurement.
3. **Then `possession.json` and the viewer.** Association for now is the crudest possible
   stand-in — greedy nearest-neighbour in field space, team-gated, max-speed-gated — and it
   must be **labelled as a stand-in in the code and in the output**. 14 slots, every frame,
   `observed` when matched and `unknown` when not. Nothing else.
4. The viewer swaps its synthetic camera for `<video>` plus an overlay canvas driven by
   `calibration.json`. Mind `clip_frames_sync` in `clip.json`: `frames/n` is up to one source
   frame behind a uniform `n/15` clock, and a silent one-frame offset puts the overlay on the
   wrong moment with nothing to signal it.

## 7. Habits this project has earned

Four bugs across M1 and M2 shared one shape: **something reported success while being wrong**,
and only a check that could contradict it caught the problem.

- A chamfer objective sampled its distance field with integer indices, so the optimiser saw
  zero gradient, stopped at its seed, and reported success.
- An acceptance test called two well-calibrated frames 10 and 34 yards wrong because its own
  RANSAC had fitted a needle-thin ellipse along the halfway line. *A test that fails for its
  own reasons is worse than no test.*
- A calibration reported `rms 0.0000 yd` at confidence 0.55 on a collapsed fit. Residuals far
  below what painted lines physically allow are now rejected, as are fits to too short an arc.
- "Longest straight line = halfway line" was wrong, quietly, because the longest line in a
  wide shot is the *ultimate* sideline.

So: prefer a check that can contradict the thing it is checking. `tools/pancheck.py` is the
model — it compares the calibration's pan against masked phase correlation on grass texture,
sharing no code and no inputs (correlation 0.946, scale 0.939).
