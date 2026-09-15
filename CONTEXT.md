# Context — the project's vocabulary

A glossary, and nothing else. Decisions live in `docs/02-architecture.md` as
`AD-n`; findings live in `docs/30-findings-and-gates.md`. If a word here and a
word in the code disagree, that is a bug in one of them.

## The footage

**Possession** — one cut of broadcast video, processed end to end, published as
one page. The unit of work (AD-8). Named `pNNNN`.

**Quarter** — a period of the game, read off the broadcast score bug and stored
as `clip.json:quarter`. Teams attack fixed ends within one, and swap between.
It is the unit that **attacking direction** belongs to — see below.

## The people

**Slot** — one of fourteen fixed identities, `O1`–`O7` and `D1`–`D7`, never
created and never destroyed (AD-2). A slot is *not* a person: it is a label the
tracker maintains, and it can be on the wrong person. Saying "O2 caught it" is
saying "the person the tracker calls O2 caught it", which is why a tag can be
wrong without the tagger making a mistake.

**Jersey** — the number on the shirt. Almost always unknown: the pipeline holds
`jersey: null` for every slot in every published possession, so a jersey number
cannot be turned into a slot without tracking continuity to carry it.

**Offence / defence** — which team has the disc. Held per possession, as a single
value. **A turnover breaks that**, and the model has no room for one: after a
turnover, `offense` is wrong for the rest of the possession.

## The disc

**Holder** — the slot holding the disc on a frame. Null during a flight.

**Span** — a stretch of frames with one holder, bounded by a catch and a throw.

**Flight** — the stretch between a throw and the next catch, holder null. Every
human-tagged flight in this project runs 0.27–3.20 s.

**Named / unnamed** — a span whose holder a human has stated, or has not. An
unnamed span between two named ones is a hole, not a long flight.

## What a human supplies

**Tag** — a human statement about the *game*, written to `events.json`: a throw
or a catch at a moment, optionally naming who. **Timing-only tag** — the common
case, naming the moment and nobody; the moment is the half a person can see.

**Correction** — a human statement about the *tracking*, written to
`corrections.json` as an append-only log (AD-6). Four operations: **anchor**
(place a slot at a position), **swap** (exchange two slots' trajectories),
**confirm** (affirm an estimate), **revert** (neutralise an earlier entry).

> **`confirm` is overloaded and the two senses are related but distinct.** The
> *correction operation* `confirm` is a human affirming an estimate. The
> *evidence state* `confirmed` is what a frame becomes as a result — and also
> what an `anchor` produces. So every `confirmed` frame is human-sourced, which
> is why a hand-placed position must never count toward the tracker's own recall.

**Tag vs correction** — the split is *what the fact is about*, not who supplied
it. A fact about the game is a tag; a fact about the tracking is a correction.

## Certainty

**Evidence state** — per slot per frame: `observed`, `provisional`, `weak`,
`interpolated`, `predicted`, `unknown`, `confirmed` (AD-5). Not a score. What the
viewer draws, and what it refuses to draw, follows from this and nothing else.

**Declared** — written down at cut time and never checked. **Measured** — derived
from the footage by a stage that reports its own accuracy. **Observed** — stated
by a human watching. A number is only as good as which of the three it is, and
`docs/30` § 2.0 is what happens when a declared value is mistaken for a measured
one.

**Gate** — a named pass/fail check in `python -m tools.gates`. An issue closes
when a gate flips to PASS (`docs/31`), so a gate is a definition of done, not a
diagnostic.

## Geometry

**Attacking direction** — which end a team is attacking, `+x` or `-x` in the
ultimate field frame.

> **It is a property of a (quarter, team), not of a possession.** Teams attack
> fixed ends within a quarter, so every possession in Q1 with Sol on offence has
> the same direction, and Wind Chill's is the opposite. Holding it per possession
> writes one fact many times and lets the copies disagree — which is exactly the
> contradiction `tools.gates` used to find in three of four quarters. It also
> survives a turnover, where a per-possession value does not: direction follows
> whoever actually has the disc, not the `offense` field.

**Confirmed / derived / declared** — where a direction came from, and a separate
vocabulary from the per-frame **evidence state** above, because it is about a
statement rather than about a position.

- **Confirmed** — a human watched that quarter and said which end. The only
  source there is: `docs/30` § 2.0 measured that the drift of the offence does
  not answer this. Written as an **observation** into the possession where it was
  made, `events.json:observed`.
- **Derived** — the other team was confirmed in that quarter, so this is the
  other end. As true as the confirmation it comes from, and **never written down
  as one**: a derivation recorded as evidence becomes its own constraint, and it
  would also destroy the check that two confirmations in one quarter must
  disagree about the end.
- **Declared** — `clip.json:attacking_direction`, typed at cut time. In the
  general sense above: written down and never checked. It is not a source of
  direction, it is a thing to check against one.

The *fact* is never stored, only the observations. `ur/direction.py` resolves
`(quarter, team) → direction` from all of them at read time, so nothing is
written twice and a contradiction stays a contradiction instead of becoming a
value somebody had to pick between.

**Ultimate frame** — field coordinates in yards, `x` 0–120 along the length with
goal lines at 20 and 100, `y` 0–53⅓ across. Shared by every possession: the same
`venue_transform` everywhere, so an `x` in one possession means the same place as
an `x` in another.
