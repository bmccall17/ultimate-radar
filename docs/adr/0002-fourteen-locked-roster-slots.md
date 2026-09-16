# AD-2 — Fourteen locked roster slots, not free-running track IDs

Per point there are exactly 7 offensive and 7 defensive players. The tracker's state is 14
slot trajectories that exist for the whole possession. Detections are assigned to slots. A
slot whose detection is missing is **not** deleted — it degrades to `predicted`, then
`unknown`. There is never a 15th slot and never a 13-player possession.

*Why.* Generic MOT creates and destroys tracks, which produces the two failure modes a coach
will never forgive: a player who blinks out of existence, and a phantom extra defender. The
roster constraint is free, exact information about ultimate that generic trackers do not
have. It also turns identity into a bounded assignment problem — 7 candidates, not N — and
makes human correction cheap: there is always exactly one right answer to "which slot is
this?".

*Consequence.* Substitutions only happen between points, so a possession never changes its
roster. A new point means a new possession file.
