# Next session — start here

Written 2026-09-14 at the end of a long session. `docs/29-scouting-possessions.md`
is the full write-up of what was built; this is only what is *not done*.

## Goal 2 is the open one, and it is blocked on twenty keystrokes

Everything around the disc is built, measured and pushed. Nothing has been
measured against a human, because there are no tags yet.

**What to ask for:** open <https://bmccall17.github.io/ultimate-radar/> (p0001),
press `t` on the frame each throw is released and `c` on the frame it is caught.
**No player selection needed** — that changed this session and it matters:
identifying a jersey at this range is the thing M5's OCR failed at, and the
moment is the half a person can actually see. Then **Download events** and put
the file at `work/p0001/events.json`.

**What happens then, in order:**

```bash
python -m ur.spans work/p0001        # who threw to whom, with a margin per span
python -m ur.disc  work/p0001        # folds it in; flights become `interpolated`
python -m tools.disc_score work/p0001 --out eval/m9   # the first ground truth
python -m tools.disc_loop  work/p0001                 # what to tag next, or stop
python -m ur.possess work/p0001 && python -m tools.build_site   # AGENTS rule 7
```

- `tools/disc_score.py` holds out every third tag over all three folds and
  scores the unaided inference against them. **This is the first ground truth in
  the project.** Expect it to be bad — `docs/27` says so.
- `tools/disc_loop.py` refuses to stop without a threshold calibrated on
  held-out tags, which is `docs/27`'s first trap. Its second trap — never feed
  the solver's own output back as a constraint — is enforced in code: only
  `source: "human"` events are ever constraints.
- **The bar** (from the original brief): at least one throw where "Separation at
  release" shows a number not labelled `inferred`. With timing-only tags the
  receiver is *solved*, so the card shows a number capped at `partial` and says
  "worked out from the tracking, not tagged". **Clearing the bar as written
  needs a tag that names the receiver** — select the player, then `c`.

## Also open

- **p0009 at 25.8 s, p0003 at 32.6 s.** Not a calibration fault: the camera
  follows the throw and only 5-8 of 14 players are anchored, the rest frozen at
  their last seen position. A viewer presentation question, not a pipeline one.
  Nothing proposed yet.
- **The `Space` toggle.** It is `docs/06`'s spec - a nearest-player Voronoi over
  the whole pitch - and it does not inform, because it colours 40-yard cells
  over grass nobody can contest and ignores that players are moving. The version
  that answers a question is time-to-reach. Player speed is measured across six
  possessions and 18,246 observed steps: p50 3.52, p90 6.81, p99 10.47 yd/s.
  Owner has parked this deliberately.
- **`docs/` is 222 MB** and each published possession adds ~35 MB to git history
  permanently. Re-encoding the published clips smaller would roughly quarter it.
- **Four possessions cut and unpublished** - p0006, p0007, p0008, p0010 - all
  passing M1 acceptance, none with a median frame that has a located player on
  it. p0008 passes at 0.077 yd, better than anything published, on 35 % of its
  frames.
- **`docs/08` #5, the field length**, is still unresolved and still the
  highest-leverage unknown. Six calibrated possessions now exist, several
  endzone-framed, which is what that risk says it needs.

## Two things not to relearn

- **No still-based pre-filter predicts whether a possession will calibrate.**
  Three were tried; correlation +0.11 across nine known outcomes, and the
  best-scoring candidate of all 49 calibrates at 35 %. Screening means running
  the calibration: six minutes, six wide.
- **Measure the outcome, not the log.** Three fixes this session printed success
  while leaving the defect in place - a loop bound capped at six iterations that
  reported "dropped 6" for every possession alike, an acceptance cliff
  calibrated on the wrong population, and a check comparing against neighbours
  that had already been removed. All three were caught by re-measuring the
  artefact afterwards.
