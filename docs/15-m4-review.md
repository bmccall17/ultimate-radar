# 15 — Review of M4 (in progress)

Independent check of the mid-M4 handback. Claims that could be verified from first
principles were re-derived rather than read.

**Verdict: the tracker is sound, the escalated decision is real, and the gate it is failing
is mis-specified — my fault, not the tracker's.** One process problem is larger than either:
nobody has looked at what this tracker actually does.

---

## Verified independently

**The motion model is correct, and the diagnosis behind it is the good part.** Re-derived
both verification claims from scratch with σ_v = 2.6 yd/s:

| Claim | Check |
|---|---|
| Velocity sd saturates at σ_v | 1 s → 2.196, 2 s → 2.491, 5 s → 2.597, 10 s → **2.600**, 30 s → 2.600 yd/s |
| Q_pp → white-noise-acceleration limit as dt falls | dt = 1.0 s → 0.642, 0.2 → 0.912, 1/15 → **0.969**, 0.02 → 0.991 |
| The rejected model grows without bound | piecewise WNA at σ_a = 1.2: 2 s → 1.70, 10 s → 3.80, 30 s → **6.57 yd/s** |

All three behave exactly as the handback says. The third reproduces the reported symptom —
a filter that believes an unseen player might be sprinting at 7.8 yd/s is not a filter, it is
a licence, and it will absorb any detection within a huge radius while its own slot sits
somewhere wrong.

The diagnosis deserves more credit than the fix. **Two of the three failures presented as
association bugs and were covariance bugs.** "736 detections, median 13 yd from every slot"
reads as a gating problem; the usual response is to loosen the gate, which would have buried
the real fault and produced a tracker that quietly assigns detections to the wrong players.
Following it back to a frame-rate-dependent process-noise model is the right kind of
stubbornness, and integrated OU — where damping is the model rather than smoothing applied
afterwards — is the right answer.

**The two noise estimates agree.** M3 measured foot-point error over 50 hand-checked
detections: median 0.435 yd, **rms 0.761**, p95 1.221. Two-frame displacement noise is
therefore √2 × 0.761 = **1.076 yd**; M4's speed measurement used 1.183, about 10 % higher.
Two independent estimates within 10 % is a good sign, and M4 is on the conservative side —
which, since noise is subtracted in quadrature, makes σ_v = 2.6 yd/s a mild *under*estimate
rather than an over-fit. Fine as it stands; worth a line in the code saying so.

**Incidental good news on a gate nobody has claimed yet.** Raw detections are already at
median 0.435 yd and p95 1.221 against M4's position gate of median < 0.8 and p95 < 1.8.
Kalman smoothing should only improve on that. Of the five gates, this is the one most likely
to pass on the first measurement.

**The working tree is clean.** `git status` showed 51 modified files when I ran it, but the
diff is a pure CRLF/LF flip — `git diff --ignore-cr-at-eol` is empty. That is git running in
a Linux VM against a Windows checkout, not the repo. Worth adding a `.gitattributes` with
`* text=auto eol=lf` so tooling on either side stops seeing phantom changes.

---

## The escalated decision

**Recommendation: (a) keep excluding `weak_team` — and re-specify the gate, which is the
actual problem.**

The gate reads "observed fraction within 5 points of the visible fraction". I wrote it, and
it is a comparison of two *counts*, which is a weak thing to gate on: it can be satisfied by
counting the wrong objects. That is exactly what options (b) and (c) would do. Admitting
`weak_team` adds ~1.10 detections per frame that are mostly the three uncaught referees, and
buys ~7.9 points of "observed" by putting non-players into player slots. The number would
pass and the product would be worse. Declining that trade was right.

But (a) as stated leaves the project carrying a failing gate it cannot act on, and that is
also bad — a permanently red gate stops being read.

**The fix is to make it a recall gate on players, position-matched.**

> For each of the 20 labelled frames, take every detection a human labelled `sol` or `chill`.
> Project its foot point to field coordinates. Ask whether a slot **of that team** is
> `observed` within 1.5 yd. Report the fraction over all labelled player-boxes.

This is the question the gate was always trying to ask — *did the tracker see the players who
were there* — and it has the property the count comparison lacks: **a referee cannot improve
it**, because referees are not in the denominator. The perverse incentive disappears, and the
"zero phantom slots" gate stops being traded against, because the two gates now measure
different things instead of the same coverage from opposite ends.

**It needs no jersey identity labels.** This is a positional match, not an identity match,
and `eval/m3/team_labels.json` already has every in-bounds box labelled `sol` / `chill` /
`ref` / `crew` / `unsure` on those 20 frames. The gate unblocks today. The 1 Hz jersey
labelling is still needed — but only for the ID-switch gate, which is a genuinely different
question and should be sequenced separately rather than blocking this one.

Two caveats to state when reporting it:

- The denominator is *detected and labelled* players, so a player the detector missed
  entirely is invisible to it. Bound that with M2's recall (0.987) and say so; or use the
  hand-counted 11.85/frame as a second denominator and report both.
- 1.5 yd is a threshold, so report the number at 1.0 and 2.0 yd as well. If the answer moves
  a lot between them, the position gate is doing the work and should be read first.

**And a prediction, so the measurement decides rather than the argument.** Given that only 9
of the 245 unassigned detections cost a real observation, I expect per-player recall to come
out around 0.90 or better — in which case the tracker is fine and the old gate was the whole
problem. If it comes out near 0.75, there is a real coverage gap, and **then** option (b) —
inflate R rather than drop the detection, so a weak-team detection competes weakly instead of
not at all — becomes worth trying, because it would be buying real players rather than
referees. Measure before choosing.

On (d): re-measuring the visible fraction was right, and 84.6 % from 20 labelled frames
supersedes 88 % from three hand-counted M0 frames. Correct the number in `docs/04` and
`docs/05` rather than leaving two figures in circulation.

---

## The bigger problem: nobody has watched this tracker

`eval/m4/` contains one file, `m4_speed.json`. M1 produced a verification video, M2 produced
a detections video, M3 produced a possession video and a stills sheet. **M4 produced no
render at all.**

A tracker is the first stage whose failures are *temporal* — a slot that swaps, a ghost that
drifts somewhere absurd, a referee quietly holding a defender's slot for six seconds. None of
those are visible in a per-frame statistic, and all of them are obvious within thirty seconds
of watching. Several of the questions in HANDOFF §3 would answer themselves: you would see
whether the excluded `weak_team` detections are referees or players, because you would see
what is standing where the slot is not.

**Do this before measuring anything else.** Two panes, 24 seconds: the video with the 14
slots drawn as ground rings, and the overhead view beside it, with evidence state rendered
per `docs/05` — solid for observed, dashed for predicted, sigma disc sized in real yards.
That is most of the M6 viewer anyway, and it is the cheapest instrument this project can
build. Measuring a tracker nobody has looked at is the wrong order of operations.

---

## Smaller notes

1. **The M3 render draws projected field lines across the sponsor banner.** Clip drawing to
   the registration mask — the same mask registration already uses. Cosmetic now, misleading
   later when an overlay element lands on a graphic and looks like a detection.
2. **σ_v = 2.6 yd/s is now load-bearing** and lives in a tracker constant. Put it in
   `docs/02` § AD-1 as a measured sport constant, with the method and the baseline curve it
   came from, so the next person does not treat it as a tuning knob.
3. The `weak_team` sink is worth its own line in the M4 write-up regardless of the gate
   decision: 1.10 detections per frame is 9 % of everything the detector offers, and knowing
   how that splits between referees, crew and genuinely ambiguous players is a direct read on
   M3's quality. The team labels can answer it without new work.
