# 08 — Risks, unknowns, and open questions

## Verified, unverified, and blocked

**Verified in this design pass.** Licences in `docs/07-licenses.md` (repo LICENSE files,
September 2026). The source video's identity and shape: *Pro Frisbee Semifinals: Austin Sol
vs Minnesota Wind Chill | FULL GAME BROADCAST | August 27, 2026*, UFA Ultimate Frisbee
Association channel, 2:22:27, AV1, 60 fps available; description names Breese Stevens Field,
Madison WI. Team facts: Wind Chill founded 2013, colours metallic blue / black / white, 2024
champions; Austin Sol founded 2016. From the video's own title card, the Sol wear light kit
and the Wind Chill dark — which is what AD-3 rests on.

**Resolved in M0 (2026-09-12)** — all measured on the real broadcast; evidence and method in
`docs/00-footage-report.md`.

- **Field dimensions: confirmed from the primary source.** UFA Rule Book v13.0 §2.1.1,
  "53 ⅓ yards wide by 80 yards long plus 20-yard end zones on each end". PDF kept at
  `eval/ufa-rulebook-2025-v13.pdf`. *But see the new open question 1 below — §2.3.3 allows a
  110 yd field by exception, and whether this venue uses it is unsettled.*
- **Brick mark: confirmed at 20 yd** (§2.3.1). The rulebook also defines **reverse brick
  marks** 10 yd behind each goal line (§2.3.2), which no project doc had.
- **Broadcast rig.** 1920×1080 h264 High, **59.94 fps genuine** (mpdecimate keeps 98.9 % of
  frames), 5.4 Mbps. 403 hard cuts over the game (2.83/min) — but **every live-play shot ran
  36–174 s, median 96 s**, so a possession typically contains *zero* cuts. Hard zooms within
  a shot are the real registration hazard.
- **Football markings at Breese Stevens: NO.** It is a soccer pitch — centre circle, halfway
  line, penalty and goal areas — with ultimate paint and pylons over the top. This changes
  the M1 plan for the better: calibrate to the soccer frame, which is exactly specified, then
  apply one fixed venue transform.
- **Visibility: 10.4 of 14 in wide shots, confirming the modelled 10.1**; 8.3/14 across all
  live play; worst observed frame is 1, not 3. About 48 % of the broadcast is not a usable
  field shot at all.
- **Player pixel size: 50–70 px at the widest live framing, 80–130 px typical**, ~460 px in a
  tight shot — roughly twice the 25–45 px this project assumed. SAHI tiling is demoted from
  required to measure-first.
- **Team colour: ΔE 36.6 between kits.** Not a risk. The reject class is.

**No longer blocked.** The earlier design pass could not reach YouTube media, so every claim
about pixel sizes, legibility and framing was modelled. The file has now been downloaded
(format 299, 1080p60 avc1, 5.95 GB) and 76 frames inspected at pixel level.

## Risks that could sink round one

**Calibration on a soccer-marked field.** *(Rewritten after M0 — the original risk was
"sparsely-marked field", and the venue turns out to be the opposite.)* The pitch is richly
marked, just with the wrong sport's geometry: centre circle, halfway line, penalty and goal
areas, corner arcs. The ultimate paint is present but thin and low-contrast, and in a typical
wide shot the only paint visible is the soccer circle and halfway line.

*Plan.* Calibrate to the **soccer** frame — its dimensions are exactly specified (centre
circle radius 9.15 m; halfway line through the centre, perpendicular to the touchlines) and
its features are visible in far more frames than the ultimate paint. Then apply a **single
fixed venue transform** from the soccer frame to the ultimate frame, established once from a
frame where an ultimate line and a pylon are both visible, and reused for every shot and
every possession at this venue.

*The residual risk is the venue transform itself*, which is one estimate that everything
depends on. Estimate it from several frames and check the spread, rather than from one.
*Remaining mitigations, unchanged:* use the mosaic (AD-4) so correspondences only need to
exist somewhere in the shot, not in every frame; add stadium fixtures — pylons, advertising
boards, light poles — as additional fixed world points; fall back to a fixed camera-position
model and solve only pan/tilt/zoom per frame, which is three unknowns instead of eight and is
valid because the camera does not move.

**Deep players are invisible when they matter most.** The players who leave the frame are the
deep defenders, and the huck at the end of a possession is decided by exactly them. No amount
of tracking fixes this; only the honesty model and human correction do. If the M0 visibility
count is much worse than 10/14, consider scoping round one to possessions that stay in the
handler set, and say so.

**Same-team identity swaps.** Expected, not preventable. The plan is detection plus one-click
repair (M5). The risk is that they are *frequent* enough to make correction tedious. If M4
shows more than a handful per possession, tighten the association gate — better to drop an
association and go `predicted` than to make a confident wrong one.

**Foot-point error under occlusion.** Bottom-centre of a box is wrong when a player is
partially occluded or airborne, and a half-yard of foot error shows up directly in the
separation numbers. Measure it in M3 before deciding whether pose keypoints are worth it.

**The tool convinces someone of something false.** The worst outcome available. It happens if
sigma is under-estimated, if a metric reports `measured` when an input was inferred, or if the
ghost drift is drawn confidently. The sigma-calibration gate in M4 and the provenance rules in
M5 exist for this; treat a failure of either as a release blocker, not a polish item.

## Things deliberately not built

Automatic disc tracking; automatic scheme naming beyond the two measured quantities;
handedness inference and therefore force naming; whole-game processing; player identification
by face or name; any tactical judgement the tool would be asserting rather than measuring.

## Open questions

*(Append here as they come up, rather than stalling.)*

1. Does the broadcast cut between multiple cameras within a possession? If so, does the
   second camera have a usable view of the field, or is it a tight reaction shot to be
   skipped entirely?
2. How should a possession that ends in a turnover be modelled — one possession object with
   the teams' roles swapping, or two adjacent possessions? Two is simpler; confirm that is
   what a coach wants when reviewing a turn.
3. Is 15 Hz enough for the separation-at-release measurement, given the disc leaves the hand
   in well under a frame? Consider sampling events at the native 60 fps even if tracking runs
   at 15.
4. Should `confirmed` positions be exported as training labels automatically, or only on an
   explicit "contribute this possession" action? Defaulting to automatic collects more data;
   defaulting to explicit is the better habit.

*Added in M0 (2026-09-12):*

5. **Is this a 120-yard field or a 110-yard one?** UFA rule §2.3.3 allows a 110 yd field "if
   a special exception has been granted … due to venue limitations", with the brick mark
   moving from 20 yd to 15 yd. Breese Stevens is a soccer pitch, and soccer pitches run
   110–120 yd, so this is a live possibility rather than a technicality. The broadcast camera
   never frames both endzones at once, and the venue publishes no dimensions.
   **This is now the highest-leverage unknown in the project: every field coordinate depends
   on it.** Resolve it in M1 the first time a homography exists — the soccer centre circle
   gives absolute scale (radius 9.15 m = 10.006 yd), so measuring goal-line separation is
   then a one-line check. Until then `clip.json` carries the rulebook default, 120 yd, which
   may be wrong.
6. **Is the field frame possession-relative or venue-fixed?** `calibration.json` stores a
   homography into "field yards", but the field frame's origin and `+x` are defined by the
   direction of attack, so the same physical shot means two different things in two
   possessions attacking opposite ways. Recommendation: store a venue-fixed frame in
   `calibration.json` and move the flip into `derive`. Not changed unilaterally — it is an M1
   decision and it touches a data contract.
7. **Referees sit inside both the field bounds and the dark colour cluster.** They wear black
   and grey vertical stripes, stand on the field, and appear two or three at a time in most
   live frames. AD-3's reject class has to handle them explicitly. The same applies to Wind
   Chill's light-blue alternate kit, worn on the sideline, which lands in the *Sol* cluster —
   a cross-team misassignment risk, which is the error class AD-3 exists to eliminate.
8. **A possession containing a camera cut is rare** (Q7), so M1's multi-shot path will not be
   exercised by accident and needs a deliberately chosen second clip. Unverified candidates:
   the short shots interrupting long ones at t ≈ 2893.9–2901.2 and t ≈ 5645.5–5652.9.
