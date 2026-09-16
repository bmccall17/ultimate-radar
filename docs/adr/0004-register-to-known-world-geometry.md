# AD-4 — Register to known world geometry, not to a neighbouring frame

> **Amended 2026-09-12, after M0 and its review.** The decision's *reason* is unchanged and is
> the important part: **never chain frame-to-frame, because the error accumulates monotonically
> and nothing signals it.** Two measurements changed the preferred means.
>
> **(a) Registration must run on a mask, never the whole frame.** The rendered score bug and
> sponsor banner occupy 12.6 % of this broadcast's frame, move 0 px, and dominate phase
> correlation (peak 0.973 and 0.867, against 0.054 for the playing surface). Whole-frame
> registration reported **a static camera on 10 of 11 frame pairs** while the camera was
> actually panning 38–360 px. The mask excludes the rendered graphics, everything above the
> horizon (the stands are off the ground plane, so their motion is parallax, not camera
> motion), and — once M2 exists — the players. Derive the horizon from the calibration rather
> than hard-coding a row, and find the graphic regions by low temporal variance plus high
> texture rather than fixed boxes. `tools/regcheck.py` reproduces the failure.
>
> **(b) The per-frame camera fit is now primary and the mosaic is the fallback.** Peak
> response on the *masked* playing surface is only 0.008–0.468: mown turf is close to
> featureless, and its stripes give an aperture problem along their own direction. A mosaic
> built by dense correspondence over that is marginal. But the camera is a fixed broadcast
> hard camera — it pans, tilts and zooms, and does not translate — so each frame is **three
> unknowns (pan, tilt, focal), not eight**, solvable directly against world geometry that is
> exactly specified: the soccer centre circle (radius 9.15 m), the halfway line, and the
> penalty area when in shot. Fitting every frame independently to known world geometry
> accumulates no drift at all, which is what AD-4 was protecting. `docs/03-data-contracts.md`
> already anticipates storing pan/tilt/focal per frame, and `docs/08-risks.md` already listed
> this as a mitigation. Keep the mosaic for stretches where too little paint is visible.

The original decision, which still governs where the amendment is silent:

Split the clip at camera cuts. Within a shot, build a background mosaic (players masked
out), register every frame to that mosaic, and register the mosaic **once** to field
coordinates using human-clicked correspondences.

*Why.* Chaining frame-to-frame homographies accumulates drift monotonically; after twenty
seconds of panning the radar is visibly wrong and there is no signal saying so. Registering
every frame to a single reference makes the error bounded rather than accumulating, and it
reduces the human's job from "click points on many keyframes" to "click points once per
shot". A possession typically contains one to three shots.

*Consequence.* Zoom range within a shot can be large; the mosaic must be built at the widest
zoom available in that shot, and matching should use a scale-robust matcher. Use LoFTR
(Apache-2.0) or LightGlue with **DISK or ALIKED** features — *not* SuperPoint, whose weights
are non-commercial research-only.

### The world geometry available at this venue

Even with no gridiron paint, a UFA field on a soccer pitch is a well-conditioned target.
Exact positions, from the rulebook (§2.2.1, §2.3.1, §2.3.2) and the FIFA laws:

- **Seven centreline marks**, at X = 10 (reverse brick), 20 (goal-line centre), 40 (brick),
  60 (midfield), 80 (brick), 100 (goal-line centre), 110 (reverse brick), all at Y = 26.667.
- **Ten pylons** — the four endzone back corners, the four goal-line ends, and the centre of
  each back line.
- **Soccer centre circle**, radius 9.15 m = 10.006 yd, and the **halfway line** through its
  centre perpendicular to the touchlines. These are the two features visible in the most
  frames, and the circle is a conic, so it constrains five degrees of freedom by itself.
- **Penalty area** (16.5 m deep, 40.32 m wide), **goal area** (5.5 m, 18.32 m), **penalty
  spot** (11 m) and **penalty arc** (9.15 m) when the camera is near an end.

*Measured in M0, and it changes the shape of this problem.* A possession contains **typically
one shot, not one to three**: every live-play frame sampled sat inside a shot of 36–174 s
(median 96 s), and none was shorter than a possession. The human cost of AD-4 is therefore
one set of clicks per possession. But the zoom warning above is now the live risk rather than
a theoretical one — at t ≈ 7326 s the camera whips from a wide field shot to a tight catch
and back *within a single detected shot*, which no cut detector will flag and which will
break naive frame-to-frame registration. Build the mosaic at the widest zoom and verify
against that case. See `docs/00-footage-report.md` Q7.

*Also measured in M0:* this venue has **no football yard lines or hash marks** — it is a
soccer pitch. The richest available geometry is the soccer centre circle and halfway line,
which are visible in far more frames than the ultimate paint is. The plan that follows is to
calibrate to the *soccer* frame, whose dimensions are exactly specified, and apply one fixed
venue transform into the ultimate frame, established once. See `docs/00-footage-report.md` Q2.
