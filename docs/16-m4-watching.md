# 16 — Watching the M4 tracker

Written after watching `eval/m4/p0001_tracks.mp4` twice, before computing any gate.
Nothing here is a measurement against an acceptance criterion. Where a number appears it
is there to pin down something I had already seen, or to say how big it was.

The render is two panes: the broadcast with each slot drawn as a ring on the ground, sized
to its sigma in real yards, and the same fourteen slots overhead with the camera's footprint
on the field. Below the overhead view is a strip per slot showing its evidence state across
the whole possession, with a playhead. That strip turned out to be the most useful single
element — it is the only place a six-second dropout is visible as a shape rather than as a
thing you have to notice not happening.

---

## The short version

The tracker is better than I expected on position and worse than I expected on who is in a
slot. Rings sit on players. Ghosts behave. But **one slot spends the end of the possession
locked onto a camera operator**, and **most of the detections the tracker refuses are real
players**, which is the opposite of what I assumed when I wrote the handback.

## Does any slot visibly hold the wrong person?

**Yes. D6 — a Wind Chill defender — holds a camera operator from frame 339 to the end.**

`eval/m4/d6_holds_a_camera_operator.png`. At f339 the D6 ring is on a man crouched behind the
far sideline next to a tripod, in front of the sponsor banner, with a second crew member
standing at a camera beside him. D6 had been `unknown` for 7.9 seconds before that; it
re-acquired 30.9 yd from where it went dark, and what it re-acquired was not a player.

It got there through three filters, each by a hair:

- field y = **55.09**, which is 1.76 yd beyond the far sideline at 53.33 — inside the 2.0 yd
  bounds margin AD-3 allows, with 0.24 yd to spare;
- height ratio **0.779**, against a floor of 0.62;
- torso L\* **51.0**, against a neither-kit band that starts at **51.39**. It missed being
  flagged `weak_team` by **0.39 L\***, so `ur/team.py` called it `chill` with a team score of
  1.0 — full confidence.

That last one is the uncomfortable part. The crew reject in `ur/team.py` needs *both* a torso
matching neither kit *and* feet beyond the far sideline. This man satisfies the position half
comfortably and fails the appearance half by four tenths of a luminance unit. The two-part
rule I argued for in `docs/14-m3.md` is doing exactly what I said it would — declining to
reject on position alone — and here that is the wrong answer.

Elsewhere I could not adjudicate identity by eye. Two same-team pairs cross within a yard
(O2 and O7 come within 0.67 yd at f153; O1 and O3 within 0.80 yd at f48) and in both cases
the rings pass through each other with nothing visible to say which is which. Those are the
cases the jersey labels exist for.

What I can say is that there are **no long-range swaps**. The largest move a slot makes
between two consecutive observed frames, anywhere in the possession, is **1.15 yd** — that is
detection jitter, not a slot jumping to another player. Whatever identity errors exist here
are between players who were already close together.

## Where do the predicted ghosts go?

**They behave.** This is the part I was most worried about and it is fine.

When the camera pans downfield around f250, three or four slots are left behind and go
`unknown`. On the overhead view they sit as large faint circles outside the camera footprint,
growing. They do not wander off the field, they do not sprint, and they do not pile up in a
corner. Re-acquisition distances, over gaps of 1.9 to 8.7 seconds, imply speeds of 1.9 to
5.2 yd/s — all comfortably inside what a person can do.

That is the Ornstein-Uhlenbeck damping working as intended: the mean coasts to a stop instead
of extrapolating a sprint for eight seconds. I had expected to find at least one ghost
somewhere absurd and did not find one.

The honest caveat: "physically possible" is not "right". A ghost that coasts to a stop 15 yd
from where the player actually went is still wrong, it is just not *obviously* wrong. The
render cannot tell me which, because the player is off camera — that is the whole point.

## Do the sigma discs look like they contain the truth?

Broadly yes, with one reservation.

An `observed` ring is about 0.35–0.5 yd in radius, which on screen is roughly twice a
player's shoulder width, and the player's feet are inside it essentially always. That matches
what M3 measured for the foot point (0.435 yd median) and it looks right rather than
flattering.

`predicted` rings grow to 1.5–3.5 yd over a two-second gap and `unknown` rings to 6–16 yd.
Those I cannot check by eye, because the player is not on screen — which is the reservation.
**The sigma disc is only verifiable exactly where it is least interesting.** The
sigma-calibration gate will have the same problem and should say so.

One thing the render did show: when a slot re-acquires after a long gap, the ring snaps from
several yards down to half a yard in one frame. That is correct Kalman behaviour and it reads
correctly on screen — the disc collapsing is a visible "ah, there you are".

## What are the excluded `weak_team` detections?

**Roughly half of them are real players.** `eval/m4/weak_team_excluded.png` is a seeded sample
of 40 of the 341, cropped and magnified. Counting them by eye: about 16–17 are referees
(unmistakable black-and-white vertical stripes), about 6 are camera crew at the pylon, and
about 17–18 are real players — overwhelmingly a dark and a light player overlapping in one
box, which drags the torso sample into the gap between the kits.

There is a clear time structure. The early frames (f47 to f166) are dominated by the referee,
who is in shot for much of the first half of the possession. From f208 onward the sample is
almost entirely real players.

So the decision to exclude `weak_team` from association, which I defended in the handback and
the review endorsed, is **buying about 0.55 non-player detections per frame at a cost of about
0.5 real player detections per frame**. That is a much narrower trade than I implied when I
wrote that excluding them "costs almost nothing". It does cost something, and the cost is
real players going unobserved.

## What are the `unassigned` detections?

**Almost all of them are real players too**, and this is the finding I did not expect at all.
`eval/m4/unassigned_detections.png`, 30 sampled from 248: Sol players in white with blue
shorts, Wind Chill players in dark. One possible crew member. No referees.

In the handback I wrote that the 227 detections "outside every gate at a median of 23 yd" are
"almost always a non-player". **That was wrong.** I inferred it from the distance without
looking at the pixels, and the pixels say otherwise.

Worse, **245 of the 248 unassigned detections happen in a frame where that team still had a
free slot.** Only 3 are a genuine surplus of more than seven. The tracker is leaving real
players unobserved while slots sit idle.

Having seen that, I went looking for which gate was doing it:

| Rejected by | n | nearest free slot | that slot's reach | its sigma | gap | chi² |
|---|---|---|---|---|---|---|
| the reach gate only | **70** | 2.8 yd | 2.0 yd | 0.81 | 2 frames | **4.4** |
| chi² only | 38 | 34.2 yd | 39.6 yd | 7.22 | 62 frames | 14.4 |
| both | 124 | 12.3 yd | 3.8 yd | 1.12 | 6 frames | 29.9 |
| lost a contested slot | 12 | | | | | |

The first row is a plain defect. Those 70 detections are **statistically fine** — a chi² of
4.4 against a threshold of 9.21, i.e. the filter considers them a perfectly plausible match —
and they are rejected by `GATE_FLOOR_YD = 2.0`, a hard floor I put in as a *physical backstop*
for long gaps. At a gap of one or two frames the floor is **tighter than the statistical
gate**, so it does the opposite of its job: instead of stopping a huge covariance swallowing
the field, it overrides the covariance when the covariance is small and correct.

I have not changed it. The instruction was to get the number before changing the tracker to
hit the number, and that is right — but this one should be fixed after the gate is scored, and
scored again, so the improvement is attributable rather than folded in.

## Other things I saw

**The first twelve frames are blank and the render does not say why.** Calibration confidence
is 0.40 at f3, below the 0.5 floor, so `ur.detect.run` states no positions and the tracker has
nothing. The overlay correctly draws nothing — but it also says nothing, so it looks like a
bug rather than a refusal. The `pf is None` branch prints an explanation; this case does not,
because `H` exists and only the confidence is low. Both should say the same thing.

**Coverage tracks the camera, hard.** While the shot is wide, 10 to 13 of 14 slots are
observed. When the camera pans downfield to follow the disc around f250–f290, it falls to 6
of 14 within about two seconds — see `eval/m4/watching_camera_pans_away.png`. Nothing is wrong
with the tracker there; the players are simply not in shot. It is a good argument for the
camera-footprint polygon being on screen permanently, because with it the drop reads as "the
camera left them" rather than "the tracker lost them".

**Slots interpolate while real detections go unused in the same frame.** At f18, three Sol
slots are `interpolated` — meaning they were not matched at association time — while two real
Sol detections sit unassigned in that frame. The tracker chose to fill a gap by interpolation
rather than match a detection that was there. This is the reach-floor defect above, seen from
the other side, and it is worth stating separately because the interpolated samples *look*
like successful tracking on the timeline strip.

**Something I cannot name yet.** The state strip shows a lot of short alternation — a slot
going observed, predicted, observed, interpolated across a second or two — and I do not know
whether that is the detector flickering, the association gate chattering at its boundary, or
genuine occlusion. It does not look harmful; the positions stay put. But 39 state runs for a
slot over 24 seconds is a lot of transitions and I would like to know which of the three it
is, because two of those three are fixable and one is not.

## What this changes

Nothing in the tracker, yet. Two things in what I believe:

1. **The `weak_team` exclusion is a real trade, not a free win.** Half of what it discards are
   players. It is still probably the right call, but `docs/14-m3.md` and the handback both
   undersell the cost and should be corrected.
2. **The unassigned detections are not junk.** My claim that they are "almost always a
   non-player" was an inference from a distance statistic and it was wrong. The reach floor is
   the mechanism, and it is fixable.

Both of those were invisible in every number I had computed before watching, and both took
about ten minutes of looking. The review was right to put this first.
