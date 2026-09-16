# AD-8 — The possession is the unit of work

Ingest cuts one possession. Every artefact, metric, share link and comparison is scoped to
it. Nothing in the pipeline needs whole-game state.

*Why.* It bounds every algorithm to about 20 seconds and 300 frames — cheap to run, cheap to
re-run after a correction, cheap to reason about. It also matches how film study actually
happens.
