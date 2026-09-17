# AD-14 — A jersey read inside the span settles the name, and nothing else does

A tag's *moment* is the half a person can see. Its *name* is not: a tagger clicks
somebody in the viewer and the name that comes back is the **tracker's** name for that
person, so a tag on a mislabelled slot is a wrong tag and the tagger made no mistake.
That is `docs/30` § 2.5, and #4 is the change it produced.

`identities.json` gives a slot the only referent it has, the number on the shirt. The
question this decision answers is when that number settles a tagged name.

**A jersey read settles a tag when, and only when, the reading falls inside the span
that tag bounds.** Everything else is `tracker` and drops out of the graded sample.

*Why.* `CONTEXT.md` is blunt that a jersey number cannot be turned into a slot without
tracking continuity to carry it. A number read at f212 and a tag at f319 are joined by
something, and the something is the tracker. Grading against that pair is grading the
solver against its own upstream at one remove, which is the brief's second trap wearing
a disguise good enough that it took a second look to see. Inside the span there is
nothing to carry: the person holding the disc and the person whose shirt was read are
one person at one moment, and the claim rests on a human's eyes alone.

*The alternative, and why it lost.* The looser rule is "a reading, plus the slot
observed continuously between the reading and the tag". It is tempting because it
would have made seven of p0003's eight spans gradeable instead of one. It loses for
the reason above: *observed continuously* is the tracker's own account of its own
continuity, so the rule would have asked the tracker to vouch for the evidence used to
score the tracker. The strict rule yields a smaller number that means something over a
larger number that does not, which is the choice this project makes everywhere else.

*What it costs, measured.* p0003 has seven hand-read jerseys and eight named spans.
Exactly one span qualifies: O4 at 10.4–16.1 s, where jersey 5 was read at 12.2 s.
`span identity accuracy` reads **0/1** where it once read 8/18 = 44 %. p0001 and p0009
have no readings, so all 18 of their names are the tracker's.

*Why that cost is the right one.* The 44 % was the solver graded partly against names
its own upstream supplied, and the gate now fails on **sample size** rather than on the
solver, which is a different and honest failure. It also turns the shrinking sample
into an instruction anybody can act on: **read a number during the span you want
graded.** A denominator that grows by watching is worth more than one that was never
independent.

*Mechanism.* `ur/provenance.py:derive` is the rule; `python -m ur.provenance <work>`
applies it and is re-runnable, and it never overwrites a declaration somebody made
while looking. The result is marked `reconstructed`, because it was worked out
afterwards from a file rather than stated by a person watching. `every named tag says
what carried it` is the gate, and it counts declarations, not truth: nothing can check
that `footage` is honest, and a check claiming to would be worth less than none.

*Scope.* This is about a tagged **name**. AD-13 governs positions and everything else a
person supplied, and this sits inside it rather than beside it. #22 is what would let
the graded sample grow rather than shrink, by tying a slot to a jersey for a whole
possession; until then a reading covers the span it lands in and no more.
