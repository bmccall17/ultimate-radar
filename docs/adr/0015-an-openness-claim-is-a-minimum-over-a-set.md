# AD-15 — An openness claim is a minimum over a set, so its badge rests on the whole set

A metric's evidence badge is taken over **everything the claim quantifies over**, not over
the players its number happens to name. Where the claim is *"the nearest defender was
5.1 yd away"*, that is every defender on the field, and one of them outside
`observed`/`confirmed` caps the badge — however well the rest were seen. The ones that
were not seen are **named on the card, as people**: the slot, and the jersey where one has
been read.

*Why.* On p0001 at 15.867 s the separation card printed **5.1 yd** and badged it
**MEASURED**. O4 and D6 are both `observed` on that frame and the distance between them is
exactly 5.1 yd. **D5 is `predicted`** — dead-reckoned, drawn dashed on the overhead,
correctly recorded in the file — and the card searched it, ranked it, and said nothing
about it. The deep-cover card repeated the whole thing one row down.

The number was right. The word above it was not. *"The receiver had 5.1 yd of room"* is not
a statement about D6, it is a statement about **all seven defenders**, and a minimum over a
set with an unseen member is not a measurement of that minimum. D5 could have been three
yards from O4 and nothing on that card would have moved.

*Why this is not already covered by AD-5.* It is, and that is the point. `evidence(f,
slots)` refuses `measured` the moment a contributor was not seen, and it has done since
AD-5. Coverage, defensive shape and shape lag all hand it the whole roster. The openness
cards handed it two names. **The machinery was right and the argument about what
contributes was wrong**, which is a class of error no amount of state-carrying prevents —
so it gets a decision of its own rather than a fix.

*The general form.* Ask what would have to change for the number to change. If a player
nobody saw could move and move the number, that player contributes, and AGENTS rule 3
applies to them whether or not they are named in the sentence.

*What is dropped, and what survives.* The deep-cover card asserted *"no defender sits on
the far side of the deepest cutter"* and *"the huck is on"* from a test on the nearest
defender alone — `goalSide` was assigned inside the loop that found the minimum, so it
described one player and read as describing seven. **The negative is gone and nothing
replaces it.** The positive survives as an honest existence claim: `covered` means somebody
the camera saw is standing between the deepest cutter and the endzone, and one witness
proves it. Where nobody is, the card says that whether the space is open is a question
about every defender and that it is not answering it. The reader has the overhead for where
everybody is; what they needed was to stop being told what it meant.

*What it costs.* All seven defenders are `observed`/`confirmed` on 24 % of p0001's frames
and **0 %** of p0005's — 9 %, 2 %, 11 % and 7 % on the other four. These two cards are now
`inferred` on most frames of every published possession. That is the finding and not a
regression: the tool was calling things measured that it had not measured. The route back
is repair mode and coverage, never a looser word.

*What checks it.* `no measured claim over an unseen defender`, per possession, under AD-12
and its constraints unchanged — `tools/openness.py` runs the page's own code rather than a
copy, and the negative scenario takes an input away rather than predicting an output. The
positive scenario is **constructed**, as AD-12's widening requires of a claim whose subject
may not be on the page: p0005 makes no measured claim on any of its 450 frames, so blinding
a slot there would take nothing away from nothing and pass having covered nothing (AD-11).

It lifts **`opennessCard`, not `opennessClaim`** — the strings, not the numbers under them.
The badge and the naming are two separate promises and only one of them is a number: a card
that keeps the downgrade and deletes the naming tells a reader the figure is weak and never
who made it weak, which is this finding again one layer up. So the sweep asserts both, and
`docs/30` § 2.19 names the one hop still uncovered — `renderCards` pasting those strings
into `card()`.

*What is not yet under it.* **The Mark card.** The gap it prints is the distance to the
nearest defender to the holder, which is the same minimum over the same seven, and it still
takes its badge from those two players. The rule reaches it and the code does not, because
#14 named the two openness cards and this ADR is what that work produced. It is written
down rather than quietly left: `docs/30` § 2.19 carries it, and the gate cannot see it —
`opennessClaim` is swept over attackers, and the mark is measured from the holder.

*Where it does not reach.* The claim's badge says the defence was seen whole; it says
nothing about **whether the right people are in the slots**. A separation between the wrong
two players is a different number, and that is capped separately where the receiver's name
was solved or reached by elimination — AD-14 and `docs/27`. The two caps are independent
and both apply.

Findings: `docs/30` § 2.19. Issue #14, desired outcome 8 of #9.
