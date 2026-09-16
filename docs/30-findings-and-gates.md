# 30 — What is known, and what has to be true to call it good

Written 2026-09-14 at the end of a long session, as the entry point for the next
one. `docs/29` is how the possessions were found and calibrated; `docs/27` is the
disc. This is the summary and, more usefully, **the list of things that have to
pass**.

```bash
python -m tools.gates                       # every gate, every possession
python -m unittest discover -s tests -t .   # the pure-logic modules, on invented data
```

The gates exit non-zero if anything fails. Some things fail on purpose; § 3 says
which. They need **`node` on PATH** as well as the Python environment: two of the
site checks read the accuracy sentence the viewer *renders*, which is JavaScript,
and § 2.7 is the defect that made that necessary. Without node those two rows go
red saying so rather than quietly skipping, because a gate that cannot run has
not passed. Licence and reasoning: `docs/07-licenses.md`. `tests/` holds stdlib `unittest` cases for the three things that can be
graded on invented data rather than on footage: `ur/direction.py`, whose job is
to turn two contradictory human statements into a refusal; `tools/checks.py`,
which is the difference between a gate and a measurement; and
`tools/gate_sentence.py`, which renders the viewer's accuracy sentence so a gate
can read it. Everything else in the pipeline is graded against real footage,
which the gates do.

---

## 1. Where it stands

**Six possessions published**, three Sol on offence and three Wind Chill — which
is new, every possession before today was Sol.

| | offence | frames the calibration accepts | median roster in shot | blank | M1 mean | M1 max |
|---|---|---|---|---|---|---|
| p0001 | Sol | 96 % | 11 of 14 | 4 % | 0.118 | 0.446 |
| p0009 | Wind Chill | 86 % | 9 of 14 | 10 % | 0.132 | 0.314 |
| p0003 | Sol | 72 % | 9 of 14 | 22 % | 0.160 | 1.262 |
| p0005 | Wind Chill | 72 % | 8 of 14 | 19 % | 0.208 | 1.277 |
| p0004 | Sol | 65 % | 9 of 14 | 32 % | 0.113 | 0.745 |
| p0015 | Wind Chill | 62 % | 8 of 14 | 34 % | 0.102 | 0.304 |

**Four cut and not published** — p0006, p0007, p0008, p0010. All pass M1
acceptance; p0008 passes at 0.077 yd, better than anything published. None has a
median frame with a located player on it. That gap between "passes M1" and
"worth looking at" is § 2.1.

---

## 2. The findings, in the order they cost the most

### 2.0 The attacking direction has never actually been measured

`ur.possess` fit the drift of the offence along x and `clip.json` recorded the
answer as `attacking_direction`. On 2026-09-15 that was checked across every
possession at once for the first time, and it does not survive. **The finding
stands; what was built on top of it is at the end of this section.**

**Two teams on the field attack opposite endzones.** That statement needs no rule
about when ends are switched, who receives the pull, or how quarters work. So
within a quarter, a Sol possession and a Wind Chill possession must drift in
opposite directions. They do not:

| quarter | Sol on offence | Wind Chill on offence | |
|---|---|---|---|
| Q1 | p0008 **+53.8**, p0003 **+27.2** | p0009 **+20.2** | same sign |
| Q2 | p0004 **−8.4** | p0005 **−23.3**, p0006 **−12.3** | same sign |
| Q3 | p0007 **−1.8** | p0010 **−40.4** | same sign |
| Q4 | p0001 −1.7 | p0015 +54.5 | consistent |

Three of the four quarters contain a direct contradiction. Quarters are read off
the broadcast score bug and now stored as `clip.json:quarter`.

**The measurement is not the problem.** Three things were checked before blaming
the number:

- *The frame is shared.* Every possession carries an identical `venue_transform`
  (`x_sign 1, x_offset 60`), and pointing the camera at field x = 60 in p0003,
  p0005 and p0009 shows the same stand, the same videoboard over the halfway
  line. The x-axis means the same thing in all of them.
- *It is real movement, not framing.* The centroid is computed over players in
  shot, so panning could have moved it. Recomputed over only the offence slots
  anchored at **both** ends of the possession, the answer is identical to a
  tenth of a yard — on the possessions where that cohort exists it is all seven.
  `tools/gates.py:_drift` now uses a per-player least-squares slope anyway.
- *The labels are right.* p0003's scorer is in light kit (Sol) and p0009's disc
  is in the hands of a dark-kit player with a light-kit mark on them (Wind
  Chill), both read off the frames.

So the offence really does move that way, and "the offence moved +x" really is
not "the offence attacks +x". **No possession's attacking direction is currently
established**, including the six published ones.

Two consequences were corrected the same day. `docs/30` previously recorded
p0001 as *disputed* and p0010's direction as *wrong*; both rested on this check
and neither is established. The viewer's overhead now labels the arrow
`unverified`, and the "Deepest threat" card no longer concludes "the huck is on",
because deep and goal-side are defined by an endzone nobody has pinned down.

**One lead, offered as a lead.** Direction sign is predicted by the parity of
`(point number + team)` on all ten possessions, with no exceptions — point number
being goals scored before the cut, from the score bug. Ten for ten is worth
writing down, but the model was chosen after seeing the data from a small family
of candidates, so it is a hypothesis to test on the next cut, not a finding.

What would settle it properly: the disc crosses a goal line when a point is
scored, and both goal lines are at known x (20 and 100). A possession cut to
*include* its score locates the attacking endzone directly, with no inference.
`docs/29` avoided cutting through scores because endzone framing breaks the
calibration — that trade is now worth revisiting for one deliberate cut.

**What was done instead, 2026-09-15 (AD-10, issue #5).** The measurement was not
replaced with a better measurement; the fact was moved to where it can be stated.
Direction is held once per `(quarter, team)`, a human confirms it against the
footage — one click under the overhead, or `python -m ur.direction confirm` — and
`ur/direction.py` resolves the rest: the other team attacks the other end, and
every possession in the quarter follows. The observation is written into that
possession's `events.json`; the fact is stored nowhere, so no two copies of it can
disagree. `clip.json:attacking_direction` went back to being a declaration,
checked against the confirmation rather than feeding it. § 3 has the gates and
the count of quarters actually confirmed, which is the number to read.

### 2.1 An acceptance number is about the frames it sampled

`ur/calibrate/accept.py` draws its held-out frames from the frames that already
cleared the confidence gate. On a possession where the gate rejects most of the
footage, a beautiful mean is a statement about the good quarter. p0006 passed at
0.35 yd on **six testable frames inside a 139-frame span of 450**.

The acceptance JSON now carries `usable_fraction`, and `tools/gates.py` prints it
beside the mean rather than under it. **The fix was not a better number, it was
refusing to report one without its denominator.**

### 2.2 The halfway line is the whole game

Counting which frames fail across every possession: **not one line-bearing frame
fails, anywhere.** p0001 316/316, p0004 289/289, p0006 118/118, p0010 61/61. The
usable fraction *is* the fraction of frames with a halfway line in shot, and
frames without one collapse to a focal length of 10¹⁵.

`docs/28` had already shown circle-only frames are not inherently worse and
removed the confidence penalty on them; the solve still ran away, because a
circle pins the plane and the scale and leaves rotation about its normal
unobserved. `ur/calibrate/mosaic.py` observes that direction from the stands and
the boards, and the paint then refines inside the box its measured accuracy
allows.

### 2.3 Three checks, because each one catches what the others cannot

All three are in `ur/calibrate/mosaic.py` and all three found real defects:

1. **A floor.** A pose implying more than 2 yd of error is not written at all —
   dead reckoning is 0.6–3.5 yd (`docs/05`), so a worse pose says less than
   predicting does. Caught a run of p0004 frames scored **0.0001** that were
   producing twelve player positions each.
2. **Registration cross-check.** Every paint-solved frame is re-derived from the
   others. Median disagreement on p0004 is **0.02 yd**, p90 0.07 — and one frame
   at **4.51**, a circle-only fit 9° out that nothing else could contradict,
   because the known-geometry check abstains without a halfway line.
3. **Impossible motion.** A pose can be self-consistent, agree with its sources
   *and* pass known geometry and still be somewhere the camera cannot have been.
   Threshold 1 yd, from p0001 never exceeding 0.35 across its whole length while
   the offenders run 1–16 yd.

### 2.4 No cheap pre-filter predicts whether a possession will calibrate

Three were tried — conic-and-line on the raw frame, the same masked below the
horizon, and a halfway-line-only screen built on the measured cause. Correlation
across nine known outcomes is **+0.11**, and the single best-scoring candidate of
all 49 calibrates at 35 %. **Screening means running the calibration**: six
minutes, six wide, and the hit rate is about two keepers in nine.

### 2.5 The first ground truth says the holder solver fails completely

Six timing-only tags and four identities on p0001. Full account in `docs/27`
under "The first ground truth".

| span | truth | solved | margin it reported |
|---|---|---|---|
| 0.00–7.60 s | O7 | O5 | 0.93 yd |
| 8.47–9.93 s | O4 | O1 | 1.58 |
| 11.80–15.87 s | O5 | O3 | 1.58 |
| 16.53–23.93 s | O4 | O1 | 1.58 |

**0 of 4.** Three things follow:

- **The emission cost prefers the wrong answer.** True holder ranks 3rd, 3rd, 3rd
  and 1st of seven; the truth totals 28.6 yd against the pick's 20.6. Not noise.
- **The margin is not a confidence.** Four wrong answers at 0.93–1.58 yd, the
  range a right answer would give. `docs/27` step 4 — ask where the margin is
  thinnest — rests on it.
- **Flight speed is a strong signal that was used as a wide gate.** The three
  true throws fly at **11.0, 11.0 and 11.2 yd/s** over a 2.7× range of distance,
  every endpoint observed. The solver's picks imply 11.3, **2.0** and 8.0. n = 3.

**Acted on the same day, and it did not survive contact.** The gate became a
ranking and was tested on two possessions tagged afterwards and held out:
**p0009 3 / 7, p0003 1 / 5, together 4 / 12 = 33 %** against about 14 % for a
guess and a 75 % gate. The 11 yd/s centre generalises (p0009's true throws median
11.79) but the *tightness* did not — p0001's three throws spanned 0.26 yd/s and
p0009's six spanned 9.7, so a wrong pair can sit closer to 11 than the true one.
p0001's tight cluster was a coincidence of n = 3. Full account in `docs/27` under
"Flight speed as the ranking signal".

### 2.6 Measure the artefact, not the log

Three fixes this session printed success while leaving the defect in place: a
loop bound capped at six iterations reporting "dropped 6" for every possession
alike; an acceptance cliff calibrated on frames whose paint was good, then
applied to frames whose paint was degenerate; and a smoothness check comparing
against neighbours that had already been removed. All three were caught by
re-measuring the output afterwards, and none by reading what the tool said.

### 2.7 A null is not a zero, and only the rendered sentence can tell you

Five of the six published pages printed a rounded **`0 %`** for tracker recall
and again for sigma containment. Nobody had measured either on those
possessions: `per_player_recall` and `sigma_containment` are `null` in their
data, and `measured_on` says `p0001`. The data was correct and honest.
`Math.round(null * 100)` is `0`, so the viewer turned "unmeasured" into
"measured, and terrible" on its way to the screen.

Every data-side check was green through all five, and correctly so — including
`no borrowed gate numbers` in the site table in § 3, which exists to stop exactly
this class of misstatement and could not see it, because the misstatement was not
in the numbers. It was in the rounding.

This is the limit of the rule at the top of `tools/audit_site.py`, which says to
read the published JSON and not the rendered page. That rule is right about what
a page *asserts*, and it is blind to what a page *prints* when the two disagree.
So two checks now run the viewer's own `gateSentence` under node against the
published document and read the string that comes back —
`tools/gate_sentence.py`. Not a Python re-implementation of the formatting: a
second copy would agree with itself and catch nothing, and it would have to
reproduce JS's half-up rounding rather than Python's half-to-even to avoid
disagreeing about `12.5`.

The test is not "does the printed number match the expected one". It is: **render
the page a second time with every measurement removed, and see what still
prints.** A figure that survives having its measurement taken away was never
resting on one. That is what makes it catch the bug on `p0001` as well, where
the page prints a true `97 %` today over code that was one null away from
printing `0 %` — comparing values would have called that page clean.

Printing no number is only half the fix, so the second check asks the page to
say the word. A page that prints nothing and says nothing has left a gap where a
figure would go, and a gap reads as "fine".

The general form, and the reason this is a finding rather than a bug report: **a
formatter is a place a claim can be invented.** Rule 3 in `AGENTS.md` gets every
position to the page with its evidence state attached, and then one `Math.round`
threw the state away. Anywhere a null, a NaN or an empty list passes through
arithmetic on its way to a reader, the number that lands is a claim nobody made.

---

## 3. The gates, and which of them fail on purpose

`python -m tools.gates` prints **143 rows, and only 119 of them can fail.** It
ends on two totals, and they are not the same kind of number:

```
105 of 119 failable check(s) pass, 14 failing.
24 informational row(s) report a measurement and no verdict.
```

The fourteen failures are every one either a known-unpublished possession or a
documented open problem, and the tables below say which. The twenty-four
informational rows are **measurements** — numbers with no threshold to hold them
to — and the first table below names all twenty-four and what each is waiting
for.

Until 2026-09-16 those twenty-four were built as gates with an unconditional
pass. They printed `[PASS]`, they counted into one total of 132, and that total
was the number a reader trusted. It was inflated by rows that could not have done
anything else — and worse, `docs/31` closes an issue when a named check flips to
PASS, so a row that can never flip is a definition of done that can never be met.
They now print `[measured]`, carry the reason there is no threshold instead of a
`want`, and are totalled apart. `tools/checks.py` holds the distinction and is
where a new check picks its kind.

### The rows that cannot fail, and what each is waiting for

Twenty-four rows, four kinds. Each reports a number the run is better for
carrying, and none of them can be a gate today. What is in the last column is
what would make one failable — and until that exists, a threshold on it would be
a number chosen to make current output pass, which is the first of the three
things the brief asks not to happen.

| row | rows per run | what it reports | why it is not a gate today | what would make it one |
|---|---|---|---|---|
| `...measured on` | 10, one per possession | the fraction of frames the M1 mean was measured on | there is no fraction below which the possession is *wrong*. A thin denominator makes the **mean** weaker evidence; it is not itself a defect, and the mean it qualifies is already gated. § 2.1 | a measured relation between usable fraction and the error on the frames the acceptance never sampled. Nothing has measured that, and § 2.2 suggests the honest quantity is "is the halfway line in shot", which is a different row |
| `offence drifts` | 10, one per possession | median per-player least-squares drift of the offence along x | § 2.0: this quantity is **not** the attacking direction, so no value of it is right or wrong. It stayed in the run because the movement is real and worth seeing, not because it decides anything | nothing, and that is the point. The thing it was mistaken for is gated across possessions in `Qn: opposite teams disagree`; this row is the diagnostic that was promoted to a fact once already |
| `...quarters confirmed` | 1 | how many quarters have a human-confirmed attacking direction — today **0 of 4** | an unconfirmed quarter claims nothing, so there is nothing to contradict. Gating it would fail every possession cut before somebody got round to watching it, and a queue is not a defect | confirming becoming part of cutting a possession rather than a backlog. Then `0 of 4` **is** a defect, the threshold is *all of them*, and it moves to the failable total under #5 |
| `...longest blind stretch` | 3, the published possessions carrying human tags | the longest stretch inside the tagged region where a reader sees no disc at all | no principled threshold exists. `disc not lost for long` bounds a *flight* at 5 s on physics — every human-tagged flight runs 0.27–3.20 s. This one has no physics behind it, and a number picked because it happened to fail p0003 is tuning a constant to produce a verdict, backwards | #8. Naming a holder does not supply a position — p0003's 21.27–26.33 s span is named O2 and still mostly blank, because the tracker observes O2 on 6 of its 77 frames. A threshold needs a distribution measured across more than three tagged possessions |

The count moves with the work: ten possessions in `work/`, so ten of each
per-possession row, and a fourth published possession with tags adds a fourth
`...longest blind stretch`. What does not move is that none of them can be
counted as a passing check.

### Per possession — all six published ones pass

| gate | threshold | where it comes from |
|---|---|---|
| M1 acceptance, mean | < 0.75 yd | `docs/04` M1, unchanged since the first milestone |
| M1 acceptance, max | < 1.5 yd | `docs/04` M1 |
| …measured on | *measurement* — see below | § 2.1. A mean without its denominator is not a result |
| roster structure | zero problems | `docs/04` M4, AD-2 |
| camera motion is possible | 0 frames over 1 yd | § 2.3 |
| median roster in shot | ≥ 6 of 14 | publishing gate. Below this the median frame is mostly empty |
| frames with nothing at all | ≤ 35 % | publishing gate |
| offence drifts | *measurement* — see below | § 2.0. The drift is real; it is not the attacking direction |

**Currently failing and expected to:** p0006, p0007, p0008 and p0010 on coverage
and on camera motion — they have not been through the impossible-motion check and
are not published.

### The published site — 56 rows, 53 of them failable, all passing

`tools/audit_site.py`, folded into `python -m tools.gates`. Every other gate in
this document reads `work/`; these read `docs/`, which is the only thing anybody
sees. They exist because clicking through the live site on 2026-09-15 found two
defects that the whole suite was green through.

| gate | threshold | where it comes from |
|---|---|---|
| site is current | published events **and confirmed direction** == `work/<id>/events.json` | AGENTS rule 7 — the live site is the deliverable. The direction was added with AD-10: `make_view` resolves it into the page at build time, so a confirmation made after the last build is one the reader never sees, and the page goes on saying `unverified` over something somebody had settled |
| published tags are used | tags naming a player produce disc frames sourced `human` | p0003 and p0009 published 14 and 12 human tags while every disc frame was still `inferred`. `ur.disc` had not been re-run, so the tagging bought **nothing** on the site. Fixed: 0 → 485 and 0 → 405 frames |
| no borrowed gate numbers | numeric gates only on the possession they were measured on | every page shipped p0001's `per_player_recall: 0.9744` in its data. `measured_on` labelled it honestly, but anything reading `possession.js` still got p0001's recall for p0003. The numbers now travel only with their own possession |
| no unmeasured percentage printed | render the page a second time with **every measurement removed**; no percentage may survive | § 2.7. Five pages printed a rounded `0 %` for recall and sigma containment off `null` fields. These two are the only checks here that read the **rendered sentence** rather than the data behind it, because the data was right and the sentence was not — they run the viewer's own `gateSentence` under node (`tools/gate_sentence.py`), which is why `node` has a row in `docs/07`. Taking the measurement away rather than comparing against an expected value is what makes it catch the bug on p0001 too, where it was latent behind a real 97 %. #11 |
| an unmeasured page says so | the word `unmeasured` appears in the sentence, on a page with no measurement of its own | § 2.7, the other half. Printing no number is not the same as saying there is none: a gap where a figure would go reads as "fine". Only the five pages with nothing measured carry this row; p0001 has numbers and says so. #11 |
| no disc drawn from the failed inference | every drawn frame rests on a human tag | already true, now locked in — the viewer correctly suppressed all 385 `predicted` frames on p0009 |
| no disc drawn on a guessed position | the holder's own position is `observed`/`confirmed` on every drawn frame | the check above asks WHO, this asks WHERE, and they are two facts about one frame. p0003 published the disc on a match official at `confirmed`: the tracker lost O2, re-acquired 26.9 yd away over the sideline, and a correct tag about the catch carried the disc there. 3 frames → 0. The tracker's own error is #4; this is the stage that was publishing it |

Two things that audit taught about writing the audit itself. **Match behaviour,
not source text**: the first version grepped the rendered HTML for "the huck is
on" and flagged it, when the phrase survived only inside a code comment.
**A gate that fires on the wrong thing is worse than no gate**: the staleness
check first compared against `possession.json`'s `events`, which stays empty
until `ur.possess` re-runs, so it failed the instant any tag existed.

And a pipeline-order trap worth knowing: `ur.possess` reads `disc.json`, so
tagging requires `ur.disc` **then** `ur.possess`. Running them the other way
round silently republishes the old disc, which is exactly what the "published
tags are used" check caught me doing.

### Across possessions — nothing claimed, and nothing contradicted

| gate | threshold | where it comes from |
|---|---|---|
| Q*n*: opposite teams disagree | confirmed directions point opposite ways | § 2.0. Two teams cannot attack the same endzone at once |
| *n* : *m* quarters confirmed | *measurement* — see below | the queue, not a defect |
| p*NNNN*: declared direction holds | `clip.json` matches what was confirmed | AD-10 |

**All passing, and read the second line before believing the first.** These
checks used to be fed the **drift** of the offence, and Q1, Q2 and Q3 failed on
it. That failure was real and its cause was § 2.0: the drift is not the
attacking direction, so a contradiction between two drifts was never a
contradiction about direction. AD-10 moved the fact to a `(quarter, team)` and
put a human in front of it, and what these check now is whether two people who
watched the same quarter disagree.

So a quarter nobody has confirmed passes, because it claims nothing. **The number
that says how much of the job is done is `...quarters confirmed`**, and today it
is **0 of 4**. Until it moves, every published page says `unverified` over its
arrow and the `Deep cover` card stays a separation rather than a conclusion —
which is the honest state, not a broken one.

Confirming is one click under the overhead, or:

```bash
python -m ur.direction confirm work/p0003 --direction=+x   # note the =, -x is not a flag
python -m ur.direction                                     # what is known now
```

One confirmation per quarter is the whole ask: the other team attacks the other
end, and every possession in that quarter follows — including ones not yet cut.
A direction reached that way is marked `derived` and never recorded as a
confirmation of its own, so a second confirmation in the same quarter remains an
independent check rather than an echo.

Note what this replaced: this document previously called p0001 *disputed* and
p0010 *wrong* on the strength of the per-possession drift check. Both readings
are withdrawn — not because the possessions are fine, but because the check
that condemned them does not measure what it claimed to. `p*NNNN*: declared
direction holds` is where a wrong `--attacking-direction` gets caught now, and it
stays silent until the quarter has a confirmation to check against.

### The disc — both gates fail, and this is the work

| gate | threshold | why that number |
|---|---|---|
| span identity accuracy | ≥ 75 % over ≥ 8 graded spans | currently **8 / 16 = 50 %**, and that includes p0001's 4 / 4, which is the training set. **Held out on p0003 + p0009 it is 4 / 12 = 33 %**, against about 14 % for a guess |
| margin predicts correctness | r ≥ 0.5 | currently **r = −0.16**. Not a confidence, and briefly measured at −0.47, so `docs/27` step 4's plan to ask where the margin is thinnest is withdrawn either way |

**These are the two numbers that decide whether Goal 2 works.** Neither can move
without more identity tags, and both must be measured on a possession the solver
was not built against.

---

## 4. What to do next, in order

1. **Tag a second possession.** p0009 (86 % calibrated, 9 of 14 in shot) is the
   best target. Timings with `t`/`c`, then name the holder on each span. That
   gives `tools/gates.py` the eight graded spans it needs and gives any rewrite
   something it was not fitted to.
2. **Then rebuild the span cost around flight speed** (§ 2.5), not stillness.
   Do it in that order: the current cost is known to be wrong, and a replacement
   tested only on the four spans that disproved the first one would prove
   nothing.
3. **Confirm one direction per quarter.** The surface exists now (AD-10, § 2.0):
   open a possession, click which way it is attacking under the overhead, and
   download `events.json` over the one in `work/`. Four clicks for four quarters
   settles every possession cut and uncut, and it is the difference between the
   published pages saying `unverified` and saying something. Do Q1 first, from
   p0003 or p0009 — both are well covered, and confirming **both** of them puts
   the cross-check to work instead of leaving it a formality.

## 5. Parked deliberately

- **`Space`** — `docs/06`'s nearest-player Voronoi. It colours 40-yard cells over
  grass nobody can contest and ignores that players are moving. The version that
  answers a question is time-to-reach; player speed is measured over six
  possessions and 18,246 observed steps at p50 3.52, p90 6.81, p99 10.47 yd/s.
- **p0009 at 25.8 s and p0003 at 32.6 s** — the calibration is smooth there
  (steps 0.22–0.66 yd). Only 5–8 of 14 players are anchored while the camera
  follows the throw, the rest frozen at their last position. A viewer
  presentation problem, not a pipeline one.
- **`docs/` is 222 MB**, and each published possession adds ~35 MB to git history
  permanently.
- **`docs/08` #5, the field length** — still unresolved, still the
  highest-leverage unknown. Six calibrated possessions now exist, several
  endzone-framed, which is what that risk says it needs.
