# 11 — Review of M0

Independent check of the M0 handback, done by re-reading the primary sources and
re-measuring from the extracted frames rather than from the report. Numbers below were
produced by `tools/regcheck.py` and by reading `eval/ufa-rulebook-2025-v13.pdf` directly.

**Verdict: M0 is genuinely complete and the work is sound.** The evidence trail is real, the
report's figures reproduce, and two of the three carried-forward concerns are correctly
identified. One finding is not adequately supported. One hazard that lands squarely on M1 is
missing, and it is the kind that silently produces plausible wrong answers rather than
errors.

---

## Confirmed independently

**Field dimensions — settled, and the spec was right.** UFA Rule Book v13 §2.1.1, read from
the PDF: *"The field is a rectangle measuring 53 ⅓ yards wide by 80 yards long plus 20-yard
end zones on each end."* 120 × 53⅓ yd total, 80 yd playing proper. `clip.json` is correct.
`docs/08-risks.md`'s "corroborated only by two secondary sources" caveat can now be closed —
the primary source is in the repo.

**§2.3.3 is a real risk, correctly escalated.** The 110-yard venue exception exists and moves
the brick to 15 yd. Keeping it open rather than assuming was right.

**The centreline-marks insight is the best thing in the report.** Enumerating the seven
centreline marks and ten pylons from §2.2.1/§2.3.1/§2.3.2 — including the reverse bricks,
which no project doc had — turns a sparsely-marked field into a well-conditioned calibration
target. That belongs in `02-architecture.md` § AD-4, not only in the footage report.

**The soccer-pitch finding and its optimistic reading are correct.** A centre circle is a
conic of exactly known radius; gridiron hash marks vary by level and would have been worse.

**Ingest is properly engineered.** `start_verification` does not assert the start offset, it
*proves* it — eleven candidate source frames scored by mean absolute grey-level difference,
best 3.904 against runner-up 5.938, margin 2.03. `clip_frames_sync` does the same for the
`frames/` ↔ `clip.mp4` index relation, asserted against real pixels at two points. Both are
the kind of check that is usually skipped and later costs a week.

**The `frames/` vs `clip.mp4` offset is a real trap, correctly caught.** A silent one-frame
offset would put every overlay on the wrong moment with nothing to signal it.

**Referee contamination is real.** Frame 000180 has two referees standing inside the field of
play in black-and-white stripes, plus two seated photographers on the far touchline inside
the field polygon. The out-of-bounds filter will not catch any of the four.

> Worth adding: referee stripes are separable from Wind Chill's flat navy by *texture*, not
> colour. Torso luminance standard deviation is high for stripes, low for a solid kit — a
> one-line test that works while the referee is inside the field, where the geometric filter
> does not.

---

## Not adequately supported

**"Jersey numbers are on the back only, both kits."**

UFA Rule Book v13 **§3.2.3**: *"Each player shall be conspicuously numbered on the back of
the jersey **and the front of the uniform**."* The report checked §2.3.1 in the same PDF but
not this rule.

So the finding — based on three front views — contradicts the governing rule. Either these
kits do not comply, or the sample missed the numbers. Three frames is too thin to conclude
either, and the conclusion carries real weight: it is what "halves the frames OCR can ever
succeed on" rests on, which in turn sets M5's expectations.

Note also that both crops cited as evidence of back numbering (`q4_front_chill.png`,
`q4_front_sol2.png`) show players facing **away** from the camera, and are named "front".
Worth a second look.

**Suggested re-check, cheap:** sample 30–50 crops of players demonstrably facing the camera —
a marker on a thrower, players walking back after a goal, the pull line-up — and look for a
chest number or a number on the shorts (§3.2.3 says "front of the uniform", not "front of the
jersey", which permits the shorts). Settle it before M5 plans around a halved frame budget.

---

## Missed, and it lands on M1

**Whole-frame image registration reports a static camera on this footage.**

Three things in every frame move at three different rates:

| Region | Motion, frames 000000 → 000120 | Share of frame |
|---|---|---|
| Playing surface (the ground plane) | **338 px** | 48 % |
| Stands, barrier, buildings (off-plane parallax) | 227 px | 40 % |
| Score bug and sponsor banner (rendered on top) | **0 px** | 12.6 % |

The broadcast graphics are the strongest alignment signal in the image. Phase correlation
peak response on the sponsor banner alone is **0.867** and on the score bug **0.973**; on the
playing surface it is **0.054**. The graphics win by more than an order of magnitude.

Measured over eleven consecutive frame pairs from the possession, two seconds apart:

- whole-frame registration returned |dx| < 1 px — *a static camera* — on **10 of 11 pairs**
- masked to the playing surface, the same method recovered the real pans: 38, 56, 66, 77,
  113, 121, 173, 270, 289, 360 px

This is not a crash. It is a confident, plausible, wrong answer, and every downstream number
inherits it. It hits three places at once:

1. **AD-4's shot mosaic.** Frame-to-mosaic offsets are hundreds of pixels, which is exactly
   where the graphics dominate hardest. The mosaic would build as though the camera never
   moved.
2. **Any GMC/ECC-based tracker fallback** (BoT-SORT's ORB/ECC module) has the same exposure.
3. **Ground-plane homography fits** that draw correspondences from the stands. The stands are
   not on the ground plane — their 227 px is parallax, not camera motion — so a homography
   fitted through them is wrong even when it converges cleanly.

**Fix, and it is small:** every registration, matching and motion-compensation step runs on a
mask, never the raw frame. `eval/m1/registration_mask.png` is a working first version —
48 % of the frame, excluding the banner (y ≥ 980), the score bug (y 915–990, x 500–1420) and
everything above the horizon (y < 430). Add player boxes to it once M2 exists.

Two caveats on that mask, both cheap to remove: the horizon cut is a fixed row and will be
wrong when the camera tilts, so derive it from the calibration once one exists; and the score
bug and banner are fixed in image space but their *content* changes (the banner rotates ads
between t = 15 s and t = 16 s), so detect the regions by low temporal variance plus high
texture rather than hard-coding, and re-check per broadcast.

`tools/regcheck.py` reproduces every number above.

**One more thing the numbers imply.** Peak response on the masked surface is weak — 0.008 to
0.468 across those eleven pairs, with one negative. Mown turf is close to featureless and its
stripes give an aperture problem along their direction. Dense correlation will be marginal on
this footage; the painted lines, the centre circle and the pylons are carrying the
information. That is an argument for the feature/line-based path over the mosaic, and it is
worth measuring at the top of M1 before committing to AD-4.

---

## The unmet criterion — a second opinion

M0 declined to claim a scheme change or poach without watching the clip. That was the right
call, and the caution holds up: a crude colour-blob detector over the twelve sampled frames
recovers only 3–8 of the 14 players, which is not enough to distinguish "a defender is ten
yards from anyone" from "the offender was not detected" — the exact failure the tool exists
to avoid. No tactical claim is available before M2.

By eye, across frames 0, 120, 180, 240 and 345: **this reads as a straight person defence
throughout.** At t = 12.0 s all fourteen players are in frame as seven paired matchups, none
more than about four yards apart (figure: `eval/m1/m0-review.png`, top panel). I see no poach,
and I would expect the extended cut to the goal at ≈ 7330 s not to produce one either.

**Recommendation — split the requirement rather than re-cut.** p0001 is an unusually good
*calibration and detection* clip: a single shot, the centre circle and halfway line in every
frame, 88 % player visibility, and one moment with all fourteen players separated. Keep it for
M1–M3. Then choose a **second** possession specifically for M4's tactical validation, picked
for a zone look or a visible poach. One clip does not have to satisfy both jobs, and forcing
it to will cost a good calibration clip.

---

## Amendments to make

1. **`docs/02-architecture.md` § AD-4** — add: registration operates on a masked region, never
   the whole frame; the mask excludes rendered graphics, everything off the ground plane, and
   (from M2) players. Add the centreline-marks enumeration from the footage report.
2. **`docs/04-milestones.md` § M1** — add an acceptance criterion: *whole-frame and masked
   registration are compared on at least ten frame pairs, and the masked result recovers pans
   the whole-frame result misses.* Ten minutes, and it stops the failure above from reaching
   M4 disguised as a tracking problem.
3. **`docs/08-risks.md`** — close the field-dimension item (primary source now in repo);
   re-open the jersey-number item against §3.2.3; add the registration-mask hazard.
4. **`docs/05-uncertainty.md`** — the fixture assumed ~10/14 visibility. M0 measured 10.4/14
   in wide shots but 8.3/14 across all live play. Use 8.3 when sizing how much of the viewer's
   time is spent showing estimates.
5. **Housekeeping** — the handback is right that this is not a git repository. `git init` and
   commit before anything else; `eval/m0/visibility_counts.json` is hand-labelled data and is
   currently one accident away from gone.
