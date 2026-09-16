# AD-8 — The possession is the unit of work

> **AMENDED, 2026-09-16.** The last sentence below was "Nothing in the pipeline
> needs whole-game state", and that is no longer true. A possession is a game unit
> ending in a score or a turnover, and where one begins cannot be read off the cut
> — it is read off the game. So the pipeline now carries a **game-wide possession
> index**: proposed by an agent over the whole broadcast (#16, #17), settled by a
> person in one sitting (#18, #19), and the thing every published cut binds itself
> to (#21).
>
> **The decision itself stands.** The possession is still the unit of *work*: one
> cut, one page, one set of artefacts, bounded at about 20 seconds. What changed is
> that its boundaries are now supplied by whole-game state instead of chosen at cut
> time. The index says where a possession starts; everything downstream of that is
> still scoped to one.

Ingest cuts one possession. Every artefact, metric, share link and comparison is scoped to
it.

*Why.* It bounds every algorithm to about 20 seconds and 300 frames — cheap to run, cheap to
re-run after a correction, cheap to reason about. It also matches how film study actually
happens.
