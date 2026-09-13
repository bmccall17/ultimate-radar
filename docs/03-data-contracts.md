# 03 — Data contracts

Every stage reads and writes files in a possession working directory. Stages communicate
only through these files, so any stage can be re-run alone.

```
work/p0001/
  clip.json            ingest    what was cut, and where it came from
  frames/000000.jpg    ingest    15 fps, the tracking rate
  clip.mp4             ingest    native rate, for the viewer
  calibration.json     calibrate per-frame homography + confidence
  detections.json      detect    boxes per frame, with team
  tracks.json          track     14 slots, immutable
  identities.json      identify  slot -> jersey number, with evidence
  events.json          human     throws, catches, turns, goal
  corrections.json     human     append-only edits
  possession.json      derive    the single file the viewer reads
```

Units everywhere: **yards**, **seconds**, and frame indices at the tracking rate.

Field frame: origin at the **back corner of the defending endzone on the near sideline** —
the corner where `X = 0` (the back line the offence is attacking away from) meets `Y = 0`
(the sideline nearest the camera). `X` runs 0→120 along the field in the direction of attack;
`Y` runs 0→53.333 across, increasing toward the far sideline, the side away from the camera.
Because `X` is defined by the direction of attack, `attacking_direction` in `clip.json` is
`+x` by construction; it exists to record which way that is in *image* space.

> **Open question (M1), logged in `docs/08-risks.md`.** This frame is possession-relative, so
> the same physical shot maps to two different field frames in two possessions attacking
> opposite ways — which makes `calibration.json`'s homography possession-scoped rather than
> venue-scoped. The likely fix is to store a venue-fixed field frame in `calibration.json`
> and move the flip into `derive`. Not changed yet.

---

## clip.json

```json
{
  "schema": "ultimate-radar/clip@1",
  "possession_id": "p0001",
  "source": {"platform":"youtube","id":"IDnoyd4cKfM","file":"sol-vs-windchill-2026-semi.mp4",
             "start_s":7264.023433,"end_s":7288.014066,"requested_start_s":7264.0,
             "video_fps":59.94005994,"video_w":1920,"video_h":1080,"video_codec":"h264",
             "video_duration_s":8546.801,
             "start_verification":{"ok":true,"measured_t":7264.023433,
                                   "intended_t":7264.00675,"off_by_s":0.016683,
                                   "best_mad":3.904,"runner_up_mad":5.938,"margin":2.034},
             "clip_frames_sync":{"model_holds":true,
                                 "frames_to_clip_frame":"ceil((n + 0.5) * src_fps / track_fps) - 1",
                                 "max_error_vs_uniform_s":0.028695}},
  "fps": 15, "frames": 360, "duration_s": 24.007317,
  "teams": {"sol":{"name":"Austin Sol","kit":"light"},
            "chill":{"name":"Minnesota Wind Chill","kit":"dark"}},
  "offense": "sol", "defense": "chill", "attacking_direction": "+x",
  "field": {"length_yd":120,"width_yd":53.333,"endzone_yd":20,"brick_yd":20,"spec":"UFA 2026"},
  "provenance": {"seed":20260827,"tools":{"ffmpeg":"...","ffprobe":"..."},
                 "ffmpeg_cut":"...","clip_sha256":"...",
                 "frame_count_expected":360,"frame_count_drift":0}
}
```

**`frames` and `duration_s` are measured, not computed.** `frames` is the number of files
actually in `frames/`; `duration_s` is ffprobe's duration of the cut clip. Ingest asserts
`|frames − round(duration_s × fps)| ≤ 1` and warns loudly otherwise, because a mismatch means
the clip boundaries are wrong and everything downstream inherits it. (An earlier version of
this example said 21.0 s × 15 fps = 316 frames, which is 315.)

**`source.start_s` is what makes any moment in the viewer traceable back to the broadcast —
never lose it, and never take it on trust.** It is the **measured** source timestamp of
`frames/000000.jpg`, not the value passed to ffmpeg: ffmpeg's input seek keeps frames strictly
after the seek timestamp, so asking for a frame's exact pts silently drops that frame. Ingest
extracts the neighbouring source frames, picks the one that matches clip frame 0 by mean
absolute grey-level difference, and records the winner plus its margin in
`start_verification`. `requested_start_s` keeps what was asked for.

**`clip_frames_sync` exists because `clip.mp4` and `frames/` do not index the same instants.**
The viewer plays `clip.mp4` and draws an overlay indexed by `frames/`; ffmpeg's `fps` filter
resamples 59.94 → 15 by keeping the *last* input frame in each output slot, so `frames/n` is
up to one source frame behind a uniform `n/fps` clock. The exact relation is recorded and
asserted against real pixels at two points in every clip. Treat `n/fps` as correct to within
`max_error_vs_uniform_s` (~29 ms here), or use the formula when that is not good enough.

## calibration.json

```json
{
  "schema": "ultimate-radar/calibration@1",
  "shots": [{"from":0,"to":188},{"from":189,"to":315}],
  "anchors": [{"shot":0,"frame":12,
               "correspondences":[{"image":[412,688],"field":[20.0,0.0],"label":"goal line x near sideline"}]}],
  "frames": [{"f":0,"H":[[..3..],[..3..],[..3..]],"residual_yd":0.41,"confidence":0.93,"shot":0}]
}
```

- `H` maps **image pixel → field yard** as a 3×3 homography on homogeneous coordinates.
- `residual_yd` is the mean reprojection error of the shot's correspondences, evaluated on
  this frame after propagation through the mosaic. It is the honest quality signal.
- `confidence` ∈ [0,1] derives from the residual and feeds the tracker's measurement noise
  (AD-1). Frames below 0.5 must not produce `observed` samples.

If the camera is fixed in position (it is, on this broadcast) you may additionally store
pan/tilt/focal per frame; it makes smoothing better-behaved than smoothing H directly.
The fixture stores exactly that form — see `camera.per_frame` in `fixtures/`.

## detections.json

```json
{"schema":"ultimate-radar/detections@1",
 "frames":[{"f":0,"dets":[
    {"box":[1201,540,1248,648],"score":0.91,"team":"chill","team_score":0.97,
     "foot":[1224.5,648],"field":[63.2,27.4],"tile":3}]}]}
```

`field` is present only when the frame's calibration confidence allowed it. Keep `box` — the
correction dataset needs image space.

## tracks.json — immutable

```json
{"schema":"ultimate-radar/tracks@1",
 "slots":[{"slot":"D6","team":"chill",
   "samples":[{"f":0,"xy":[71.0,24.6],"state":"observed","sigma":0.3,"det":12},
              {"f":1,"xy":[71.2,24.5],"state":"predicted","sigma":0.9,"det":null}]}]}
```

Exactly 14 slots, each with a sample for **every** frame — no gaps, because a gap is a
decision the viewer would have to re-make. `det` indexes back into `detections.json`.

Nothing downstream may write to this file. See AD-6.

## identities.json

```json
{"schema":"ultimate-radar/identities@1",
 "slots":[{"slot":"D6","jersey":5,"method":"ocr_vote","support":37,"frames_legible":41,
           "confidence":0.86,"alternatives":[{"jersey":6,"support":4}]},
          {"slot":"O7","jersey":null,"method":"none","confidence":0.0}]}
```

`jersey: null` is a valid, expected outcome. The viewer shows `?` and offers a one-time
manual assignment.

## events.json

```json
{"schema":"ultimate-radar/events@1",
 "events":[{"t":0.0,"type":"possession_start","player":"O1"},
           {"t":4.2,"type":"throw","player":"O1","target":"O4","source":"human"},
           {"t":5.0,"type":"catch","player":"O4","source":"human"},
           {"t":20.3,"type":"goal","player":"O6"}]}
```

Types: `possession_start`, `throw`, `catch`, `drop`, `block`, `turnover`, `stall`, `goal`.
`source` is `human` or `suggested`; a `suggested` event is shown differently until confirmed.

## corrections.json — append-only

```json
{"schema":"ultimate-radar/corrections@1",
 "corrections":[
   {"id":"c1","at":"2026-09-13T10:04:00Z","op":"anchor","slot":"D6","f":156,
    "xy":[82.5,26.0],"note":"visible at the top of frame just before the pan"},
   {"id":"c2","at":"2026-09-13T10:05:12Z","op":"swap","slots":["D5","D7"],"from_f":156},
   {"id":"c3","at":"2026-09-13T10:06:00Z","op":"confirm","slot":"O6","f":210},
   {"id":"c4","at":"2026-09-13T10:07:30Z","op":"revert","target":"c2"}]}
```

Order matters; `resolve.py` replays them in sequence. `revert` neutralises an earlier
correction rather than deleting it, so the log stays a true history.

## possession.json — what the viewer reads

One self-contained file: `clip.json` fields, plus resolved per-slot arrays, plus events, plus
derived metrics. The synthetic fixture `fixtures/possession_demo.json` is a valid instance
(with an extra `truth` array the real pipeline will not have, used only to render a
stand-in camera view). Its shape:

```json
{"schema":"ultimate-radar/possession@0.2",
 "possession":{...}, "field":{...}, "teams":{...},
 "camera":{"image_w":1280,"image_h":720,"position_yd":[58,-21,13],
           "per_frame":[{"aim":[48.5,24.1],"focal_px":1180.4}]},
 "disc":[[x,y,height_yd]],
 "events":[...],
 "players":[{"id":"D6","team":"chill","slot":"D6","jersey":5,"role":"defender",
             "est":[[x,y]], "state":["observed"], "sigma":[0.3]}],
 "derived":{"coverage":[10], "assignment":[{"D6":"O6"}], "metrics":{...}}}
```

Parallel arrays indexed by frame, not per-frame objects: at 300+ frames × 14 players the
object form triples the file size for no benefit, and the viewer wants columnar access.

For real footage the viewer plays `clip.mp4` behind an overlay canvas instead of rendering a
camera view; the projection math is identical, sourced from `calibration.json` rather than
the synthetic `camera` block.
