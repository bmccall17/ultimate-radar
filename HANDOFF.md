# Handoff — M0 to M6 built, 2026-09-13

Pick this up cold. Read this, then `docs/04-milestones.md`, then AD-1, AD-2, AD-3 and
`docs/05-uncertainty.md`. The spec in `docs/` still governs; where a milestone changed it, the
change is recorded in that milestone's own document and in the commit message.

Working directory: `E:\dev\playertrackerultimate\ultimate-radar`

> **Two results are short of their gate, and both are recorded rather than hidden.** M5's
> jersey gate wants 5 of 7 on a team and got 3. M6's `file://` criterion and its comprehension
> test are unrun, because neither can be run by the thing that built the page. Everything else
> in M0–M6 is measured and passes. §2 is the list; §4 is what to do next.
>
> **Nothing here needs a paid service, a network call at runtime, or an AGPL/GPL/NC
> dependency.** The licence register is `docs/07-licenses.md` and the gate applies before you
> install anything.

---

## 1. Where the project is

| | Milestone | Status |
|---|---|---|
| **M0** | Ingest + footage report | **Done**, independently reviewed (`docs/11-m0-review.md`) |
| **M1** | Calibration | **Done**, acceptance passed (`docs/12-m1-calibration.md`) |
| **M2** | Detection | **Done.** Recall passed here; its false-positive gate passed in M3 (`docs/13-m2-detection.md`) |
| **M3** | Team assignment + projection | **Done**, both gates passed (`docs/14-m3.md`) |
| **M4** | Tracking | **All five gates measured** (`docs/17-m4-tracking.md`). Four pass. The identity gate's second clause failed in M4 and was **closed by M5** — 0 of 2 switches caught became 2 of 2 |
| **M5** | Identity, events, corrections | **Three of four criteria pass** (`docs/18-m5-identity-events-corrections.md`). The jersey gate **fails: 3 of 7, gate is 5** |
| **M6** | Viewer | **Built** (`docs/19-m6-viewer.md`). Renders the fixture and the real possession; **`file://` unverified and the comprehension test unrun** |
| M7 | Sharing + a second possession | Not started. `p0003` is already cut for it |

Numbers that stand (measured, gated, committed):

- **M1** — mean reprojection error **0.0996 yd** (gate 0.75), max **0.4096 yd** (gate 1.5).
  Confidence ≥ 0.5 on **93.9 %** of frames.
- **M2** — recall **0.9873** (gate 0.95) on 236 players in 20 held-out frames.
- **M3** — team accuracy **0.9957** (gate 0.99); foot-point error **0.4345 yd** median
  (gate 0.6); false positives **1.15 → 0.30 per frame** (gate 1.0), zero real players lost.
- **M4** — per-player recall **0.8846** at 1.5 yd; position error **0.3698 yd** median
  (gate 0.8), p95 **1.0337** (gate 1.8); sigma containment **80.0 %** (gate 80); zero phantom
  or missing slots across 14 slots × 360 frames.
- **M5** — swap detector finds the injected swap at the right frame and pair with no false
  positives; an anchor's joins move **0.0669 yd** (allowed 0.0992); reverting every correction
  reproduces the uncorrected output **byte for byte**.
- **M6** — full redraw with every layer on, **10.6 ms** against a 66 ms budget; the viewer's
  exported `corrections.json` round-trips through `ur.resolve` unmodified.
- The M0–M6 pipeline re-runs byte-identical.

## 2. The three results that are not clean

Read these before quoting anything.

**M5's jersey gate fails, and it fails on the footage rather than on the plumbing.** EasyOCR
reads about **7 %** of crops over the whole possession, and **18.8 %** of the 48 crops a human
had already found legible. Voting over a tracklet recovers a lot of that — 7 of 14 slots get a
number, 7 are honestly `null` — but the best team is Sol at 3 correct against a gate of 5. Two
details shape what to do about it: the vote never contradicted a stable hand reading (its one
disagreement is on the slot M4 measured switching between two people), and O1 had the right
answer and emitted `null` because the margin to a misread was too thin. **The policy is
working; the reader is not good enough.** `docs/18` lists the three ways forward in order of
likely effect. There is also no roster to score against — the truth is a modal jersey from 48
hand readings, which is thin.

**M4's per-player recall is 0.8846 with the threshold deliberately unset.** The review
predicted ≥ 0.90 before the measurement. The largest single lever to reach it is readmitting the
14 `weak_team` misses, and those are the detections that keep referees out of player slots.
That is a product decision, not a tuning decision, and `docs/04` § "The `observed` fraction gate
was retired" lays out the trade. **Whoever sets the threshold should decide it explicitly.** Do
not change the tracker to hit the number.

**M4's sigma gate passes marginally.** 32 of 40 is exactly 80.0 %; the Wilson 95 % interval on
n = 40 runs 65.2 % to 89.5 %. A bigger sample is the only way to call it.

## 3. What M6 shipped, in one page

`viewer/index.html` — one file, 1100 lines, no build step, no framework, no dependency. It
loads `data.js` (the committed synthetic fixture) and then `live-data.js` (the real possession,
gitignored, written by `tools/make_view.py`); the second overrides the first, so a fresh clone
renders the fixture and a working copy renders the real thing from the same page.

The projection sits behind one interface with two backends — the fixture's simulated pinhole
and the real homography — so everything above it is written once. Two traps are documented in
`docs/19`: the negative `w` from `inv(H)` (third time this project has had to solve it) and a
new one, the **horizon**, where sampling the image's top edge to build the camera frustum hands
the homography points behind the camera and silently scrims the entire overhead view.

Corrections are held in memory, replayed over pristine copies of the tracks, and handed back as
`corrections.json` — a `file://` page cannot write to disk and pretending otherwise loses a
coach's work. A log produced entirely by clicking and dragging was fed straight into
`ur.resolve`, applied cleanly, and reverted byte for byte.

**`ur/standin.py` and `viewer/live.html` are deleted.** Both were M3 scaffolding that M4 and
M6 superseded.

## 4. What to do next, in order

1. **Open `viewer/index.html` by double-clicking it.** One minute. That closes M6's first
   criterion, which could not be verified from the environment that built the page — the
   browser available there renders local files as static snapshots. Everything else was verified
   over `http://localhost`. If you test through a server yourself, use one that supports range
   requests, or the video will not seek and the scrub bar will look broken.
2. **Run the comprehension test (`docs/01-brief.md`) with a real person, on the fixture.**
   Not on p0001, and the reason matters: questions 2 and 4 ask about the disc and about the
   receiver at the last throw. Nothing in this pipeline has seen the disc (AD-7) and no throw on
   p0001 carries a tagged target, so the viewer correctly answers "I cannot tell you" to two of
   five. That would measure the pipeline's known gap, not the viewer. Run it on the fixture,
   which has both; or hand-tag one throw and its receiver in `events.json` first, which is cheap
   and turns Separation at release back on for real footage.
3. **Decide the M4 recall threshold** (§2). It is the only open decision blocking M4 from being
   called finished.
4. **Then either M7, or the jersey gate.** They are independent:
   - **M7** — export a possession as a self-contained folder that opens anywhere, and run a
     **second, different possession** end to end. `p0003` is cut. That second possession is what
     tells you whether this is a pipeline or a one-off, and it is the higher-value of the two.
   - **The jersey gate** — a digit recogniser trained on this project's own crops, which would
     also remove the one unverifiable weights licence in the register (`docs/08`). Or accept
     that at this framing jersey identity is a human's one-per-point assignment, which
     `docs/07` already names as the third source of identity and may simply be right here.

**p0002 and p0003 still carry the pre-M3 calibration**, written before
`BREESE_STEVENS_NEAR_SIDELINE_Y` existed. Re-run `ur.calibrate.run` on them before use.

## 5. Environment

Python **3.11.16** in `.venv` (uv-managed).

```powershell
$env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
uv venv --python 3.11 .venv
uv pip install --python .venv\Scripts\python.exe -r requirements-m0.txt
uv pip install --python .venv\Scripts\python.exe torch torchvision --index-url https://download.pytorch.org/whl/cu128
uv pip install --python .venv\Scripts\python.exe -r requirements-m2.txt
uv pip install --python .venv\Scripts\python.exe -r requirements-m5.txt
```

torch **2.11.0+cu128** sees the RTX 4070 Ti SUPER. ffmpeg 9.0.1 gyan **full** build (GPL —
exec'd as a separate process, never linked, never vendored). Seed **20260827** everywhere.
Licence register: `docs/07-licenses.md`; code *and* weights are checked separately, and **no
Ultralytics anywhere**. M5 added the first non-permissive dependency — `python-bidi`, LGPL-3.0,
pulled in by EasyOCR for right-to-left scripts that nothing here needs. It passes the gate as
LGPL, not as permissive, and a release should say so. **EasyOCR's checkpoints could not be
verified offline** and that gap is logged in `docs/08-risks.md`. M6 added nothing at all.

## 6. What exists

```
ur/ingest.py            M0. Cuts a possession; source.start_s is measured, not assumed.
ur/ffprobe.py           ffmpeg/ffprobe wrappers.
ur/calibrate/           M1. world, camera, mask, paint, features, fit, run, venue,
                        render, verify, accept.
ur/detect/              M2. model (D-FINE + suppression), run, overlay.
ur/team.py              M3. Kit fit, the stripe test, the crew reject.
ur/track/               M4. kalman (the motion model), run (slots, association, states).
ur/possess.py           M4. tracks.json -> possession.json. Never mutates tracks.json.
ur/issues.py            M5. Four detectors for the "needs a human" queue.
ur/resolve.py           M5. Replays corrections.json over immutable tracks. AD-6.
ur/identify/            M5. ocr (crop + read), vote (per-tracklet, emits null freely).
ur/events.py            M5. Hand-tagged events; suggest emits only possession_start.
viewer/index.html       M6. The viewer. One file, no build step.
viewer/prototype.html   The design reference for M6. Kept.
tools/                  survey, sheet, crop, measure, paint, cuts, fpscheck, heights,
                        jerseysheet, teamcolour, regcheck, pancheck, m2_label,
                        m3_label, m3_foot, m3_render, make_view, m4_speed, m4_label,
                        m4_render, m4_structure, m4_recall, m4_foot,
                        m5_resolve, m5_identity.
```

Decisions worth not re-litigating:

- **AD-4 amended** (`docs/02-architecture.md`): the per-frame **3-DOF camera fit is primary**,
  the mosaic is the fallback. Solved centre **C = (0.47, −50.21, 6.98) yd** in the soccer frame.
  `possession.json` now carries it converted to the **ultimate** frame, with the soccer value
  beside it as `position_yd_soccer`, because every other coordinate in that file is
  ultimate-frame yards and a file that mixes frames under one key is a trap.
- **Registration runs on a mask, never a raw frame.** `tools/regcheck.py` reproduces why.
- **The referee test is stripe periodicity, not luminance variance.** The M0 review predicted
  variance; a numbered dark jersey and a two-player box both have high torso variance too.
- **The kits are fitted per possession**, and the fit refuses to report two teams when the
  separation is below 20 L\*.
- **`sigma_yd` is measured** (5.83 px rms), not the 3 px M2 assumed, which put only 46 % of
  truths inside the drawn disc against the ≥ 80 % `docs/05` requires.
- **Sigma is a containment radius, not a per-axis σ.** A disc of radius 1 σ contains 39.3 % of a
  2-D Gaussian, so a per-axis σ can never reach an 80 % gate. `docs/03` carries the definition
  and a table of which producer uses which containment level.
- **The venue transform lives in code**, `venue.BREESE_STEVENS_NEAR_SIDELINE_Y`, after M3 found
  M2's correction had been hand-edited into `calibration.json` and would have been silently
  reverted by any re-run.
- **`SIGMA_V_INF = 2.6 yd/s` is a measured sport constant, not a tuning knob** (`docs/02` § AD-1).
- **A detector built on implausibility is blind to the errors the tracker makes.** M5's first
  identity detector asked how *surprising* a re-acquisition was and fired zero times in 161
  chances; the tracker admits the wrong player precisely because it is plausible. The detector
  that works asks whether the choice was **ambiguous** — how many candidates were in the gate
  and the chi-square margin to the runner-up.
- **`inv(H)` returns negative `w` for points in front of the camera here.** Three places have
  now had to solve this. The sign is derived per frame from a point known to be in front.
- **Overlay drawing must be clipped to the registration mask.** M3's render puts projected field
  lines across the sponsor banner. Cosmetic now; misleading once an overlay element lands on a
  graphic and reads as a detection.

## 7. On disk

```
raw/           5.6 GB   GITIGNORED   the broadcast (format 299+140, 1080p60 avc1)
work/p0001/    24.0 s, 360 frames    clip.json, calibration.json, detections.json,
                                     tracks.json, possession.json, issues.json,
                                     identities.json, events.json
work/p0002/    18.0 s, 270 frames    the pull; clip.json, calibration.json
work/p0003/    26.0 s, 390 frames    endzone-framed; clip.json, calibration.json
survey/                 GITIGNORED   161 stills
eval/m0..m5/            COMMITTED    evidence, hand labels, acceptance JSON, videos
viewer/live-data.js     GITIGNORED   regenerate with tools.make_view
```

Hand labels — the most expensive artefacts here and the hardest to regenerate:
`eval/m0/visibility_counts.json`, `eval/m2/labels.json`, `eval/m3/team_labels.json`,
`eval/m3/foot_labels.json`, `eval/m4/foot_labels_fresh.json`, `eval/m4/jersey_labels.json`.

**This is personal film study.** Do not redistribute the video or the extracted frames.

## 8. Habits this project has earned

Eight bugs across M1–M6 shared one shape: **something reported success while being wrong**, and
only a check that could contradict it caught the problem.

- A chamfer objective sampled its distance field with integer indices, so the optimiser saw zero
  gradient, stopped at its seed, and reported success.
- An acceptance test called two well-calibrated frames 10 and 34 yards wrong because its own
  RANSAC had fitted a needle-thin ellipse along the halfway line. *A test that fails for its own
  reasons is worse than no test.*
- A calibration reported `rms 0.0000 yd` at confidence 0.55 on a collapsed fit.
- "Longest straight line = halfway line" was wrong, quietly, because the longest line in a wide
  shot is the *ultimate* sideline.
- **A sigma disc that contained the truth 46 % of the time**, stated as an assumption in M2 and
  believed until M3 measured it.
- **A process-noise model that made the tracker certain about players it had not seen for two
  seconds.** It presented as an association failure, not a covariance error.
- **A reach gate that compared a bound on player movement against a distance between two
  measured points**, with no allowance for the noise of either. It rejected 70 associations that
  chi-square scored at 4.4 against a threshold of 9.21. Fixing it moved recall 0.8846 → 0.8846.
  The defect was real, the fix is right, and it bought nothing — all three are worth saying.
- **A camera frustum built by sampling above the horizon**, which folded through infinity and
  scrimmed the entire overhead view. The page looked plausible; it was wrong.

And two of my own tests were wrong before the code was: M5's continuity check first measured a
span containing a pre-existing 25 yd snap that swamped anything the correction did, and its
revert check compared against the wrong baseline and failed for that reason.

So: prefer a check that can contradict the thing it is checking. `tools/pancheck.py` compares
the calibration's pan against masked phase correlation sharing no code and no inputs
(correlation 0.946). `tools/m3_render.py` is the only thing that exercises the field→image
direction. `tools/m4_speed.py` measures a constant the tracker would otherwise assume, and
prints zeroes at the baselines where it cannot measure rather than reporting a number. M6's
frustum fix is checked by sampling the rendered canvas under every observed player.
