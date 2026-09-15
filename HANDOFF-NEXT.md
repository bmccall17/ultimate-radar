# Start here

**Read `docs/30-findings-and-gates.md`.** It is the state of the project, the
findings, and the list of things that have to pass. Then:

```bash
python -m tools.gates
```

Every gate, every possession, one command, non-zero exit if anything fails.
Seventeen checks fail today and `docs/30` § 3 says which are deliberate.

## The one-paragraph version

Six possessions are published and all six pass every pipeline gate. The
calibration work is done and measured: the halfway line turns out to be the whole
game, and `ur/calibrate/mosaic.py` plus three independent checks now recover the
frames that have none. **Goal 2 is the open one.** The disc tagging surface,
the span solver, the scorer and the loop are all built and wired — and the first
ground truth, four identities on p0001, scored the solver **0 of 4**.

## The next three things

1. **Tag p0009.** It is the best remaining possession (86 % calibrated, 9 of 14
   in shot). Open <https://bmccall17.github.io/ultimate-radar/p0009/>, press `t`
   on each release and `c` on each catch — **no player selection needed** — then
   go back and name the holder on each span by selecting the player and pressing
   `c` again. Download events, drop at `work/p0009/events.json`.

   That is what `tools/gates.py` needs for its two disc gates: eight graded spans
   across at least two possessions, so a fix cannot be fitted to the cases it is
   tested on.

2. **Then rebuild the span cost around flight speed.** The three true throws on
   p0001 fly at 11.0, 11.0 and 11.2 yd/s over a 2.7x range of distance;
   `ur/spans.py` uses speed only as a 2-40 yd/s admissibility gate and ranks on
   stillness, which measurement says prefers the wrong answer. Order matters:
   get the second possession's tags first.

3. **Settle the attacking direction, for the whole game.** It is not a p0001
   problem: `docs/30` section 2.0 measured that the drift check never measured
   attacking direction at all, and in three of the four quarters cut so far
   BOTH teams' offences drift the same way. Nothing is established anywhere.
   Cheapest fix is one deliberate cut that includes a score - the goal lines are
   at x = 20 and x = 100, so which one the disc crosses names the endzone with
   no inference - then `clip.json:quarter` propagates it.

## Commands

```bash
python -m tools.scout goals --out eval/m9/goals.json    # find candidates
python -m tools.pipeline work/pXXXX --from calibrate    # the whole chain
python -m tools.gates                                   # every gate
python -m ur.spans work/pXXXX                           # who threw to whom
python -m tools.disc_score work/pXXXX --out eval/m9     # score against tags
python -m tools.disc_loop work/pXXXX                    # what to ask next
python -m tools.build_site                              # AGENTS rule 7
```

## Two things not to relearn

- **No still-based pre-filter predicts whether a possession will calibrate.**
  Three were tried; r = +0.11 over nine known outcomes, and the best-scoring
  candidate of all 49 calibrates at 35 %. Screening means running the
  calibration: six minutes, six wide.
- **Measure the artefact, not the log.** Three fixes in this session printed
  success while leaving the defect in place. All three were caught by
  re-measuring the output afterwards.
