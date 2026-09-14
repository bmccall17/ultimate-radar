# 29 — Finding possessions worth cutting

**A possession is 20–40 s of somebody's attention for the rest of its life, and the
cheapest moment to reject one is before any of it.** `docs/10-getting-the-footage.md` § 4
says so, and it says so because p0002 was cut, calibrated, detected, tracked and published
before anyone said out loud that it was an out-of-bounds pull with no play in it.

This is what happens when those two filters are measured off the broadcast instead of
remembered.

```bash
python -m tools.scout goals  --out eval/m9/goals.json
python -m tools.scout score  --goals eval/m9/goals.json --out eval/m9
python -m tools.scout sheet  --start 2394 --end 2424 --out eval/m9/sheets
```

---

## Filter 1 — something happens, and the scoreboard already knows when

Every goal is a score change, and the score sits in a fixed box at the bottom of the
frame. Scanning **keyframes only** reads the whole 2 h 22 m in about a minute — a keyframe
every 4.6 s, which is finer than the thing being measured — and a 4 fps pass around each
change pins it to a quarter second.

The digits are not OCR'd. The bug is rendered identically every time, so identical scores
produce identical bitmaps; they cluster into 24 and 28 patterns, and the clusters are
labelled once by eye. Two look-alike pairs at this size (8/3, 13/18, 14/19) never formed
their own cluster and came back as the other member, which does not move a goal's
timestamp and would badly misreport a scoreline — so the reconstruction repairs them from
the constraint that a score only ever rises by one.

**52 score changes. Final 24–28 Minnesota.** The check that could have contradicted it:
every change moves exactly one team by exactly one, and 24 + 28 = 52. Both hold.

## Filter 2 — the paint, asked the question calibration will ask

Not "is there white on the grass". `find_centre_circle_ransac` and `find_halfway_line`,
M1's own detectors, on eight frames spread across each window. A frame where both are
found is a frame that can be calibrated.

It is a pre-check and cannot promise M1 will pass — `docs/28` is the story of a
calibration that looked healthy in every in-possession signal and was 6.8 yd out — but it
costs seconds and it rejects the hopeless.

---

## The two things the first version got wrong

Both were caught the same way: by running the method over a window somebody had already
chosen by watching, and comparing.

### The score bug is not the goal. It trails it by 9 to 15 seconds.

The bug updates over the replay, not over the catch. A window anchored to it walks
straight through the cut into a celebration close-up — which is precisely what
`docs/22-m7-preflight.md` records p0003's first cut doing, 6.4 s past the boundary.

**The game clock is the goal.** UFA stops the clock on a score, so the last second it
ticks is the catch, to within its own one-second resolution. It is not read either — only
watched for the moment it stops changing.

| | hand-written in `clip.json` | clock freeze |
|---|---|---|
| p0003 | "the point ends in a Sol goal" at ~1617 | **1616.85** |
| p0001 | "the point ends in a Sol goal at ~7330 s" | **7329.57** |

### A phase-correlation pan measurement, deleted rather than shipped

`attacking_direction` must not be inherited from the previous possession, and it is not
readable off a contact sheet: a pan looks exactly like play moving, and the two are
opposite. So the first attempt measured the camera's own pan by phase correlation on the
grass — the same argument `tools/pancheck.py` makes for using it as an independent check.

It returned a **positive** drift for both p0001 and p0003. Their calibrations' own pan
angles go **opposite ways**: p0001 −22.47° → −6.28°, p0003 +11.80° → −10.54°. The
measurement was not measuring the pan, so it is not in the tool.

**Where the direction is settled instead: `ur.possess`, where the tracker already knows.**
It fits the drift of the offence centroid over the possession and reports it against what
`clip.json` claims.

Not the obvious test. "Does the offence finish inside the endzone it was attacking" is
decisive and needs an absolute field x, and the along-pitch offset is unresolved
(`docs/08-risks.md` #5, `docs/28` "what it does not fix"). On p0003 — a possession that
*does* end in a goal — the leading receiver finishes at **x = 87.4 yd** with the endzone
nominally at 100. The endzone test called that no goal, and it was the offset lying, not
the tracker. A difference cancels the offset out.

It flags rather than vetoes, because a possession can genuinely go backwards. p0001 does:
−8.4 yd while legitimately attacking +x, and it says so on every run.

---

## Three gates that were not gates

All the same shape as the eight bugs in `HANDOFF.md` § 8 — something reporting success
while being wrong.

**`ur/calibrate/accept.py` printed `FAIL` and exited 0.** `docs/28` moved the
known-geometry gate *inside* `tools/pipeline.py` specifically so it could not be
forgotten, and the pipeline stops at the first non-zero exit. It never got one. A
possession could fail M1 acceptance and be detected, tracked, viewed and published
anyway — the whole of `docs/28` again, one layer up. So could `tools/m4_structure.py`,
which was also only ever run by hand, on p0001.

**`tools/pipeline.py` ran `ur.possess` before `ur.disc`.** `ur.disc` reads
`possession.json` and `ur.possess` reads `disc.json`, so on a possession that had never
been through the chain the disc was solved and nothing carried it back. The symptom is a
viewer saying "no disc position in this data" with `disc.json` sitting next to it.
`ur.possess` runs again after; the loop is not circular, because `ur.disc` uses only the
player positions and the second pass does not change them.

**Every acceptance stage defaulted its evidence to p0001's directory.** `eval/m1`,
`eval/m4`. Running one on another possession would overwrite the evidence the write-ups
cite. The pipeline now gives each stage a directory keyed on the possession.

---

## What was cut

Of 52 goals, **49 sit at the end of a shot long enough to hold a 30 s possession.** Ten
were put up with contact sheets; four were chosen.

| | broadcast s | offence | ends in | M1 mean | M1 max | `m4_structure` |
|---|---|---|---|---|---|---|
| **p0004** | 2394.0–2424.0 | Sol | Sol goal | **0.1359** | 0.4551 | 0 problems |
| **p0005** | 3039.2–3069.2 | Wind Chill | Chill goal | **0.2292** | 1.2771 | 0 problems |
| p0006 | 3572.6–3602.6 | Wind Chill | Chill goal | 0.3485 | 1.2068 | 0 problems |
| p0007 | 5679.4–5709.4 | Sol | Sol goal | 0.2913 | 0.7970 | 0 problems |

All four pass every stated gate. **Two of them are published and two are not**, and the
reason is not in that table.

### M1 acceptance is a measurement of the frames that already passed the confidence gate

`accept.py` samples its held-out frames from the frames with confidence ≥ 0.5. On a
possession where the gate rejects most of the footage, that is a measurement of the good
part.

| | frames the calibration accepts | anchored slot-frames | median roster in shot | frames with nothing at all |
|---|---|---|---|---|
| p0001 | 92 % | 72 % | 11 of 14 | 8 % |
| p0003 | 72 % | 52 % | 9 of 14 | 28 % |
| **p0004** | 64 % | 45 % | 8 of 14 | 36 % |
| **p0005** | 71 % | 47 % | 8 of 14 | 29 % |
| p0006 | **26 %** | 18 % | **0 of 14** | **74 %** |
| p0007 | **38 %** | 26 % | **0 of 14** | **62 %** |

p0006's 0.35 yd is six testable frames inside a 139-frame span of 450. The montage is
honest — the ellipse is on the real centre circle, the halfway line is the real halfway
line — and the number is a true statement about those six frames and says nothing about
the other 400. p0004 and p0005 sit just below p0003, which was already published. p0006
and p0007 are nowhere near it: the median frame has no located player on it at all.

**So the acceptance JSON now carries `usable_fraction`, `testable_frames` and
`testable_span_frames`, and the command prints a warning below 50 %.** It is not a gate —
where to put that threshold is a product decision — but the number can no longer be absent
from the page it is quoted on. This is `docs/28`'s lesson at one remove: a test that is
only ever run on the possession it was written for is a test of that possession, and an
acceptance that only ever samples accepted frames is an acceptance of those frames.

### Why p0006 and p0007 fail, and it is a known unbuilt thing

275 of p0006's 450 frames carry the same note: *"residual 0.00000 yd is below what painted
lines physically allow — the fit has collapsed, not converged"*, with `n_line_px: 0` and a
focal length of 3 × 10¹⁵. These possessions spend most of their length framed on the
endzone, where the centre circle is out of shot or reduced to a short arc, and the solve
runs away. The collapse detector catches every one of them and zeroes the confidence,
which is the right behaviour and is why nothing wrong was published.

`docs/28` § "what it does not fix" already names the answer, and it is not a threshold:
*"a frame with no fit at all stays rejected… AD-4's amendment already names the answer —
keep the mosaic for stretches where too little paint is visible — and the mosaic fallback
is still not built."* That is what caps p0006 and p0007.

### The pre-filter was looking at the crowd

`scout`'s paint check ran M1's detectors on the whole frame. Calibration never does: it
builds a registration mask and zeroes everything above the horizon. Without that, the
banners, tents and a video board full of white are all candidate paint, and
`find_centre_circle_ransac` will fit a conic to them.

Scored against the six possessions whose calibrations are now known, the unmasked version
cannot separate a good possession from a bad one. Masked, it can:

| | unmasked | masked | frames that calibrate |
|---|---|---|---|
| p0001 | 0.88 | 0.50 | 92 % |
| p0003 | 0.62 | 0.62 | 72 % |
| p0004 | 0.75 | 0.62 | 64 % |
| p0005 | 0.50 | 0.62 | 71 % |
| p0006 | **0.62** | **0.12** | **26 %** |
| p0007 | 0.50 | **0.25** | **38 %** |

Unmasked, p0003 and p0006 both score 0.62 and one of them is unusable. Masked, the four
that calibrate score 0.50–0.62 and the two that do not score 0.12 and 0.25. Six
possessions is a thin calibration and p0001 is badly under-predicted at 0.50 against 92 %,
so this ranks and rejects rather than estimating.

### The attacking direction, measured

All four were ingested `+x` provisionally and all four were contradicted:

| | offence centroid drift | direction |
|---|---|---|
| p0004 | −21.0 yd | −x |
| p0005 | −27.4 yd | −x |
| p0006 | −16.9 yd | −x |
| p0007 | −9.2 yd | −x |

Each of the four ends in a goal by the declared offence, so the direction they moved is
the endzone they attacked. p0003, which also ends in a goal, drifts **+20.6 yd** and is
`+x`; the two disagree because they are different points, and in ultimate the teams switch
which endzone they attack after every goal.

Re-cutting to fix the field cost nothing, which is worth recording because it was not
obvious: `ur.ingest` is deterministic and only wipes `frames/`, so all four clips came back
**byte-identical by `clip_sha256`**, and `ur.calibrate.accept` re-run on p0004 reproduced
0.1359 yd exactly. Only `clip.json` and `possession.json` changed.

p0001 also reports a disagreement — −8.4 yd against a declared `+x` — and is left alone.
It does not end in a goal; its `clip.json` says the point ends in a Sol goal at ~7330 s,
outside the clip. That is why the check flags rather than vetoes.

## Honest limits

- **A window that ends in a goal is not the same as a window containing one possession.**
  Thirty seconds before a goal usually is, and sometimes contains a turnover, in which
  case `offense` in `clip.json` is right for only part of it. Nothing here detects that;
  the contact sheet is what a person looks at, and `ur.disc` now warns when a human tag
  names somebody who is not on the offence, which is the same fact arriving late.
- **Possessions that end in a turn are not found at all.** The scoreboard only knows about
  goals. `docs/10` § 4 asks for "a score or a turn" and this finds half of that.
- **The cut threshold is arguable and known to be.** `tools/cuts.py` says a hard cut and a
  whip pan both score high, and the 0.20–0.35 band on this footage contains both the
  dissolve into p0003's replay (0.235, a real boundary) and three camera moves inside
  p0001's single 104 s shot (0.23–0.29, not boundaries). Windows are rejected above 0.35
  and flagged in the band, which is why a person looks at the sheet.
- **The digit labelling is by eye and is not portable.** `SCORE_L` and `SCORE_R` are a
  labelling of this broadcast's clusters in this scan's order. A different game needs them
  redone, and `scout` says so when the count does not match rather than quietly
  mislabelling.
