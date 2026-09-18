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
**p0009 3 / 7, p0003 1 / 7, together 4 / 14 = 29 %** against about 14 % for a
guess and a 75 % gate. (p0003 was 1 / 5 when this was written; two more of its
spans became gradeable later — § 3 says which commits and why.) The 11 yd/s centre generalises (p0009's true throws median
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

### 2.8 The page hid the work somebody was paid to do

p0001, p0003 and p0009 publish 6, 14 and 12 human tags. All three pages opened
saying **"Nothing tagged yet"**, on a possession somebody had already sat and
tagged.

The tag list rendered from `TAGS`, the array of tags made in this browser tab,
which starts empty on every load. The published tags reached the metric cards
through `allEvents()`, and reached the download button through `D.events`, and
never reached the one pane whose entire job is to say what has been tagged. The
data was right on all three pages, every data-side check was green, and § 2.7's
two rendered-sentence checks were looking at a different pane.

It is the same shape as § 2.7 one pane over — a correct file, a lying render —
so it gets the same treatment rather than a new one. `tagListHtml(published,
session, fps, nf)` is now a pure function of its arguments, `tools/tag_list.py`
lifts it out of the published page and runs it under node, and `published tags
show on load` counts the rows against the events the page was given. The
mechanics the two checks share — find the function, run it, strip the markup —
came out into `tools/page_js.py` at that point, because a second copy of the
subprocess boilerplate is how the two drift apart.

The gate renders **twice**, and the second render is the half that cannot be
faked: hand the page the same document with `events` emptied and it has to fall
back to the empty state. Counting rows alone would pass a page that hardcoded
the right number of them. And it fails in both directions — a page listing
*more* rows than it was given is a tag counted twice, which is exactly what
seeding the in-session array from `D.events` instead of seeding the render would
do, and is the obvious next way to break this.

One thing the render taught about reading a render. Markup is a **separator**:
stripping tags to nothing glued `8.47s</div>` and `<div>From` into `8.47sFrom`
and lost a row the page had rendered correctly and put on the screen. A check
that reads a page has to read it the way the page is laid out, not the way its
source happens to concatenate.

Two things beyond the bug. The first is why it matters more than a cosmetic
miss: tagging is the one part of this project that costs a person's attention,
and a page that shows no sign of the last pass invites a second one over the same
possession. The second is the shape of the rule — **evidence that is used is not
the same as evidence that is shown.** `published tags are used` has been green
since the day it was written and asks only whether the tags changed the artefact.
They did, in the disc stage, invisibly. Whether the reader can *see* the work is
a separate question and now has a separate row. #12.

### 2.9 A guard is only as wide as the array it reads

Nobody throws to themselves. `addTag()` has refused a catch naming the player of
the preceding throw since the first p0009 tagging pass, where selecting the
thrower and pressing `t` then `c` named them twice across the whole back half of
the possession. It found that preceding throw in `TAGS` — the tags made in the
current browser tab.

So a throw already in `events.json` was invisible to it. § 2.8 putting the
published tags on screen is what made that reachable: a reader could select O2,
press `c` after p0003's published `throw O2 @ 26.33 s`, and watch a self-pass
join the list with nothing said. The same read was wrong a second way. `TAGS` is
sorted by `t`, so "the last tag made" is not "the last tag before this one" —
tag a throw at 30 s, scrub back to 5 s, tag a catch, and the guard compared
against a throw twenty-five seconds in the future.

**The general form.** § 2.8's rule was that evidence which is used is not the same
as evidence which is shown. This is the third member of that family: evidence the
page *displays* is not the same as evidence the page *reasons over*. Three code
paths read the published events — the metric cards through `allEvents()`, the
download button through `D.events`, and, since § 2.8, the list — and a fourth,
the one guard whose whole job is to refuse a wrong tag, read none of them. When a
fact has several consumers, each is a separate place it can be missed, and the
consumers that stay silent when they are wrong are the ones to go looking at.

**The trap in checking it.** Every `events.json` in `work/` is correct, so no
published possession contains a self-pass. A check that read the published data
would therefore have passed today whether or not the guard was fixed — a
definition of done that can never fail to be met, which is the AD-11 trap in a
new costume. So `a self-pass is always refused` **constructs its failure**: it
runs the page's own `selfPassRefusal` under node against four invented scenarios,
using two slots off that page's own roster. Two of the four exist only to stop
the row going green the easy way — a legitimate catch by somebody else, which
must *not* be refused, and the same self-pass with the published throw taken
away, which must go quiet. Without the first, a guard that refused every tag
would pass. Without the second, a guard that refused on the selection alone
would.

---

### 2.10 A repair pass raises the score it was excluded from

AD-13 keeps a hand-placed position out of every grading sample, and that closes
the direct route: a person's own work cannot be counted as the tracker's. It does
not close the indirect one. **A person repairs the frames the tracker got wrong**,
which is what repair is for, so `blind()` removes exactly the hard cases and the
sample that survives is the easier part of the possession. Recall over it goes up,
computed honestly, meaning less.

Nothing is wrong with the arithmetic, which is what makes this worth writing down.
§ 2.7 was a formatter turning a null into `0 %`; here the number is real, the
fields behind it are real, and it is still not the thing a reader takes it for.

The answer is a name and a denominator. A figure measured over a possession
carrying any hand-placed frame is **bounded** - an upper bound, not a result - and
`CONTEXT.md` now carries that beside declared, measured and observed. And every
percentage prints its sample size, whether bounded or not, because `83 %` and
`33 of 40` are different claims and only the second can be weighed.

Bounded-ness follows `measured_on` rather than the page. Five of the six published
pages quote `p0001`, so a repair pass on p0001 makes p0003's printed figure a
ceiling while nothing in p0003 changes at all. `tools/make_view.py` resolves it at
build time across `work/`, the same way and for the same reason it resolves the
attacking direction (AD-9: the page has no siblings to read).

**Two gates, and the second half of each was the part that did the work.**

`every percentage names its sample` began as one ablation, the § 2.7 move a field
over: null every denominator and fail on any percentage that survives. It passed a
deliberately broken page that required the sample size and never printed it,
because removal proves a figure *depends* on its denominator and the row claims
the figure *names* it. So the denominator is now also **substituted** for 4242, a
number nothing else on the page could produce, and has to appear in what a reader
sees. The wording is free - `of 4242`, `4242 labelled players`, `n=4242` all pass.

`a bounded number says it is one` forces the flag both ways, because no possession
is hand-placed yet and the claim has to be constructed (AD-12). The negative
scenario is the one that matters: a page hard-coding the phrase satisfies the
positive case forever. A third run checks the probe reaches a printed figure at
all, since five of six pages print none of their own and agreement on an empty
sentence is not agreement.

All four deliberate breakages fire: denominator dropped from the sentence,
denominator no longer required, bounded prefix disabled, phrase hard-coded.

Today every possession in `work/` is 0.0% hand-placed, so no published page has
printed a bounded number yet. The gates exist ahead of the defect on purpose. #8
lands the first repair pass, and the day it does these rows are what stop the
tracker quietly scoring better for it.

### 2.11 A correction is not a movement, and the first new gate forgot it

**2026-09-17, and the finding is about the tooling rather than the footage.**

A person repairing p0003 on the live page reported the slot labels jumping
between players: *"NO player should be suddenly teleporting across the field like
this during a single continuous camera view."* Measured against
`possession.json`, they were apparently right — `O2` crossed **55.3 yd in 0.27 s**
and then **55.1 yd in a single frame**, `observed` at both ends. A gate,
`player motion is possible`, was written against exactly that.

**It was measuring the wrong pair of numbers.** Frames 339 and 345 are
`confirmed`, which is what an `anchor` produces: they were the person's own
hand-placed positions, three hours old. The check was comparing where a human put
the marker against where the tracker had it and reporting the gap as movement.
Run over `ur.human.blind`, the corpus contains **zero** impossible moves.
`MAX_SPEED_YD_S` in `ur/track/run.py` had been holding the line all along.

Three things worth keeping from it.

**The gate is still right to exist, and now passes honestly.** The camera has
been asked whether it could have moved that way since M1; nothing had ever asked
it of a person, and that asymmetry was worth closing whatever the answer was.

**`no human position in a metric` earned its place.** The first new check written
after `ur/human.py` existed — same session, same afternoon, with the trap
documented three files away — still forgot to call it. That is the argument for a
gate over a convention, and it is why the exclusion is checked by running the
graders rather than by reading the source for the word `blind`.

**What the 55 yards actually is, is a real finding and a different one.** The
tracker has `O2` on a `sol` player at the far sideline, `[67.2, 53.5]`. The person
repairing clicked the disc holder near the camera, `[56.0, 0.2]`, and at that
frame the detector finds eight in-bounds players of whom the nearest to that
sideline is at `y = 12.3` — **nobody is where they clicked**. So the disc holder
is a player the detector never found, which is § 2.5 and #4 again: the jersey-#28
player who has no correct slot anywhere in p0003. Anchoring `O2` onto them does
not correct `O2`; it moves the label from one person to another, and the page
would look repaired while the data said something new and false. The repair pass
stopped there, which was the right call.

### 2.12 The tracker loses a slot and dead reckoning hands it to somebody else

**This finding has no ticket, and that is the finding.** It is the shared
mechanism under three of them and no check closes it short of rewriting the
tracker, so a ticket pointed at it would be a permanent red row that teaches
people to stop reading red rows.

The shape is always the same. The tracker stops observing a slot, dead reckoning
walks the marker for a few seconds, and the re-acquisition adopts whatever is
nearest. What is nearest decides which ticket you are looking at:

- **another player on the same team** — the label moves and the tag made against
  it is wrong. p0003 at 8.73 s: the tracker lost O1 and put the same body under
  O5, so the tagger clicked one human twice and produced "O1 caught, O5 threw".
  That is § 2.5, and #4 is the grading answer to it.
- **a player on the other team** — p0003 at 31.40 s, a Sol player carrying `D5`,
  read downstream as a turnover in a possession that has none. AD-3 makes team
  colour a hard gate and it did not fire, because the kit classifier never sees a
  prediction.
- **somebody who is not playing** — a match official at 21.27–26.33 s, or the
  bench inside `BOUNDS_MARGIN_YD`. #26 gives a person the `detach` operation to
  say so; #29 is the coverage number counting them.

**Why no gate.** Every candidate measures the consequence rather than the cause,
and each already belongs to one of those three tickets. A distance check cannot
help: a sideline official stands exactly where a sideline player stands, and
p0003's worst `observed` position is 2.04 yd against a 5 yd threshold. What would
close this is the tracker not losing the slot, which is not a threshold.

So it is written here, where it outlives the work, and #4, #26 and #29 each own
the part of it that has a definition of done. The sentence that used to assign it
to #4 was struck from #26 on 2026-09-17.

### 2.13 The oracle's own first check un-applies every correction

**2026-09-17, from a `docs/32` pass against the published p0003 and p0009.**

`docs/32` § 0 opens with `python -m ur.resolve <work> --verify-revert`, and § 9
puts the same command at step 4, between `tools.pipeline --from correct` and
`tools.build_site`. It prints **YES, byte for byte** and it is telling the truth.
It also **leaves the reverted document on disk**:

```
python -m ur.resolve work/p0003                  ->  corrections_applied = 17
python -m ur.resolve work/p0003 --verify-revert  ->  corrections_applied = 0
python -m ur.resolve work/p0003                  ->  corrections_applied = 17
```

The revert is the whole method — apply nothing, compare against the uncorrected
output — and the comparison is sound. What is missing is putting the corrected
document back afterwards. So a verification command that promises to read
silently writes, and what it writes is the uncorrected page.

**Run the script in its own order and it publishes the uncorrected page.** Step 3
applies the corrections, step 4 removes them, step 5 builds `docs/` from what
step 4 left. Nothing between them says so. This is precisely "the silent one"
§ 9 warns about — *"any run of `ur.possess` ... rewrites `possession.json`
without corrections and nothing in the artefact shows it"* — except the stray
command is not `ur.possess` and not a parallel session. It is step 4 of the
script, and it is also the first thing § 0 tells a runner to type.

**`corrections reached the page` caught it, for the third time.** That is the
gate's whole job and it did it: after the § 0 oracle ran, p0003 reported
`0 applied, 15 active in the log` against a published page carrying all fifteen.
Re-running plain `ur.resolve work/p0003` restored `15 applied, 15 active` and the
row went green, with nothing else in the suite moving — 158 of 173 before, 159 of
173 after, one row's difference.

**The near-miss is worth recording, because § 10 is what stopped it.** That FAIL
was first written up as a pre-existing dirty work tree — a stray `ur.possess` by
an earlier session. It was not. It was this pass's own § 0 oracle, four commands
earlier. The question § 10 asks is whether the thing being measured is the
tracker's output or somebody's correction held up against it; the useful
generalisation is that the runner is also somebody, and a QA pass has to suspect
its own footprints before it suspects the tree it walked into.

**What would close it.** `--verify-revert` should either restore the corrected
document before exiting or refuse to touch `possession.json` at all and do the
comparison in memory. Until one of those, § 0 and § 9 step 4 need `ur.resolve
<work>` run immediately after them, and `docs/32` should say so.

**Fixed 2026-09-17, and one level below where the finding puts it.**
`--verify-revert` never wrote anything. `ur/possess.py::build` did: it ended on
`GV.write(work, doc)`, so *building* a document put it on disk, and
`ur/resolve.py::load_uncorrected` calls `build` precisely to get the uncorrected
one to compare against.

So restoring the corrected document afterwards — the first option above — would
have left the side effect in place for every other caller and made
`--verify-revert` responsible for cleaning up after a function it only wanted to
read from. `build` now returns and `ur.possess.main` writes, which is where the
one-writer rule `ur/grading.py::write` describes was always meant to sit.

Two tests hold it: `load_uncorrected` and `--verify-revert` must each leave
`possession.json` byte-identical. They run against the real p0003 rather than a
fixture, because the failure is about a path on disk and a temp directory would
not have caught it.

This also closes the two earlier sightings. Both were recorded as unreproducible
and blamed on a parallel session; both had `--verify-revert` run immediately
before, which nobody thought to look at because it is a verification command.


**Re-run 2026-09-17, confirmed.** `--verify-revert` leaves `possession.json`
byte-identical: same md5 over three consecutive runs on p0003 and on p0009, with
`corrections_applied` steady at 15. Driven through `docs/32` § 9 in its own
order, step 4 no longer strips what step 3 applied — after the pipeline the file
carries 17, after `--verify-revert` it still carries 17 (md5 unchanged), and the
page step 5 builds carries `c16` and `c17`. `corrections reached the page`
reports **17 applied, 17 active**, with no new failures against the run before
the append. Last time this sequence published an uncorrected page.

### 2.14 The calibration refusal is skipped exactly where the camera model is worst

**2026-09-17, same pass, and it is a § 5 red on p0003 and a green on p0009 for a
reason that has nothing to do with either possession.**

`docs/32` § 5 asks that at a frame under `PLACE_MIN_CALIB` the repair panel says
so, names the number, and offers a button to the nearest frame that clears 0.5.
At the fixture's dead frame for p0003 — **f0, calibration 0.00** — it does none of
the three. There is no warning, no number and no jump button; the panel still
reads *"Click their feet on the video — that is the picture that knows where they
are."* The click is then swallowed: nothing stages, and the console is clean. The
person gets neither the refusal nor the anchor, and no account of either.

At p0009's dead frame — **f67, also calibration 0.00** — the refusal renders
correctly, names `0.00`, and offers *"Go to 4.40 s, the nearest frame it does"*.
The two frames carry the same confidence. The difference is the homography.

```js
function projector(i){ ... const M = inv3(pf.H); if (M) { o = {...} } ... }
function calibHere(){ const P=projector(S.f); return P && P.conf!==undefined ? P.conf : 1; }
```

When `inv3(pf.H)` fails, `projector` returns `null` and `calibHere` falls back to
**1** — the value meaning *fully calibrated* — so `canPlaceOnVideo()` is true and
the refusal branch never renders. The fallback is backwards: a frame with no
usable projection is the one case where the page is least entitled to vouch for
anything.

**It is not confined to p0003, and the fixture only made it look that way.**
`det(H) == 0` on **41 of p0003's 555 frames**, f0–f11 among them, and on **10 of
p0009's 555**, f440–f449. Driving p0009 at f440 and f445 reproduces the p0003
behaviour exactly — no refusal, no number, no jump, click swallowed — and f67
keeps working. `tools/qa_fixture.py` picks the dead frame by
`confidence < 0.01`, which finds a singular frame first on p0003 and an
invertible one first on p0009. The scenario's pass on p0009 was luck of the
scan order.

**Severity, honestly.** This is *not* the thing § 5 calls the worst this mode can
do. No anchor is produced at 0.00 — the placement path needs the projector it
does not have, so it bails a few lines later. What fails is every positive
requirement of § 5, plus a silent swallow: the panel invites a click, the click
does nothing, and nothing explains it. A person reads that as the page being
broken, or worse, keeps clicking.

**What would close it.** `calibHere()` should return `0`, not `1`, when
`projector()` gives back nothing — a frame with no invertible homography is
below any floor, not above every one. `nearestPlaceable()` already skips those
frames correctly, so the jump button has somewhere to send people the moment the
refusal renders.

**Fixed 2026-09-17, exactly as written above**, plus the wording. The two dead
frames are not the same thing and the refusal now says which one it is: a low
confidence still has a homography and reads *"calibration is 0.01, under 0.5"*; a
collapsed one does not invert at all and reads *"no usable projection at all —
its homography does not invert"*. Both offer the jump, both stage nothing,
verified on p0003 f0 and f42.

**And the fixture now names both**, because § 5 passed for a year on whichever
kind `qa_fixture` happened to surface first. `dead_frame_collapsed` and
`dead_frame_low_confidence` are separate entries, so a run that only exercises
one is visibly a run that only exercised one. That is the general shape of this
finding: the case that slipped through did so because it looked like the absence
of a problem rather than the worst instance of one.


**Re-run 2026-09-17, confirmed on both kinds and both possessions.** p0003 f0 and
p0009 f426 give the collapsed wording and no number; p0003 f42 (0.01) and p0009
f67 (0.00) give the number and no mention of the homography. All four offer the
jump, stage nothing on a video click, leave the overhead drag working, and throw
nothing. Sampling wider — 16 frames on p0003 and 11 on p0009, drawn from the
collapsed, the merely low-confidence and the healthy — the refusal fires on
exactly the frames below the floor, with the wording that matches the kind, and
on none of the others. p0003 has 70 collapsed and 87 low-confidence frames of
555; p0009 has 24 and 38 of 450.

One nicety, recorded rather than filed: p0009's collapsed frames carry no `H` at
all, and the page still says *"its homography does not invert"*. It is the right
category and the right refusal, and `qa_fixture` classifies the no-`H` case the
same way, so the script and the page agree. Only the sentence is loose.

### 2.15 The QA script's first instruction cannot be followed from a clone

**2026-09-17, and this one is about `docs/32` itself.**

`docs/32` opens with *"Run this first, and use what it prints"* and
`tools/qa_fixture.py`, whose own docstring says it *"reads the **published**
page, not `work/`, because that is what a QA pass drives"*. It reads both. The
clean frame is chosen by asking whether each matched detection lands inside the
lines, and that test needs `work/<pid>/detections.json`:

```
FileNotFoundError: [Errno 2] No such file or directory: 'work/p0003/detections.json'
```

`.gitignore` excludes it deliberately and for a good reason — it is footage — and
it cannot be regenerated without the clip and the M2 weights. So a fresh clone
gets no further than the first command, and the runner has no fixture at all: not
the clean frame, and not the busy frame, collision or dead frame either, because
the loader fails before any of them are computed.

The published page is not missing the information by accident. `possession.js`
carries `unused_detections`, but only the leftovers and without the indices
`players[i].det[f]` refers to, so the matched detection's own field position
cannot be recovered from the page. Counting `est` instead is the substitution
`#29` already warns about — f430 read fourteen of fourteen with four of them on
the sideline crowd — so the substitution is worse than the gap.

Two ways out, and they are not equivalent. Publishing each matched detection's
field position into `possession.js` makes the fixture true to its docstring and
the script runnable by anyone with the URL. Failing that, `docs/32` should say in
the first section that the fixture needs a work tree, and `qa_fixture` should
degrade to the three frames it can derive from the page alone rather than dying
on the import of the one it cannot.

**Fixed 2026-09-17 by taking the substitution this finding rules out, because the
measurement does not support ruling it out.** The objection is that counting the
slot's `est` instead of its detection's field position repeats `#29`, where f430
read fourteen of fourteen with four of them on the sideline crowd. That is a fair
thing to suspect and it turns out not to be the same substitution.

`#29`'s error was counting *matched* slots without asking where the match was, so
a slot on a spectator counted as a slot on a player. Using `est` still asks where
it is; it asks of the filtered estimate rather than the raw detection. On f430,
the frame `#29` came from, the two agree exactly — **10 of 14 in-field either
way**, and the same four slots flagged: `O1`, `O3`, `D1`, `D4`. Across p0003's
4053 matched slot-frames they disagree on **5**, 0.12 %, all of them within
inches of a line.

A fifth of a percent of boundary cases is not worth a dependency that stops the
tool running at all, and the alternative — publishing every matched detection's
field position — puts a second copy of a coordinate on every page to answer a
question the first copy already answers. `qa_fixture` now reads `docs/` and
nothing else, which is what its docstring always claimed.

**Re-run 2026-09-17: the tool runs from a clone, and the substitution holds —
including where this note did not look.** `tools.qa_fixture` was run against a
clone with `work/` deleted outright, for p0003 and for p0009, and printed every
frame including both dead kinds.

The reasoning above was re-derived against the real `detections.json` rather than
taken. p0003: 5 disagreements in 4053 matched slot-frames, 0.12 %, exactly as
stated, and f430 reads 10 of 14 either way. p0009, which this note does not
cover: 3 in 3775, 0.079 %. **The check the note stops short of is the one that
settles it** — the frame the fixture actually picks is identical under both
rules, f204 on p0003 and f22 on p0009, at the same 13 and 14 in-field with 0 on
the crowd. Every disagreement runs the same direction, a detection just outside
the line whose estimate sits on it, so none of them can promote a spectator.

One correction to the wording: *"within inches"* is right for p0003, whose worst
is 0.80 yd, and generous for p0009, whose worst is 1.34 yd. Both are a player
astride a line, and both are far inside the 5 yd that `nobody observed in the
stands` allows, so the conclusion is untouched.

### 2.16 The suite § 0 calls green is not green from a clone

**2026-09-17, found while confirming § 2.13's fix, and it is § 2.15 again one
file over.**

`docs/32` § 0 lists four invariants, and the fourth is *"the suite is green:
`python -m unittest discover -s tests -t .`"*. From a clone it is not:

```
FAILED (errors=4, skipped=2)
```

The four are `tests/test_contaminated_identity.py::Verdicts`, which sets
`WORK = Path("work/p0003")` and has no guard, so with no footage it errors rather
than saying it cannot run. They fail the same way at `d436819` and `ef89b08`, so
this is not something the fixes introduced — it is what § 2.15 found, sitting in
the next file along, and the QA pass that reported the fixture missed it because
the fixture died first and the suite was only ever run where the footage is.

**The two skips are the sharper half.** They are `BuildingIsNotWriting`, the
regression test written this morning to stop § 2.13 coming back. It *does* guard,
which is the right instinct, and the consequence is that it does not run in a
clone or anywhere else without the footage. Run on its own there it prints:

```
OK (skipped=2)
```

A green that covered nothing. So the check standing between this project and the
bug that silently deleted a repair runs on exactly one machine, and the two files
handle the identical missing dependency in opposite ways — one errors, one
reports OK — while neither tells the runner the one thing that is true, which is
that the test did not run.

**What would close it.** Whichever way it goes, § 0 has to be satisfiable by
somebody with a clone and a URL, since that is who `docs/32` is written for.
Either the footage-dependent tests are split into a suite § 0 names separately,
so that "the suite is green" means a suite that ran; or they are given a fixture
they can run on. `test_contaminated_identity` should skip rather than error
whichever is chosen — a test that cannot run has not failed, and it has not
passed either.

**Fixed 2026-09-17, and the two halves take different fixes because they are
different faults.**

**The skips were mine and they are gone.** `BuildingIsNotWriting` guarded itself
on `work/p0003` existing, so the test written that morning to stop § 2.13 coming
back ran on one machine and printed `OK (skipped=2)` everywhere else. It now
builds its own working directory — fourteen slots, three frames, an identity
homography, no detections — which is all `ur.possess.build` needs to be asked
whether it writes to disk. It is not a possession and is not meant to be one. A
third case joined it while the fixture was there: `build` itself must leave no
file, which is the property stated directly rather than through `--verify-revert`.

**The four errors were a missing guard, and a guard is the right answer there.**
`test_contaminated_identity.Verdicts` measures verdicts over p0003's real spans
and real tags; its own docstring says a hand-built document would be testing the
fixture, and that is correct. So it skips, with a reason naming this section,
instead of erroring four times on a missing file — which reads as a broken suite
rather than an absent input.

**What stops a skip being a green is counting.** `docs/32` § 0 now states both
numbers: **153 tests and no skips** where `work/` is present, **149 and one skip**
from a clone. A skip anywhere else, or any skip on the machine that has the
footage, is a test that has guarded itself into irrelevance. That is the general
form of this finding and the reason it is worth more than the four errors it came
in as.

**Two wordings from the same pass, both recorded as niceties and both taken.**
p0009's collapsed frames carry no `H` at all, and the refusal said *"its
homography does not invert"* about a frame that has none — right refusal, wrong
reason. It now distinguishes: *"this frame has no homography at all"* on p0009
f426, *"its homography does not invert"* on p0003 f0. And `qa_fixture`'s "within
inches" was p0003's number; p0009's worst disagreement is 1.34 yd. Both are
players astride a line, both far inside the 5 yd the stands gate allows, and the
docstring now carries both possessions' figures and the observation that actually
settles it — the frame the tool picks is identical under either rule.


### 2.17 What a person saw that no check can: six answers from the footage

**2026-09-17. `docs/32` § 11 run by hand on p0003 and p0009**, because every other
check in this project compares the page to its own data and these are the ones
that compare the data to the world. Two of the six are findings; the rest are the
first evidence that the surface works on real footage.

**Jerseys are legible and sparse, and the sparsity is the result.** On p0003's
clean frame the bottom three offence shirts are clearly readable and the rest are
not; on p0009's, four of fourteen — one offence, three defence. So `#4`'s
referent exists, and **a roster cannot be named from one frame**. The pass has to
walk a slot until its number turns toward the camera, which makes the unit a span
rather than a frame for a second, independent reason: § 2.16's was that a slot is
one label over time, this one is that a shirt is only sometimes facing you.
Seven of p0003's offence were named this way in an earlier session and confirmed
correct on this pass; p0009's four are in `work/p0009/identities.json`.

**`D5` is on a referee, p0003 f73.** Selected on the collision frame the fixture
named, `D5`'s marker sits on the official at the left touchline. This is `#26`'s
case observed rather than argued, on the frame a tool picked without knowing what
it would find, and it is what `detach` was built for. The same frame's *fixture*
collision is `O1` against `O5`, so there are at least two bad slots on it.

**Placement, marks and matchups check out.** Markers land where they are clicked
and stay consistent; every player on the clean frames has a label and the labels
are as good as the tracker can make them. The disc indicator is right most of the
time and is sometimes lost — which is `#8`'s blind stretch seen rather than
measured, and the measurement already agrees.

**The goal lines come apart when the camera moves quickly, and halfway does not.**
Field paint on a well-calibrated frame sits clean at the halfway line and jumbles
at the goal lines under a fast pan. That is a shape, not a level: `confidence` is
one number for a whole frame, and a fit can be good at the centre of the image
and wrong at the edges, which is exactly what a homography estimated mostly from
central paint would do. It also says the error is worst where the endzone is,
which is where scoring happens and where `docs/08` #5 — the unresolved field
length — has to be settled from.

Nothing here is gateable yet and one of them may not be gateable at all. What
they change is where to look: the calibration's *spatial* error has never been
measured, only its per-frame confidence, and § 2.2's suggestion that the honest
quantity is "is the halfway line in shot" now has a second half — **and are the
goal lines still where they should be when it is**.


### 2.18 The first calibration ground truth, and it is one reading

**2026-09-17.** Seventeen paint landmarks dragged onto the real paint on p0009,
through the viewer's repair mode — the first time anybody has measured where this
project's camera model is wrong rather than how confident it says it is. It is
the measurement `#30` asked for, and it is **one reading long**.

**The reading.** On **f379**, a frame the page scores **0.75**, the far goal-line
corner is **5.06 yd** from where the model puts it — 100 px in a 1920-wide frame,
far more than the painted line is thick. On the same possession, `M1 acceptance`
measures **0.132 yd mean, 0.314 yd max**, and it measures the **centre** of the
image.

**Two numbers about one possession, a factor of thirty-eight apart, and both
honest.** That is `#30` stated as a measurement instead of an impression: the
calibration is sub-yard where it is scored and five yards where it is not, and
nothing in the project had ever looked at the second place.

**The other sixteen readings say nothing about it, and the average of all
seventeen would be a lie.** They sit on frames scoring 0.00–0.15, where the page
already refuses to place and the viewer already says so. Their errors run 4.6 to
29.6 yd, the median over all seventeen is 19.45 yd, and quoting that would be
§ 2.1's rule broken in a new way — not a number without its denominator but a
number over the wrong population. What they do show is that `confidence` is
directionally right: where it is low the geometry really is bad.

**The caveat the single reading carries.** The far goal-line corner is the
hardest point in the frame — the intersection of two lines at maximum distance,
near the image edge at x = 1890 of 1920 — so it is the worst case rather than a
typical one. That is the right place to look for this failure and the wrong place
to generalise from.

**What would settle it:** the same drag on frames the page stands behind. p0009
has **388 of 450** at confidence ≥ 0.5, and one of them has been read. The tool
exists, the store exists, `...paint is where the model says` reports the split on
every run, and the thing that is missing is twenty minutes of dragging.

### 2.19 An openness claim is a minimum over a set, and one of the set was missing

**2026-09-17, from the outside audit.** On p0001 at **15.867 s** the separation
card printed **5.1 yd** and badged it **MEASURED**. O4 and D6 are both `observed`
on frame 238, twelve of fourteen slots are anchored, and the number is the true
distance between them. **D5 is `predicted` there** — dead-reckoned, drawn dashed
on the overhead, honestly recorded in the file — and the card searched it,
ranked it, and never mentioned it. The deep-cover card did the same thing one
row down, on the same frame, with the same slot.

**The number was never the defect.** 5.1 yd to D6 is what the camera saw. The
defect is the word above it. "The receiver had 5.1 yd of room" is not a statement
about D6; it is a statement about **all seven defenders**, because it is a
*minimum over the set*. D5 could have been three yards from O4 and nothing on
that card would have moved. A minimum over a set with an unseen member is not a
measurement of that minimum, however well the other six were seen — and the badge
was taken over the two slots the number happened to name.

**What every other card had already got right.** AD-5 gets an evidence state to
every sample and AGENTS rule 3 carries it to the page, and `evidence(f, slots)`
implements exactly that: hand it the contributors and it refuses `measured` the
moment one of them was not seen. Coverage, defensive shape and shape lag all hand
it the whole roster. The two openness cards handed it two names. The machinery was
right; the argument about **what contributes** was wrong, and it was wrong in the
direction that flatters the tool.

**The assertion that went with it.** The deep-cover card also printed *"no
defender sits on the far side of the deepest cutter"* and *"the huck is on"*,
from a test that looked only at the nearest defender — `goalSide` was assigned
inside the `if (v < bd)` that found the minimum, so it described one player and
was read as describing seven. It is gone. The positive half stays and is now an
honest existence claim: `covered` means somebody the camera saw is standing
between the deepest cutter and the endzone, and there they are, named. Nothing
replaces the negative. Where nobody is standing there the card says so in as many
words: whether the space is open is a question about every defender, and this
card answers it only when one of them is in it.

**What it costs to be honest.** Across the six published possessions, all seven
defenders are `observed`/`confirmed` on **24 % of p0001's frames and 0 % of
p0005's** (p0003 9 %, p0004 2 %, p0009 11 %, p0015 7 %). So these two cards are
now `inferred` far more often than they were, and that is the finding rather than
a regression: the tool was calling things measured that it had not measured. The
route to getting them back is repair mode and more coverage, not a looser word.

**The check, and why it reads the page.** `no measured claim over an unseen
defender` runs the viewer's own card builder under node — the fifth site gate to
do so and the same AD-12 exemption, because every field behind the 5.1 yd is
correct and the claim built on them was not. `tools/openness.py` lifts the
functions out of the published HTML with the two state sets they read, rather
than restating `MEASURABLE` in Python where it would agree with itself forever.

**It reads the card, not the claim, and that distinction was earned.** The first
version swept `opennessClaim` — the numbers — and would have stayed green over a
card that kept the downgrade and stopped naming anybody, which is this same
finding one layer up: a reader told the figure is weak and never told who made it
weak. So the page grew `opennessCard`, which holds the whole of what a reader is
shown, and the sweep asserts both promises: no `measured` badge over an unseen
defender, **and** every unseen slot named on the card. **One hop is still not
covered** — `renderCards` pasting those strings into `card()`. A card that
ignored them and hard-coded its own badge would pass this row. Lifting
`renderCards` is not possible; it writes to the DOM and closes over the whole
page. What is written down instead is where the check stops.

**Three scenarios, and the middle one is constructed.** Sweeping the published
page proves only that it makes no such claim today. So `sighted` hands the page a
defence it can see whole and a measured badge **has to appear**; `blinded` puts
one slot back out of sight and every measured badge **has to go**. The positive
half is constructed rather than taken from the possession because p0005 makes no
measured claim on any of its 450 frames — an ablation that takes nothing away
from nothing is a row that passes having covered nothing, which is AD-11 in its
fourth costume.

**What is not under the rule yet: the Mark card.** It prints the gap to the
nearest defender to the *holder* — the same minimum over the same seven — and
still takes its badge from those two players. The rule reaches it; the code does
not, because #14 named the two openness cards and stopped there. The gate cannot
see it either: the sweep runs over attackers, and the mark is measured from the
holder. It is here rather than nowhere so that `CONTEXT.md` and AD-15, which both
name the mark as an openness claim, are not quietly asserting something one card
disagrees with.

### 2.20 A check that counts things cannot see a value change

**2026-09-16, from the outside audit; fixed 2026-09-18 (#13).** The audit took a
published `possession.js`, moved one event's time by a second and gave another
event a different player, **in memory, never on disk**, and ran the site audit
over the doctored page. All eight site checks passed, `site is current` among
them.

**Why it could not have done anything else.** The row compared three things: how
many events the page carried against how many are in `work/`, how many frames,
and which way the resolved attacking direction points. Every one of those is a
count or a category, and none of them moves when a value underneath it changes.
Two events at the wrong time are still two events. It is the same shape as § 2.7
and § 2.9 from the other side: there the field was right and the rendering lied,
here the rendering is faithful and the field it renders had drifted, and a check
built out of totals is blind to both.

**What that allows.** The site is the deliverable (AGENTS rule 7) and `work/` is
the pipeline. A page can carry a tag at the wrong second, a throw attributed to
the wrong player, a position from a superseded tracker run, or a gate block from
before a threshold moved, and the board stays green, because nothing that
changed changed a count. The scenario is not hypothetical: `docs/30` § 2.6 exists
because two ghost players were reported as live defects when they had been fixed
and pushed, and the published page was simply an older build.

**The fix is a content digest, not a bigger list of counts.** `make_view.compose`
was split out of `build`: it is everything the site builder does except choosing
where the file goes, so the comparison is against the real builder rather than a
Python re-derivation that would only ever agree with itself. It is the argument
`tools/gate_sentence.py` makes about rendering, made here about data.
`tools/site_digest.py` reduces the published document and the freshly composed one
to a hash per named part and reports which parts disagree.

**One field is excluded and that is the whole exclusion list.** `video_src` is
the relative path from the page to its clip, so `viewer/live-data.js` says
`../work/p0003/clip.mp4` where `docs/p0003/possession.js` says `clip.mp4` for the
same page. Hashing it would make every published page permanently stale against a
viewer build. Everything else is in, **including the position arrays**. The
ticket asked for "event values and resolved claims"; a pipeline re-run that moves
every player and no event is exactly the staleness this row exists to catch, and
a check that would not see it has the same hole in a larger place.

**Why parts rather than one hash.** A gate row has one line to say what is wrong,
and a possession document is a few megabytes. So the document splits into
`possession`, `players`, `disc_meta`, `events`, `observed`, `gates`,
`identity_readings` and `rest`, each hashed alone. Only the part that differs is
walked, so the row says `event 0 t: published 7.6, work/ 8.6` rather than
`something differs`. `rest` is not there for convenience: it means a field added
to the document tomorrow is covered the day it lands rather than the day somebody
remembers this file.

**A working directory that will not compose is a failure, not a skip.** The row
that would have caught a stale page is exactly the row that must not quietly
disappear when the pipeline is broken. `tools/grading_view.py` calls this failing
open, and it is the same argument here.

**The test is the audit's own move.** `tests/test_site_digest.py` reads the real
published p0003, makes the two edits the audit made, and requires the row to
fail; a fourth test asserts that those edits still do not move any of the three
counts the old row read, so the first two keep testing what they were written for
if the row ever changes again. The no-op case is tested first and deliberately:
all six published pages pass unchanged, which is what stops this being a tripwire
somebody turns off.

### 2.21 The goal lines are declared, and two lines nobody identified keep turning up

**2026-09-18, #7.** `docs/08` open question 5 has stood since M0: is Breese
Stevens a 120 yd field or the 110 yd venue exception, with the note that **every
field coordinate depends on the answer**. That note is wrong, and
`ur/calibrate/world.py` says why. M1 registers to the **soccer centre circle**,
`CENTRE_CIRCLE_R = m(9.15) = 10.0066 yd`, and the halfway line. Both are FIFA
dimensions. So the length of a yard comes from the circle, and a 110 yd answer
does not change how long a yard is.

**What the answer does move**, and it is a short list. `goal_lines` returns
`(20, length - 20)`, so the answer decides where the ultimate goal lines and the
brick sit inside a frame that is already right. Separation, speed, spacing and
every relative shape are untouched, and those are what the project is looking
for. Anything measured against an endzone is not: deep and goal-side, the brick,
how far a receiver is from scoring, a throw quoted as ground gained.

**The machinery to settle it already existed and nobody had read its answer.**
`venue.decide_field_length` pools every paint pixel in a possession into one
ground-plane map and looks for lines of constant x. A goal line should sit
40 yd from the halfway line on a 120 yd field and 35 on a 110, and the tolerance
is 1 yd because the per-frame calibration residual is 0.15. Every
`calibration.json` has carried a verdict since M1. Nothing read them together,
and nothing put the answer on a page.

**Run across every calibrated working directory: not one resolves.** That is
thirteen cuts and one superseded copy of p0003, and every one says
`unresolved`. So **the published goal lines are declared from the UFA rulebook,
not observed off the grass**, and until 2026-09-18 six published pages drew them
as though somebody had seen them.

**And the paint is not empty, which is the part worth keeping.** Two lines of
constant x recur across the cuts:

| possession | confident frames | x peaks near a goal line (yd from halfway) |
|---|---|---|
| p0001 | 345 | +38.15, +43.15 |
| p0003 | 398 | −38.05, −42.45 |
| p0004 | 292 | −37.75 |
| p0009 | 388 | +37.65, +42.85 |
| p0010 | 123 | +38.35 |
| p0014 | 158 | −37.85, −42.55 |
| p0015 | 279 | −37.95, −42.55, +38.05, +42.45 |
| p0016 | 55 | −37.75, −41.75, +38.65 |

Eight of the thirteen live cuts find a line at |x| ≈ **38.0**, ten readings
spread 37.65 to 38.65. Six find a second at |x| ≈ **42.7**, seven readings spread
41.75 to 43.15. p0015 finds both, on both sides, symmetric about the halfway line
to within 0.1 yd. Independent possessions, independent pooled maps, the same two
distances: that is not noise, whatever it is.

**Neither is a goal line under either hypothesis.** 38.0 is 2.0 yd from where a
120 yd field puts one and 3.0 from a 110, against a calibration good to 0.15.
42.7 is 2.7 and 7.7. The existing rule rejects them twice over — outside the 1 yd
tolerance, and under 5 % of the halfway line's support — and it is right both
times.

**The likeliest explanation is that they are soccer paint, and it does not quite
fit.** A FIFA penalty area is 16.5 m = 18.04 yd from the goal line and the
penalty arc's apex is 11 m + 9.15 m = 22.04 yd from it, so on a pitch whose half
length is L/2 they appear at L/2 − 18.04 and L/2 − 22.04: a pair of lines
**3.99 yd apart**, symmetric about halfway, which is the shape observed. The
observed separation is **4.61 yd**, mean over the seven pairs in the six
possessions that see both, and it ranges 4.00 to 5.20. 0.6 yd is four times the
calibration residual, so this is a hypothesis carrying an error it does not
explain, not an identification. It is written down because
the next person to look at these peaks should start from it and not from
scratch.

**What that says about `decide_field_length`.** It excludes the centre circle
from both marginals and nothing else. Every other line on a shared venue is
soccer paint, and the function has no way to say "that is a penalty area, not a
goal line" — it can only reject on distance and support. On this footage the
rejection happens to be right. On a venue where a soccer line fell within a yard
of 40, it would resolve open question 5 confidently and wrongly.

**What is published instead.** `tools/make_view.py` bakes
`field.length_source` and the whole evidence block into every page at build
time, the same way the attacking direction and the bounded flag are baked in
(AD-9). The viewer draws the goal lines, the back lines and the brick **dashed**
where the source is `declared`, which is the convention the page's own legend
already carries: solid is observed, dashed is an estimate. And `fieldSentence`
prints the claim in as many words, with the sample it rests on.

**The caution #7 raised, honoured and then found to be unmeetable.** The ticket
asked that any measurement here report how many frames it rests on.
`decide_field_length` never recorded that, so the six published calibrations
carry a verdict and no sample. It records `frames` and `paint_points` from
2026-09-18, and until a possession is recalibrated the page says **at most N
frames** off the confident-frame count and says plainly that the map's own count
was not recorded. An upper bound labelled as one is worth more than a number
that looks measured.

**Three rows, and the gate is about honesty rather than about the answer.**
Nobody has the answer and no gate should demand it. `goal lines say which they
are` requires every published page to carry `observed` or `declared`, and
refuses `observed` from a page with no measurement behind it — the one way to
cheat a label is to type the stronger word. `the page says which they are` runs
the page's own `fieldSentence` under node, the fifth check to read a rendered
page rather than the data behind it, because the field block can be right and
the page silent; the ablation is what makes it a test, since a sentence that
survives `length_source` being taken away is prose somebody typed that happens
to be true today. `...goal lines found in the paint` reports and judges nothing.

---

### 2.22 The page said nobody had touched it, over 181 hand-placed positions

**2026-09-18, #31, found while writing down what a stranger would see on p0003
for #24.** That page carries **15 applied corrections** placing **181 positions
across 165 of its 555 frames**, 30 % of the possession. It printed:

> 0 human corrections applied.

`const LOG = []` starts empty in the browser and nothing ever seeded it from
`D.corrections_applied`, so the line counted this session's edits and nothing
else. Five of the six published pages have no corrections, so five of them said
zero and were right, and the sixth said zero and was not.

**It is § 2.8 one pane over, and worse in the direction that matters.** There the
tag list rendered from the in-session array and said "Nothing tagged yet" over
fourteen published tags. Same root cause, same shape. But hiding tags only wastes
work somebody was paid for, and hiding corrections **overstates the machine**: a
reader was told the tracker produced something a person had placed a third of.
And it landed on the one page the sprint's cold read is about, where question 5
asks a stranger which parts the tool told them it was guessing at.

**Why no gate saw it, and the distinction is the useful part.**
`corrections reached the page` has been green throughout and is correct: it
compares `corrections.json` against `possession.json`, asking whether the
pipeline replayed the log. Whether the **reader** is told is a different
question, and only the rendered string answers it. That is now six checks reading
the rendered page rather than the data behind it, and every one of them was the
same discovery: a correct file, and a page saying something the file does not
support.

**Two numbers, because they are two facts.** `ur/human.py::count` counts
(slot, frame) cells, which is what AD-13 excludes from a grading sample. How much
of the *clip* a hand reached is the union of those frames, which is what a reader
is asking. Two markers moved on one frame is two cells and one frame, and quoting
either alone reads as the other, so the page prints both: **15 corrections,
placing 181 positions across 165 of 555 frames (30 %)**. Operations would have
been the third and worst choice - one anchor moves every frame between the
bracketing observations (`docs/05`'s ramp), so "15" understates it by an order of
magnitude.

**The first version of `tools/cold_read.py` reproduced the bug it was written to
expose.** It read `disc_meta.human` alone and reported `0 hand-placed frames` over
the same possession. The count now goes through `tools/corrections_line.py`, which
is the module the check uses, so there is one answer rather than two.

**The row, and the ablation that makes it a test.** `the page counts the hand in
it` renders the page's own `correctionsLine` twice: once as published, and once
with every correction and every hand-placed frame taken away. A sentence that says
the same thing both times is a sentence nobody seeded, which is AD-11 in the
costume `tools/openness.py` names. Three faults are separable - the correction
count missing, the frame count missing, the position count missing - so the row
says which.

---

### 2.23 What p0003 looked like on the day nobody had read it

**2026-09-18, for #24.** The ticket was amended on 2026-09-17 to read the page
**unrepaired**, and that amendment is what makes this section necessary. A
stranger reading a page somebody spent hours hand-placing tells you what a person
can make the pipeline look like. A stranger reading the page as it stands tells
you what the pipeline produces with its gaps showing, and that only stays a fact
if the gaps are written down **before** the read - afterwards, every answer
invites an argument about whether the page was showing that at the time.

`python -m tools.cold_read p0003` produced this, at the commit that carries it:

**p0003 as it stands.** 555 frames at 15 fps (37.0 s), 14 published tags, **15 human corrections placing 181 positions across 165 of 555 frames** (30 %). **#24's first acceptance criterion asks for a page with no repair pass, and this is not one.**

**The disc.** Drawn on 184 of 555 frames. 15 stretch(es) with no disc at all, the longest 7.87 s. A reader asked about the last throw is reading the video through those.

| from | to | length |
|---|---|---|
| 0.0 s | 5.67 s | 5.67 s |
| 5.73 s | 6.53 s | 0.8 s |
| 6.6 s | 6.93 s | 0.33 s |
| 7.0 s | 7.33 s | 0.33 s |
| 7.4 s | 7.73 s | 0.33 s |
| 7.8 s | 8.13 s | 0.33 s |
| 8.2 s | 8.53 s | 0.33 s |
| 8.6 s | 10.4 s | 1.8 s |
| 16.13 s | 16.87 s | 0.73 s |
| 18.13 s | 18.4 s | 0.27 s |
| 19.27 s | 27.13 s | 7.87 s |
| 30.13 s | 31.47 s | 1.33 s |
| 31.53 s | 31.67 s | 0.13 s |
| 32.07 s | 32.33 s | 0.27 s |
| 32.8 s | 37.0 s | 4.2 s |

**What the cards admit.** 268 of 2771 openness claims reach a measured badge; the other 2503 say inferred and name the slot they could not see (AD-15). Question 5 is about whether that is believed.

**The repair queue, unopened: 91 items.** 48 x `unverified_stretch`, 24 x `long_blind_stretch`, 18 x `reacquire_surprise`, 1 x `cold_start`.

**Jerseys.** 7 of 14 slots carry a number read off a shirt (O1, O2, O3, O4, O5, O6, O7), 0 a voted one, 7 none at all. Not a blocker: the brief's non-goals put the tactical meaning on the slot, so `D3` answers question 2.

**What the page says about itself.** Attacking direction **unverified**. Accuracy measured on `p0001` and **unmeasured here**. Goal lines **declared**.

**And the first acceptance criterion is not met.** "p0003 is published as the
pipeline produces it, with no repair pass." It is not: a repair pass ran on
2026-09-17 and placed 181 positions across 30 % of the possession. Whoever runs
the read has two honest options and this document does not choose between them:

1. **Revert and republish.** `ur/resolve.py --verify-revert` reproduces the
   uncorrected output byte for byte, so the repairs can come out and go back.
   The read then measures the pipeline, which is what the amendment asked for,
   and the preparation hours are close to zero as the ticket predicts.
2. **Read it as it stands and say so.** The numbers then describe a
   *hand-corrected* page, the preparation hours are whatever that pass cost, and
   the result answers the pre-amendment question instead. Still worth having;
   just not the same finding.

What is not an option is reading it as it stands and reporting it as unrepaired,
which is what would have happened had the page kept saying zero.

**The answers go here when the read happens**, verbatim, including the wrong
ones, with the reader named and the preparation hours beside them. § 2.17 is the
format: six answers from the footage, written down as given.

---

---

## 3. The gates, and which of them fail on purpose

`python -m tools.gates` prints **238 rows, and only 197 of them can fail.** It
ends on two totals, and they are not the same kind of number:

```
183 of 197 failable check(s) pass, 14 failing.
41 informational row(s) report a measurement and no verdict.
```

The fourteen failures are every one either a known-unpublished possession or a
documented open problem, and the tables below say which. The informational rows
are **measurements** — numbers with no threshold to hold them
to — and the first table below names each kind and what it is waiting for.

Until 2026-09-16 those twenty-four were built as gates with an unconditional
pass. They printed `[PASS]`, they counted into one total of 132, and that total
was the number a reader trusted. It was inflated by rows that could not have done
anything else — and worse, `docs/31` closes an issue when a named check flips to
PASS, so a row that can never flip is a definition of done that can never be met.
They now print `[measured]`, carry the reason there is no threshold instead of a
`want`, and are totalled apart. `tools/checks.py` holds the distinction and is
where a new check picks its kind.


### The rows that cannot fail, and what each is waiting for

Five kinds. Each reports a number the run is better for carrying, and none of
them can be a gate today. What is in the last column is
what would make one failable — and until that exists, a threshold on it would be
a number chosen to make current output pass, which is the first of the three
things the brief asks not to happen.

| row | rows per run | what it reports | why it is not a gate today | what would make it one |
|---|---|---|---|---|
| `...measured on` | 10, one per possession | the fraction of frames the M1 mean was measured on | there is no fraction below which the possession is *wrong*. A thin denominator makes the **mean** weaker evidence; it is not itself a defect, and the mean it qualifies is already gated. § 2.1 | a measured relation between usable fraction and the error on the frames the acceptance never sampled. Nothing has measured that, and § 2.2 suggests the honest quantity is "is the halfway line in shot", which is a different row |
| `offence drifts` | 10, one per possession | median per-player least-squares drift of the offence along x | § 2.0: this quantity is **not** the attacking direction, so no value of it is right or wrong. It stayed in the run because the movement is real and worth seeing, not because it decides anything | nothing, and that is the point. The thing it was mistaken for is gated across possessions in `Qn: opposite teams disagree`; this row is the diagnostic that was promoted to a fact once already |
| `...quarters confirmed` | 1 | how many quarters have a human-confirmed attacking direction — today **0 of 4** | an unconfirmed quarter claims nothing, so there is nothing to contradict. Gating it would fail every possession cut before somebody got round to watching it, and a queue is not a defect | confirming becoming part of cutting a possession rather than a backlog. Then `0 of 4` **is** a defect, the threshold is *all of them*, and it moves to the failable total under #5 |
| `...slots on somebody off the field` | 10, one per possession | the share of matched slot-frames whose detection sits outside the lines — p0003 **7 %**, p0001 and p0005 **0 %** | AD-3 puts a two-yard margin outside the sidelines on purpose: a thrower plants a pivot foot on the line. So "outside" is not by itself wrong and no fraction of it is defensibly the limit. The row exists to stop `coverage` being believed — p0003 at 28.67 s reads `14/14` over a frame with ten players on it, because the bench and the camera crew stand inside that margin | #29. Probably arithmetic rather than tolerance: at most fourteen people can be on the field, so a two-yard band holding twenty-six detections is a crowd by counting. That needs measuring across possessions before it is a threshold |
| `...longest blind stretch` | 3, the published possessions carrying human tags | the longest stretch inside the tagged region where a reader sees no disc at all | still no principled threshold, and **two candidates were tried and rejected on 2026-09-17** — see below. A number picked because it happened to fail p0003 is tuning a constant to produce a verdict, backwards | a tolerance somebody decides and can defend, or a full repair pass becoming part of publishing a possession. #8 supplied the *remedy* and not the threshold |
| `...goal lines found in the paint` | 6, one per published page | how many lines of constant x the possession's pooled paint put within 1 yd of a goal line under either hypothesis, and the paint sample it rests on — today **0** on every one | there is no count that makes a possession wrong. The camera never frames an endzone and the halfway line together, so demanding a goal line demands footage that does not exist. § 2.21 | a cut whose paint shows one. `survey/random/010_t1615.7.png` is such a shot and is not cut. Then the threshold is *at least one*, and it moves under #7 |

The count moves with the work: ten possessions in `work/`, so ten of each
per-possession row, and a fourth published possession with tags adds a fourth
`...longest blind stretch`. What does not move is that none of them can be
counted as a passing check.

#### Why `...longest blind stretch` is still not a gate, after #8

#8 asked for a threshold "set from a measurement rather than from what p0003
happens to score", and what it actually produced was the **remedy**: repair mode,
and a measured demonstration that the number now moves. Anchoring the two holders
the tracker loses on p0003 — O1 across 5.67–8.73 s and O2 across 21.27–26.13 s,
one keyframe every 8 frames — takes it from **3.1 s to 0.5 s**, through the real
path: `corrections.json` → `ur.resolve` → `ur.disc` → `ur.resolve` →
`tools.build_site`. Before that the number had no remedy at all, so gating it
would have condemned a page nobody could fix. That much has changed.

The threshold has not, and two candidates were put up and knocked down:

- **The median human-tagged flight, 1.23 s.** Rejected, and rightly: a flight
  duration is not a property of the sport. A five-yard dump and a forty-yard huck
  share no duration, so the median of the 16 tagged flights measures which throws
  happen to have been tagged and nothing else. It would have been a tuned
  constant wearing a measurement's clothes.
- **The longest tagged flight, 3.20 s.** Sourceable, and useless: every published
  possession passes it today, p0003 included at 3.1 s, so it is a row that cannot
  fail — AD-11 — and it would close #8 without the number ever moving.

And the argument both of them rested on is wrong anyway. **A tagged flight is
already drawn**, interpolated between the throw and the catch, so a blind frame
inside the tagged region is never the disc legitimately being in the air — it is
the machinery having failed. The principled target is therefore **zero**, and
every number above zero is a tolerance somebody chooses, not something the
footage measures. Zero is honest and not yet reachable: it would mean hand-placing
the holder on every tagged frame of every possession.

So the row stays a measurement, and the reason is now a decision waiting to be
made rather than a measurement waiting to be taken.

### Per possession — all six published ones pass

| gate | threshold | where it comes from |
|---|---|---|
| M1 acceptance, mean | < 0.75 yd | `docs/04` M1, unchanged since the first milestone |
| M1 acceptance, max | < 1.5 yd | `docs/04` M1 |
| …measured on | *measurement* — see below | § 2.1. A mean without its denominator is not a result |
| roster structure | zero problems | `docs/04` M4, AD-2 |
| camera motion is possible | 0 frames over 1 yd | § 2.3 |
| player motion is possible | 0 moves over 12 yd/s + 2.5 yd | #28, and the counterpart to the row above. Until 2026-09-17 this project asked whether the **camera** could physically have moved that way and never once asked it of a **person**. p0003's O2 crosses 55 yd in a single frame, `observed` at both ends, and went through every gate green. 12 yd/s is a sprinter's top speed — a property of people, not of this footage. The 2.5 yd is `tools/m4_foot`'s p95 position error doubled: without it, 1 yd of foot-point jitter over one frame reads as 15 yd/s and the check fires on 178 transitions of sub-yard wobble. With it the corpus has **three**, all on p0003, two of them the slot #8's repair pass is placing |
| corrections reached the page | every active correction is replayed | #8. Seen once and not reproduced: a pipeline run left `disc_meta` confirmed from twelve hand-placed positions while `corrections_applied` was empty — the disc stage got the corrections and the pass after it rebuilt the players without them. A correction sitting in a file nobody replayed is silent; only the two counts disagreeing says otherwise |
| median roster in shot | ≥ 6 of 14 | publishing gate. Below this the median frame is mostly empty |
| frames with nothing at all | ≤ 35 % | publishing gate |
| offence drifts | *measurement* — see below | § 2.0. The drift is real; it is not the attacking direction |

**Currently failing and expected to:** p0003 on `player motion is possible` (#28,
and it is what a person watching the live page found in about a minute), and
p0006, p0007, p0008 and p0010 on coverage
and on camera motion — they have not been through the impossible-motion check and
are not published.

### The published site — 116 rows, 107 of them failable, all passing

`tools/audit_site.py`, folded into `python -m tools.gates`. Every other gate in
this document reads `work/`; these read `docs/`, which is the only thing anybody
sees. They exist because clicking through the live site on 2026-09-15 found two
defects that the whole suite was green through.

| gate | threshold | where it comes from |
|---|---|---|
| site is current | a **content digest** of the published document, part by part, equals the digest of what `make_view.compose` emits now — every field but `video_src` | AGENTS rule 7 — the live site is the deliverable. It counted events, frames and the resolved direction until § 2.20: the audit changed one event's time and one event's player in an in-memory copy and all eight site checks passed, because a count cannot see a value. `tools/site_digest.py` hashes eight named parts so the row can say `event 0 t: published 7.6, work/ 8.6` rather than `something differs`, and `rest` covers any field added to the document after this table was written. Direction is in it the same way everything else is — `compose` resolves it (AD-10), so a confirmation made after the last build shows up as a difference in `possession`. #13 |
| published tags are used | tags naming a player produce disc frames sourced `human` | p0003 and p0009 published 14 and 12 human tags while every disc frame was still `inferred`. `ur.disc` had not been re-run, so the tagging bought **nothing** on the site. Fixed: 0 → 485 and 0 → 405 frames |
| no borrowed gate numbers | numeric gates only on the possession they were measured on | every page shipped p0001's `per_player_recall: 0.9744` in its data. `measured_on` labelled it honestly, but anything reading `possession.js` still got p0001's recall for p0003. The numbers now travel only with their own possession |
| no unmeasured percentage printed | render the page a second time with **every measurement removed**; no percentage may survive | § 2.7. Five pages printed a rounded `0 %` for recall and sigma containment off `null` fields. These two are the only checks here that read the **rendered sentence** rather than the data behind it, because the data was right and the sentence was not — they run the viewer's own `gateSentence` under node (`tools/gate_sentence.py`), which is why `node` has a row in `docs/07`. Taking the measurement away rather than comparing against an expected value is what makes it catch the bug on p0001 too, where it was latent behind a real 97 %. #11 |
| an unmeasured page says so | the word `unmeasured` appears in the sentence, on a page with no measurement of its own | § 2.7, the other half. Printing no number is not the same as saying there is none: a gap where a figure would go reads as "fine". Only the five pages with nothing measured carry this row; p0001 has numbers and says so. #11 |
| published tags show on load | the page lists exactly the tags it was given before a key is pressed, the empty state appears only where there is nothing, and the list falls back to it once those tags are taken away | § 2.8. Three pages published 6, 14 and 12 human tags and all three opened saying "Nothing tagged yet", because the list was seeded from the in-session array alone. The third check here that reads the **rendered page** rather than the data: `tools/tag_list.py` runs the viewer's own `tagListHtml` under node, twice. Four ways to fail — dropping a tag, listing one twice, claiming emptiness over tags that exist, and printing rows that survive having the tags removed. #12 |
| a self-pass is always refused | the page's own guard refuses a catch naming the player of the preceding throw, whether that throw is published or made in this session, and still takes a catch naming anybody else | § 2.9. The guard read only the tags made in the current browser tab, so a throw in `events.json` was invisible to it, and § 2.8 is what made that reachable. The fourth check to read the published page, and the only one about what the page **refuses** rather than what it says. It has to construct its own failure — every `events.json` in `work/` is correct — so it runs four invented scenarios off the page's own roster, two of which exist to stop a guard that refuses everything, or refuses regardless of its input, from passing. #25 |
| the page counts the hand in it | the sentence names the corrections the file carries and the positions and frames they placed, and says none over a document with none | § 2.22. p0003 printed `0 human corrections applied` over 15 applied corrections and 181 hand-placed positions, because `LOG` starts empty in the browser and nothing seeded it. § 2.8 one pane over, and worse: hiding tags wastes work, hiding corrections overstates the machine. The sixth check here to read the **rendered page**. `corrections reached the page` in the pipeline suite was green throughout and is right to be — it asks whether `possession.json` replayed the log, which is a different question from whether the reader is told. #31 |
| goal lines say which they are | every published page carries `field.length_source`, `observed` or `declared`, and `observed` only where the calibration measured a line | § 2.21. Thirteen cuts, no verdict on any of them, and six pages drawing a goal line as though somebody had seen it. The yard comes from the soccer centre circle so separations and speeds hold either way; what a declared length moves is every claim measured against an endzone. The gate refuses `observed` without the measurement because the one way to cheat a label is to type the stronger word. #7 |
| the page says which they are | the page's own `fieldSentence` prints the source, and prints nothing once `length_source` is taken away | § 2.21, and the fifth check here to read the **rendered page** rather than the data behind it. The field block can be right and the page silent, which is § 2.7 from the other side. The ablation is the test: a sentence that survives its data being removed is prose somebody typed that happens to be true today. #7 |
| no measured claim over an unseen defender | no openness claim badges `measured` while any defender is outside `observed`/`confirmed`; a defence the page can see whole reaches a measured badge, and blinding one slot takes every measured badge away | § 2.19. p0001 at 15.867 s printed 5.1 yd as MEASURED with D5 dead-reckoned and unnamed. A nearest-defender number is a **minimum over the defensive set**, so the badge rests on all seven and the missing ones are named as people. The fifth check to read the **rendered page**: `tools/openness.py` runs the viewer's own `opennessCard` — the strings, not the numbers under them — over every frame and every attacker, and asserts both promises, the badge and the naming. Three scenarios, because the published page passing proves only that it makes no such claim today — and the positive one is constructed, since p0005 makes no measured claim at all on any of its 450 frames. #14 |
| no disc drawn from the failed inference | every drawn frame rests on a human tag | already true, now locked in — the viewer correctly suppressed all 385 `predicted` frames on p0009 |
| no disc drawn on a guessed position | the holder's own position is `observed`/`confirmed` on every drawn frame | the check above asks WHO, this asks WHERE, and they are two facts about one frame. p0003 published the disc on a match official at `confirmed`: the tracker lost O2, re-acquired 26.9 yd away over the sideline, and a correct tag about the catch carried the disc there. 3 frames → 0. The tracker's own error is #4; this is the stage that was publishing it |
| no confirmed disc from an inferred name | no frame renders a `confirmed` disc state from a tag carrying `player_inferred` | the third way a tag is weaker than it looks, after WHO and WHERE: **how the person arrived at the name**. p0003's 21.27–26.33 s holder was settled by elimination, not read off a jersey (§ 2.5 and `docs/27`), and part of that argument is which slots the tracker loses, so `span identity accuracy` already refuses to grade against it. The flag stopped at span resolution. The disc stage saw a human tag and observed coordinates and emitted `confirmed`, so the Mark card said MEASURED about a holder nobody named. 6 frames → 0. The span still draws, at `predicted`, on exactly the frames it drew on before, and every card built on it says the name was inferred. Suppressing it would reopen the display hole that naming it closed. #15 |

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

### Human positions — the one gate repair mode had to bring with it

| gate | threshold | where it comes from |
|---|---|---|
| no human position in a metric | every grader answers the same with and without hand-placed positions | #8. `anchor` produces `confirmed`, and CONTEXT.md is blunt that **every** `confirmed` frame is human-sourced — so a metric counting them scores the tracker better the more a person fixes. Same contamination as § 2.5's inferred name and as the withdrawn `identity_switches_caught: "2 of 2"` |

Repair mode invites somebody to hand-place fourteen markers and a disc, which
makes this the difference between a correction log and a way to cheat. The
mechanism is `ur/human.py`: every frame a correction created **or moved** is
written to `possession.json:human`, and `blind()` hands a grader a document those
frames are missing from. Three graders carry it — per-player recall, the sigma
containment sample, and the span solver's grade.

**The gate does not read the source for the word `blind`.** A call that had been
commented out would pass that. It lays down a deterministic **probe keyframe** —
every slot and the disc moved 12 yd, on a fixed stride, through `ur.resolve` by
exactly the route a person's save takes — and runs each grader three times: with
its exclusion switched off, as it normally runs, and over the blinded document.
The last two must agree, and the first must differ from them. Deleting either
`HU.blind` that the probe can reach turns the row red, which was checked both
ways round.

The third run is what stops this being a row that cannot fail. Per-player recall
reports **`unreachable`**, not a pass: it asks for `observed`, an anchor produces
`confirmed`, and docs/05's ramp never moves the bracketing observations, so a
correction cannot enter it whatever `blind` does. It is clean by construction and
the run says so rather than taking credit. The two that the probe *does* reach —
sigma containment and the solver grade — are the ones the row is about.

One thing this gate is not: a claim about the artefact. A correction is supposed
to make the published page better and it does. `blind` is a grading view and
never a publishing one.

### The disc — both gates fail, and this is the work

| gate | threshold | why that number |
|---|---|---|
| span identity accuracy | ≥ 75 % over ≥ 8 graded spans | currently **0 / 0**, and failing on **sample size** rather than on the solver. Every tag in the corpus was named by clicking somebody in the viewer, so every name is the tracker's, and none of them may be scored against until a tagger declares `provenance` (#4, AD-13's amendment). It read 8 / 18 = 44 % until 2026-09-17 — p0001 4 / 4, p0003 1 / 7, p0009 3 / 7 — and that number was the solver graded partly against its own upstream. The two new rows below are what replaced the old `player_inferred` filter |
| margin predicts correctness | r ≥ 0.5 | currently **r = −0.17**. Not a confidence, and briefly measured at −0.47, so `docs/27` step 4's plan to ask where the margin is thinnest is withdrawn either way |

**These are the two numbers that decide whether Goal 2 works.** Neither can move
until the corpus carries provenance, and then only with more identity tags, and
both must be measured on a possession the solver was not built against.

| gate | threshold | why that number |
|---|---|---|
| no contaminated identity in a metric | every grader answers the same with and without a name the tracker supplied | AD-13's probe argument applied to the other half of what a person supplies, and it took two goes to aim. It puts a wrong name on every tag that is **already excluded** — mangling one that *grades* takes it out of the sample, so the number moves for a good reason and the probe reads its own damage as a leak. Four runs: the mangled names must leave the blinded grade untouched and must move the unblinded one, or the probe reached nothing and the agreement says nothing (AD-11). The first version compared "names in" against "names out", which differ for a reason unrelated to the probe, so every possession came back `excluded` and the row was green while not one tag had been changed. #4 |
| every possession read goes through the view | only `ur/grading.py` may build a path to `possession.json` | the registry was the hole. `tools/human_positions.py` probes the graders `graders()` names, a hand-written list of three, and `tools/disc_score.py` was in none of them — so the probe reported `1 of 1 grader run(s)` and passed while a scorer it never saw applied neither exclusion. An `unreachable` row admits it could not reach something; an absence prints nothing. Matched on the syntax tree so prose stays legal, and it **fails open** on a file that will not parse. #4 |

> **Why 50 % became 44 %, and why that is the right direction.** The 8 / 16 this
> table used to carry was measured before three commits changed what counts as
> truth on p0003. `d3961d5` *removed* four names, because the tagger had selected
> people in the picture and been handed the **tracker's** label for them — § 2.5's
> finding and #4's. `926bc29` named O2. `f3aff10` named the last span by
> elimination and, in the same commit, marked it `player_inferred` and taught
> `check_disc` to skip it: part of that argument is which slots the tracker loses,
> so counting it would grade the solver against its own upstream (now AD-13).
> p0009 never moved. p0003 went 1 / 5 → 1 / 7, the solver got neither new span
> right, and the headline fell 50 % → 47 % → 44 %. **A score that drops when more
> truth arrives is a score that is working.**

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
