# AD-17 — An answer at the edge of its own search window is not a measurement

A detector that looks for a moment inside a window may not return that window's
boundary as the answer. If nothing was observed to happen inside, it returns
**nothing** — `None`, not the nearest thing it saw. Where an independent bracket
for the answer exists, the detector's output is checked against it, and an answer
outside the bracket is treated as no answer at all.

*Why.* Two detectors in the goal index failed this way on 2026-09-18, and the
shape is identical in both. Neither looked wrong from the outside: each returned
a plausible float for every one of the game's 52 goals, which is how both passed
as working.

- `scout.clock_freeze` searched `[flip − 45 s, flip + 2 s]` for the last change to
  the game clock. On goals where the clock was still ticking when the window
  closed, the last change *was* the last frame, so it returned the window's edge.
  On goals where a graphic wiped the box after the clock had already stopped, the
  wipe was the last change, and that also sits at the window's end.
- `scout._refine` searched `[after_t − 1 s, before_t + 2 s]` for the frame the
  score bug changed on, with a criterion nothing on a clean goal could satisfy.
  It returned a time **past `before_t`** on 49 of 52 goals — past the keyframe
  that already showed the new score, so the change happened after the frame
  proving it had happened.

Both are the same defect: **the answer is a property of where the looking
stopped, not of what was seen.** A number produced that way is indistinguishable
from a measurement at a glance, it varies smoothly with the data, and it cannot
be caught by asking whether the detector returned something — it always does.
`docs/30` § 2.6 is the general form, *measure the artefact, not the log*; this is
the form it takes inside a detector.

*What it costs.* Refusing means the index is incomplete: `every goal has a
readable clock freeze` fails today on 2 of 52 rather than reporting 52 of 52 with
ten of them wrong. That is the trade this decision makes, and it is the right way
round. A gap says where to look. A boundary dressed as a measurement does not,
and it survived a whole milestone because it did not.

*How it is enforced.* `scout.freeze_index` requires a run of changes to be
followed by observed silence **inside** the window before it will call it a stop.
`scout.flip_index` requires the last unbroken stretch reading as the new score,
and `tests/test_score_flip.py` asserts every flip lands inside its own
`[after_t, before_t]` bracket, to within the one 4 fps sample separating a
quarter-second grid from a keyframe time. The bracket check is the cheap half:
it needs no footage, it is arithmetic on the committed file, and it is what
caught 49 of the 52.

*The other half of the rule.* The window itself is chosen against a correct
anchor or not at all. The freeze window's 2.0 s tail was left alone through the
first repair for exactly that reason — widening it depended on a `goal_t` that
turned out to be wrong — and was only fixed in place once the flip was corrected
and the widening could be measured. `docs/30` § 2.24.
