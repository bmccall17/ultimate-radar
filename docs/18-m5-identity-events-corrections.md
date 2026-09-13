# 18 — M5, identity, events and corrections

**Status: three of four acceptance criteria pass. Jersey OCR fails, and it fails on the
footage rather than on the plumbing.**

| M5 criterion | Required | Measured | |
|---|---|---|---|
| Swap detector finds the fixture's injected swap | right frame, right pair | **f156, D5/D7**, 0 false positives | pass |
| `resolve.py` anchor produces a path continuous at both ends | — | joins move **0.0669 yd** (allowed 0.0992) | pass |
| `revert` restores byte-identical output | identical | **identical**, 860349 bytes | pass |
| Jersey correct for ≥ 5 of 7 on a team, rest `null` | ≥ 5 | **3 of 7** (Sol) | **fail** |

A fifth result, not asked for here but owed from M4: the detector added in this milestone
closes M4's failing second clause. **Identity switches caught: 0 of 2 → 2 of 2.**

Evidence: `eval/m5/`. Code: `ur/issues.py`, `ur/resolve.py`, `ur/identify/`, `ur/events.py`.

---

## The detector M4's failure asked for, and the one that did not work

`docs/05` specifies three detectors. M4 measured two of them catching **none** of the two
identity switches that actually happened, because both happened across a dropout rather
than a single-frame crossing. So M5 owed a fourth, and the first version of it was wrong in
a way worth keeping.

**Re-acquisition surprise** asks how far a returning player is from the dead-reckoned
position, in units of the sigma the model was claiming. It fires **zero times on p0001**.
Over all 161 re-acquisitions, the largest is **1.73 sigma**. A player who reappears 25 yd
away after eight seconds is 1.56 sigma, because an honest covariance after eight seconds
says "could be 16 yd away in any direction".

That is not a threshold to tune, and tuning it would have been fitting to two known
answers. **The tracker admitted the wrong player precisely because it was plausible, so any
detector built on implausibility is blind to exactly the errors the tracker makes.**

**Contested re-acquisition** asks the question that works: was more than one candidate
plausible? A swap is not surprising, it is *ambiguous* — the right player and the wrong one
were both inside the gate and the filter picked on a thin margin. That statistic exists only
inside the tracker, so `ur/track/run.py` now records, per observed sample, how many
candidates were in the gate and the chi-square margin to the runner-up. A margin in
chi-square units is a log-likelihood ratio, so the 2.0 threshold means the winner was less
than about 2.7× more likely than the second.

It catches both switches: **D2 at f163** (3 candidates, margin 0.48) and **D1 at f322**
(2 candidates, margin 1.25).

Honest limit: it fires 16 times over 24 seconds, and only 2 are known switches. They are
ranked by margin so the worst come first, but precision beyond those two is unmeasured —
the labels could only read 20 % of crops.

## Corrections, and two flaws in my own test

`ur/resolve.py` replays an append-only log over a fresh read of `tracks.json`, which is never
edited (AD-6). Three operations — anchor, swap, confirm — and revert, which marks an entry
inert rather than deleting it, because the log is a history.

Both flaws were found by running the test, not by reading it:

- The continuity check first measured the largest frame-to-frame step anywhere in the span.
  The span it picked contains O6's 25 yd re-acquisition snap, which swamps anything a 4 yd
  anchor does — the number moved from 24.9682 to 24.9040 and would have "passed" whatever
  the ramp did. A discontinuity from the ramp appears **at the joins**, so that is where it
  is measured now.
- The revert check first compared against the raw rebuild and failed. That was the test
  being wrong: `resolve` annotates the document it returns, so the comparison was testing
  annotations. The baseline is now `resolve` over an *empty* log, which puts both sides
  through one code path — and a separate assertion covers what that gave up, namely that an
  empty log alters nothing but those two keys.

A swap moves `est`, `state`, `sigma`, `det` **and** the association record together.
Swapping positions alone would leave each slot pointing at the other's detections, which is
a subtler wrong than the one being fixed.

## Jersey OCR: measured, built, and still short

**Probed before it was built.** EasyOCR was run against the 48 crops a human had already
read by hand in M4. It returned nothing on 33 of them, and of the 15 it did read, 9 were
right — **18.8 % accuracy, 60 % precision on crops selected for being legible.** The full
population is harder: over the whole possession it produced 243 candidate reads from 3243
crops, about 7 %.

That is why the module votes rather than reads. A winner must clear a support bar and a
margin over the runner-up; failing either emits `null`, which `docs/04` asks for explicitly.

**Result: 7 of 14 slots named, 7 honestly null.**

| | correct | wrong | null with a truth to check | unverifiable |
|---|---|---|---|---|
| Sol | **3** | 0 | 2 | 2 |
| Wind Chill | 2 | 1 | 4 | 0 |

The gate wants ≥ 5 correct on one team. The best is Sol with 3.

Two things are worth saying about the shape of that failure rather than just its size:

- **The vote never contradicted a stable hand reading.** Its single disagreement is D1,
  voted #4 against a hand modal of #5 — and D1 is precisely the slot M4 measured switching
  from #5 to #4. The slot held both people, and the vote picked one of them. Counting it
  "wrong" is the strictest available reading.
- **O1 had the right answer and lost.** Its top candidate carried 20.44 of support against
  15.7 for "20", which is "28" misread; the margin came to 0.23 against a bar of 0.40, so it
  emitted `null`. That is the policy working — a coin flip between 28 and 20 should not
  become a name on screen.

**What the truth actually is, and is not.** There is no roster. The truth here is a modal
jersey per slot from 48 hand readings at 1 Hz, which leaves two slots with nothing to check
against, treats a switched slot's number as the one it held longest, and carries about four
reading errors in fifty-two of its own. A clean test of this gate needs a real roster — the
most legible crop per slot across all 360 frames, or the published team sheet.

**What would fix the result**, in order of likely effect: a digit recogniser trained on this
project's own crops rather than a scene-text model (which would also remove the unconfirmed
weights licence, see below); higher-resolution source; or accepting that at this framing
jersey identity is a human's one-per-point assignment, which `docs/07` already names as the
third source of identity and may simply be the right one here.

## Events

AD-7 decides this: events are tagged by hand and disc detection is a stretch goal. So
`ur/events.py` is a place to put a human's knowledge, and `suggest` emits only what the
tracks support — `possession_start` at the first observed frame.

It deliberately does **not** guess throws and catches from player motion. A throw is an
event about the disc, nothing in this pipeline has seen the disc, and a "suggested throw"
inferred from two players changing direction would be a plausible-looking invention. Every
suggestion carries `source: "suggested"` so the viewer shows it differently until confirmed.

## Licences

`docs/07-licenses.md` has the full rows. Two items need calling out:

- **`python-bidi` is LGPL-3.0**, the first non-permissive dependency in this project. Not
  AGPL, GPL or NC, and this register already treats LGPL as the acceptable option for
  linking — but it passes as LGPL, not as permissive, and a release should say so. It
  arrives only because EasyOCR imports it for right-to-left scripts, which nothing here
  needs.
- **EasyOCR's checkpoints could not be verified offline.** The repository is Apache-2.0;
  the weights download separately from JaidedAI. By this register's own rule that is a gap,
  and it is recorded in `docs/08-risks.md`. Nothing currently depends on them, because the
  gate failed anyway.

## Reproducing

```bash
python -m ur.issues        work/p0001          # -> issues.json
python -m ur.issues        fixtures/possession_demo.json --out eval/m5/fixture_issues.json
python -m tools.m5_resolve work/p0001          # anchor + revert gates
python -m ur.identify.vote work/p0001          # -> identities.json  (~4 min, GPU)
python -m tools.m5_identity work/p0001         # the jersey gate
python -m ur.events        work/p0001 suggest
python -m ur.resolve       work/p0001 --verify-revert
```
