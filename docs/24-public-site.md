# 24 — The public site, and a regression it exposed

## The regression: a fresh clone rendered a black camera pane

`viewer/index.html` drew nothing behind the overlay when there was no video. On a real
possession that is invisible, because `<video>` is behind the canvas. On the **fixture** —
which is what a fresh clone, and the public site, and anyone without `work/` gets — the camera
pane was a black rectangle with ground rings floating on it.

M6 reported the fixture's simulated pinhole as "ported from the prototype". The **projector**
was ported; the **scene render** was not. `viewer/prototype.html` still had it at
`drawVideo()`: surround, mown stripes, endzone tints, field lines, brick marks, depth-sorted
bodies, the disc.

Ported into `drawSyntheticScene(P,s)`, called from `drawCamera` when `vid.hidden` and the
projector is the pinhole. Two deliberate differences from the prototype:

- **Bodies are drawn from `truth`, not `est`.** The overlay is the estimate; where the two
  disagree you are looking at the tracker being wrong, which is the fixture's whole purpose.
- **Line width is measured, not guessed.** The prototype scaled width by
  `IW/max(260, depth)`, which clamps for everything nearer than ~260 and so drew a far
  sideline the same thickness as a near one — a 35 px wall across the frame. UFA rule 2.1.3
  puts every line at 4 inches, so project a 4-inch offset at the line's midpoint and use that
  distance. A far line now thins the way a real one does.

The scene also draws when the **Overlay toggle is off** — that control governs the rings, not
the pitch, and turning it off should show the bare view rather than a black rectangle.

> Checked: `over` canvas goes from unpainted to 415 lit samples, 260 of them green; no page
> errors; the real-footage path is untouched because it is gated on `vid.hidden`.

**This was found by trying to publish, not by a test.** Worth a line in the M6 acceptance: the
viewer must be exercised with `work/` absent, since that is every first run.

## The site

`tools/build_site.py` builds `docs/` from `viewer/`. One source of truth: edit the viewer and
rebuild; do not edit `docs/index.html`.

It strips the `live-data.js` script tag, copies `data.js`, and writes `.nojekyll`. The site is
**the synthetic fixture and nothing else** — 272 KB, no broadcast footage, no real tracking
output. `work/` and `viewer/live-data.js` stay gitignored.

    python -m tools.build_site
    python -m http.server -d docs 8080      # to check it locally

GitHub Pages serves from `docs/` on the default branch. The design documents already in
`docs/` are served alongside it; `.nojekyll` stops Pages trying to process them.

## Before the repo goes public: 213 MB of broadcast imagery is committed

`git ls-files` counts **250 image and video files, 213 MB**, almost all of it frames and
renders from the UFA broadcast — including `eval/m1/p0001_verification.mp4` (33.5 MB),
`eval/m2/p0001_detections.mp4` (30.6 MB) and `eval/m4/p0001_tracks.mp4` (10.3 MB), which are
the broadcast with overlays drawn on it.

The decision to ship the site as fixture-only was taken specifically to avoid republishing
footage. Publishing the repo as-is would republish far more of it.

**Stripping media from history leaves 139 files and 3.3 MB** — all the code, all 24 design
documents, and all 35 eval JSON files, which are where the acceptance numbers, hand labels and
measurements live. The engineering record survives intact; the frames do not. Nothing has been
pushed yet, so history can still be rewritten freely.

That is a judgement call for the repo's owner, not a default to apply silently. Both paths are
one command; see the handoff note accompanying this document.
