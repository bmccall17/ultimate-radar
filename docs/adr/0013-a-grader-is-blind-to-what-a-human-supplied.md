# AD-13 — A grader is blind to what a human supplied

No score of the machine's work may be computed **over** a fact a person supplied.
Scoring **against** one is fine, and is how every grader in this project already
works — the direction is the whole rule.

- A human statement the grader is measured *against* is **ground truth**. M1
  acceptance is scored against points somebody painted, and that is what makes
  `mean_error_yd < 0.75 yd` mean anything.
- A human statement the grader is measured *over* is **contamination**. An
  `anchor` produces `confirmed`, `confirmed` is what a frame the tracker got right
  also reads, and a metric counting those frames scores the tracker better the
  more of a possession a person fixes.

The rule is about the direction and not about the kind of data. Positions are the
first instance and the only one built; jersey read accuracy (#22) and whatever
replaces the identity ground truth in #4 inherit it before they exist.

## The mechanism, positions as the worked example

`possession.json` carries `"human": [312, 313, ...]` per player and beside
`disc_meta` — a sorted list of frame indices, empty on everything the pipeline
produced alone, because a 555-frame array of `false` on every published page buys
nothing. `ur/human.py` reads it and `blind()` hands a grader the same document
with those frames removed: position `None`, state `unknown`, which is the shape
the pipeline already handles everywhere as a slot nothing has seen. A hand-placed
position cannot match a held-out label, cannot sit inside its own collapsed sigma,
and cannot lower a span's emission cost. It is not that it scores zero — it is not
in the sample at all.

**The mark is per frame, not per operation.** An anchor does not only change the
frame it was placed on: the `docs/05` ramp shifts every frame between the
bracketing observations so the corrected path still meets them, and those frames
keep reading `predicted` while being partly a person's work. Marking only the
anchored frame would leave the ramp's output looking like the tracker's own —
the same lie one frame over.

**Never infer the mark from the evidence state.** `confirmed` is what an anchor
produces, but a `predicted` frame inside a ramp is human-sourced too, and a
`confirmed` frame is also what `confirm` produces over an estimate the tracker
made alone.

`blind()` is a grading view and never a publishing one. A correction is supposed
to make the artefact better — that is the point of AD-6, and the reader should see
the repaired path. What it must never do is make the *score* better.

## Other instances take the shape of the proof, not this data structure

Jerseys are not frames, and forcing a frame-index list onto them would produce an
ADR everybody reads as clearly not written with their case in mind. What transfers
is the proof — hand the grader a view the human contribution is absent from, and
have a check that fails when somebody stops doing it. The list and the null-out are
how that works for positions, and carry no further.

## The check, and what its pass rests on

`tools/human_positions.py` builds a probe keyframe — every slot and the disc moved
12 yd, on a stride of 8 keyframes, laid in through `ur.resolve` by exactly the
route a person's save takes. It runs each grader three times: with its exclusion
switched off, as it normally runs, and over `blind()` of the document. The last two
must be identical and the first must differ from them, or the probe never reached
that grader and the agreement says nothing.

Reading the source for the word `blind` would pass on a call that had been
commented out. Running the graders will not.

**Per-player recall is exempt, and the exemption is stronger than the test.** It
asks for `observed`; an anchor produces `confirmed`; the ramp never moves the
bracketing observations. The probe cannot reach it at all, so the run reports
`unreachable` and does not count it (AD-11). That is structure rather than
evidence — worth more, but only while the structure holds.

**So no correction operation may produce `observed`.** The ops are `anchor`,
`swap`, `detach`, `confirm` and `revert`; anchor and confirm both produce
`confirmed`, and `detach` produces `unknown` (`#26`, landed after this was
written). Adding
one that produced `observed` would void recall's guarantee silently, and it would
be the worse bug on its own terms: `observed` means the detector saw somebody, and
a person saying where they are is not the detector seeing them.

## Bounded — a number that is only true in one direction

Blinding stops a person's hand entering the score. It does not stop a repair pass
*raising* the score, because a person repairs the frames the tracker got **wrong**,
and removing exactly those leaves a sample of the frames it already handled. Recall
over a repaired possession goes up — honestly computed, and meaning less.

A number measured after any hand placement is **bounded**: an upper bound, not a
result. It joins declared, measured and observed in `CONTEXT.md` as a fourth answer
to what kind of number this is, and it carries one obligation — **print the
denominator beside it**, so a sample that shrank under blinding is visible rather
than inferred.

This is #11's finding one level up. There the page rounded a null to `0 %` and
printed a measurement nobody took. Here the arithmetic is sound and the number is
real, and it still is not the thing a reader will take it for.

*Why.* The brief's second trap is a solver's own output returning as its own
constraint, and this project has now hit that shape three times: the identity
ground truth that is not independent of the tracker (#4), the withdrawn
`identity_switches_caught: "2 of 2"` — the swap detector agreeing with the analysis
that produced it — and a derived attacking direction written back as an observation
(AD-10, #5). Repair mode is the fourth and the most dangerous, because it is the
feature that makes a person *want* to correct a lot of frames. Every previous
instance was caught by somebody noticing; this one is caught by construction.

*Why not just remember.* Three call sites carrying a `blind()` is exactly what
rots. The failure is also invisible in the direction that flatters — the numbers go
up, every gate stays green, and nothing looks wrong.

*What it costs.* A new grader must take `blind()` of its input and must be
reachable by the probe, or say in one line why it is structurally unreachable. A
number computed over any hand-placed frame must print as bounded with its
denominator. Neither the label nor the denominator exists in the viewer or the gate
rows yet, and today every possession in `work/` is 0.0% hand-placed, so nothing has
been printed wrong — the first repair pass that lands is what makes this due.

*What this does not claim.* It does not say the graders are *right*, only that a
person's hand is not in them.

## Calibration — the line is drawn, and the case has not arisen

M1 is scored against painted points, which is ground truth under the rule above and
stays exactly as it is.

Nothing currently lets a person correct a calibration, so the contamination case
cannot occur — it is absent rather than solved. `calibration_truth.json` has a data
contract in `docs/03` and the viewer writes one from a paint drag, and no Python
reads it. Whoever consumes it inherits this: a painted point may be the truth M1 is
scored against, and may never be folded into the fit M1 then scores.


---

## Amended 2026-09-17 — the subject is everything a person supplied, not positions

This decision already said it: *no score of the machine's work may be computed
over a fact a person supplied*. The mechanism only ever covered one such fact.
`ur/human.py` blinds **positions**, and identity walked straight past it.

A tagger selects somebody in the viewer and the name that comes back is the
tracker's name for that person, so a tag on a mislabelled slot is a wrong tag and
the tagger made no mistake. 32 of 32 tags in the corpus are named that way.
Grading the span solver against them is grading it against its own upstream, which
is the brief's second trap and exactly the shape this ADR was written to stop.

**`ur/grading.py` is now the whole of the mechanism.** One call returns the
possession with hand-placed frames blinded *and* the tags with tracker-supplied
names stripped. A grader takes that and nothing else; a renderer says
`read_for_publishing` and means it. Blinding a name strips the name and keeps the
moment, because the moment is the half a person can see and is not in doubt.

### The registry was the real hole, and this ADR could not see it

`tools/human_positions.py` probes the graders its `graders()` registry names. That
registry is a hand-written list of three. `tools/disc_score.py` read both files
raw, applied neither exclusion, and is in no registry — so the probe reported
`1 of 1 grader run(s)` and passed, which was true and said nothing. An
`unreachable` row at least admits the probe could not reach something. An absence
prints nothing at all.

So `tools/grading_view.py` is a second check beside the probe:

> Only `ur/grading.py` may build a path to `possession.json`.

No allowlist, nothing to register. It **fails open**: a file that will not parse
is a finding, not a skip.

### It reads source, and this ADR says not to

The paragraph above says reading the source for the word `blind` would pass on a
call that had been commented out. That is right, and it is about whether an
exclusion **ran** — which the probe still answers, and still is the only thing
that can.

This asks a different question: does a bypass **exist**. Source is the only place
that can be answered from, precisely because a module no gate run calls is the one
the probe cannot reach. The two are complements. Delete an exclusion from the view
and the probe goes red; add a grader that never asks the view and the scan goes
red. Neither substitutes for the other, and the exemption is this narrow: a
structural question about what exists, never a behavioural one about what ran.

### What it cost, and why that is the right cost

`span identity accuracy` went from `8/18 = 44 %` to `0/0`. No tag carries
provenance yet, so no span may be scored against, so the gate fails on **sample
size** rather than on the solver. That is the honest reading: the 44 % was a
number about the solver computed over names the solver's own upstream supplied.
The old exclusion filtered on `player_inferred`, which asks whether anybody read
the jersey — a different question, and the wrong one. p0001's names were reached
by elimination over the throws the tagger watched and p0003's O2 by elimination
over the tracker's coverage counts; both are inferences and only the second is
contaminated.

The number comes back when a tagger declares what carried each name, and `#22`'s
slot-to-jersey mapping is what would let it grow rather than shrink. `#4`.
