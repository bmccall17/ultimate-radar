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
  calibration_truth.json human   where the field paint really is, in image pixels
  possession.json      derive    the single file the viewer reads
```

Units everywhere: **yards**, **seconds**, and frame indices at the tracking rate.

**`work/` is gitignored and three files in it are not.** The directory is ignored because
it holds the footage, which `docs/10-getting-the-footage.md` says not to redistribute.
`events.json`, `corrections.json` and `calibration_truth.json` are not footage — they are
what a human typed, they are the only inputs this project cannot regenerate, and AD-6 says
the correction log is the highest-value thing it produces. They are tracked; everything
else under `work/` is not.

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

  > **Read that literally: not `observed`, not "nothing".** Until the mosaic there was no
  > difference — a frame below the threshold had no usable pose at all, and `ur.detect.run`
  > wrote no `field` position. `ur/calibrate/mosaic.py` changed that: a frame with no paint
  > on it is now placed to a measured 0.2–2.4 yd from frames that do have paint. Those
  > positions are written, tagged `weak_calibration` on the detection, and become the
  > **`weak`** evidence state — which is not `observed`, is excluded from the viewer's
  > `MEASURABLE` set, and can never make a metric call itself measured. A two-yard ring on
  > a 53-yard-wide field still answers a question about team shape; a blank frame does not.
  > Changed 2026-09-14; `docs/29-scouting-possessions.md` has the measurements.

- `basis` on a frame record says where its pose came from when it did not come from the
  paint on that frame: `"mosaic"` (registered against paint-solved frames) or
  `"mosaic+paint"` (registered, then refined against this frame's own paint inside the box
  the registration's measured accuracy allows). Absent means the paint solved it outright.

If the camera is fixed in position (it is, on this broadcast) you may additionally store
pan/tilt/focal per frame; it makes smoothing better-behaved than smoothing H directly.
The fixture stores exactly that form — see `camera.per_frame` in `fixtures/`.

## detections.json

```json
{"schema":"ultimate-radar/detections@1",
 "frames":[{"f":0,"dets":[
    {"box":[1201,540,1248,648],"score":0.91,"team":"chill","team_score":0.97,
     "team_p":0.993,"foot":[1224.5,648],"field":[63.2,27.4],"tile":3}]}]}
```

`field` is present only when the frame's calibration confidence allowed it. Keep `box` — the
correction dataset needs image space.

**`team_p` is the one to read; `team_score` is kept for continuity.** `team_p` is the
probability that this detection's kit is the team named in `team`, so the other kit is
`1 − team_p` — there are exactly two. `weak_team` is now shorthand for `team_p < 0.9` rather
than a separate judgement, and it no longer means "discard this": see AD-3's amendment.
`non_player` (`"ref"` or `"crew"`) is the only flag that means discard, and downstream must
count the two separately — conflating them is what produced the wrong justification for M4's
recall gate.

## tracks.json — immutable

```json
{"schema":"ultimate-radar/tracks@1",
 "slots":[{"slot":"D6","team":"chill",
   "samples":[{"f":0,"xy":[71.0,24.6],"state":"observed","sigma":0.3,"det":12,
               "assoc":{"alts":2,"margin":4.1,"chi2":1.2,"kit_p":0.99,
                        "kit_penalty":0.02,"branch":"chi2",
                        "runner_up":{"det":7,"xy":[73.1,25.0],"cost":5.3}}},
              {"f":1,"xy":[71.2,24.5],"state":"predicted","sigma":0.9,"det":null},
              {"f":40,"xy":[71.2,24.5],"state":"unknown","sigma":3.4,"det":null,
               "anchor_f":1},
              {"f":41,"xy":[66.0,29.8],"state":"provisional","sigma":0.8,"det":4,
               "reacquire":{"gap_frames":40,"gap_s":2.67,
                            "jump_from_prediction_yd":7.2}}]}]}
```

Exactly 14 slots, each with a sample for **every** frame — no gaps, because a gap is a
decision the viewer would have to re-make. `det` indexes back into `detections.json`.

Three fields added in round 2, each because something downstream could not otherwise tell
two different situations apart:

- **`assoc.margin` is never null.** It used to be omitted whenever a slot had only one
  candidate, which is the majority of records — D5 had zero non-null margins out of 253 — so
  any statistic over it was mostly reading absent data, and reading the absence as zero says
  the *least* contested slot is the most. It is now the cost gap to the best alternative,
  where a slot with no alternative is measured against the gate ceiling: the cost at which
  the least attractive admissible rival would have sat. Alone in the gate now reads as a
  large margin, which is what it is. `assoc` also carries `kit_p` (the kit probability the
  assignment was taken on), `branch` (which gate admitted it), and `runner_up`.
- **`anchor_f`** on an `unknown` sample — the frame its position was last actually observed.
  The position is held there rather than dead-reckoned, so the reader needs to know how old
  it is.
- **`falsified`**, **`sigma_floor_unseen`** and **`covered`** on an `unknown` sample — the
  camera was pointed at the estimate and found nobody; how far the nearest unsearched ground
  is, which floors the sigma; and whether every place the player could be has been searched,
  in which case the viewer draws nothing and the roster says so. `ur/possess.py` re-exports
  `falsified` and `covered` as per-frame boolean arrays, because the viewer needs them and
  cannot recompute them without the homography and the detections.
- **`reacquire`** on a `provisional` sample — the gap that preceded it and how far the
  observation landed from the dead reckoning. `ur/issues.py` turns these into the review
  queue; they are the only record of which observations have an unverified identity.

**What `sigma` means, because it is easy to get wrong.** It is the **radius of a disc intended
to contain the truth**, not a per-axis standard deviation. `docs/05-uncertainty.md` draws a
disc of this radius and gates on ≥ 80 % of truths falling inside it, and those two statements
are only consistent under the containment reading: for a 2-D Gaussian with per-axis σ, the
disc of radius σ contains just **39.3 %**, so a per-axis value cannot reach 80 % however well
calibrated the filter is. M4 shipped a per-axis σ at first and failed the gate at 57.5 % while
its covariance was, if anything, 31 % *conservative* — the number was right and the units were
wrong.

Two producers, and they do not use the same containment level:

| Field | Producer | Definition | Containment |
|---|---|---|---|
| `detections[].sigma_yd` | `ur.detect.run` | rms of the measured 2-D foot-point offset × local scale | ~94 % |
| `tracks.slots[].samples[].sigma` | `ur.track.run` | 1.794 × the filter's per-axis position σ | ~80 % |

Both are radii; neither is a per-axis σ. The difference in level is not principled, it is
history — M3 chose the rms because it is a definition rather than a number chosen to clear a
gate, and M4 chose the level the gate actually asks for. **If they are ever unified, unify on
the containment level `docs/05` gates, and re-measure both.**

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

`source` is one of **three** values, and the third was added because its absence caused a
real error: `human` (a person watched and tagged it — authoritative), `suggested` (the
pipeline proposed it, shown differently until confirmed), or `example` (schema filler, never
authoritative). An event written to demonstrate the schema carried `source: "human"` from M5
until `ur/disc.py` read it as truth and forced a holder for one frame in the middle of
another player's possession. If it is not a real observation, it is not `human`.

`player_inferred: true` is the fourth thing a tag can say, and it qualifies `player`, not
`source`. The tag is still a human's. The **name** on it was reached by elimination, from
the chain, from coverage, from what the play obviously was, rather than read off a jersey.
Everything downstream treats it as the weaker claim it is: `tools/gates.py` will not grade
the span solver against it, `ur/disc.py` will not emit a `confirmed` disc from it however
well the slot was seen, and the viewer's cards say the name was inferred. `docs/27` works
the one case in the corpus, p0003's 21.27–26.33 s span, and says why it is still worth
having in the file.

### `observed` — statements about the possession, not about a moment

```json
{"schema":"ultimate-radar/events@1",
 "possession_id":"p0009",
 "observed":{"attacking_direction":{"team":"chill","direction":"-x","source":"human"}},
 "events":[]}
```

A block beside `events` for facts a human states about the whole possession rather than
about one instant. It holds one key today.

`attacking_direction` names **which team** and **which end**, and the team is not optional
decoration: `offense` is a single value for the whole possession, so after a turnover it is
wrong, and an observation that inherited its team from it would be wrong with it (AD-10).
The shorthand `"attacking_direction": "+x"` is accepted and means the team `clip.json` has
on offence.

This is an **observation**, and the fact it contributes to is stored nowhere. Direction
belongs to a `(quarter, team)`, and `ur/direction.py` resolves it across every possession at
read time: one confirmation settles the other team in that quarter and every possession in
it. A direction arrived at that way is marked `derived`, names the possession it came from,
and is **never written back here** — that would make the derivation its own evidence and
destroy the only check there is, which is that two independent confirmations in one quarter
must disagree about the end (`tools.gates`, `Qn: opposite teams disagree`).

`clip.json:attacking_direction` stays what it always was: a **declaration** typed at cut
time. It is now checked against the resolved fact instead of being the source of it.

The file's top-level `note` is carried onto `possession.json` as `events_note` by
`tools/make_view.py`, purely so the viewer's **Download events** can put it back. That
download replaces `events.json` wholesale, and p0003's note is three hundred words on how
its identities were arrived at — a round trip that dropped it would destroy the only record
of them.

## disc.json

```json
{"schema":"ultimate-radar/disc@1",
 "samples":[{"f":0,"xy":[70.3,28.0],"z":1.2,"state":"predicted","basis":"held",
             "holder":"O1","sigma":0.9,"source":"inferred","name_inferred":false},
            {"f":59,"xy":[72.1,29.4],"z":2.0,"state":"interpolated","basis":"flight",
             "holder":null,"sigma":3.3,"source":"human","name_inferred":false}]}
```

One sample per frame with a position in every one, for the same reason `tracks.json` has no
gaps. Two orthogonal fields, and conflating them is the mistake to avoid:

- **`state`** is provenance, from the same vocabulary as a player's. It is **never
  `observed`** — nothing in this pipeline has detected a disc. `confirmed` means a human
  tagged the holder; `predicted` means the geometry inferred one; `interpolated` is a flight
  between two tagged endpoints; `unknown` means the position is carried and not to be
  believed.
- **`basis`** is *what kind of thing* the disc is doing — `held`, `flight`, `loose`,
  `unknown` — and says nothing about how well it is known.
- **`name_inferred`** carries `player_inferred` down from the tag that fixed this frame's
  holder. The moment is a person's and so is the reasoning, but the name was reached by
  elimination rather than read off a jersey. It is why `state` can be `predicted` on a
  frame `source` calls `human`. A tag vouches for the holder only as well as the tagger
  could see them, and a name nobody read is no stronger evidence than the solver's own.
  `docs/27` works the one case in the corpus.

`ur/possess.py` re-exports these as `disc` (the `[x, y, z]` triple the viewer draws) and
`disc_meta` (the provenance beside it, `name_inferred` included), plus
`disc_meta.trustworthy`, which is the module's verdict on its own holder sequence. See
`docs/27-disc.md`.

## corrections.json — append-only

```json
{"schema":"ultimate-radar/corrections@1",
 "corrections":[
   {"id":"c1","at":"2026-09-13T10:04:00Z","op":"anchor","slot":"D6","f":156,
    "xy":[82.5,26.0],"note":"visible at the top of frame just before the pan"},
   {"id":"c2","at":"2026-09-13T10:05:12Z","op":"swap","slots":["D5","D7"],"from_f":156},
   {"id":"c3","at":"2026-09-13T10:06:00Z","op":"confirm","slot":"O6","f":210},
   {"id":"c4","at":"2026-09-13T10:07:30Z","op":"revert","target":"c2"},
   {"id":"c5","at":"2026-09-16T18:02:00Z","keyframe":"k1","op":"anchor",
    "slot":"O2","f":330,"xy":[64.0,22.0]},
   {"id":"c6","at":"2026-09-16T18:02:00Z","keyframe":"k1","op":"anchor",
    "slot":"disc","f":330,"xy":[64.4,22.3]}]}
```

Order matters; `resolve.py` replays them in sequence. `revert` neutralises an earlier
correction rather than deleting it, so the log stays a true history.

**`keyframe`** groups the entries one save produced. The viewer's repair mode pauses the
clip and lets a person put every marker and the disc right at once (#8), and that is one
statement about one moment rather than fifteen unrelated ones — so the log carries the
grouping, the correction panel shows one row per keyframe, and one Undo reverts the whole
save. It is optional: a single drag writes an entry with no `keyframe` and nothing changes
for it.

**`slot: "disc"`** anchors the disc rather than a player. AD-2's fourteen slots are
*people*, never created and never destroyed, so `"disc"` cannot collide with `O1`–`D7` and
the disc needs no operation and no file of its own. It brackets its ramp against
`confirmed` frames only — `interpolated` is the straight line drawn *between* two human
tags, so treating it as an observation would pin the correction to the estimate it is
there to fix. Its height is left alone unless stated: a person clicking on the grass is
saying where the disc is over the field, not how high it is.

A correction is only ever applied by `ur/resolve.py`, and it is applied **in front of**
`ur/disc.py` in the pipeline. The disc's position is the holder's position, so placing a
holder the tracker lost places the disc, and the disc stage has to be the one that finds
out. `tools/pipeline.py` carries the order and the measurement behind it.

## calibration_truth.json — where the paint really is

```json
{"schema":"ultimate-radar/calibration-truth@1",
 "possession_id":"p0003",
 "image":{"w":1280,"h":720},
 "observations":[
   {"id":"g1","at":"2026-09-16T18:04:00Z","f":71,
    "landmark":"goal line +x @ yW","field":[100.0,53.333],"image":[499.4,309.7]}]}
```

A person watching can see where the painted line is; the calibration solve can be wrong
about it by yards and say nothing. So repair mode draws the field paint on the video
through the frame's own homography, and dragging a landmark onto the paint states a
correspondence: this field point, whose position is known exactly, appears at these image
pixels. `field` is ultimate-frame yards and `image` is pixels in the source frame, not in
whatever the canvas happened to be scaled to.

**It is a separate file from `corrections.json` on purpose, and the two must never share
one.** A paint reading is a fact about the *camera*; a correction is a fact about
somebody on the field. They are gathered in the same session with the same gesture, which
is exactly why the split has to be in the storage rather than in anybody's memory: a paint
reading replayed as a player anchor would move a person onto a line they were nowhere
near, and it would poison the log AD-6 wants to be a training set of human-verified player
positions. `ur/resolve.py` never reads this file.

## possession.json — what the viewer reads

One self-contained file: `clip.json` fields, plus resolved per-slot arrays, plus events, plus
derived metrics. `attacking_direction_resolved` is the exception to "self-contained": it is
a property of a `(quarter, team)` and so needs every possession at once, which is why
`tools/make_view.py` writes it as the page is built rather than `ur/possess.py` writing it
here. It is `null` where nobody has confirmed that quarter, and the viewer then says
`unverified`. The synthetic fixture `fixtures/possession_demo.json` is a valid instance
(with an extra `truth` array the real pipeline will not have, used only to render a
stand-in camera view). Its shape:

```json
{"schema":"ultimate-radar/possession@0.2",
 "possession":{"quarter":1,"attacking_direction":"+x",
               "attacking_direction_source":"declared",
               "attacking_direction_resolved":{"team":"sol","direction":"+x",
                                               "source":"derived","from":["p0009"]},
               "offence_drift_check":{"drift_yd":21.8,"agrees":true}},
 "field":{...}, "teams":{...},
 "camera":{"image_w":1280,"image_h":720,"position_yd":[58,-21,13],
           "per_frame":[{"aim":[48.5,24.1],"focal_px":1180.4}]},
 "disc":[[x,y,height_yd]],
 "events":[...],
 "players":[{"id":"D6","team":"chill","slot":"D6","jersey":5,"role":"defender",
             "est":[[x,y]], "state":["observed"], "sigma":[0.3], "human":[]}],
 "derived":{"coverage":[10], "assignment":[{"D6":"O6"}], "metrics":{...}}}
```

Parallel arrays indexed by frame, not per-frame objects: at 300+ frames × 14 players the
object form triples the file size for no benefit, and the viewer wants columnar access.

For real footage the viewer plays `clip.mp4` behind an overlay canvas instead of rendering a
camera view; the projection math is identical, sourced from `calibration.json` rather than
the synthetic `camera` block. Concretely, `camera.per_frame[i]` then carries `H` (image pixel
-> ultimate field yard, homogeneous) instead of `aim` and `focal_px`, and `ur/possess.py`
writes both plus a `frame` note. `viewer/index.html` reads whichever is present.

Two fields added after M4 and M6, both because something downstream was about to be misled:

- **`gates`** — the measured acceptance numbers for the tracker that produced this file, and a
  `note` naming the one that is marginal. A position without the recall beside it is a number
  waiting to be over-trusted; the viewer prints them in its provenance banner.
- **`human`** — per player, and beside `disc_meta`: the frames whose position a human's
  hand created or moved, as sorted frame indices. Empty on everything the pipeline
  produced alone; `ur/resolve.py` fills it. It is not the evidence state wearing a
  different name. `confirmed` is what an `anchor` *produces*, but `docs/05`'s ramp also
  shifts the frames between the bracketing observations, and those keep their original
  state while their position is now partly a person's — so a consumer asks `human`, never
  `state`. A list of indices rather than a per-frame array because it is empty in the
  normal case and 555 `false`s would ride onto every published page for nothing.
  `ur/human.py` holds the vocabulary and the grading view; `tools/human_positions.py` is
  the gate that no metric has read one.
- **`camera.position_yd` is ULTIMATE-frame yards**, converted through `venue_transform`. The
  soccer-frame value `calibration.json` solves in is kept beside it as `position_yd_soccer`.
  Before M6 this key carried the soccer value in a file whose every other coordinate was
  ultimate-frame. Nothing had read it yet, which is exactly why it was worth fixing.
