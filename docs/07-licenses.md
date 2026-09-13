# 07 — Licence register

The project must stay free to run and clean to release. Every dependency and every set of
model weights gets a row here **before** it is used. Licences were verified against repo
LICENSE files and project pages in September 2026; re-check before release, and never guess.

## The traps, stated once

- **Ultralytics YOLO — every version, v8 through v12 — is AGPL-3.0.** So is anything built
  on it, including **YOLOv10**. AGPL's disclosure obligation reaches a hosted service, not
  just distributed binaries. Ultralytics sells an enterprise licence specifically to escape
  it. **Do not use it.** This is the most common way a project like this quietly becomes
  un-releasable, because Ultralytics is the default everyone reaches for.
- **`boxmot`** (the convenient all-in-one tracker toolkit) is **AGPL-3.0**. The individual
  trackers it wraps — ByteTrack, BoT-SORT, OC-SORT, SparseTrack, Hybrid-SORT — are MIT.
  Vendor those directly instead.
- **YOLOv9** and **StrongSORT** are GPL-3.0. **SportsLabKit** is GPL-3.0.
- **Sapiens** (Meta's human-centric vision models) is **CC-BY-NC 4.0** — non-commercial.
- **SuperPoint / SuperGlue** (Magic Leap) are non-commercial research-only, no
  redistribution. **LightGlue** itself is Apache-2.0 but inherits SuperPoint's terms if you
  use the SuperPoint front-end — pair it with **DISK** (Apache-2.0) or **ALIKED**
  (BSD-3-Clause) instead.
- **DINOv3** ships under a custom Meta licence with export-control and use restrictions —
  not standard permissive. **DINOv2 is Apache-2.0** and is the clean choice.
- **KPR / BPBreID** (the sports re-ID models) use the **Hippocratic License**, which is not
  OSI-approved. Usable for a private prototype; call it out explicitly if you ever ship.
- **Field-registration models are mostly encumbered**: the SoccerNet calibration baseline has
  no LICENSE file at all; the 2023 challenge winner is CC-BY-NC-SA; NBJW and PnLCalib are
  GPL-2.0; `sportsfield_release` is non-commercial *and* patent-encumbered. **TVCalib (MIT)**
  and **SCCvSD (BSD-2-Clause)** are the clean ones — and none of them transfer to an ultimate
  field without retraining anyway (see `docs/08-risks.md`).

## Approved stack

| Stage | Choice | Licence | Fallback |
|---|---|---|---|
| Detection | **D-FINE** — `Peterande/D-FINE` | Apache-2.0 | **RT-DETRv2** — `lyuwenyu/RT-DETR`, Apache-2.0; or **YOLOX** — Apache-2.0 |
| Small-object inference | **SAHI** — `obss/sahi` | MIT | — |
| Tracker reference code | **BoT-SORT** — `NirAharon/BoT-SORT` (vendored) | MIT | **SparseTrack**, **Hybrid-SORT**, **ByteTrack** — all MIT |
| Feature matching (mosaic) | **LoFTR** — `zju3dv/LoFTR` | Apache-2.0 | **LightGlue + DISK/ALIKED** — Apache-2.0 / BSD-3 |
| Homography, image ops | **OpenCV** | Apache-2.0 | — |
| Homography utilities | **roboflow/sports** `ViewTransformer` | MIT | trivial to reimplement |
| Jersey OCR | **PaddleOCR** | Apache-2.0 | **PARSeq** — Apache-2.0; **docTR** / **EasyOCR** — Apache-2.0 |
| Pose (only if needed) | **RTMPose / MMPose** | Apache-2.0 | **ViTPose** — Apache-2.0 |
| Appearance embedding (weak signal only) | **torchreid** | MIT | **DINOv2** — Apache-2.0 |
| Pipeline architecture reference | **TrackLab** — `TrackingLaboratory/tracklab` | MIT | read it, don't necessarily depend on it |
| Ingest | **yt-dlp** — `yt-dlp/yt-dlp` | Unlicense | — |
| Ingest | **ffmpeg / ffprobe** — gyan.dev "full" build 9.0.1 | **GPL-3.0** (that build; see note) | an LGPL build, if we ever link rather than exec |

### Added in M0 (2026-09-12)

Verified against each project's own LICENSE file, not PyPI metadata.

| Use | Package | Version | Licence | URL checked |
|---|---|---|---|---|
| Arrays, all measurement code | **numpy** | 2.4.6 | BSD-3-Clause | `numpy/numpy/LICENSE.txt` |
| Image I/O, colour, morphology, connected components | **opencv-python** | 5.0.0.93 | Apache-2.0 (OpenCV ≥ 4.5); MIT wrapper | `opencv/opencv/LICENSE`, `opencv/opencv-python/LICENSE.txt` |
| Image I/O (transitive) | **pillow** | 12.3.0 | MIT-CMU | `python-pillow/Pillow/LICENSE` |
| Source download | **yt-dlp** | 2026.8.19 | Unlicense | `yt-dlp/yt-dlp/LICENSE` |
| Reading the UFA rulebook PDF (M0 only, not a pipeline dependency) | **pypdf** | 6.18.1 | BSD-3-Clause | `py-pdf/pypdf/LICENSE` |
| Interpreter and venv management (a tool, not a dependency) | **uv** | 0.12.13 | MIT **or** Apache-2.0 | `astral-sh/uv/LICENSE-MIT` |

### Added in M1 (2026-09-12)

| Use | Package | Version | Licence | URL checked |
|---|---|---|---|---|
| Non-linear least squares for the per-frame camera fit; `linear_sum_assignment` later in M4 | **scipy** | 1.17.1 | BSD-3-Clause | `scipy/scipy/LICENSE.txt` |

**On the ffmpeg build.** The installed binary is the gyan.dev *full* build, which bundles
GPL components (libx264 among them) and is therefore **GPL-3.0**, not LGPL. This project
invokes it as a **separate process** via `subprocess`, passing file paths — no linking, no
combined work, and we distribute neither the binary nor any derived work of it. That keeps
the GPL off our own code. Two constraints follow and should not be forgotten:

1. **Never vendor or redistribute the ffmpeg binary** with this project, and never bundle it
   into a release artefact.
2. **Never link ffmpeg's libraries** (via PyAV, ffmpeg-python's bindings, or ctypes). If
   in-process decoding is ever wanted, switch to an LGPL build first and add a row here.

`ur/ffprobe.py` records the exact ffmpeg version string into every `clip.json`, so which
build produced a given artefact is always answerable.

Weights carry their own terms. Where a repo is permissive but the weights are distributed
separately with no stated licence (DEIM is one), treat the weights as **unconfirmed** and
either train your own or pick a model whose weights are covered.

## On re-identification — set expectations now

Appearance re-ID cannot reliably tell teammates apart. The SoccerNet re-ID baseline says so
in its own README: players from the same team have very similar appearance. Embeddings mostly
encode team plus pose and lighting; cosine similarity between two teammates routinely exceeds
that between the same player across a shadow boundary.

So identity in this project comes from three other places, in order of weight: **track
continuity in field coordinates** (AD-1, AD-2), **jersey-number OCR voted per tracklet**, and
**one human assignment per point**. Budget engineering accordingly — time spent on re-ID
embeddings is time not spent on the motion model, which is where the wins are.

## Data

No public ultimate-frisbee tracking or calibration dataset appears to exist. Searches for
ultimate/AUDL computer-vision work surfaced only community tooling — rankings, rosters,
playbooks — and no CV projects. Treat "no prior art" as likely but unproven.

Consequence: every labelled frame this project produces is novel. The Roboflow
`football-field-detection` keypoint dataset (CC BY 4.0, 317 images) is a useful scale
reference — a few hundred labelled frames was enough to bootstrap a pitch-keypoint model for
soccer, which suggests the same order of effort would work here if automatic calibration
becomes worth building.

## Adding a dependency

1. Find the LICENSE file in the repo. Not the README, not PyPI metadata — the file.
2. Find the weights' licence separately.
3. Add a row above with both, and the URL you checked.
4. If either is AGPL, GPL, NC, or custom, use the fallback instead.
5. If you cannot confirm, do not use it, and note it in `docs/08-risks.md`.
