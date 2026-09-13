# Handoff — end of M3, 2026-09-13

Pick this up cold. Read this, then the milestone write-ups it points at, then
`docs/04-milestones.md` § M4. The spec in `docs/` still governs; where a milestone changed
it, the change is recorded in that milestone's own document and in the commit message.

Working directory: `E:\dev\playertrackerultimate\ultimate-radar`
Git: clean tree, `M3` complete.

---

## 1. Where the project is

| | Milestone | Status |
|---|---|---|
| **M0** | Ingest + footage report | **Done**, independently reviewed (`docs/11-m0-review.md`) |
| **M1** | Calibration | **Done**, acceptance passed (`docs/12-m1-calibration.md`) |
| **M2** | Detection | **Done.** Recall passed here; its false-positive gate passed in M3 (`docs/13-m2-detection.md`) |
| **M3** | Team assignment + projection | **Done**, both gates passed (`docs/14-m3.md`) |
| **M4** | Tracking | **Next. The hard one.** |
| M5 | Identity, events, corrections | Not started |
| M6 | Viewer | Not started; `viewer/prototype.html` is the design target, `viewer/live.html` is M3's working page |
| M7 | Sharing + a second possession | `p0003` is already cut for it |

Numbers that stand:

- **M1** — mean reprojection error **0.0996 yd** (gate 0.75), max **0.4096 yd** (gate 1.5),
  on 34 held-out correspondences over 20 frames. Confidence ≥ 0.5 on **93.9 %** of frames.
- **M2** — recall **0.9873** (gate 0.95) on 236 players in 20 held-out frames.
- **M3** — team accuracy **0.9957** (gate 0.99). Foot-point error **0.4345 yd** median
  (gate 0.6). False positives **1.15 → 0.30 per frame** (gate 1.0), zero real players lost.
- The whole pipeline re-runs byte-identical.

## 2. The four things carried forward

**1. Referees still leak, and M4 is where that closes.** The stripe test is
high-precision, moderate-recall: 5 of 8 referees rejected, **0 of 234 players**. The other
three survive as Wind Chill players and carry `weak_team` with a low `team_score`. It is
visible in `eval/m3/p0001_teams.mp4` — frame 60 reports 8 Wind Chill in a seven-a-side
point, and detection #4 there is a referee. **M4 must vote team over a tracklet and must
not treat a `weak_team` detection as a confirmed player.** A referee whose stripes fail one
frame's pose is still a referee across a track. 8.7 % of kept detections sit in the
neither-kit band; that is the upper bound on the leak.

**2. The sigma M4 inherits is measured now, and it was badly wrong before.** M2's assumed
3 px of foot error is really **5.83 px rms**, and the assumed value put only **46 %** of
truths inside the disc the viewer draws, against the ≥ 80 % `docs/05-uncertainty.md`
requires. Corrected to 94 %. M4's sigma-calibration gate is the same question asked of
tracked positions; do not re-derive the constant, and do not assume the old one.

**3. The field is still 120 yd by assumption** (`docs/08-risks.md` #5). Unchanged from M2.
p0001 cannot settle it — the camera never looks far enough down the field to see a goal
line. **p0003 is framed on an endzone** but has no soccer centre circle, so the calibrator
has nothing exactly-specified to fit there. Settling it needs soccer penalty-area geometry
added to `ur/calibrate/world.py` plus the **fixed camera centre as a bridge** between the
two frames. *It bounds only absolute distance along the field* — deep cover, the
deep-deterrent boolean. Matchups, separation at release and person-vs-zone are unaffected,
so M4 is not blocked.

**4. `ur/standin.py` is not a tracker and M4 replaces it outright.** Greedy
nearest-neighbour, no motion model, no re-identification. **467 slot claims fell outside
its own speed gate and took a free slot anyway** — those are identity shuffles, and they
are counted in `possession.json`. Do not build on it; read it once to see what the contract
looks like filled in, then delete the dependency.

## 3. Environment

Unchanged since M2. Python **3.11.16** in `.venv` (uv-managed). M3 added no dependencies.

```powershell
$env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
uv venv --python 3.11 .venv
uv pip install --python .venv\Scripts\python.exe -r requirements-m0.txt
uv pip install --python .venv\Scripts\python.exe torch torchvision --index-url https://download.pytorch.org/whl/cu128
uv pip install --python .venv\Scripts\python.exe -r requirements-m2.txt
```

torch **2.11.0+cu128** sees the RTX 4070 Ti SUPER. Detector runs ~30 fps batched. ffmpeg
9.0.1 gyan **full** build (GPL — exec'd as a separate process, never linked, never
vendored). Seed **20260827** everywhere. Licence register: `docs/07-licenses.md`; code
*and* weights are checked separately, and **no Ultralytics anywhere**.

## 4. What exists, and the decisions embedded in it

```
ur/ingest.py            M0. Cuts a possession; source.start_s is measured, not assumed.
ur/ffprobe.py           ffmpeg/ffprobe wrappers.
ur/calibrate/           M1. world, camera, mask, paint, features, fit, run, venue,
                        render, verify, accept.
ur/detect/              M2. model (D-FINE + suppression), run, overlay.
ur/team.py              M3. Kit fit, the stripe test, the crew reject.
ur/standin.py           M3. The greedy stand-in. M4 deletes this.
viewer/live.html        M3. Video + overlay + radar. Not the M6 viewer.
tools/                  survey, sheet, crop, measure, paint, cuts, fpscheck, heights,
                        jerseysheet, teamcolour, regcheck, pancheck, m2_label,
                        m3_label, m3_foot, m3_render, make_view.
```

Six decisions worth not re-litigating:

- **AD-4 amended** (recorded in `docs/02-architecture.md`): the per-frame **3-DOF camera
  fit is primary**, the mosaic is the fallback. Solved centre: **C = (0.47, −50.21, 6.98)
  yd** in the soccer frame.
- **Registration runs on a mask, never a raw frame.** Whole-frame phase correlation reports
  a static camera on 10 of 11 pairs of this footage. `tools/regcheck.py` reproduces it.
- **Evidence states:** until M4 exists there is no motion model, so a stage that loses a
  detection emits **`unknown`**, never `predicted` or `interpolated`. In `ur/standin.py` an
  `unknown` sample carries `xy: null` — a sample in every frame, as the contract requires,
  but no number.
- **The venue transform's y offset was corrected by M2's own output**, from −25.95 to
  −32.75. M3 found that this had been applied by hand-editing `calibration.json`, leaving
  `H` computed from the superseded offset and leaving `ur.calibrate.run` able to revert the
  correction silently on any re-run. Now `venue.BREESE_STEVENS_NEAR_SIDELINE_Y`, with
  `--near-sideline` to override.
- **The referee test is periodicity, not variance.** See §2.1 and `docs/14-m3.md`.
- **The kits are fitted per possession, not hard-coded** — deterministic 2-means on torso
  L\*, and the fit refuses to report two teams when the separation is below 20 L\*.

## 5. On disk

```
raw/           5.6 GB   GITIGNORED   the broadcast (format 299+140, 1080p60 avc1)
work/p0001/    24.0 s, 360 frames    clip.json, calibration.json, detections.json,
                                     possession.json
work/p0002/    18.0 s, 270 frames    the pull; clip.json, calibration.json
work/p0003/    26.0 s, 390 frames    endzone-framed; clip.json, calibration.json
survey/                 GITIGNORED   161 stills
eval/m0..m3/            COMMITTED    all evidence, hand labels, acceptance JSON, videos
viewer/live-data.js     GITIGNORED   regenerate with tools.make_view
```

`p0001` is the working possession: broadcast 7264.023–7288.014 s, 4th quarter,
ATX 20 – MIN 25, Sol on offence, Wind Chill defending, one camera shot, no cut.
**p0003's calibration is deliberately near-useless** — confidence ≥ 0.5 on 1 % of frames —
because the honesty guards correctly refuse to fit it. That is intended, not a regression.

**p0002 and p0003 still carry the pre-M3 calibration**, written before
`BREESE_STEVENS_NEAR_SIDELINE_Y` existed. Re-run `ur.calibrate.run` on them before using
them for anything.

Hand labels, the most expensive artefacts here and the hardest to regenerate:
`eval/m0/visibility_counts.json`, `eval/m2/labels.json`, `eval/m3/team_labels.json`,
`eval/m3/foot_labels.json`.

## 6. Where M4 starts

Per `docs/04-milestones.md` § M4, plus what M3 learned:

1. **Read AD-1, AD-2, AD-3 and `docs/05-uncertainty.md` first.** The state machine there is
   M4's, and M4 is the first milestone allowed to emit `predicted` and `interpolated`.
2. **Team is a tracklet-level vote, not a per-frame label.** That is what closes the last of
   the referee leak, and `team_score` / `weak_team` are the inputs.
3. **The sigma-calibration gate is the one people skip** — ≥ 80 % of truths inside the drawn
   disc. M3 already failed and fixed exactly that question at the detection level, so the
   machinery to ask it exists; `tools/m3_foot.py` is the model.
4. **Hand-label the possession at 1 Hz** (21 frames × 14 players) before trusting anything.
   That is the M4 gate's ground truth and it does not exist yet.
5. Slot initialisation: the first frame where 7 of a team are visible seeds the slots.
   `ur/standin.py` does a one-player-at-a-time version; the real thing should seed as a
   group and leave never-seen players `unknown`.

## 7. Habits this project has earned

Five bugs across M1–M3 shared one shape: **something reported success while being wrong**,
and only a check that could contradict it caught the problem.

- A chamfer objective sampled its distance field with integer indices, so the optimiser saw
  zero gradient, stopped at its seed, and reported success.
- An acceptance test called two well-calibrated frames 10 and 34 yards wrong because its own
  RANSAC had fitted a needle-thin ellipse along the halfway line. *A test that fails for its
  own reasons is worse than no test.*
- A calibration reported `rms 0.0000 yd` at confidence 0.55 on a collapsed fit.
- "Longest straight line = halfway line" was wrong, quietly, because the longest line in a
  wide shot is the *ultimate* sideline.
- **A sigma disc that contained the truth 46 % of the time**, stated as an assumption in M2
  and believed until M3 measured it. An uncertainty that does not contain the truth is worse
  than no uncertainty, because it looks like a claim.

And one that was cheap only because it was loud: `inv(H)` returns **negative** `w` for
points genuinely in front of the camera on this footage, so the obvious `w > 0` visibility
test drew nothing at all. Had the sign been right and the offset wrong, the overlay would
have drawn confidently in the wrong place.

So: prefer a check that can contradict the thing it is checking. `tools/pancheck.py` is the
model — it compares the calibration's pan against masked phase correlation on grass texture,
sharing no code and no inputs (correlation 0.946). `tools/m3_render.py` is the M3 equivalent:
it is the only thing that exercises the field→image direction, which nothing else uses.
