# 10 — Getting the footage

The source is a public YouTube upload on the league's own channel:

```
Pro Frisbee Semifinals: Austin Sol vs Minnesota Wind Chill | FULL GAME BROADCAST | August 27, 2026
https://www.youtube.com/watch?v=IDnoyd4cKfM
UFA Ultimate Frisbee Association  ·  2:22:27  ·  1080p, 60 fps available, AV1
Breese Stevens Field, Madison WI
```

Download it once, keep it local, work from the local file. This is personal film study —
don't redistribute the video or the extracted frames.

> If a better source exists — UFA's own platform, a coach's sideline film, or a tactical
> wide-angle feed — use it instead. A fixed wide camera that keeps the whole field in frame
> would remove most of this project's hard problems at a stroke. Worth ten minutes of asking
> before committing to the broadcast feed.

## 1. Tools

```powershell
winget install yt-dlp.yt-dlp
winget install Gyan.FFmpeg
```

(or `pip install -U yt-dlp`, plus ffmpeg on PATH.)

## 2. Pick a format

```powershell
yt-dlp -F "https://www.youtube.com/watch?v=IDnoyd4cKfM"
```

**Prefer H.264 (`avc1`) over AV1 if a 1080p avc1 stream is offered.** AV1 decodes correctly
but is slow to seek and to decode frame by frame, and you will be decoding this file a lot.
VP9 is an acceptable middle ground. Whatever you take, the pipeline transcodes each
possession clip anyway (step 4), so the only cost of AV1 is the one-time cut.

> **Confirmed in M0: a 1080p60 avc1 stream is offered.** Format **`299`** —
> 1920×1080, 59.94 fps, `avc1.64002a`, 5.40 GiB — plus `140` for audio. So take `299+140` and
> there is no AV1 compromise to make. The selector below resolves to exactly that.

```powershell
yt-dlp -f "bv*[height<=1080][vcodec^=avc1]+ba/bv*[height<=1080]+ba/b[height<=1080]" `
       --merge-output-format mp4 `
       -o "raw/sol-vs-windchill-2026-semi.%(ext)s" `
       "https://www.youtube.com/watch?v=IDnoyd4cKfM"
```

Budget 4–10 GB and a long download. Do it once.

## 3. Check what you actually got

```powershell
ffprobe -v error -select_streams v:0 `
  -show_entries stream=width,height,r_frame_rate,avg_frame_rate,codec_name,nb_frames `
  -of default=noprint_wrappers=1 raw/sol-vs-windchill-2026-semi.mp4
```

Two things to confirm and record in `docs/00-footage-report.md`:

- **Is 60 fps real?** A broadcast upscaled from 30 fps will have duplicate frames. Put `-ss`
  **before** `-i` — as an output option it decodes the whole 25 minutes before it starts
  measuring — and sample several stretches, not one, since a static graphic also decimates
  heavily:

  ```powershell
  ffmpeg -ss 25:00 -i in.mp4 -t 10 -vf mpdecimate -fps_mode vfr -f null -
  ```

  Count the frames that survive. If roughly half are dropped, treat the footage as 30 fps and
  stop paying for 60. `tools/fpscheck.py` does this across several timestamps and prints a
  verdict.

  > **Measured in M0: the 59.94 fps is genuine** — 4740 of 4792 frames survive across eight
  > 10-second stretches (98.9 %).
- **Does the feed cut between cameras?** `tools/cuts.py` answers this over the whole game in
  one pass. A cut mid-possession is fine — M1 handles multiple shots — but a tight reaction
  shot with no field in frame is a segment the pipeline must skip rather than try to
  calibrate.

  > **Measured in M0:** 403 cuts (2.83/min), but **every live-play shot runs 36–174 s**
  > (median 96 s), so a possession usually contains none. About 48 % of the broadcast is not
  > a usable field shot. Hard zooms *within* a shot are the real hazard and no cut detector
  > flags them.

## 4. Cut one possession

Frame accuracy matters here: the whole pipeline indexes off frame 0 of the clip.

```powershell
ffmpeg -ss 00:25:10 -i raw/sol-vs-windchill-2026-semi.mp4 -t 21 `
       -c:v libx264 -crf 16 -preset slow -pix_fmt yuv420p -an `
       work/p0001/clip.mp4
```

Re-encoding (rather than `-c copy`) is deliberate: a stream copy can only cut on a keyframe,
which silently shifts your start time by up to a couple of seconds. CRF 16 is visually
lossless enough for detection and keeps the file small.

Then the tracking-rate frames:

```powershell
ffmpeg -i work/p0001/clip.mp4 -vf fps=15 -q:v 2 work/p0001/frames/%06d.jpg
```

Sanity check: frame count should equal `round(duration × 15)`. If it doesn't, the clip
boundaries are off and everything downstream inherits the error.

> **Use `ur/ingest.py` rather than running these by hand.** The commands above are the right
> shape but two details bite, and M0 found both by checking rather than by reading the output:
>
> 1. **ffmpeg's input seek keeps frames strictly *after* the seek timestamp**, so seeking to a
>    frame's exact pts silently drops that frame and the clip starts one frame late. Ingest
>    measures which source frame actually became frame 0, by comparing pixels against the
>    neighbouring source frames, and records the winner as `source.start_s`.
> 2. **`-vf fps=15` does not put clip frame 0 in `frames/000000.jpg`.** The filter buckets
>    input frames into output slots and keeps the *last* in each bucket, so `frames/n` sits up
>    to one source frame behind a uniform `n/15` clock. `clip.mp4` is what the viewer plays and
>    `frames/` is what the overlay is indexed by, so an unnoticed offset puts the overlay on
>    the wrong moment. Ingest asserts the exact relation at two points in every clip and writes
>    it into `clip.json` as `clip_frames_sync`.
>
> ```powershell
> python -m ur.ingest --source raw/sol-vs-windchill-2026-semi.mp4 --id p0001 `
>     --start 7264.0 --duration 24.0 --offense sol --defense chill
> ```

## 5. Record where it came from

`ur/ingest.py` writes `clip.json` (see `docs/03-data-contracts.md`) and **must** record
`source.start_s` — the offset of clip frame 0 within the full broadcast. That single number
is what lets a coach jump from a moment in the viewer back to the original video, and what
lets you re-cut the same possession at a different rate later. Losing it means re-finding the
possession by hand.

## 6. For the footage report

M0 also needs stills for measurement, not just the clip. Pull 30 frames spread across the
whole game to sample framing, and a set of crops for player size and jersey legibility:

```powershell
python -m tools.survey uniform --every 240 --out survey/uniform
python -m tools.survey random --n 40 --seed 20260827 --out survey/random
```

One frame every four minutes across 2h22m gives about 35 frames — enough to check the field
markings and see how often the camera sits tight versus wide. The seeded random sample is what
the visibility count is computed from, because a uniform sample is not a random one and the
count needs to be reproducible.

Two reasons to use `tools/survey.py` rather than a single `-vf fps=1/240` pass: it **seeks**
instead of decoding all 2h22m, which turns minutes into seconds; and it writes **PNG**, not
JPEG. Every measurement in the footage report — pixel heights, torso colour, digit legibility
— is taken off these frames, and a second lossy generation would quietly bias all three.

A caveat the report spells out: a sample spread over the whole broadcast lands on timeouts,
replays, interviews and crowd shots. Roughly **48 %** of this broadcast is not a usable field
shot, so classify each frame before averaging anything over it.
