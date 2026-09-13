# Handoff — end of M0, 2026-09-12

Pick this up cold. Read this file, then `docs/00-footage-report.md`, then
`docs/04-milestones.md` § M1. The nine-doc spec in `docs/` is still the spec and still
governs; M0 corrected the figures in it that turned out to be wrong, and every correction is
listed at the foot of the footage report.

Working directory: `E:\dev\playertrackerultimate\ultimate-radar`

---

## 1. Where the project is

**M0 is complete.** `ur/ingest.py` exists, one possession is cut and verified on disk, and
`docs/00-footage-report.md` answers all eight M0 questions from real frames. Nothing else in
the pipeline is built — no calibration, no detection, no tracking.

**Next milestone is M1 (calibration).** Do not start M2 before M1's acceptance test passes;
AD-1 makes everything downstream depend on calibration quality.

### The four M0 findings that change the plan

1. **Breese Stevens Field is a soccer pitch.** No football yard lines, no hash marks. It
   carries centre circle, halfway line, penalty and goal areas, corner arcs — plus the
   temporary ultimate paint and orange pylons. This is *better* than gridiron lines: a centre
   circle is a conic of exactly specified radius (9.15 m = 10.006 yd). **Plan: calibrate to
   the soccer frame, then apply one fixed venue transform into the ultimate frame.**
2. **Players are 50–130 px, not 25–45.** The camera never frames the whole field, so players
   never get small. SAHI tiling is demoted from required to measure-first in M2.
3. **A possession contains one camera shot, not three.** Every live-play shot sampled ran
   36–174 s (median 96 s). AD-4's design holds but costs one set of human clicks per
   possession, not three. Hard zooms *within* a shot are the real registration hazard and no
   cut detector flags them.
4. **Visibility is 10.4/14 in wide shots** — the fixture's modelled 10.1 was very nearly
   right — **but 8.3/14 across all live play, with a worst frame of 1**, and ~48 % of the
   broadcast is not a usable field shot at all.

### The three things I would not let slide

1. **Is this a 120-yard field or a 110-yard one?** UFA rule §2.3.3 allows a 110 yd field by
   venue exception, with the brick mark moving from 20 yd to 15 yd. Soccer pitches run
   110–120 yd, so this is live. The broadcast never frames both endzones, and the venue
   publishes nothing. **Every field coordinate in the system depends on the answer.** It is
   cheap to settle in M1's first hour: the centre circle gives absolute scale, so measuring
   goal-line separation is a one-line check. Until then `clip.json` carries the rulebook
   default of 120 yd, **which may be wrong**.
2. **Jersey numbers are illegible below ~85 px of player height and at any size in side
   view.** That much is measured on 47 crops and stands. The stronger claim this file
   originally made — *numbers are on the back only* — has been **withdrawn**: it rested on
   three crops and contradicts UFA rule §3.2.3, "numbered on the back of the jersey **and
   the front of the uniform**" (note: *uniform*, so the shorts count). Open question 9 in
   `docs/08-risks.md`. Does not affect M1–M3; settle it before M5 sizes its frame budget.
3. **Referees stand on the field in black-and-grey stripes**, two or three per frame, landing
   squarely in the Wind Chill colour cluster; Wind Chill's light-blue alternate (worn on the
   sideline) lands in the *Sol* cluster. Colour separation itself is a non-issue (ΔE 36.6) —
   **AD-3's out-of-bounds reject filter is doing more work than the colour gate**. Build and
   measure it first.

Full open-question list: `docs/08-risks.md` § Open questions, items 5–10.

---

## 2. Environment — rebuild it in two commands

Python **3.11**, not 3.13: PaddleOCR (needed in M5) has no 3.13 wheels, and D-FINE / LoFTR /
SAHI are tested on 3.8–3.11.

```powershell
# uv is already installed at $env:USERPROFILE\.local\bin\uv.exe (not on PATH by default)
$env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
uv venv --python 3.11 .venv
uv pip install --python .venv\Scripts\python.exe -r requirements-m0.txt
```

Run everything as `.\.venv\Scripts\python.exe -m <module>`.

| | |
|---|---|
| Interpreter | CPython 3.11.16, uv-managed, venv at `.venv/` (193 MB, not committed) |
| M0 deps | numpy 2.4.6, opencv-python 5.0.0.93, pillow 12.3.0, yt-dlp 2026.8.19, pypdf 6.18.1 |
| ffmpeg | 9.0.1 gyan.dev **full** build, on PATH. **This is a GPL build** — see the note in `docs/07-licenses.md`. We exec it as a separate process, never link it, never vendor it. |
| GPU | RTX 4070 Ti SUPER, 16 GB, sm_89, driver 591.86 (CUDA 13.1 capable) |
| torch | **Not installed yet.** Deferred to M2 deliberately. Intended: stable torch + `cu128` wheel; pin the exact version when M2 starts and verify the wheel exists then rather than inheriting a stale guess. |
| Determinism | Seed `20260827` throughout. Ingest is verified byte-identical across two runs. |

---

## 3. What is on disk, and what is not in the repo

```
ultimate-radar/
  raw/                     5.6 GB   GITIGNORED - the broadcast
  work/p0001/              120 MB   GITIGNORED - the cut possession
  survey/                  247 MB   GITIGNORED - 161 extracted stills
  eval/                     33 MB   COMMITTED  - M0 evidence + the rulebook PDF
  ur/, tools/, docs/, viewer/, fixtures/, schemas/
```

### Committed and worth knowing about

| Path | What |
|---|---|
| `ur/ingest.py` | M0's deliverable. Cuts a possession, writes `clip.json`. Read its docstring before changing it — the start-offset measurement is load-bearing. |
| `ur/ffprobe.py` | Thin ffmpeg/ffprobe wrappers. `frame_times()` has a `-read_intervals` gotcha documented in place. |
| `tools/survey.py` | Seek-based still extraction (uniform / seeded-random / span / explicit). Writes **PNG**, deliberately. |
| `tools/measure.py` | Green-segmentation blob finder. **M0-only, not a detector.** See the caution in `eval/m0/README.md`. |
| `tools/paint.py` | Paint detector — the tool that answered "are there yard lines". Likely useful again in M1. |
| `tools/cuts.py` | Whole-game scene-change scan with CUDA decode. Already run; results in `eval/m0/cuts_full/`. |
| `tools/crop.py`, `tools/sheet.py`, `tools/jerseysheet.py` | Crop with pixel grid, contact sheet, fixed-magnification sheet. General-purpose; reuse them. |
| `tools/fpscheck.py`, `tools/heights.py`, `tools/teamcolour.py` | One-question M0 tools. Keep for re-measurement, don't build on them. |
| `eval/m0/` | Everything the footage report cites, with a README mapping file → report section. |
| `eval/m0/visibility_counts.json` | **The hand counts themselves**, per frame, with the counting rules written down. This is a hand-label set; treat it as data, not as scratch. |
| `eval/ufa-rulebook-2025-v13.pdf` | Primary source for the field dimensions. |
| `requirements-m0.txt` | Pinned M0 deps. |

### Not in the repo — regenerate if needed

```powershell
# the broadcast (5.95 GB, format 299+140 = 1080p60 avc1 + m4a)
.\.venv\Scripts\python.exe -m yt_dlp -f "299+140" --merge-output-format mp4 `
    -o "raw/sol-vs-windchill-2026-semi.%(ext)s" "https://www.youtube.com/watch?v=IDnoyd4cKfM"

# the possession (deterministic - reproduces byte-identically)
.\.venv\Scripts\python.exe -m ur.ingest --source raw\sol-vs-windchill-2026-semi.mp4 `
    --id p0001 --start 7264.0 --duration 24.0 --offense sol --defense chill

# the survey stills (seeded)
.\.venv\Scripts\python.exe -m tools.survey uniform --every 240 --out survey\uniform
.\.venv\Scripts\python.exe -m tools.survey random --n 40 --seed 20260827 --out survey\random
```

---

## 4. The possession, `work/p0001/`

| | |
|---|---|
| Broadcast span | **7264.023 → 7288.014 s** (02:01:04 → 02:01:28), 24.0 s |
| Output | `clip.mp4` (59.94 fps, CRF 16), `frames/000000.jpg … 000359.jpg` (15 fps), `clip.json` |
| Game state | 4th quarter, ATX 20 – MIN 25, clock 7:31 → 7:07 |
| Offence / defence | Austin Sol (light kit) / Minnesota Wind Chill (dark kit) |
| Shot | Sits entirely inside one broadcast shot (7246.3 – 7350.5 s). **No cut.** |
| Visible players | 11 / 14 / 12 at frames 0 / 180 / 345, hand counted → ≈ 88 % |
| Calibration features | Soccer centre circle **and** halfway line in *every* frame; one ultimate line and one pylon at the far side |

**Two subtleties baked into `clip.json` — do not re-derive them by hand.**

- `source.start_s` is the **measured** source timestamp of `frames/000000.jpg`, not the value
  passed to ffmpeg. ffmpeg's input seek keeps frames strictly *after* the seek timestamp, so
  asking for a frame's exact pts silently drops it. Ingest proves which frame won by pixel
  comparison and records the margin in `start_verification`.
- `clip.mp4` and `frames/` do **not** index the same instants. ffmpeg's `fps` filter buckets
  input frames into output slots and keeps the last in each, so `frames/n` is up to one source
  frame behind a uniform `n/15` clock. The exact relation is in `clip_frames_sync`, asserted
  against real pixels at two points in every clip. **The viewer's overlay depends on this** —
  a silent one-frame offset would put the overlay on the wrong moment with nothing to signal
  it.

**One M0 criterion not met, stated rather than papered over:** M0 asks the chosen possession
to contain "at least one scheme change or poach". The defence reads as a person look from
stills at 1 Hz, but I did not watch the clip play and will not claim a poach I have not seen.
**Play `work/p0001/clip.mp4` and confirm before committing M4's labelling effort to it.** If
it turns out to be a flat person look with no poach, the point continues past the clip and
ends in a Sol goal at ≈ 7330 s, so a longer or later cut is available from the same shot.

---

## 5. Where I would start M1

Not instructions — my reading, for you to overrule.

1. **Settle the 120 vs 110 yd question first.** It is an hour's work once any homography
   exists, and it invalidates field coordinates if left. Use the centre circle for absolute
   scale.
2. **Build the verification render before the calibration.** `docs/04-milestones.md` calls it
   "the only honest way to see whether calibration is working". It is also the fastest way to
   discover the venue transform is wrong.
3. **Decide the field-frame question** in `docs/08-risks.md` open question 6 — venue-fixed vs
   possession-relative — *before* writing `calibration.json`, because it changes a data
   contract. My recommendation is in there: venue-fixed frame in `calibration.json`, flip in
   `derive`. I did not change it unilaterally.
4. **Shot detection is already done for the whole game** — `eval/m0/cuts_full/events.json` has
   every scene-change candidate with scores, threshold-validated at 0.35 against four
   hand-checked cuts. M1 can read it rather than re-running the scan.
5. **Reuse `tools/paint.py`** for the correspondence tool's line overlay. It already finds the
   circle and the halfway line cleanly.
6. **Find a multi-shot possession deliberately.** A cut inside live play is rare, so M1's
   multi-shot path will not be exercised by accident. Unverified candidates: the short shots
   interrupting long ones at t ≈ 2893.9–2901.2 and t ≈ 5645.5–5652.9.

---

## 6. Housekeeping you may want to do first

- **This is not a git repository.** `git rev-parse` fails; there is no `.git`. A `.gitignore`
  exists and is correct (`raw/`, `work/`, `survey/`, `.venv/`). If you want history, `git
  init` and commit before touching anything — M0's evidence in `eval/` is worth a baseline
  commit, and `AGENTS.md` rule 2 (never mutate tracking output) is much easier to honour with
  history behind you.
- `schemas/` is still empty. `schemas/README.md` says to write the JSON Schemas in M1 as the
  contracts stabilise, and `clip.schema.json` can be written now against a real `clip.json`.
- `docs/00-footage-report.md` § "Corrections made to other documents" is the authoritative
  list of what M0 changed and why. If something in the specs looks wrong, check there before
  assuming it is stale.
