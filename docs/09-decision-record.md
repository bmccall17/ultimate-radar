# 09 — Decision record

A one-page orientation. Written 2026-09-12, before any code existed. If you read nothing
else first, read this, then `04-milestones.md`.

Target footage: UFA 2026 semifinal, Austin Sol vs Minnesota Wind Chill, 27 Aug 2026, Breese
Stevens Field, Madison WI. YouTube `IDnoyd4cKfM`, 2:22:27. **Downloaded as format `299+140` —
1920×1080, h264 (avc1) High, 59.94 fps, 5.4 Mbps, 5.95 GB.** The AV1 compromise the docs
anticipated was not needed: a 1080p60 avc1 stream is offered.

## State at handoff

*Updated 2026-09-12, after M0.*

- **Ten docs, the data contracts, a synthetic possession fixture, a working prototype viewer,
  and `ur/ingest.py` plus the M0 measurement tools in `tools/`.** No pipeline code beyond
  ingest.
- **M0 is done and the assumptions have been checked against real frames.** Read
  `docs/00-footage-report.md` before M1 — it changes the detection plan (players are twice
  the assumed size), the calibration plan (soccer markings, not gridiron), and the shot model
  (one shot per possession, not three). The corrections it made to the other docs are listed
  at its foot.
- **One possession is cut and verified**: `work/p0001/`, broadcast 7264.023–7288.014 s, 24.0 s,
  360 frames at 15 fps, deterministic across runs.

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

## The nine architectural decisions

Reasoning for each is in `02-architecture.md`; this is the index.

1. **Track on the field, not the screen.** Project detections to field yards before
   association; filter in yards with physical speed limits. Removes the need for camera
   motion compensation, which fails exactly during the hard zooms this footage is full of.
2. **Fourteen locked roster slots**, never created or destroyed. No phantom players, no
   vanishing ones.
3. **Team colour is a hard association gate** (Sol light kit, Wind Chill dark). Eliminates
   cross-team identity swaps, the most damaging error class for defensive analysis.
4. **Register each frame to a per-shot background mosaic**, not to its neighbour. Bounded
   drift, and one set of human clicks per shot rather than per keyframe.
5. **Evidence states, not confidence floats** — observed / interpolated / predicted /
   unknown / confirmed, each with a sigma in yards.
6. **Corrections are an append-only layer** over immutable tracking output.
7. **Events are human-tagged**; disc detection is a stretch goal.
8. **The possession is the unit of work.**
9. **No server** — a static viewer reading JSON.

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
