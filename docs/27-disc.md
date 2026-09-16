# 27 — The disc

**Status: the machinery is built, the contract is met, and the part that was supposed to
work without a human does not. That last finding is the useful one.**

```bash
python -m ur.disc     work/p0001     # -> disc.json
python -m ur.possess  work/p0001     # carries it into possession.json
```

| gate | required | measured | |
|---|---|---|---|
| Disc position present | every frame | **360 / 360 (100 %)** | pass |
| …each carrying an evidence state | every frame | **360 / 360** | pass |
| Holder inferred without a detector | ≥ 90 % of frames where a holder exists | **not established — the sequence is not a possession** | **fail** |
| A disc sample is ever `observed` | never | **never** | pass, by construction |

---

## The model, and why it is not a detector

`docs/25` Part 3 is right and this follows it. A disc is about 27 cm, motion-blurred at
60 fps, and for most of a possession it is **held** — occluded by a hand and a torso inside
the densest cluster of bodies on the field. That is the hardest version of the problem and
the version nobody needs to solve, because a held disc is not an independent object. It is a
property of whoever is holding it, and the tracker already knows where every player is.

So the disc is a state machine over the possession:

```
HELD(player) --release--> FLIGHT(from, t0) --catch--> HELD(player')
                               |
                               +--incompletion--> LOOSE --pickup--> HELD
```

Only FLIGHT would need pixels — the one phase where the disc is separated from every body,
silhouetted against grass, on a smooth arc, inside a window bounded by two known endpoints.
That stage is not built, and on the evidence below it is also not the bottleneck.

**No disc sample is ever `observed`, and that is structural rather than a shortfall.** Nothing
in this pipeline has detected a disc, so the strongest claim available is `confirmed` — a
human said who was holding it. The ordinary case is `predicted`: the geometry says a
particular player is the thrower and the disc is assumed to be in their hand. A
separation-at-release computed from a guessed holder is not a worse measurement of
separation; it is a measurement of something else, and `docs/05`'s propagation rules already
know what to do with that.

**`confirmed` also needs the holder's own position to have been seen, and that was learned
the expensive way.** A tag is a statement about **who** held the disc. It says nothing about
where the tracker's marker for that slot had drifted to, and the two were collapsed: any
`ANCHORED` state counted, `provisional` included. On p0003 the tracker lost O2 at 18.0 s,
dead-reckoned it for 3.1 s, and re-acquired 26.9 yd away on somebody standing a yard over
the far sideline — a match official. The human tag at 21.27 s was correct about the catch,
so the disc was published **on the official, at `confirmed`**, the strongest state the
format has. Three frames on the live site, and every disc gate was green through all of
them: the one that checks `source` saw an honest `human`, and the one that checks how far
outside the lines a position is saw 2.04 yd against a 5 yd threshold — because a sideline
official stands exactly where a sideline player stands. Distance cannot separate them;
provenance can. `ur/disc.py:POSITION_SEEN` is now the narrower test, and
`no disc drawn on a guessed position` (`tools/audit_site.py`) is the gate. On a
`provisional` holder the disc is `predicted` and the viewer declines to draw it — it
disappears for the stretch rather than asserting a place nothing saw.

## Holder inference, and the measurement that sank it

The idea is sound on paper. In ultimate the thrower plants a pivot foot, and UFA rule §15.1
requires the marker to be within 3 m — so the thrower and their mark are **both** nearly
still while every other pair on the field is running. It is a sequence problem rather than a
per-frame one, because in person defence *every* offensive player has a defender within a
yard or two on any single frame; what distinguishes the holder is that they persist, and
change only at a catch.

Implemented as a Viterbi pass over the possession: hidden state is which offensive slot holds
the disc or `none` (in flight), emission cost is the combined path length of a candidate and
their nearest defender over one second — in yards, so it is a physical quantity rather than a
score — and **a direct hand-over is forbidden**, because a disc does not move between two
people without being thrown.

It produces a confident, plausible-looking, wrong answer.

There are no labelled holders anywhere in this project, so the sequence cannot be scored
against truth. It can be scored against physics and the sport, which is weaker and was
sufficient:

| | measured on p0001 |
|---|---|
| throws inferred | 7 |
| **throws that reverse the previous throw's direction** | **83 %** |
| net field position gained over the whole possession | +7.9 yd |
| where the disc ends up | x = 65 yd, with the endzone starting at 100 |

The throw sequence gains 27 yd, loses 28, gains 25, loses 21 — a disc oscillating across the
field every second and a half. That is not a team moving a disc; it is a holder estimate
flipping between two candidates whose emission costs are nearly equal. Chance alone would
alternate about 50 % of the time; 83 % is the signature of a two-state oscillation.

**It is not a tuning problem, which was worth checking before concluding anything.** Sweeping
the switch cost over 3, 6, 10, 15, 25, 40 and 60 yd moves the alternation only from 88 % to
75 % and never moves the final disc position off x = 65.3. The signal is not there to be
recovered by weighting it differently.

Three reasons it fails, in order of how much they cost:

1. **Several offence–defence pairs are near-stationary at any moment.** A reset handler, a
   poaching defender, a cutter between accelerations — all look like a thrower and a mark.
2. **The positions it reasons over are the tracker's**, with a median error of 0.39 yd and
   27 % of slot-frames estimated rather than observed. "Stillness" measured over a second is
   comparable to that noise.
3. **The camera follows the disc**, so the holder is nearly always in shot and so are the
   players around them. The one signal that would break the tie — who the camera is centred
   on — is one this stage does not use.

### The system says so itself

`ur/disc.py` scores its own output on the three checks above and, when they fail, **emits
every inferred sample as `unknown`** rather than as a position. On p0001 that is 360 of 360
samples: the file still carries a coordinate for every frame, as `docs/03` requires, and
every one of them says it is not to be believed.

Suppressing the inference entirely was the alternative and is worse: it would leave the
viewer with nothing and no reason. Saying "here is a number and here is why it is not
trustworthy", in the file, is what lets `ur/possess.py` and the viewer decline to use it
without either of them having to re-derive the judgement.

## What actually makes the disc real: two keys

AD-7 decided this five milestones ago — *"a small tagging pass: scrub, press `t` on a throw,
`c` on a catch. Roughly 20 keystrokes per possession"* — and it was right. **The surface was
never built.** That is the finding behind the finding: `ur/disc.py` fell back on inferring
the holder because there was nothing authoritative to work from, and the only human event in
`work/p0001/events.json` turned out to be a schema example that had been carrying
`source: "human"` since M5. Read as truth, it forced O4 as the holder for a single frame in
the middle of another player's possession. It now carries `source: "example"`, and the
`events@1` contract names the three sources explicitly so the next one cannot be mistaken.

The tagging surface now exists in the viewer. Select a player, press `t` on the frame they
release and `c` on the frame they catch; the pane lists what has been tagged and downloads
`events.json`, which goes in the possession directory. `ur.disc` treats a tagged frame as a
**hard constraint** — no other holder is admissible there — and still solves the spans
between tags, so partial tagging degrades gracefully instead of all-or-nothing.

Two clicks per throw fix the disc exactly: held by the thrower up to the release, in flight
between, held by the receiver after. Nine throws is eighteen keystrokes, and it turns an
entire possession from `unknown` to `confirmed`.

## What this changes about the build order

`docs/25` Part 3 proposed: (1) holder inference, (2) two-click tagging, (3) flight detection,
(4) automatic release and catch. Step 1 was expected to reach ≥ 90 % on its own and to
produce the labels step 3 needs.

**Reverse 1 and 2.** Tagging is not the fallback for when inference is not good enough; it is
the source of the only ground truth this problem has. Nothing here can be validated without
it — not the holder inference, not a flight detector, not an automatic release. Twenty
keystrokes on one possession would produce, for the first time, a labelled holder sequence
to measure against; the inference could then be scored honestly rather than argued about, and
tuned against something real.

The visual check that started this points the same way. Rendered at 5× around the inferred
holder, **the disc is plainly visible in hand on some frames** (`eval/m8/holder_check.jpg`) —
so a human can do this quickly and reliably, and so, eventually, could a detector trained on
what the human tags.

## Next: tag, score, ask again — a loop rather than a pass

*Agreed 2026-09-14. Not built; this is the shape it should take.*

Reversing steps 1 and 2 gets ground truth into the problem, but tagging every throw of every
possession by hand does not scale past the first few games. The thing that scales is a loop,
and the loop is worth building properly the first time:

1. **A human tags a few throws** on a possession — not all of them.
2. **The inference is re-solved with those as hard constraints**, which it already supports,
   and the spans between them get much easier: a tagged catch fixes one end of the next
   holder run, so the search is bounded rather than free.
3. **It scores itself** — against the tags it now has (did it recover a held-out tag?) and
   against the physics checks it already runs.
4. **It asks for the next tag where it is least certain**, rather than in frame order. The
   Viterbi already computes the cost of the second-best path; the frames where that margin is
   thinnest are exactly the ones a human should look at.
5. **Repeat until the confidence threshold is met**, then stop asking.

The payoff is that the human cost per possession *falls* as the model improves, instead of
staying at twenty keystrokes forever, and the stopping rule is a measured confidence rather
than "we tagged them all". It is ordinary active learning, and the two pieces it needs
already exist: tags as hard constraints, and a solver that can report its own margin.

Two things to get right when it is built:

- **The confidence threshold has to be calibrated against held-out tags**, not against the
  physics checks. The physics checks can only ever say a sequence is *implausible*; they
  cannot say a plausible one is right. Scoring against a tag the solver was not given is the
  only honest measure, and it is cheap — hold out every third tag.
- **Do not let the loop train on its own output.** A confident wrong holder that gets fed
  back as a constraint is how this fails silently, and it is the same failure mode as the
  `identity_switches_caught: "2 of 2"` figure that was withdrawn in round 2 — a detector
  agreeing with the analysis that produced it.

## Honest limits

- **One possession, and the holder sequence in it is unverified.** Every number above scores
  the inference against physics, not against a person. It establishes that the sequence is
  wrong; it does not establish which frames are wrong, or that a tagged sequence would be
  right.
- **`z` is a shape, not a measurement.** It exists so the viewer draws a flight rather than a
  ground slide. Never quote it.
- **The flight duration floor is a stand-in.** Where a release happened is exactly what the
  `t` key is for; until it is pressed, a flight shorter than a quarter second is widened
  symmetrically, which is an assumption wearing a number.
- **LOOSE is unimplemented.** A disc on the ground after a turn is rare and needs a turnover
  event to bracket it. Nothing in `p0001` needs it.

---

# The first ground truth, 2026-09-14

**Six timing-only tags and four identities on p0001. The span solver got 0 of 4.**

This is the first time anything in this project has been scored against a person
rather than against physics, which is what the section above said was needed. The
answer is worse than the section expected.

## What was tagged, and what the solver said

The tagging design changed first, and the change is the reason there are tags at
all: `t` and `c` with **nobody selected**. The moment is the half a person can
see; identifying a jersey at this range is the half M5's OCR failed at, reading
7 % of crops. `ur/spans.py` then solves who from the timing, constrained by the
chain (the receiver of one throw is the thrower of the next), no self-passes, and
a disc's speed range.

| span | truth | solved | margin the solver reported |
|---|---|---|---|
| 0.00–7.60 s | **O7** | O5 | 0.93 yd |
| 8.47–9.93 s | **O4 #50** | O1 | 1.58 yd |
| 11.80–15.87 s | **O5 #5** | O3 | 1.58 yd |
| 16.53–23.93 s | **O4 #50** | O1 | 1.58 yd |

O7 → O4 → O5 → O4, and the solver said O5 → O1 → O3 → O1. Nothing in common.

## Three things that follow, and only one of them is encouraging

**The emission cost is measuring the wrong thing.** Ranked by "combined path
length of a candidate and their nearest defender", the true holder comes
**3rd, 3rd, 3rd and 1st of seven**. Summed over the possession the truth costs
28.6 yd against the solver's pick at 20.6 — the model does not merely fail to
separate them, it **actively prefers the wrong answer**. That is not noise to be
averaged away with more tags. `docs/27` above argued the stillness signal was
drowned by tracker error and near-stationary pairs; measured against a person, it
is worse than that.

**The margin is not a confidence, and the loop was going to lean on it.** All
four wrong answers carry margins of 0.93–1.58 yd, which is the same range a right
answer would produce. "Ask where the margin is thinnest" — the whole of step 4 —
rests on a quantity that has now been observed to be uninformative on the only
four cases with truth. It is not calibrated and must not be presented as though
it were.

Note the fourth span especially: the truth **ranked first on emission** and the
solver still picked O1, because the chain had already committed to a wrong
holder upstream. The chain constraint is real and it propagates early errors to
the end.

## The encouraging one: a disc flies at one speed

The three true throws:

| throw | | distance | flight | speed |
|---|---|---|---|---|
| 7.60 s | O7 → O4 | 9.5 yd | 0.87 s | **11.0 yd/s** |
| 9.93 s | O4 → O5 | 20.5 yd | 1.87 s | **11.0 yd/s** |
| 15.87 s | O5 → O4 | 7.5 yd | 0.67 s | **11.2 yd/s** |

Over a 2.7× range of distance, the speed is constant to within 2 %. Every
endpoint is `observed`, so these are measurements rather than dead reckoning.

The solver's own picks, by contrast, imply 11.3, **2.0** and 8.0 yd/s — and 2.0
is precisely the floor of the admissible band, meaning the penalty was pushing
against that pair and the solver took it anyway because the emission cost told
it to.

**So the speed was used as a wide gate when it should have been the signal.**
`FLIGHT_SPEED_YD_S = (2, 40)` only rules out the absurd. A cost that *prefers*
assignments whose implied speeds are consistent — with each other and with
~11 yd/s — would have rejected the middle pick outright. That is the change to
make, and it is grounded in three measurements rather than a parameter sweep.

n = 3 throws on one possession. It is a striking regularity and it is not yet a
constant; the next possession's tags either confirm it or do not.

## What this does not undermine

The tagged moments themselves are worth exactly what they claimed. With the four
identities supplied, p0001 now carries **181 `confirmed` disc frames and 48
`interpolated` flights**, and the Mark and Separation-at-release cards read off
a holder a human named. The tagging surface and the round trip work. It is the
*inference* between tags that has now been measured and failed.

## Flight speed as the ranking signal, and its first held-out test (2026-09-15)

`docs/30` § 2.5 recorded that the three true throws on p0001 fly at 11.0, 11.0 and
11.2 yd/s over a 2.7× range of distance, while `FLIGHT_SPEED_YD_S` was spending
that signal on a 2–40 yd/s admissibility gate. Measured, that gate is nearly
inert: **of the 41 wrong pairings available at each of p0001's three throws, 40,
39 and 31 sit inside the range and cost exactly nothing.**

So the gate became a ranking: `SPEED_LOG_WEIGHT_YD * |log(v / 11.0)|`, log because
speed error is multiplicative. On p0001 that ranks the true pair **1st, 2nd and
1st of 42**.

**p0001 cannot test this and was never asked to.** v0 = 11.0 is the median of
those same three throws, and the ranking is knife-edge sensitive to it — at
v0 = 8 the true pair ranks 8th, 13th, 6th; at v0 = 14, 9th, 15th, 5th. The weight
is not knife-edge: 20, 40 and 80 give the same assignment, so the robust claim is
"speed should outrank the emission", which is what the evidence asks for — over
p0001's four spans the emission ranks the true holder **3rd, 3rd, 3rd and 1st of
seven**, against the 4th a coin would give.

### The test: p0009, held out, run once

| | |
|---|---|
| p0001 (training, proves nothing) | 4 / 4 |
| **p0009 (held out)** | **3 / 7 = 43 %** |
| gate | ≥ 75 % |

**The gate is not met.** Three findings come out of it, and the second is the one
worth keeping:

1. **It is a real improvement.** The unaided solver scored 0 / 4; this scores 3 / 7
   on a possession it never saw, and the first three spans are right.
2. **The speed model generalises in its centre and not in its precision.** p0009's
   true throws fly at 11.96, 13.13, 9.25, 11.62, 13.89 and 4.19 yd/s — median
   **11.79** against the assumed 11.0, so the constant is about right. But
   p0001's three throws span a range of **0.26 yd/s** and p0009's six span
   **9.7**. The tightness that made speed look like a sharp discriminator was a
   coincidence of n = 3. A wrong pair can sit closer to 11.0 than the true one
   does, and on four of seven spans it did.
3. **The margin is now anti-predictive: r = −0.47.** Not merely uninformative —
   inverted. p0009's three correct spans carry margins 3.92, 1.54 and 1.54; three
   of the four wrong ones carry 7.84, 7.84 and 8.77. **Step 4 of this document —
   ask for the next tag where the margin is thinnest — would therefore ask in the
   places the solver is most likely to be right.** That strategy is withdrawn
   until something predicts correctness.

One caveat on the denominator: p0009's last throw ends at the goal catch, where
O6's position is `predicted` and lands outside the sideline. That is where the
4.19 yd/s comes from. The span is graded anyway — dropping the inconvenient one
is how a number starts flattering itself — but it is one of the seven.

### The second held-out possession: p0003, and the verdict

p0003 was tagged after the model was frozen, so it is a second clean test.

| | spans | accuracy |
|---|---|---|
| p0001 — training | 4 / 4 | 100 % (proves nothing) |
| p0009 — held out | 3 / 7 | 43 % |
| **p0003 — held out** | **1 / 5** | **20 %** |
| **both held out** | **4 / 12** | **33 %** |
| gate | | ≥ 75 % |

Seven candidates per span, so chance is about 14 %. **33 % is better than guessing
and nowhere near usable, and the honest reading of "43 %" a possession earlier is
that n = 7 was too small to tell.** The margin over all sixteen spans correlates
with correctness at **r = −0.16** — no longer strongly inverted, but still not a
confidence.

The one p0003 span it got right is the weakest of the five: the true holder is
anchored on 5 of that span's 71 frames. Three of the four it got wrong had the
true holder anchored on *every* frame of the span. So the failures are not a
tracking-coverage problem; the model is being shown the right players and
choosing the wrong one.

**Two things p0003 exposed that are not about accuracy.**

*The span model has no room for a turnover.* The tagger marked **D5** catching at
31.40 s and throwing at 32.73 s — a Wind Chill defender with the disc, in a
possession whose cut note in `clip.json` states "no turnover (disc held by a Sol
player at 1586, 1594, 1604 and 1611)". `ur/spans.py` builds its candidate list
from the offence only, so a defender's name silently resolves to "unnamed" and
the span is guessed among the seven Sol players. Whatever the footage really
shows, one of those two records is wrong, and the solver cannot represent the
possibility that the tagger is right.

*A goal is scored where the tracking is not.* Both p0009's goal and p0003's goal
were expected to settle the attacking direction for free — a goal is caught in an
endzone and the goal lines are at known x. Neither could. p0003 has **no anchored
player at all from 33 s to the end**, and p0009's goal catch is `predicted` and
lands outside the sideline. That is not bad luck: the camera tightens on the
endzone to show a score, which is exactly the framing `docs/29` measured as
breaking the calibration. **Scores are systematically the least observable moments
in the footage**, which is worth knowing before planning any measurement around
one — including the direction cut proposed in `docs/30` § 2.0.

### Two of the findings above are withdrawn, and the reason matters more than they did

The tagger checked p0003 against the footage. Both of the things "p0003 exposed"
were mine, not the data's:

- **There is no turnover.** The D5 catch-and-throw at 31.40–32.73 s is a Sol
  player carrying a Wind Chill label. `clip.json`'s "no turnover" note was right
  and the doubt cast on it here was wrong.
- **There are no untagged throws.** The two "chain breaks" are tracking identity
  errors. At 5.67 s O1 catches; by 8.73 s the tracker has lost O1 and put the same
  person under the label O5, so the tagger — clicking the same human both times —
  produced "O1 caught, O5 threw". At 21.27–26.33 s the player is jersey #20 and is
  *neither* O1 nor O5; no slot names them correctly at all.

**What that means is the important part: the identity ground truth is not
independent of the tracker.** A tagger selects a person in the picture and the
name they get back is the tracker's name for that person. Where the tracker's
identity is wrong the tag is wrong, and the solver is being graded against its own
upstream's mistake. On a stretch where two slots have been swapped, "which slot
holds the disc" is not a well-posed question, and no cost function can be right
about it.

**The mechanism, which is fixable.** At 31.40 s the D5 marker is `interpolated`,
by 31.80 s `predicted`, and its dead reckoning walks it to y = −3.4 — off the
field — while the kit classifier, which never sees a prediction, reports 0.99 all
the way through. The kit model did not fail. A marker that is only a prediction
drifted onto a real player of the other team and was clickable, and the tag it
produced was indistinguishable from a tag on somebody observed. The viewer now
says so at tag time and stamps such a tag `named_on: <state>`.

**Three things were tested against this and none of them rescued the accuracy.**

| | |
|---|---|
| corrected tags, all graded spans | 8 / 17 = 47 % |
| corrected, held out (p0003 + p0009) | 4 / 13 = 31 % |
| held out, restricted to spans whose truth names an **observed** player | **3 / 9 = 33 %** |

The last row is the one that settles it. If the failures were caused by tags on
dead-reckoned ghosts, grading only the trustworthy spans would lift the number; it
does not move it. p0003 scores **0 / 3** on precisely the spans where the truth is
solid. **The model is wrong about spans where everything is observed and named
correctly**, which is what the 33 % means and why no amount of tag hygiene will
fix it.

And a check that came to nothing, recorded so it is not retried: all three
mislabelled stretches fall inside a flagged `unverified_stretch`, which sounds
like the issue detector predicting them until you notice that **issues cover 83 %
of p0003's timeline**. Three hits at an 83 % base rate is p ≈ 0.57. It predicted
nothing.

### Closing p0003's last span, and why it does not count as truth

The tagger, watching the possession ring, asked to relabel the player they read
as jersey **#28** to close the 21.27–26.33 s hole. The pipeline carries no jersey
numbers at all, so a jersey read cannot be mapped to a slot directly. It was
settled by elimination instead:

- **The chain** rules out O3 (who threw it at 19.27) and O6 (who catches the dump
  at 27.13); nobody throws to themselves.
- **Coverage** rules out the rest. Over the span's 77 frames the tracker observes
  O2 on **6** and O6 on **11**, against **40–69** for every other offence slot.
  The two it loses are exactly O2 and O6, and O6 is already out.
- **The play agrees**: O2 dumps to O6 and gets it straight back to huck, which is
  what the tagger described watching.

That leaves O2, and only O2. The span is named, and p0003's display hole closes —
`disc not lost for long` goes from 7.8 s to 3.1 s.

**It is marked `player_inferred` and the grader refuses it.** Part of that
argument is *which slots the tracker loses*, so scoring the holder solver against
it would be scoring the solver partly against its own upstream — the brief's
second trap, never feed the solver's own output back. It stays in the file, where
it closes a real hole in what a reader sees; it does not count in
`span identity accuracy`, which reads **8 / 18 = 44 %** with it excluded.

**And the display it closes is the weaker one.** The flag used to stop at span
resolution. `ur/disc.py` read the named slot's coordinates, found them observed,
and emitted `confirmed`, so the Mark card at 26.20 s said MEASURED about a holder
nobody had read. Evidence about *who* and evidence about *where* are different
claims and the weaker one governs, which is the rule that already sends a tag on
a dead-reckoned slot to `predicted`. The span is `predicted` throughout now, and
`disc_meta.name_inferred` carries the reason.

The viewer still draws it, on the frames where it drew before. Suppressing the
span outright would reopen the 7.8 s hole that naming it closed, and every card
built on it now says the name was settled by elimination. It draws on those
frames and no others: `predicted` here means either the identity is weak or the
position is, and on three frames of this very span it means the second, because
the slot is the re-acquisition onto the match official. A name nobody read does
not improve a position nothing saw. The site check
`no confirmed disc from an inferred name` fails if any frame goes back. #15.

Worth noticing which way that moved. Naming the span *lowered* the headline
number — 47 % to 44 % — because it added spans the solver gets wrong. That is the
direction more truth should move a score that is not yet good.
