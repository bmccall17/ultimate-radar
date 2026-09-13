# 00 — Footage report

**Status: written 2026-09-12 from the real broadcast.** Every number below was measured on
decoded frames of the downloaded file, not modelled. Where a figure is a judgement rather
than a measurement it says so.

Source: YouTube `IDnoyd4cKfM`, downloaded once as format `299+140`
(1920×1080 avc1 + m4a), 5 950 048 571 bytes, kept at
`raw/sol-vs-windchill-2026-semi.mp4`. Everything here is reproducible from that file with
the tools in `tools/` and the seed `20260827`.

---

## The two answers that matter most

**1. Breese Stevens Field has no football markings. It is a soccer pitch.** There are no
yard lines and no hash marks anywhere on it. What it does carry is a full set of association
football markings — centre circle, halfway line, penalty and goal areas, corner arcs — with
the temporary ultimate lines and orange pylons painted and placed over the top. The M1 plan
has to change, but *not* in the direction the docs feared: a centre circle is a better
calibration primitive than a yard line, because it is a conic with an exactly specified
radius. See Q2.

**2. In a wide broadcast shot, 10.4 of 14 players are visible on average — the fixture's
10.1 was very nearly right.** But that average only holds for wide shots, and wide shots are
35 % of the broadcast. Across *all* live-play frames the figure is 8.3/14, and the tight
shots the broadcast cuts to during a catch drop to 1–5 players. The honest headline is
therefore: **the modelled visibility was correct for the framing it modelled, and the
framing is more variable than the model.** See Q6.

---

## Q1 — Resolution, framerate, and whether 60 fps is real

`ffprobe` on the downloaded file:

| | |
|---|---|
| Resolution | 1920 × 1080 |
| Codec | h264, High profile, level 4.2, `yuv420p`, progressive |
| Colour | bt709 primaries / transfer / matrix |
| Frame rate | `60000/1001` = **59.940 fps**, `r_frame_rate` = `avg_frame_rate` |
| Frames | 512 292 |
| Duration | 8546.801 s (2:22:27) |
| Video bitrate | 5 425 834 bps |

**The 60 fps is genuine.** `mpdecimate` over eight 10-second stretches spread across the game
kept 4740 of 4792 frames — a mean kept ratio of **0.989**. A 30 fps feed doubled to 60 would
keep about half. The one stretch below 100 % (t = 2700 s, 91.3 %) is a near-static graphic,
not duplication. Full numbers in `eval/m0/fpscheck.json`.

Note the rate is 59.94, not 60. `docs/03-data-contracts.md` shows `"video_fps": 60` in its
`clip.json` example; `ur/ingest.py` writes the true 59.94005994 value.

**Bitrate is the quality risk, not resolution.** 5.4 Mbps for 1080p60 of a wide, textured,
constantly-panning grass field is thin. Distant players show visible blocking and the
jersey-number strokes are the first thing to go (Q4).

---

## Q2 — Does the venue carry football yard lines and hash marks?

**No.** This is the single biggest correction in the report.

Method: a paint detector (`tools/paint.py`) that keeps pixels that are bright, unsaturated
*and* thin — thinness is what separates a painted line from a white jersey — then renders
the result over the frame so the answer can be seen rather than believed.

Evidence: `eval/m0/paint/007_t1800.0_overlay.jpg` is a wide midfield shot covering the full
width of the pitch and a large part of its length. The only paint the detector finds is **a
circle and one straight line through its centre**. If there were yard lines there would be a
ladder of transverse stripes every 5 yards across the whole frame, and hash marks in two
rows. There are none, in that frame or in any of the 76 frames inspected.

What is actually on the ground, in descending order of usefulness for calibration:

| Feature | Where seen | Value for M1 |
|---|---|---|
| **Soccer centre circle** | Visible in most live-play frames, including *every frame* of the chosen possession | Highest. A conic with an exactly specified radius (9.15 m = 10.006 yd) |
| **Soccer halfway line** | Same | High. A straight line through the circle's centre, perpendicular to the touchlines |
| Soccer penalty area, goal area, corner arcs | End-of-pitch shots (e.g. t = 1616, 1259) | Useful when the camera is near an endzone |
| **Ultimate painted lines** | Present but thin and low-contrast; one visible in `eval/m0/paint_p0001/000180_overlay.jpg` at the far side | Needed once, to tie the soccer frame to the ultimate frame |
| **Orange pylons** | Confirmed at line intersections, e.g. `eval/m0/q2_pylon_right.png`, `eval/m0/q2_lines_lower.png` | Point correspondences. Rulebook 2.2.1 puts 10 of them on the field |
| Mowing stripes | Everywhere | None — spacing is not specified |

**The consequence for M1 is a plan change, and it is a favourable one.** Calibrate to the
*soccer* pitch, whose geometry is exactly specified and richly marked, and then apply a
single fixed venue transform from the soccer frame to the ultimate frame. That transform is
established once, from a frame where an ultimate line and a pylon are both visible, and
reused for every shot and every possession at this venue. Per-shot human clicking then only
has to pin the soccer features, which are present in far more frames than the ultimate paint.

### While confirming this, the primary rulebook was checked

`docs/01-brief.md` and `docs/08-risks.md` both asked for the rulebook PDF rather than the
Wikipedia paraphrase. Retrieved and quoted from **UFA Rule Book Version 13.0 (2025 season)**,
saved at `eval/ufa-rulebook-2025-v13.pdf`. No 2026 edition is published at the expected URL.

- **2.1.1** — "The field is a rectangle measuring 53 ⅓ yards wide by 80 yards long plus
  20-yard end zones on each end." **Confirms 120 × 53⅓ with 20 yd endzones.** The docs were
  right.
- **2.3.1** — brick marks are "20 yards in front of the goal lines". **Confirms `brick_yd:
  20`.**
- **2.1.3** — "All field lines will be painted 4” wide." Useful: a 4-inch line is a known
  scale reference, and it explains why the ultimate paint is so much fainter than the soccer
  paint in these frames.
- **2.3.2 — new, and not in any project doc:** "The reverse brick marks are centered along
  the width of the field, 10 yards behind the goal lines." That is a seventh marked point on
  the centreline, inside each endzone.
- **2.2.1** — pylons mark "each corner of the end zones and the center of the back lines" —
  10 fixed world points.

The rulebook's own field diagram is extracted to `eval/m0/rulebook/p7_0_X98.jpg`. Counting
its centreline marks: reverse brick (x = 10), goal-line centre (x = 20), brick (x = 40),
midfield (x = 60), brick (x = 80), goal-line centre (x = 100), reverse brick (x = 110) —
**seven centreline marks plus ten pylons**, all at exactly known positions. Even with no
football paint, a fully-marked UFA field is not a sparse-correspondence problem.

> **Open question, and it is the important one.** Rule **2.3.3** allows a **110-yard field**
> "if a special exception has been granted … due to venue limitations", with the brick mark
> moving to 15 yd. A soccer pitch is typically 110–120 yd long, so whether Breese Stevens
> fits a full 120 yd UFA field is a real question and I could not settle it from the
> broadcast — the camera never frames both endzones at once — nor from the venue's published
> material. **Every field coordinate in the system depends on the answer.** Resolve it in M1,
> the first time a homography exists: the soccer centre circle gives absolute scale
> (radius 9.15 m), so measuring the goal-line separation is then a one-line check. Logged to
> `docs/08-risks.md`. Until it is settled, `clip.json` carries `field.spec: "UFA 2026"` with
> `length_yd: 120.0`, which is the rulebook default and may be wrong for this venue.

---

## Q3 — Player height in pixels

Measured by hand off gridded 1:1 crops (`tools/crop.py --grid`), reading head-top and
foot rows directly. Fifteen players across three framing regimes.

| Framing | Example | Player height (px) |
|---|---|---|
| **Widest live framing** — pre-pull, camera fully out | t = 1258.9 s, `eval/m0/q3_widest_players.png` | **53, 53, 60, 60, 67, 68, 70** |
| Typical wide play shot, players at the far sideline | t = 1800.0 s, `eval/m0/q3_far_007.png` | 80, 85, 102, 106 |
| Wide play shot, far side | t = 3247.5 s, `eval/m0/q3_far_015.png` | 55–100 |
| Mid-frame, wide shot | t = 1569.5 s, `eval/m0/q3_mid_009.png` | ~100 |
| **Tight shot** | t = 3471.4 s | **~460** |

**Smallest on-field player observed anywhere in a live-play frame: ~50 px.**

This is a large correction. `docs/02-architecture.md` states "at 1080p a downfield player is
25–45 px tall and whole-frame inference misses them". The real floor is roughly **twice
that**, and the reason is structural rather than lucky: **the broadcast camera never frames
the whole field.** It covers perhaps half to two-thirds of the 120 yd at its widest, so
players never recede far enough to get small. Q3's answer and Q6's answer are the same fact
seen from two sides — you get big players *because* you do not get all of them.

**Consequence for M2: SAHI tiling is optional, not mandatory.** A 50-px person at 1080p is a
comfortably-sized object for a COCO-class detector at native resolution. Start without
tiling, measure recall against the M2 gate, and add tiling only if the measurement asks for
it. That is a meaningful simplification of M2.

The automated blob distribution (`eval/m0/heights.json`, 249 person-like blobs) is consistent
with the hand measurements but is contaminated by crowd and sideline figures in the upper
image bands, so the hand measurements are what the table above reports. Read
`eval/m0/blobs_live/*_annot.jpg` before quoting anything from the automated file.

---

## Q4 — Jersey number legibility

47 crops cut at a **fixed** 4× magnification so that relative size is preserved
(`eval/m0/q4_jersey_sheet.png` — a normal contact sheet would rescale every crop and destroy
the evidence). 22 of them are players; the rest are false positives from the blob finder,
and are left in the sheet rather than quietly dropped.

**Three findings, in order of importance:**

**1. ~~Numbers are on the back only.~~ WITHDRAWN — see below.** Back views on both kits do
carry large, high-contrast digits: Wind Chill white-on-black (`eval/m0/q4_front_chill.png`,
#51), Sol navy-on-white (`eval/m0/q4_front_sol2.png`, #88). That part stands. The
*back-only* conclusion does not.

> **Correction, 2026-09-12, after the review in `docs/11-m0-review.md`.** The claim was
> based on three front views and **contradicts the governing rule**. UFA Rule Book v13
> **§3.2.3**, read from the same PDF this report cites elsewhere: *"Each player shall be
> conspicuously numbered on the back of the jersey **and the front of the uniform**."*
>
> So either these kits do not comply, or my sample missed the front numbers — and three
> crops cannot tell those apart. Note the rule says "front of the **uniform**", not "front
> of the jersey", which permits the number to be on the **shorts**; both crops I read as
> showing "only a logo on the shorts" need a second look with that in mind. Note also that
> the two files cited as evidence of back numbering are named `q4_front_*` but show players
> facing **away** from the camera — sloppy naming that helped the wrong conclusion stick.
>
> **Status: open.** It does not affect M1–M3, so it is deferred rather than resolved here.
> **Settle it before M5 plans around a halved frame budget.** The re-check is cheap: sample
> 30–50 crops of players demonstrably facing the camera — a mark on a thrower, players
> walking back after a goal, the pull line-up — and look for a chest number *or* a number on
> the shorts. Logged as `docs/08-risks.md` open question 9.

What is **not** in doubt, because it rests on the full 47-crop sample rather than three
frames: back numbers are legible, and the legibility threshold below is measured.

**2. The legibility threshold is about 85–90 px of player height.**

| Player height | Readable? | Examples read |
|---|---|---|
| ≥ 100 px | Yes, reliably | 15, 20, 24, 51 |
| 86–99 px | Yes | 3, 4, 23, 88 |
| 75–85 px | No | none of 4 crops |
| < 75 px | No | none of 6 crops |

**3. Orientation beats size.** A side-on player is unreadable at any size in this footage.
So the per-tracklet voting in AD-5 / M5 is not an optimisation, it is the whole mechanism:
any single frame is a coin flip on whether the number is even facing the camera.

Cross-referencing Q3: in the widest live framing players are 53–70 px, i.e. **below the
legibility threshold entirely**. Numbers are readable in wide play shots (80–130 px) and
tight shots, not in pull-setup shots.

---

## Q5 — Team colour separability

Torso colour (rows 20–55 % of each box) of 333 person-like blobs across 22 live-play frames,
clustered by a deterministic 2-means in CIELAB (`tools/teamcolour.py`, seed 20260827).

| | L* | a* | b* | n |
|---|---|---|---|---|
| Dark cluster (Wind Chill) | **31.8 ± 11.9** | −4.6 | 6.3 | 219 |
| Light cluster (Sol) | **66.6 ± 12.8** | −0.8 | 17.0 | 114 |

- **Centre separation ΔE = 36.6.** That is enormous — comfortably above the ~2.3
  just-noticeable difference, and far beyond anything a learned re-ID embedding would offer.
- The clusters barely touch at the tails: p95 of dark is **49.1**, p05 of light is **50.1**,
  either side of a threshold at L* ≈ 49.2.
- 15 of 333 blobs (4.5 %) fall on the wrong side of that threshold. Inspecting
  `eval/m0/teamcolour/clusters_026_t5703.7.jpg`, **essentially all of them are bad boxes** —
  a blob covering only a player's legs, or two players merged — not genuinely ambiguous
  torsos. A real detector in M2 removes this failure mode.

**AD-3 is safe on colour. The risk is entirely in the reject class,** and it is larger than
the docs anticipated:

- **Referees wear black and grey vertical stripes** and stand on the field. Their torso L*
  lands squarely in the Wind Chill cluster. They appear in most live-play frames — usually
  two or three of them.
- **Wind Chill have a light-blue alternate kit** which their sideline players wear, visible
  at t = 6632 s and at t = 1123 s. Its torso L* lands in the *Sol* cluster. Any sideline
  player who strays inside the field bounds is a cross-team false assignment waiting to
  happen — precisely the error class AD-3 exists to eliminate.
- Camera operators and photographers sit on the grass just outside the far touchline, inside
  the frame, in nearly every wide shot.

So the out-of-field-bounds filter in AD-3 is doing more work than colour is. It should be
built and measured first, not bolted on.

---

## Q6 — How much of the field is in frame, and how many players are visible

40 frames drawn at seeded random (`seed=20260827`) from the whole broadcast, each classified
by eye and then **hand-counted at full resolution**, using blob boxes only as a magnifier so
that 10-px players are not missed. Annotated frames in `eval/m0/blobs_live/`.

### First: about half the broadcast is not usable at all

| Class | Frames | Share |
|---|---|---|
| Wide live-play field shot | 14 | 35.0 % |
| Medium or tight live-play shot | 7 | 17.5 % |
| Not live play — crowd, sideline, interview, replay, graphics, halftime segment | 19 | 47.5 % |

This is worth stating plainly because a visibility figure computed over the whole broadcast
would be meaningless, and one computed over wide shots alone would flatter the system.

### Then: visible players, out of 14

| Subset | n frames | Mean visible | Median | Min | Max |
|---|---|---|---|---|---|
| **Wide live-play shots** | 14 | **10.4 / 14 (74 %)** | 11 | 5 | 14 |
| Medium / tight live-play shots | 7 | 4.1 / 14 (30 %) | 5 | 1 | 6 |
| **All live-play frames** | 21 | **8.3 / 14 (59 %)** | 8 | 1 | 14 |

Per-frame counts:

| t (s) | framing | visible | | t (s) | framing | visible |
|---|---|---|---|---|---|---|
| 1092.0 | wide | 13 | | 5307.7 | tight | 1 |
| 1292.1 | wide | 11 | | 5401.7 | medium | 4 |
| 1480.9 | wide | 11 | | 5513.7 | wide | 6 |
| 1569.5 | wide | 8 | | 5703.7 | wide | 13 |
| 1615.7 | medium | 5 | | 5899.4 | medium | 6 |
| 2572.6 | medium | 6 | | 5999.0 | wide | 5 |
| 2835.3 | wide | 8 | | 7285.1 | wide | 8 |
| 2966.5 | wide | **14** | | 7291.7 | wide | 11 |
| 3247.5 | wide | **14** | | 7386.8 | wide | 13 |
| 3471.4 | tight | 2 | | 7733.1 | wide | 10 |
| 3474.7 | medium | 5 | | | | |

**Verdict on the fixture's 10.1/14: confirmed for wide shots (measured 10.4), and it should
stay.** What needs adding is the variance. The fixture's worst frame is 3; the real worst
observed is **1**, and it is not a freak — the broadcast deliberately cuts tight on a catch
several times a point. A possession that includes one of those tight shots will have several
seconds where twelve of fourteen players are pure dead reckoning. The uncertainty model in
`docs/05-uncertainty.md` is exactly the right design for this; the numbers in it just need to
be the measured ones.

**For the chosen possession specifically** (Q8), hand counts at three points: **11 at frame
0, 14 at frame 180, 12 at frame 345** — mean ≈ 12.3/14 (88 %), better than the broadcast
average because it is a well-framed possession with no tight cut-in. The M4 gate says the
`observed` fraction must land within 5 points of the M0 visibility figure; the figure it
should be compared against is **this possession's ~88 %**, not the broadcast-wide 74 %.

The unverified per-role breakdown in `docs/05-uncertainty.md` — "handler set visible 83–89 %,
deep cutters 35–54 %" — was **not** measured here. It needs tracking output to measure
properly. Flagged as still-modelled.

---

## Q7 — How often does the camera cut?

Whole-game scene-change scan with ffmpeg's `scene` metric on a 320-wide downscale, CUDA
decode, single pass over all 8546.8 s (`tools/cuts.py`, `eval/m0/cuts_full/`).

**403 cuts at a scene score ≥ 0.35 — 2.83 cuts per minute.**

Threshold validated two ways. First, sensitivity: the count is stable in shape across
0.30–0.45 and the chosen 0.35 maximises the share of the broadcast falling inside long shots
(80.7 %). Second, and more usefully, four detected cuts were checked by extracting the frames
either side (`eval/m0/cutcheck_sheet.jpg`) — **all four are genuine hard cuts** (crowd→field,
field→wrist close-up, crowd→field, sideline→crowd).

But 2.83/min is the wrong number for M1, because it is dominated by rapid replay and graphics
clusters. **The number M1 actually needs is how long the camera holds a shot during live
play**, and that is dramatically better:

| | |
|---|---|
| Shot containing a live-play frame (n = 21) | median **96.3 s**, mean 95.4 s |
| Shortest such shot | **35.8 s** |
| Longest | 174.3 s |
| Live-play shots shorter than 21 s | **0 of 21** |
| Implied cuts inside a 21 s possession | **≈ 0.22** |

**So a typical possession contains zero camera cuts, not the one to three that
`docs/02-architecture.md` assumes.** AD-4's mosaic-per-shot design still holds and is still
right, but the human cost is one set of correspondence clicks per possession rather than
three. M1 got cheaper.

Two caveats, both real:

1. **Hard zooms score below the cut threshold and are just as hard for registration.** At
   t ≈ 7326 s the camera whips from a wide field shot to a tight catch and back inside the
   *same* detected shot. AD-4's mosaic must be built at the widest zoom in the shot and
   matched with a scale-robust matcher — which the doc already says, and this is the evidence
   for why.
2. **A possession spanning a cut is therefore rare, and M1's multi-shot path will not get
   exercised by accident.** It needs a deliberately chosen test case. Candidate boundaries
   where a long shot is interrupted by a short one and play appears to continue: t ≈ 2893.9
   → 2901.2 and t ≈ 5645.5 → 5652.9. Neither is verified as mid-possession; verify before
   relying on one.

---

## Q8 — The possession for round one

**`p0001` — broadcast 7264.023 s to 7288.014 s (02:01:04 to 02:01:28), 24.0 s, 360 frames at
15 fps.** Cut, verified and on disk at `work/p0001/`.

| | |
|---|---|
| Game state | 4th quarter, ATX 20 – MIN 25, game clock 7:31 → 7:07 |
| Offence | Austin Sol (light kit) |
| Defence | Minnesota Wind Chill (dark kit) |
| Broadcast shot | 7246.3 – 7350.5 s — **the clip sits entirely inside one shot, no cut** |
| Visible players | 11 / 14 / 12 at frames 0 / 180 / 345 (hand counted) |
| Calibration features | Soccer centre circle **and** halfway line visible in *every* frame; one ultimate line and one pylon visible at the far side |

Why this one, against the M0 criteria:

- **Clear defensive structure** — yes. Wind Chill are in a person look: through the 1 Hz
  contact sheet (`eval/m0/q8_possession_sheet.jpg`) each Sol player has a Wind Chill player
  travelling with them at short range. That is the reading a coach should be able to
  reproduce, and it is comprehension-test question 1.
- **15–30 s** — yes, 24.0 s.
- **A scheme change or poach** — **not confirmed.** I can see structure in stills at 1 Hz; I
  cannot responsibly claim a poach from them, and I did not watch the clip play. This is the
  one M0 criterion I have not met, and rather than assert it I am flagging it: play
  `work/p0001/clip.mp4` and confirm before committing M4's evaluation effort to this
  possession.
- **A camera cut** — **no, and by Q7 that is the normal case, not bad luck.** Deliberately
  accepting this: the first possession exercises the single-shot path, and M1's multi-shot
  path gets a purpose-chosen second clip (candidates in Q7).
- The point continues past the clip and ends in a Sol goal at ≈ 7330 s, so a longer cut is
  available later if the possession needs extending to include the scoring throw.

### What `ur/ingest.py` does, and the two bugs the verification caught

The milestone asks only for a cut and a `clip.json`. Two things made that harder than it
looks, and both were found by checks rather than by reading the output.

**`source.start_s` was one frame wrong.** ffmpeg's input seek keeps frames strictly *after*
the seek timestamp, so asking for a frame's exact pts silently drops that frame. `ingest`
does not assume: it extracts the neighbouring source frames, compares each against clip
frame 0 by mean absolute grey-level difference, and records the winner. For `p0001` the
winning frame is at 7264.023433 s with MAD 3.904 against a runner-up of 5.938 — decisive.
`source.start_s` is now always that **measured** value, and `requested_start_s` is kept
alongside it.

**`clip.mp4` and `frames/` disagreed about which moment frame 0 was.** ffmpeg's `fps` filter
resamples 59.94 → 15 by bucketing input frames into output slots and keeping the *last* one
in each bucket, so `frames/000000.jpg` is the second source frame of the clip, not the first,
and every index inherits the lag. This matters because the viewer plays `clip.mp4` and draws
an overlay indexed by `frames/` — a silent one-frame offset would put the overlay on the
wrong moment with nothing to signal it. The three `round` modes were measured against real
pixels; the default is the only one that keeps both the frame count and a predictable
mapping. The exact relation, asserted at two points in every clip, is now recorded in
`clip.json`:

```
frames/n  ->  clip frame  ceil((n + 0.5) * 59.940 / 15) - 1
worst error against a uniform n/15 clock: 28.7 ms
```

**Determinism** (AGENTS rule 6) is verified, not assumed: two independent runs produce a
byte-identical `clip.mp4` and byte-identical first and last frames.

`clip.json` also records the ffmpeg build string, the exact cut command, the clip's SHA-256,
and the expected-vs-actual frame count (360 vs 360, drift 0).

---

## Method and reproducibility

Environment: Python 3.11.16 in `.venv` (uv-managed), `numpy` 2.4.6, `opencv-python` 5.0.0.93,
`pillow` 12.3.0, `yt-dlp` 2026.8.19, `pypdf` 6.18.1; ffmpeg/ffprobe 9.0.1 gyan.dev full build;
RTX 4070 Ti SUPER for CUDA decode in the cut scan. Seed 20260827 throughout. New rows added to
`docs/07-licenses.md`.

```bash
python -m tools.survey uniform --every 240 --out survey/uniform
python -m tools.survey random --n 40 --seed 20260827 --out survey/random
python -m tools.fpscheck --at 900 1800 2700 3600 4500 5400 6300 7200 --out eval/m0/fpscheck.json
python -m tools.cuts scan --whole --out eval/m0/cuts_full
python -m tools.measure blobs --frames survey/live --out eval/m0/blobs_live
python -m tools.teamcolour --blobs eval/m0/blobs_live/blobs.json --out eval/m0/teamcolour
python -m ur.ingest --source raw/sol-vs-windchill-2026-semi.mp4 --id p0001 \
    --start 7264.0 --duration 24.0 --offense sol --defense chill
```

**What is measured and what is judged.** Q1, Q3, Q5 and Q7 are measurements. Q2 is a
measurement plus a negative claim — "no yard lines anywhere" rests on 76 inspected frames, not
on all 512 292. Q6's counts are careful human counts at full resolution, and a second person
counting the same frames would likely differ by ±1 on the crowded ones. Q4's threshold is a
legibility judgement made by eye on crops that are in the repository, so it can be disputed
by looking. Q8's "clear defensive structure" is a judgement from stills; its "contains a
poach" claim is **not** made.

---

## Corrections made to other documents

Each of these contradicted something measured above.

| Document | Was | Now |
|---|---|---|
| `01-brief.md` | "the venue may already carry football yard lines and hash marks … M0 must check whether this venue has them" | Recorded as answered: soccer pitch, no gridiron markings; points to Q2 |
| `01-brief.md` | Field table sourced from Wikipedia, "re-verify against the primary PDF in M0" | Verified against UFA Rule Book v13.0 §2.1.1 / §2.3.1, with the 110 yd exception (§2.3.3) noted |
| `02-architecture.md` | "a downfield player is 25–45 px tall and whole-frame inference misses them" | "50–70 px at the widest live framing, 80–130 px typical (measured, M0 Q3)"; SAHI demoted from required to measure-first |
| `02-architecture.md` | "A possession typically contains one to three shots" | "Measured: typically one. Live-play shots run 36–174 s (median 96 s)" |
| `02-architecture.md` | AD-4 consequence on zoom | Added the measured hard-zoom-within-a-shot case at t ≈ 7326 s |
| `03-data-contracts.md` | `clip.json` example: `duration_s 21.0`, `fps 15`, `frames 316` (315 ≠ 316) | Example made self-consistent; convention stated — `frames` is the count on disk, `duration_s` is measured, ingest asserts they agree within 1 |
| `03-data-contracts.md` | `"video_fps": 60` | `59.94005994` (`60000/1001`), measured |
| `03-data-contracts.md` | `source.start_s` a single unqualified number | Documented as the **measured** offset of frame 0, with `requested_start_s`, `start_verification`, `clip_frames_sync` and `provenance` added to the contract |
| `03-data-contracts.md` | Field frame origin "at the corner of the defending endzone" | Says *which* corner |
| `05-uncertainty.md` | "averages 10.1 of 14 players visible, worst frame of 3" (modelled) | Measured: 10.4/14 in wide shots, 8.3/14 across all live play, worst frame 1; the modelled figure is marked as confirmed-for-wide-shots |
| `05-uncertainty.md` | Per-role visibility (handlers 83–89 %, deep cutters 35–54 %) | Marked explicitly as still modelled — not measurable without tracking output |
| `08-risks.md` | Six items under "Not verified — check in M0" | Each resolved with the measured answer, or restated as a live open question |
| `08-risks.md` | "Calibration on a sparsely-marked field" risk | Rewritten: the venue is *richly* marked, just with soccer geometry; mitigation is now the soccer-frame-plus-venue-transform plan |
| `09-decision-record.md` | "AV1, 60 fps source"; "roughly 10 of 14 players" | 1080p60 avc1 (format 299) confirmed available; 59.94 fps; visibility replaced with measured figures |
| `09-decision-record.md` | "The highest-leverage unknown" = football markings | Answered; replaced with the new highest-leverage unknown, the 120 vs 110 yd field length |
| `10-getting-the-footage.md` | Duplicate-frame test put `-ss` after `-i` (decodes 25 minutes before measuring) | `-ss` before `-i`; points at `tools/fpscheck.py` |
| `10-getting-the-footage.md` | Format selection advice | Records that format `299` (1080p60 avc1, 5.40 GiB) exists, so no AV1 compromise is needed |
| `04-milestones.md` | M0 open | Marked done, with the three findings that move other milestones |
| `04-milestones.md` | M2: "D-FINE or RT-DETRv2 + SAHI tiling" | SAHI demoted to measure-first, with the measured pixel sizes as the reason |
| `04-milestones.md` | M4 gate: "`observed` fraction within 5 points of the visible fraction measured in M0" | Says *which* figure — this possession's ≈ 88 %, not the broadcast-wide 74 % |
| `07-licenses.md` | — | Rows added for numpy, opencv-python, pillow, yt-dlp, pypdf, uv, and a note that the installed ffmpeg is a **GPL** build invoked as a separate process — with the two constraints that follow (never vendor the binary, never link the libraries) |

### New open questions logged to `08-risks.md`

1. **Is this a 120 yd or a 110 yd field?** (§2.3.3 exception.) Highest-leverage unknown in the
   project now. Resolvable in M1 from the centre circle's absolute scale.
2. **Which corner is the field-frame origin, and is the field frame possession-relative?**
   `calibration.json` stores a homography to "field yards", but the field frame flips with
   `attacking_direction`, so the same shot means two different things in two possessions.
   Recommendation: store a venue-fixed frame in `calibration.json` and move the flip into
   `derive`. Not changed unilaterally — it is an M1 decision.
3. **Referees are inside both the field bounds and the dark colour cluster.** The reject
   class in AD-3 needs to handle them explicitly, not incidentally.
