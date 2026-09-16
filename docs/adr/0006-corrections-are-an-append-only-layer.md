# AD-6 — Corrections are an append-only layer over immutable output

`tracks.json` is never edited. Human edits land in `corrections.json` as anchors (a
position, pinned at a frame) and identity operations (swap two slots from frame N onward).
`ur/resolve.py` produces the corrected track by re-fitting the estimate between the
surrounding observations with anchors as hard constraints.

*Why.* Reversibility and auditability — a coach who cannot undo will not correct at all. And
the correction log is the highest-value training data this project can produce: every anchor
is a human-verified field position on real broadcast footage, and there is no public dataset
of those for ultimate.
