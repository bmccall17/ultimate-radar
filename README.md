# ultimate-radar

Turn one possession of broadcast Ultimate footage into two synchronized views — an
overlay on the video and an overhead field view — that let a coach see how a defence
organises, moves and breaks, and correct the system when it is wrong.

**Round one target footage:** UFA 2026 semifinal, Austin Sol vs Minnesota Wind Chill,
27 Aug 2026, Breese Stevens Field, Madison WI. `https://www.youtube.com/watch?v=IDnoyd4cKfM`
— 2:22:27, downloaded as **1920×1080 avc1, 59.94 fps** (format `299+140`, 5.95 GB). The AV1
compromise the early docs anticipated is not needed; a 1080p60 H.264 stream is offered.

**Constraints that are not negotiable**

- Free. Open weights, permissive licences, no paid APIs, no cloud inference.
- Runs on one desktop with a consumer NVIDIA GPU (8–12 GB VRAM assumed).
- **No AGPL.** Ultralytics YOLO (all versions) and `boxmot` are AGPL-3.0 and are out.
  See `docs/07-licenses.md` before adding any dependency.
- Offline and serverless. The viewer is a static page reading JSON from disk.

## Start here

| Read | For |
|---|---|
| `HANDOFF.md` | **Resuming work. Current state (M4 in progress), the open decision it is blocked on, and what still has to be measured. Read this first.** |
| `docs/09-decision-record.md` | One page: the commitments, the decisions, the state |
| `docs/00-footage-report.md` | **What the real footage actually looks like, measured. It corrected several figures in the docs below; its foot lists every change.** |
| `docs/01-brief.md` | What success means, and what this is not |
| `docs/02-architecture.md` | The pipeline and the nine decisions that shape it |
| `docs/03-data-contracts.md` | Every file the stages exchange |
| `docs/04-milestones.md` | **The build order, with acceptance tests. Work from this.** |
| `docs/05-uncertainty.md` | Evidence states and the correction model — the heart of the product |
| `docs/06-viewer.md` | Viewer spec, derived from a working prototype |
| `docs/07-licenses.md` | Licence register. Check before `pip install`. |
| `docs/08-risks.md` | What might not work, what has not been verified, and the open questions |
| `docs/10-getting-the-footage.md` | Downloading the game and cutting a possession |
| `docs/11-m0-review.md` | An independent review of M0 — found a real M1 hazard, and a claim that had to be withdrawn |
| `docs/12-m1-calibration.md` | M1: how calibration works here, its numbers, and the five bugs worth keeping |
| `docs/13-m2-detection.md` | M2: detection, why its false-positive gate had to be deferred, and what the misses are |
| `docs/14-m3.md` | M3: team assignment, the referee test that is *not* the one predicted, and a sigma that was 46 % honest |

## What already exists

*M4 in progress, 2026-09-13. M0–M3 are built and gated; the M4 tracker runs but **none of
its gates are measured yet** — the 1 Hz ground truth they need does not exist. `HANDOFF.md`
is the cold-start document; it carries the current numbers, what is still unmeasured, and
the one open decision worth a second opinion.*

**Pipeline**

- **`ur/ingest.py`, `ur/ffprobe.py`** — M0. Cuts a possession, emits 15 fps frames plus the
  native clip, writes `clip.json`. Deterministic, byte-identical across runs. `source.start_s`
  is *measured* against the source frames, not assumed.
- **`ur/calibrate/`** — M1. A fixed camera centre with per-frame pan/tilt/roll/focal, fitted
  to the soccer centre circle and halfway line. Writes `calibration.json` with a residual and
  a confidence per frame. Mean held-out reprojection error **0.0996 yd**.
  `ur.calibrate.verify` renders the line overlay; `ur.calibrate.accept` runs the gate.
- **`ur/detect/`** — M2. D-FINE (Apache-2.0 code *and* weights), person class only, whole
  frame, no fine-tune, no SAHI. Writes `detections.json` with field positions, a per-detection
  sigma, and an explicit in/out-of-bounds decision. Recall **0.9873**. Its `sigma_yd` is now
  built on a *measured* 5.83 px of foot error, not M2's assumed 3.
- **`ur/team.py`** — M3. Fits the two kits per possession by deterministic 2-means on torso
  L\*, then rejects referees on stripe periodicity and camera crew on position *and*
  appearance. Team accuracy **0.9957**; false positives **1.15 → 0.30 per frame** with zero
  real players lost, which closes the gate M2 had to defer.
- **`ur/standin.py`** — M3. A deliberately crude greedy nearest-neighbour stand-in for the
  tracker, so the clip could be watched before M4 exists. Writes `possession.json` with
  `stand_in: true` and a notice saying its slot identities must not be quoted. **M4 deletes
  it** once the tracker's output is wired through to the viewer.
- **`ur/track/`** — M4, *in progress*. A Kalman filter in field yards (AD-1), 14 slots never
  created or destroyed (AD-2), per-team gated Hungarian association (AD-3), and the `docs/05`
  evidence state machine. Writes `tracks.json`. Its motion model is an integrated
  Ornstein-Uhlenbeck velocity whose one free constant is **measured** by `tools/m4_speed.py`
  rather than chosen. **Its gates are not measured yet — do not quote its numbers.**

**Possessions on disk** (all gitignored; regenerate per `HANDOFF.md`)

- `work/p0001/` — the working possession. 24.0 s, 360 frames, one camera shot.
  `clip.json` + `calibration.json` + `detections.json` + `tracks.json` + `possession.json`.
  **`possession.json`, and so the viewer, still carries M3 stand-in data** — the tracker's
  output is not on screen anywhere yet.
- `work/p0002/` — the pull before p0001, cut as calibration reconnaissance.
- `work/p0003/` — endzone-framed, 26.0 s. Cut to settle the 120-vs-110 yd question and to be
  M7's second possession. **Its calibration is deliberately near-useless** (confidence ≥ 0.5
  on 1 % of frames) because the honesty guards correctly refuse to fit a shot with no
  exactly-specified geometry in view. That is the intended behaviour, not a regression.

**Evidence and labels** — `eval/m0/` … `eval/m3/`, all committed. Includes the acceptance
JSON for each gate, the verification videos, and the four hand-label sets
(`eval/m0/visibility_counts.json`, `eval/m2/labels.json`, `eval/m3/team_labels.json`,
`eval/m3/foot_labels.json`), which are the most expensive artefacts here and the hardest to
regenerate.

**Measurement tools** — `tools/`: seeded still extraction, paint detection, whole-game
scene-change scan, contact sheets, gridded crops, plus two checks worth knowing about.
`tools/regcheck.py` demonstrates why registration must run on a mask; `tools/pancheck.py`
cross-checks the calibration's camera motion against an independent measurement that shares
no code with it.

**For the viewer** — `viewer/live.html` plays the real clip with the overlay and radar on
it, driven by `calibration.json`. It opens from `file://` with no build step once
`tools/make_view.py` has written `live-data.js`. It is **not** the M6 viewer;
`docs/06-viewer.md` governs that and the prototype below is its design reference.
`fixtures/possession_demo.json` is a synthetic 7v7
possession in the real schema, with a camera that sees ~10 of 14 players, ghosts that drift,
and a deliberate identity swap; `tools/make_demo_possession.py` generates it and is the
easiest way to learn the schema by example. `viewer/prototype.html` is the M6 design target —
reimplement it properly, keep its behaviour. See `viewer/README.md`.

## Layout the pipeline should grow into

```
ultimate-radar/
  docs/            specs (this handoff)
  schemas/         JSON Schema for every contract
  fixtures/        synthetic + hand-labelled ground truth
  tools/           one-off scripts
  ur/              the package
    ingest.py      video -> frames + clip metadata                        [built]
    calibrate/     world model, camera, mask, paint, fit, venue, verify   [built]
    detect/        detector wrapper + bounds and size filters             [built]
    team.py        kit-colour team assignment, plus the referee test       [built]
    standin.py     greedy stand-in for the tracker; M4 deletes it          [built]
    track/         field-space Kalman + slot-locked association             [in progress]
    identify/      jersey OCR, tracklet voting
    events.py      human event tagging + heuristics
    derive.py      tactical metrics with provenance propagation
    resolve.py     applies corrections.json over tracks.json
  viewer/          static web app (no build step, no framework required)
  work/            per-possession working dirs (gitignored)
```

## Running

What works today, in order. Run everything through the venv:
`.\.venv\Scripts\python.exe -m <module>`.

```bash
python -m ur.ingest --source raw/sol-vs-windchill-2026-semi.mp4 \
    --id p0001 --start 7264.0 --duration 24.0 --offense sol --defense chill
python -m ur.calibrate.run    work/p0001        # -> calibration.json
python -m ur.calibrate.verify work/p0001 --video    # the line-overlay render
python -m ur.calibrate.accept work/p0001        # the M1 gate
python -m ur.detect.run       work/p0001        # -> detections.json
python -m ur.detect.overlay   work/p0001        # boxes burned onto the clip
python -m tools.m2_label      score work/p0001  # the M2 recall gate
python -m ur.team             work/p0001        # fills team / team_score in detections.json
python -m tools.m3_label      score work/p0001  # the team gate, and M2's deferred FP gate
python -m tools.m3_foot       score work/p0001  # the foot-point gate
python -m ur.standin          work/p0001        # -> possession.json  (STAND-IN, not a tracker)
python -m tools.m3_render     work/p0001        # the round-trip video
python -m tools.make_view     work/p0001        # then open viewer/live.html
python -m ur.track.run        work/p0001        # -> tracks.json      (M4, gates unmeasured)
python -m tools.m4_speed      work/p0001        # measures the motion model's velocity spread
```

Not built yet: `ur.identify`, `ur.events`, `ur.resolve`, `ur.derive`, and the M6 viewer. The
design-reference prototype opens standalone:

```bash
python -m http.server -d viewer 8080     # then open prototype.html
```
