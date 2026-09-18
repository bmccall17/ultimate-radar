# AD-16 — A line drawn on the field is a claim, and carries its provenance like a position does

AGENTS rule 3 says no function may return a bare `(x, y)`: every position carries an
evidence state and a sigma, and a metric computed from weak evidence is labelled as such.
**The same rule governs the field itself.** A goal line, a back line and a brick mark are
positions the page asserts, drawn at full opacity beside players whose uncertainty is
scrupulously recorded, and until 2026-09-18 not one of them said where it came from.

So: a page that draws a field line says whether it was **observed** off the grass or
**declared** from a rulebook, it draws a declared line in the shape `docs/05` already
reserves for an estimate, and it may not say `observed` without carrying the measurement.

*Why.* `docs/08` open question 5 — 120 yd or 110 — has stood since M0 with the note that
every field coordinate depends on the answer. That note is wrong, and being wrong in that
direction is what kept the question looking too big to answer. `ur/calibrate/world.py`
registers to the **soccer centre circle**, `CENTRE_CIRCLE_R = m(9.15) = 10.0066 yd`, and
the halfway line. Both are FIFA dimensions, so the length of a yard comes from the circle.
A 110 yd answer does not change how long a yard is, and separations, speeds, spacing and
every relative shape hold either way.

What it does change is where `goal_lines` returns `(20, length - 20)` inside a frame that
is already right — and therefore every claim measured against an endzone. That is the
whole exposure, and it is a short list: deep and goal-side, the brick, distance to score,
a throw quoted as ground gained.

*What the measurement says.* `venue.decide_field_length` has pooled every paint pixel into
one ground-plane map and looked for lines of constant x since M1, and every
`calibration.json` has carried its verdict. Nobody had read them together. Across thirteen
cuts **not one resolves**, so the published goal lines are declared, and six pages had been
drawing them as though somebody had seen them.

*Why it is not AD-5 already.* AD-5 gets an evidence state to every *position the pipeline
estimates*. The field is not estimated; it is assumed, from a document, before any frame is
read. Nothing in the position machinery has anywhere to put that, which is exactly how six
published pages drew an unobserved line at full opacity next to a dashed player and said
the difference out loud in the legend. The machinery was right and the question of **what
counts as a claim** was answered too narrowly — the same shape as AD-15, one object over.

*The general form.* If a reader could act on it and nobody measured it, it is a claim.
Paint on the grass is measurable; a line taken from a rulebook is a hypothesis about that
paint, and the page says which it is holding.

*What the reader gets.* `tools/make_view.py` bakes `field.length_source` and the evidence
into every page at build time, the way the attacking direction and the bounded flag are
baked in (AD-9), because it is a fact about the calibration rather than about the
possession document. The goal lines, the back lines and the brick draw **dashed** where the
source is declared, which is the page's own legend unchanged: solid is observed, dashed is
an estimate. The **sidelines stay solid** — the across-pitch half of the venue transform is
measured, one ultimate sideline at soccer y = −25.95. And `fieldSentence` says it in words,
with the sample behind it.

*The sample is part of the claim.* "Nobody saw a goal line" off one frame and off four
hundred are different statements and a reader cannot tell them apart. `decide_field_length`
never recorded its paint-map denominator, so it does from 2026-09-18, and until a
possession is recalibrated the page prints **at most N frames** from the confident-frame
count and says the map's own count was not recorded. An upper bound labelled as one is
worth more than a number that looks measured. AD-13 makes the same argument about
percentages.

*The gate is about honesty, not about the answer.* Nobody has the answer and no check
should demand one: a row requiring a measured field length would fail forever on footage
that does not exist, which AD-11 calls a definition of done that can never be met. So
`goal lines say which they are` requires the label and refuses `observed` without the
measurement behind it, since the one way to cheat a label is to type the stronger word.
`the page says which they are` runs the page's own `fieldSentence` under node (AD-12) and
takes `length_source` away to prove the sentence rests on it. `...goal lines found in the
paint` reports and judges nothing, and `docs/30` § 3 names what would make it failable:
a cut whose paint shows a goal line.

*What this does not settle.* Two lines of constant x recur across the cuts, at |x| ≈ 38.0
in eight of them and ≈ 42.7 in six, symmetric about halfway in p0015 to within 0.1 yd.
Neither is within a yard of either hypothesis. The likeliest reading is soccer paint — a
penalty area sits 18.04 yd from its goal line and the arc's apex 22.04, a pair 3.99 yd
apart — against an observed separation of 4.61. `decide_field_length` excludes the centre
circle and nothing else, so on a venue where a soccer line fell within a yard of 40 it
would resolve the question confidently and wrongly. That is the next thing to know about
this code and it is written down rather than discovered twice.

Findings: `docs/30` § 2.21. Issue #7, desired outcome 0 of #9. Open question 5 in
`docs/08-risks.md` stays open and is now correctly sized.
