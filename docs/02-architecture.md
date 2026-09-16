# 02 — Architecture

```
video ──> ingest ──> frames + clip.json
                          │
          ┌───────────────┴────────────────┐
          ▼                                ▼
     calibrate                          detect
   shots, mosaic,                 RT-DETRv2/D-FINE + SAHI
   human anchors                   boxes per frame
   -> calibration.json                    │
          │                               ▼
          │                          team assign
          │                     torso colour, 2 clusters
          │                               │
          └──────────► project ◄──────────┘
                 boxes -> field coordinates (yd)
                           │
                           ▼
                      track  (the core)
            field-space Kalman, team-gated association,
            14 locked roster slots, evidence states
                           │
                           ▼
                      identify
              jersey OCR per tracklet + voting
                           │
      events.json ────────►├◄──────── corrections.json
      (human tagged)       │          (human edits, append-only)
                           ▼
                        resolve  ──►  derive  ──►  possession.json
                                                        │
                                                        ▼
                                                     viewer
```

Ten decisions define this system, and each carries its reason, because a coding agent that
knows the reason makes better local choices than one following a diagram. They moved to
`docs/adr/` on 2026-09-16. **The names did not change**: `AD-7` is `docs/adr/0007-*.md`,
cited everywhere as `AD-7` and never as `ADR-0007`.

---

## The decisions

| | | |
|---|---|---|
| **AD-1** | Track on the field, not on the screen | [`adr/0001-track-on-the-field-not-on-the-screen.md`](adr/0001-track-on-the-field-not-on-the-screen.md) |
| **AD-2** | Fourteen locked roster slots, not free-running track IDs | [`adr/0002-fourteen-locked-roster-slots.md`](adr/0002-fourteen-locked-roster-slots.md) |
| **AD-3** | Team colour is a hard gate | [`adr/0003-team-colour-is-a-hard-gate.md`](adr/0003-team-colour-is-a-hard-gate.md) |
| **AD-4** | Register to known world geometry, not to a neighbouring frame | [`adr/0004-register-to-known-world-geometry.md`](adr/0004-register-to-known-world-geometry.md) |
| **AD-5** | Evidence states, not confidence scores | [`adr/0005-evidence-states-not-confidence-scores.md`](adr/0005-evidence-states-not-confidence-scores.md) |
| **AD-6** | Corrections are an append-only layer over immutable output | [`adr/0006-corrections-are-an-append-only-layer.md`](adr/0006-corrections-are-an-append-only-layer.md) |
| **AD-7** | Events are tagged by hand; disc detection is a stretch goal | [`adr/0007-events-are-tagged-by-hand.md`](adr/0007-events-are-tagged-by-hand.md) |
| **AD-8** | The possession is the unit of work | [`adr/0008-the-possession-is-the-unit-of-work.md`](adr/0008-the-possession-is-the-unit-of-work.md) |
| **AD-9** | No server, ever | [`adr/0009-no-server-ever.md`](adr/0009-no-server-ever.md) |
| **AD-10** | Attacking direction belongs to a quarter, not to a possession **WITHDRAWN** | [`adr/0010-attacking-direction-belongs-to-a-quarter.md`](adr/0010-attacking-direction-belongs-to-a-quarter.md) |

`docs/09-decision-record.md` is the one-page orientation over all ten.

---

## Stage notes

**ingest.** `yt-dlp` for the source, `ffmpeg` to cut `[start,end]` and emit frames at 15 fps
(tracking rate) plus the clip at native rate for the viewer. Record the source timestamp of
frame 0 in `clip.json` so any moment maps back to the original broadcast.

**detect.** Start from COCO-pretrained **D-FINE** or **RT-DETRv2** (both Apache-2.0). Then
bootstrap a fine-tune: run the COCO detector, have a human fix boxes on ~300 frames sampled
across the game, retrain. Expect this to be the single largest accuracy win available.

*On tiling.* This doc used to require **SAHI** (MIT) tiled inference on the grounds that "a
downfield player is 25–45 px tall". **M0 measured 50–70 px at the widest live framing and
80–130 px in a typical wide play shot**, with ~50 px the smallest on-field player seen
anywhere. The reason is structural: the broadcast camera never frames the whole field, so
players never recede far enough to get small — which is the same fact as the partial
visibility in AD-5, seen from the other side. So **run whole-frame first and measure against
the M2 gate; add SAHI only if recall asks for it.** See `docs/00-footage-report.md` Q3.

**project.** The foot point is the bottom-centre of the box, which is wrong when the player
is occluded at the ankles or is airborne. Prefer the pose-free heuristic first (bottom-centre,
with a fixed downward offset when the box aspect ratio is unusually short); add RTMPose
(Apache-2.0) ankle keypoints only if M4 measurements show foot-point error dominating.

**track.** Constant-velocity Kalman in yards. Association: Hungarian on Mahalanobis distance,
gated by team (AD-3) and by a max-speed constraint. Slot-locked (AD-2). Emit an evidence state
per slot per frame.

**identify.** Crop the jersey region, run **PaddleOCR** or **PARSeq** (both Apache-2.0), and
vote **per tracklet, not per frame** — this is what the SoccerNet jersey-number challenge
winners do, and it turns 40–60 % frame accuracy into 80–90 % track accuracy. Where voting is
ambiguous, leave the slot numbered `?` and let the human assign it once.

**derive.** Computes the readouts in `docs/06-viewer.md`, each carrying the weakest evidence
state of its inputs. A metric whose inputs include an `unknown` position is emitted with
`confidence: "inferred"` and the viewer dims it.
