# Prototype viewer

`prototype.html` + `data.js` is the design reference for milestone M6. Open
`prototype.html` directly in a browser — no server, no build step.

It reads `../fixtures/possession_demo.json` in the form of `data.js`, which assigns the same
JSON to `window.POSSESSION`. Regenerate both with `python tools/make_demo_possession.py`
followed by the one-liner at the bottom of that script's docstring.

**This is a prototype, not production code.** It was written to settle the design questions —
what a coach sees, how uncertainty reads, whether the correction flow feels cheap — not to be
extended. Reimplement it properly against `docs/06-viewer.md`, keeping its behaviour. The
parts worth porting almost verbatim:

- `frustumPoly()` and `clipRect()` — inverse-projecting the image corners onto the ground
  plane and clipping to the field. This is the single most valuable element on the page.
- `applyAnchor()` — the ramped re-fit of an estimated span around a human anchor.
- `findIssues()` — the swap, blind-stretch and cold-start detectors.
- The evidence rendering in `drawRadar()` — fill/outline/dash/sigma-disc/hatch conventions.
- The readout copy. The wording was chosen carefully; see the copy rules in the spec.

The camera view here renders synthetic positions through a simulated pinhole camera. With
real footage, replace that canvas with `<video>` plus an overlay canvas and take the
projection from `calibration.json`. Nothing else changes.
