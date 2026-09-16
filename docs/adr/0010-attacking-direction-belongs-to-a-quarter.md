# AD-10 — Attacking direction belongs to a quarter, not to a possession

> **WITHDRAWN, 2026-09-16.** This decision keys attacking direction to a
> quarter. Ends change every point, so a quarter-wide direction is wrong about
> the sport, and `docs/30` § 2.0, the finding it was built on, is void. Kept for
> the record. See issue #5 for what replaces it. Do not build on this.

`clip.json` carries `attacking_direction` per possession. It should carry the
quarter, and direction should be held once per **(quarter, team)** and derived
from there.

A human confirms it in the viewer — the toggle is the only reliable source, since
`docs/30` § 2.0 measured that the drift of the offence does not measure this. But
the confirmation is recorded against the quarter, and every possession in that
quarter derives from it: the other team's direction is the opposite, and any
possession's is a function of its quarter and who has the disc.

*Why.* Three reasons, in order of how much they cost to learn.

**One fact written many times can disagree with itself, and does.** Ten
possessions each declare their own direction, and `tools.gates` finds three of
the four quarters covered contain a contradiction — Sol and Wind Chill both
attacking the same end at the same time. Held per quarter, that is not a check
that fails; it is a state that cannot be represented.

**It survives a turnover, and a per-possession value does not.** `offense` in
`clip.json` is a single value, so after a turnover it is wrong for the rest of the
possession — `ur/disc.py` says so where it warns about a tag naming somebody off
the offensive roster, and p0003 produced exactly that tag. Direction attached to a
quarter still resolves correctly there, because it follows whoever actually has
the disc rather than the `offense` field.

**It makes the human's job four answers instead of ten.** One confirmation per
quarter settles every possession in it, including ones not yet cut.

*What this is not.* It is **not** the same decision as placing a player the
tracker has lost. That looked like the same thing — both are a human supplying
what the machine cannot measure — but the two facts are about different subjects,
and AD-6 already settles the second: a position is a fact about the *tracking*,
so it is a correction (`anchor`), append-only and revertible. Direction is a fact
about the *game*. The split is the subject, not who supplied it.

*Where it is stored, given every directory is one possession.* The **observation**
is made while watching a possession, so it is written there — `events.json` gains
a possession-level `observed` block beside its `events` list, because it is a
human statement about the game and that is what that file is for. The **fact** is
not stored at all: it is resolved from the observations by quarter, and a
contradiction between two of them is a gate failure rather than a value somebody
has to pick between. So nothing is written twice, and `clip.json`'s
`attacking_direction` goes back to being what it always was — a declaration made
at cut time, now checkable against something.

> **Consequence for the gates.** A confirmed direction does not silence the
> cross-possession check; it feeds it. Two confirmations that contradict each
> other are still a failure, and a useful one — it means a quarter is mis-read or
> a confirmation is wrong. And a direction derived from another quarter's
> confirmation must never be written back as if it were confirmed itself: that is
> the second trap in the brief, a solver's own output returning as a constraint.

---
