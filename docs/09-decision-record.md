# 09 — Decision record

A one-page orientation. Written 2026-09-12, before any code existed. If you read nothing
else first, read this, then `04-milestones.md`.

Target footage: UFA 2026 semifinal, Austin Sol vs Minnesota Wind Chill, 27 Aug 2026, Breese
Stevens Field, Madison WI. YouTube `IDnoyd4cKfM`, 2:22:27. **Downloaded as format `299+140` —
1920×1080, h264 (avc1) High, 59.94 fps, 5.4 Mbps, 5.95 GB.** The AV1 compromise the docs
anticipated was not needed: a 1080p60 avc1 stream is offered.

## State at handoff

*Updated 2026-09-13, after M6. `HANDOFF.md` is the operational version of this; what follows
is the one-paragraph shape of it.*

- **M0 to M6 are built.** Ingest, calibration, detection, team assignment, tracking, identity
  and corrections, and the viewer. M7 — sharing and a second possession — is not started.
- **Three results are not clean, and all three are recorded rather than hidden.** M5's jersey
  gate gets 3 of 7 against a gate of 5, and fails on the footage rather than on the plumbing.
  M4's per-player recall is **0.8932** with its threshold deliberately unset — not for the
  reason recorded until 2026-09-14 (that closing the gap means readmitting referees; that was
  measured and is false) but because the statistic is chaotically sensitive at this sample
  size, moving a full standard error under association changes that should not matter.
  M6's `file://` criterion and its comprehension test both need a human and are unrun.

- **Round 2 (2026-09-14) rewrote the tracker's gates and added a state.** See
  `docs/25-round-2-ghost-audit.md` for the audit and `docs/26-round-2-tracker.md` for what
  was built and measured. One acceptance number is not met and cannot be: a per-slot floor of
  60 % observed requires blindness to spread evenly across the fourteen slots, and the
  broadcast camera concentrates it on whoever is furthest from the disc. The detections cap
  the achievable fraction at 0.7726; the tracker reaches 93.2 % of that.
- **Everything else passes its gate**, and every number in `HANDOFF.md` § 1 has a committed
  acceptance file under `eval/`.
- **One possession is cut and fully processed**: `work/p0001/`, broadcast 7264.023–7288.014 s,
  24.0 s, 360 frames at 15 fps, deterministic across runs. **`p0003`** (1580.03-1617.03 s,
  37 s, 555 frames) is processed and published alongside it. **`p0002` was deleted**: it ran
  from an out-of-bounds pull to the brick mark and contained no play worth tracking. See
  `docs/10-getting-the-footage.md` § 4 - watch a possession before cutting it.
- **Four more were cut on 2026-09-14 and two of them are published**
  (`docs/29-scouting-possessions.md`). `p0004` (2394.0-2424.0 s, Sol) and `p0005`
  (3039.2-3069.2 s, **Wind Chill on offence, the first of those**) join p0001 and p0003 on
  the site. `p0006` and `p0007` pass every stated gate and are **not** published: they are
  framed on the endzone for most of their length, the centre circle leaves the shot, the
  fit collapses on 275 and 250 frames respectively, and the median frame has no located
  player on it at all. The mosaic fallback `docs/28` names is what would rescue them.
  Finding candidates is now `tools/scout.py` rather than scrubbing: it reads all 52 goals
  off the score bug and pins each to the second the game clock freezes.
- **The original M0 reading still governs the plan.** `docs/00-footage-report.md` changed the
  detection plan (players are twice the assumed size), the calibration plan (soccer markings,
  not gridiron) and the shot model (one shot per possession, not three); read it before
  touching any of those.

## The two product commitments

Everything else follows from these. If a decision is unclear, resolve it in their favour.

**Never pretend to know.** A single broadcast camera on a 120 × 53⅓ yd field sees, *measured*,
**10.4 of 14 players in a wide shot and 8.3 across all live play, with a worst frame of 1**,
and the ones it misses skew toward the deep defenders — exactly the players who decide whether
a huck is on. So the overhead view draws the camera's real field-of-view as a shape on the
field, everything outside it is explicitly inferred, and a derived metric refuses to present
itself as measured when its inputs were not observed.

**Always be fixable.** Same-team identity swaps are the expected behaviour of every
appearance model on players in identical jerseys, not a bug to engineer away. The system
detects its own swaps and repairs them in one click, and corrections live in an append-only
layer that never touches the raw tracking output.

## The ten architectural decisions

Reasoning for each is in `docs/adr/`, one file per decision; this is the index. The
names are the stable handle: AD-7 is `docs/adr/0007-*.md`, never `ADR-0007`.

1. **Track on the field, not the screen.** Project detections to field yards before
   association; filter in yards with physical speed limits. Removes the need for camera
   motion compensation, which fails exactly during the hard zooms this footage is full of.
2. **Fourteen locked roster slots**, never created or destroyed. No phantom players, no
   vanishing ones.
3. **Team colour is a hard association gate** (Sol light kit, Wind Chill dark). Eliminates
   cross-team identity swaps, the most damaging error class for defensive analysis.
   *Amended 2026-09-14:* the gate is on a **confident** kit call, not on a hard three-way
   label, and a weak kit call is priced into the assignment cost rather than deleting the
   detection. The prohibition it exists for is intact and measures zero; what it stopped
   doing is throwing away real players — the excluded band was 64 % players, not the
   majority officials it was assumed to be.
4. **Register each frame to a per-shot background mosaic**, not to its neighbour. Bounded
   drift, and one set of human clicks per shot rather than per keyframe.
5. **Evidence states, not confidence floats** — observed / provisional / interpolated /
   predicted / unknown / confirmed, each with a sigma in yards. *`provisional` added
   2026-09-14:* a detection was matched but the slot had been estimating long enough that
   which player it is has not been established.
6. **Corrections are an append-only layer** over immutable tracking output.
7. **Events are human-tagged**; disc detection is a stretch goal.
8. **The possession is the unit of work.**
9. **No server** — a static viewer reading JSON.
10. **Attacking direction belongs to a quarter, not a possession.** ~~Added 2026-09-15.~~
    **WITHDRAWN 2026-09-16:** ends change every point, so a quarter-wide direction is
    wrong about the sport, and the finding behind it (`docs/30` § 2.0) is void. Kept in
    `docs/adr/0010-*.md` for the record. See issue #5.

## Licence position

Out: **Ultralytics YOLO** (all versions) and **boxmot** — AGPL-3.0; **YOLOv9**,
**StrongSORT**, **SportsLabKit** — GPL; **Sapiens** — CC-BY-NC; **SuperPoint/SuperGlue** —
non-commercial; **DINOv3** — custom licence; **KPR/BPBreID** — Hippocratic.

In: **D-FINE** or **RT-DETRv2** + **SAHI** (detection), **BoT-SORT** vendored (tracking
reference), **LoFTR** or **LightGlue with DISK/ALIKED** (matching), **PaddleOCR** or
**PARSeq** (jersey numbers), **RTMPose** if pose becomes necessary. Full register with URLs
in `07-licenses.md`; add a row before adding a dependency.

## The highest-leverage unknown

*The old one — whether Breese Stevens carries football yard lines — was answered in M0:* **it
does not. It is a soccer pitch**, and the soccer markings turn out to be a better calibration
substrate than yard lines would have been, because the centre circle is a conic of exactly
known radius. Calibrate to the soccer frame, then apply one fixed venue transform into the
ultimate frame. See `docs/00-footage-report.md` Q2.

**The highest-leverage unknown is now: is this a 120-yard field or a 110-yard one?** UFA rule
§2.3.3 permits a 110 yd field by venue exception, with the brick mark moving to 15 yd. A
soccer pitch may not fit 120 yd. The broadcast never frames both endzones, so M0 could not
settle it. **Every field coordinate in the system depends on the answer.** Resolve it in the
first hour of M1, when the centre circle first gives absolute scale.

## One more thing worth knowing

No public ultimate-frisbee tracking or calibration dataset appears to exist. Every position
a human confirms in this tool is novel labelled data, and `corrections.json` is designed so
it can be exported as training data without rework. That is a real asset; do not let the
format drift away from it.
