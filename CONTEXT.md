# Context — the project's vocabulary

A glossary, and nothing else. Decisions live in `docs/adr/` as
`AD-n`; findings live in `docs/30-findings-and-gates.md`. If a word here and a
word in the code disagree, that is a bug in one of them.

## The footage

**Possession** — one cut of broadcast video, processed end to end, published as
one page. The unit of work (AD-8). Named `pNNNN`.

**Quarter** — a period of the game, read off the broadcast score bug and stored
as `clip.json:quarter`. It is a place in the broadcast and nothing more.

> **Corrected 2026-09-16.** This entry used to end "Teams attack fixed ends
> within one, and swap between. It is the unit that **attacking direction**
> belongs to." That is the claim AD-10 was withdrawn for: ends change every
> point, not every quarter. A reader who looked up `Quarter` and never reached
> `Attacking direction` was told something the project knows is false.

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

**Inferred name** — a tag whose `player` the tagger did not read, reached by
elimination instead. It carries `player_inferred`. Still a human's statement, and
a weaker kind of one. Nothing saw the jersey, and the argument usually rests
partly on the tracking, so the claim is no stronger than the solver's own. It
closes a hole in the display; it does not grade the solver, and it never renders
`confirmed`.

**Correction** — a human statement about the *tracking*, written to
`corrections.json` as an append-only log (AD-6). Four operations: **anchor**
(place a slot *or the disc* at a position), **swap** (exchange two slots'
trajectories), **confirm** (affirm an estimate), **revert** (neutralise an
earlier entry).

**Keyframe** — everything one save of repair mode placed: a person pauses the
clip, puts every marker and the disc right, and saves once. In the log it is a
`keyframe` id shared by the `anchor` entries it produced, so the correction panel
shows one row and one Undo takes the whole save back. One statement about one
moment, not fifteen unrelated ones.

**Hand-placed** — a frame whose position a correction created *or moved*, carried
per slot in `possession.json:human`. Not the same as the evidence state, and the
difference is the point: `confirmed` is what an `anchor` produces, but docs/05's
ramp also shifts the frames between the bracketing observations, and those still
read `predicted` while being partly a person's work. Every grader in the project
is blind to these frames — `ur/human.py` is the mechanism and
`tools/human_positions.py` is the check — because otherwise the tracker scores
better the more of a possession somebody fixes.

**Paint reading** — a human statement about where the *camera* is looking: a
field point whose position is known exactly, and the image pixels the painted
line actually occupies. It looks like a correction and is gathered with the same
gesture, and it goes in a different file (`calibration_truth.json`), because the
subject is the camera and not anybody on the field.

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

**Measurement** — a row in the same run that reports a number and holds it to no
threshold. It prints `[measured]` rather than `[PASS]`, carries the reason it has
no threshold where a gate carries its `want`, and is totalled separately. The
distinction matters because a row that cannot fail must not be counted as one
that passed, and because a ticket pointed at one would have a definition of done
it could never fail to meet (AD-11). `docs/30` § 3 names the measurements and
what each is waiting for before it can become a gate; `tools/checks.py` is where
a new check picks its kind.

## Geometry

**Attacking direction** — which end a team is attacking, `+x` or `-x` in the
ultimate field frame.

> **WITHDRAWN 2026-09-16, and the paragraph below is kept only so the change is
> legible.** Ends change every point: after a goal the scoring team pulls from the end
> it just scored in, so it now defends the end it was attacking. Two possessions in
> consecutive points drift the same way, legitimately. So the same-sign drift was never
> a contradiction, `docs/30` § 2.0 measured nothing, and direction belongs to a
> **(point, team)**. Issue #5 carries the replacement; this section is rewritten when
> it lands.
>
> **It is a property of a (quarter, team), not of a possession.** Teams attack
> fixed ends within a quarter, so every possession in Q1 with Sol on offence has
> the same direction, and Wind Chill's is the opposite. Holding it per possession
> writes one fact many times and lets the copies disagree — which is exactly the
> contradiction `tools.gates` used to find in three of four quarters. It also
> survives a turnover, where a per-possession value does not: direction follows
> whoever actually has the disc, not the `offense` field.

**Confirmed / derived / declared** — where a direction came from, and a separate
vocabulary from the per-frame **evidence state** above, because it is about a
statement rather than about a position. A human is the only source: nothing in
the pipeline measures which end a team attacks, and the drift of the offence,
which was once read as measuring it, does not.

- **Confirmed** — a human watched and said which end. Written as an
  **observation** into the possession where it was made, `events.json:observed`.
- **Derived** — worked out from a confirmation made elsewhere, rather than
  watched. As true as the confirmation it comes from, and **never written down as
  one**: a derivation recorded as evidence becomes its own constraint, and it
  would also destroy the only check there is, which is a second confirmation
  disagreeing with the first.
- **Declared** — `clip.json:attacking_direction`, typed at cut time. In the
  general sense above: written down and never checked. It is not a source of
  direction, it is a thing to check against one.

The *fact* is never stored, only the observations; the resolver answers from all
of them at read time, so nothing is written twice and a contradiction stays a
contradiction instead of becoming a value somebody had to pick between.

> **The three words above survive the withdrawal; what they are keyed to does
> not.** `ur/direction.py` still resolves `(quarter, team) → direction` and its
> docstring still cites AD-10, because the module has not been re-keyed yet — so
> the code and the withdrawn paragraph above agree with each other and both are
> wrong about the sport. #5 re-keys it to `(point, team)`. Until it lands, read
> "confirmed for a quarter" as "confirmed for the wrong unit", and do not add
> confirmations on the strength of it.

**Ultimate frame** — field coordinates in yards, `x` 0–120 along the length with
goal lines at 20 and 100, `y` 0–53⅓ across. Shared by every possession: the same
`venue_transform` everywhere, so an `x` in one possession means the same place as
an `x` in another.
