# ultimate-radar

Turn one possession of broadcast Ultimate Frisbee footage into two synchronized views — an
overlay on the video and an overhead field view — that let a coach see how a defence
organises, moves and breaks, and correct the system when it is wrong.

## See it

| | |
|---|---|
| **[p0001 — midfield possession](https://bmccall17.github.io/ultimate-radar/)** | 24 s, 4th quarter. 88 % tracker recall, 13 of 14 players in shot at the open. |
| **[p0003 — endzone possession](https://bmccall17.github.io/ultimate-radar/p0003/)** | 37 s, 1st quarter, ending in a goal. Harder: only 53 % of frames clear the calibration confidence floor, and the viewer says so. |
| **The synthetic fixture** | Invented throughout. Built so the hard cases are visible on demand — players leaving the camera, estimates drifting, a planted identity swap, and the correction flow that repairs it. Not published: it is a development target, and offering it beside real footage invites the two being read as the same kind of thing. Open `viewer/index.html` with no working directory to see it. |

Scrub the timeline and watch the coverage number. Every readout carries a chip saying whether
it was **measured**, **partial** or **inferred**, and an inferred one names what it could not
see. That is the point of the project rather than a disclaimer on it.

**About the footage.** The two real pages carry 24 and 37 second excerpts of a publicly posted
UFA broadcast — Austin Sol vs Minnesota Wind Chill, 27 August 2026 — used here to demonstrate
video analysis. Source and provenance are in `docs/10-getting-the-footage.md`. This project is
not affiliated with or endorsed by the UFA or either club, and the footage is theirs, not mine.
Everything else — code, documents, tracking output, the fixture — is MIT, see `LICENSE`.

Two commitments shape the whole design, and everything else follows from them:

- **Never pretend to know.** A single broadcast camera sees roughly 10 of 14 players at a
  time, and the ones it misses skew toward the deep defenders who decide whether a huck is on.
  So the overhead view draws the camera's real field of view, anything outside it is explicitly
  inferred, and a tactical readout refuses to present itself as measured when its inputs were
  not observed.
- **Always be fixable.** Same-team identity swaps are what every appearance model does to
  players in identical jerseys. The system detects its own, repairs them in one click, and
  keeps corrections in an append-only layer that never touches the raw output.

Licence: MIT, see `LICENSE`. Model and dependency licences are audited per component in
`docs/07-licenses.md` — **no AGPL**, which rules out Ultralytics YOLO and `boxmot`.

---

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
- **This is personal film study.** Do not redistribute the video or the extracted frames.

## Try it in ten seconds

Open **`viewer/index.html`** in a browser. No server, no build step, no install. With no
working directory present it renders the committed synthetic fixture and says so at the top;
with one, it renders the real possession.

## Start here

| Read | For |
|---|---|
| `HANDOFF.md` | **Resuming work. Current state (M0–M6 built), the three results that are not clean, and what to do next. Read this first.** |
| `docs/09-decision-record.md` | One page: the commitments, the decisions, the state |
| `docs/00-footage-report.md` | **What the real footage actually looks like, measured. It corrected several figures in the docs below; its foot lists every change.** |
| `docs/01-brief.md` | What success means, and what this is not |
| `docs/02-architecture.md` | The pipeline diagram and the stage notes |
| [`docs/adr/`](docs/adr/) | The ten decisions, AD-1 to AD-10, one file each |
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
| `docs/15-m4-review.md` | The mid-M4 review, including the gate that had to be re-specified |
| `docs/16-m4-watching.md` | What twenty-four seconds of watching the tracker found that no statistic had |
| `docs/17-m4-tracking.md` | M4: all five gates measured, and the three motion models it took to get there |
| `docs/18-m5-identity-events-corrections.md` | M5: the detector that fires zero times and the one that works; the jersey gate that fails |
| `docs/19-m6-viewer.md` | M6: the viewer, the horizon bug, and the two criteria a person has to close |

## What already exists

*M0–M6 are built. M0–M4 are gated and pass, with one threshold left deliberately unset. M5
passes three of four criteria — the jersey gate fails at 3 of 7 against a gate of 5. M6's page
is built and works; its `file://` criterion and its comprehension test both need a human and
are unrun. `HANDOFF.md` is the cold-start document and carries all of that in one place.*

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
  sigma, and an explicit in/out-of-bounds decision. Recall **0.9873**. Its `sigma_yd` is built
  on a *measured* 5.83 px of foot error, not M2's assumed 3.
- **`ur/team.py`** — M3. Fits the two kits per possession by deterministic 2-means on torso
  L\*, then rejects referees on stripe periodicity and camera crew on position *and*
  appearance. Team accuracy **0.9957**; false positives **1.15 → 0.30 per frame** with zero
  real players lost, which closes the gate M2 had to defer.
- **`ur/track/`** — M4. A Kalman filter in field yards (AD-1), 14 slots never created or
  destroyed (AD-2), per-team gated Hungarian association (AD-3), and the `docs/05` evidence
  state machine. Writes `tracks.json`. Its motion model is an integrated Ornstein-Uhlenbeck
  velocity whose one free constant is **measured** by `tools/m4_speed.py` rather than chosen.
  Per-player recall **0.8846**; position error **0.3698 yd** median; sigma containment **80 %**.
- **`ur/possess.py`** — M4. Reshapes `tracks.json` into the columnar `possession.json` the
  viewer reads. **Never mutates `tracks.json`** (AD-6), and carries the measured gates in the
  file so nothing downstream can quote a position without the recall beside it.
- **`ur/issues.py`** — M5. The "needs a human" queue. Four detectors, one of which fires zero
  times on real data and is kept in the code with the reason, because it is the more
  instructive of the two: a detector built on *implausibility* is blind to exactly the errors
  a tracker makes. The one that works asks whether the choice was **ambiguous**.
- **`ur/resolve.py`** — M5. Replays an append-only `corrections.json` over a fresh read of the
  immutable tracks. Anchor, swap, confirm, revert. Reverting everything reproduces the
  uncorrected output byte for byte, and that is a checked acceptance criterion.
- **`ur/identify/`** — M5. Jersey OCR and per-tracklet voting that **emits `null` freely**
  rather than guessing. 7 of 14 slots named, 7 honestly null. The gate wants 5 correct on a
  team and the best is 3; `docs/18` says why and what would fix it.
- **`ur/events.py`** — M5. A place to put a human's knowledge. `suggest` emits only
  `possession_start`, and deliberately does not infer throws from player motion: a throw is an
  event about the disc, and nothing here has seen the disc (AD-7).
- **`viewer/index.html`** — M6. One file, no build step, no framework, no dependency. Camera
  overlay and overhead radar as two renderings of one geometry, six readouts each with an
  evidence chip, the roster, the issue queue, and drag-to-correct that hands back a
  `corrections.json` the pipeline reads unmodified.

**Possessions on disk** (all gitignored; regenerate per `HANDOFF.md`)

- `work/p0001/` — the working possession. 24.0 s, 360 frames, one camera shot. `clip.json` +
  `calibration.json` + `detections.json` + `tracks.json` + `possession.json` + `issues.json` +
  `identities.json` + `events.json`.
- `work/p0002/` — the pull before p0001, cut as calibration reconnaissance.
- `work/p0003/` — endzone-framed, 26.0 s. Cut to settle the 120-vs-110 yd question and to be
  M7's second possession. **Its calibration is deliberately near-useless** (confidence ≥ 0.5
  on 1 % of frames) because the honesty guards correctly refuse to fit a shot with no
  exactly-specified geometry in view. That is the intended behaviour, not a regression.

**Evidence and labels** — `eval/m0/` … `eval/m5/`, all committed. Includes the acceptance JSON
for each gate, the verification videos, and the hand-label sets
(`eval/m0/visibility_counts.json`, `eval/m2/labels.json`, `eval/m3/team_labels.json`,
`eval/m3/foot_labels.json`, `eval/m4/foot_labels_fresh.json`, `eval/m4/jersey_labels.json`),
which are the most expensive artefacts here and the hardest to regenerate.

**Measurement tools** — `tools/`: seeded still extraction, paint detection, whole-game
scene-change scan, contact sheets, gridded crops, plus two checks worth knowing about.
`tools/regcheck.py` demonstrates why registration must run on a mask; `tools/pancheck.py`
cross-checks the calibration's camera motion against an independent measurement that shares
no code with it.

**For the viewer** — `viewer/index.html` is the product. `viewer/prototype.html` is the design
reference `docs/06-viewer.md` was written from and is kept for comparison.
`fixtures/possession_demo.json` is a synthetic 7v7 possession in the real schema, with a camera
that sees ~10 of 14 players, ghosts that drift, and a deliberate identity swap;
`tools/make_demo_possession.py` generates it and is the easiest way to learn the schema by
example. See `viewer/README.md`.

## Layout

```
ultimate-radar/
  docs/            specs and per-milestone results
  fixtures/        synthetic + hand-labelled ground truth
  eval/            committed evidence for every gate
  tools/           measurement scripts and label harnesses
  ur/              the package
    ingest.py      video -> frames + clip metadata                        [built]
    calibrate/     world model, camera, mask, paint, fit, venue, verify   [built]
    detect/        detector wrapper + bounds and size filters             [built]
    team.py        kit-colour team assignment, plus the referee test      [built]
    track/         field-space Kalman + slot-locked association           [built]
    possess.py     tracks.json -> possession.json                         [built]
    issues.py      the "needs a human" queue                              [built]
    resolve.py     applies corrections.json over tracks.json              [built]
    identify/      jersey OCR, tracklet voting                            [built]
    events.py      human event tagging                                    [built]
    derive.py      tactical metrics with provenance propagation           [in the viewer]
  viewer/          static page, no build step, no framework
  work/            per-possession working dirs (gitignored)
```

`derive.py` does not exist as a module: the six readouts are computed in the viewer, because
they change with every correction and a precomputed file would be stale the moment a coach
dragged a marker. If M7 needs them exported, that is the time to lift them out.

## Running

Run everything through the venv: `.\.venv\Scripts\python.exe -m <module>`.

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
python -m ur.track.run        work/p0001        # -> tracks.json
python -m ur.possess          work/p0001        # -> possession.json
python -m tools.m4_render     work/p0001        # the tracker video — watch it before measuring
python -m tools.m4_recall     work/p0001        # the re-specified observed gate
python -m tools.m4_structure  work/p0001        # slot structure + position + sigma gates
python -m ur.issues           work/p0001        # -> issues.json
python -m ur.identify.vote    work/p0001        # -> identities.json  (~4 min, GPU)
python -m tools.m5_identity   work/p0001        # the jersey gate
python -m tools.m5_resolve    work/p0001        # the anchor + revert gates
python -m ur.events           work/p0001 suggest    # -> events.json
python -m ur.resolve          work/p0001        # applies corrections.json, if any
python -m tools.make_view     work/p0001        # -> viewer/live-data.js
```

Then open `viewer/index.html` directly. If you would rather serve it, use a server that
supports range requests — Python's `http.server` does not, and the video will not seek.
