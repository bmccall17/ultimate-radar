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
| `HANDOFF.md` | **Resuming work. Current state (end of M2), how to rebuild the environment, what M3 should do first. Read this first.** |
| `docs/09-decision-record.md` | One page: the commitments, the decisions, the state |
| `docs/00-footage-report.md` | **What the real footage actually looks like, measured. It corrected several figures in the docs below; its foot lists every change.** |
| `docs/01-brief.md` | What success means, and what this is not |
| `docs/02-architecture.md` | The pipeline and the nine decisions that shape it |
| `docs/03-data-contracts.md` | Every file the stages exchange |
| `docs/04-milestones.md` | **The build order, with acceptance tests. Work from this.** |
| `docs/05-uncertainty.md` | Evidence states and the correction model — the heart of the product |
| `docs/06-viewer.md` | Viewer spec, derived from a working prototype |
| `docs/07-licenses.md` | Licence register. Check before `pip install`. |
| `docs/08-risks.md` | What might not work, and what has not been verified |
| `docs/10-getting-the-footage.md` | Downloading the game and cutting a possession |

## What already exists

*Updated after M2, 2026-09-13. Milestone write-ups: `docs/12-m1-calibration.md`, `docs/13-m2-detection.md`.*

- **`ur/ingest.py` and `ur/ffprobe.py`** — M0's deliverable. Cuts a possession, emits 15 fps
  frames plus the native clip, writes `clip.json`. Deterministic (verified byte-identical
  across runs).
- **`work/p0001/`** — one possession cut and verified: broadcast 7264.023–7288.014 s, 24.0 s,
  360 frames. Gitignored; regenerate with the command in `HANDOFF.md`.
- **`docs/00-footage-report.md`** — all eight M0 questions answered from real frames, with the
  evidence in `eval/m0/`. Read it before M1: it changes the calibration plan (the venue is a
  soccer pitch, not a gridiron), the detection plan (players are ~2× the assumed size) and the
  shot model (one shot per possession, not three).
- **`tools/`** — the M0 measurement kit: seeded still extraction, paint detection, scene-change
  scan, contact sheets, gridded crops. `tools/paint.py` and `tools/crop.py` are worth reusing
  in M1; `tools/measure.py` is an M0-only blob finder, not a detector.
- `fixtures/possession_demo.json` — a synthetic 7v7 possession in the real schema,
  including a camera that only sees ~10 of 14 players at a time, ghosts that drift,
  and a deliberate identity swap. Build and test the viewer against this before any
  real tracking exists.
- `tools/make_demo_possession.py` — generates the above. Read it to understand the
  schema by example.
- `viewer/prototype.html` — a working viewer built on that fixture (open it directly, no
  server). It is the design target for milestone M6, not production code — reimplement it
  properly, keep its behaviour. See `viewer/README.md`.

## Layout the pipeline should grow into

```
ultimate-radar/
  docs/            specs (this handoff)
  schemas/         JSON Schema for every contract
  fixtures/        synthetic + hand-labelled ground truth
  tools/           one-off scripts
  ur/              the package
    ingest.py      video -> frames + clip metadata
    calibrate/     shot detection, mosaic, correspondence tool, homography
    detect/        detector wrapper + SAHI tiling + finetune loop
    team.py        jersey-colour team assignment
    track/         field-space Kalman + slot-locked association
    identify/      jersey OCR, tracklet voting
    events.py      human event tagging + heuristics
    derive.py      tactical metrics with provenance propagation
    resolve.py     applies corrections.json over tracks.json
  viewer/          static web app (no build step, no framework required)
  work/            per-possession working dirs (gitignored)
```

## Running, once M0–M5 exist

```bash
python -m ur.ingest      --url <youtube-url> --start 25:10 --end 25:31 --out work/p0001
python -m ur.calibrate   work/p0001            # opens the correspondence tool
python -m ur.detect      work/p0001
python -m ur.track       work/p0001
python -m ur.identify    work/p0001
python -m ur.derive      work/p0001            # -> work/p0001/possession.json
python -m http.server -d viewer 8080           # then open ?p=../work/p0001/possession.json
```
