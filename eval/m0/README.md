# M0 evidence

Everything `docs/00-footage-report.md` cites. Kept in the repo so the report's claims can be
disputed by looking rather than argued about — particularly the judgement calls (jersey
legibility, player counts, which blobs are people).

| Path | What it is | Report section |
|---|---|---|
| `fpscheck.json` | mpdecimate kept-frame ratios over eight 10 s stretches | Q1 |
| `uniform_sheet.jpg` | 36 frames, one every 4 min across the game | Q2, Q6 |
| `random_sheet.jpg` | the 40 seeded-random frames the visibility count comes from | Q6 |
| `paint/` | paint-detector overlays on three wide frames — **the evidence that there are no yard lines** | Q2 |
| `q2_lines_lower.png`, `q2_far_side_t1800.png` | gridded line crops, daylight and night | Q2 |
| `q2_pylon_right.png` | an orange pylon sitting on a line intersection | Q2 |
| `rulebook/p7_0_X98.jpg` | the UFA rulebook's own field diagram, extracted from the PDF | Q2 |
| `q3_*.png` | gridded 1:1 crops the player heights were measured off | Q3 |
| `heights.json` | automated blob height distribution — **contaminated by crowd, see the report** | Q3 |
| `jersey/`, `q4_jersey_sheet.png` | 47 crops at a fixed 4× magnification | Q4 |
| `q4_front_chill.png`, `q4_front_sol2.png`, `q4_chill_front.png` | the back-number-only finding | Q4 |
| `teamcolour/` | 2-means cluster stats plus a frame with boxes coloured by cluster | Q5 |
| `blobs_live/` | 22 live-play frames with blob boxes — what the player counts were read off | Q3, Q6 |
| `visibility_counts.json` | **the hand counts themselves**, per frame, with the counting rules | Q6 |
| `cuts_full/` | every scene-change candidate in the game, with scores | Q7 |
| `cutcheck_sheet.jpg` | frames either side of four detected cuts — threshold validation | Q7 |
| `pick_a_sheet.jpg`, `pick_b_sheet.jpg` | the point the chosen possession was selected from | Q8 |
| `q8_possession_sheet.jpg` | the chosen possession at 1 Hz | Q8 |
| `p0001_blobs/` | annotated first and late frames of the possession | Q6, Q8 |
| `../ufa-rulebook-2025-v13.pdf` | primary source for the field dimensions | Q2 |

The frames these were cut from live in `survey/`, which is gitignored along with `raw/` and
`work/` — regenerate with the commands in the report's Method section. Everything is seeded
(`20260827`), so the same frames come back.

## A caution about the automated numbers

`heights.json` and the blob boxes come from a classical green-segmentation detector written
for M0 only (`tools/measure.py`). It has no notion of what a person is beyond shape, so it
finds bleachers, referees, camera operators and advertising hoardings alongside players. It
was good enough to *magnify* players for hand counting and to sample torso colours in bulk.
It is not good enough to quote. Every number in the report that matters was measured by hand
off the crops in this directory; where an automated distribution is cited, the report says so
and says what it is contaminated by.
