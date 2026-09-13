# 20 — Review of M6, and the three open decisions

Independent check of the M6 handback. The viewer was run in Chromium against the real
possession; claims that could be tested were tested rather than read.

**Verdict: M6 works, and the one criterion the build environment could not close is now
closed — it runs from `file://`.** The product is doing the thing it was built to do: at
t = 12.0 s it reports *"Deep cover 3.0 yd — O4 is deepest; D7 is nearest and is NOT goal-side.
Nobody is between the deep threat and the endzone — the huck is on."* That is a real tactical
read, computed from real tracking, in a coach's language, with an evidence chip on it. That is
the whole point of the project and it is on screen.

Below: the closed criterion, then the things that will mislead a first-time viewer, then the
three open decisions.

---

## Closed: `file://` works

Tested in Chromium (the same engine the user will open it in), loaded as
`file:///…/viewer/index.html`, both paths:

| | Result |
|---|---|
| With `live-data.js` present | **No page errors.** Sibling scripts load. `window.POSSESSION` = `p0001`, `synthetic: null`. Radar and coverage strip both painted. Only failed request is `clip.mp4`, which was absent from the test copy. |
| Without `live-data.js` (a fresh clone) | **No page errors.** Falls back to the committed fixture — `demo-0001`, `synthetic: true`. Radar painted. The 404 on `live-data.js` is benign, as a classic `<script src>` should be. |

**The video pane works too.** Loaded from `file://` with the clip in place, the `<video>`
element reaches `readyState: 4` at 1280x720, seeks to the requested moment (12.03 s from a
`#t=12.0` link), and the overlay canvas paints on top of it with the ground rings landing on
the players' feet. Screenshot: `eval/m6/viewer-video-overlay-verified.png`. One substitution
to note — Playwright's Chromium ships without H.264, so the test used a WebM transcode of
`clip.mp4`. Everything around the codec is verified: `../work/p0001/clip.mp4` resolves
correctly from `viewer/index.html`, the video loads, seeks and stays in sync with the overlay.
Real Chrome decodes H.264 natively, so the residual risk is small, but it is the one thing
that was substituted rather than tested.

Why it works, so it stays working: there is no `type="module"`, no `fetch`, no `XMLHttpRequest`
and no dynamic `import` anywhere in `index.html` — those are what break on `file://`, and the
page uses none of them. There is also no `getImageData` / `toDataURL` in the shipped page, so
drawing the video into a canvas never taints anything. **Both properties are load-bearing for
the double-click path. Guard them if the viewer grows.**

One asymmetry worth a one-line fix: `index.html:1031` reads
`localStorage.getItem("ur-theme")` **unguarded** at top level, while the matching
`setItem` at 1040 is wrapped in `try/catch`. It did not throw in Chromium, but it is at
top level of the main script, so if it ever throws the whole page renders blank — which is
precisely the failure mode that could not be tested from the build environment. Wrap it.

---

## What a first-time viewer sees, and why it undersells the work

**The page opens on frame 0, which is the worst frame in the possession.** Default load, no
hash: *Coverage 0 of 14. 0 % of the roster is in shot. Defensive shape: Zone or junk. 20 open
issues.* Every roster row reads `unknown`, every card is dimmed and says "do not quote it".

None of that is dishonest — frame 0 genuinely has nothing observed, and the cold-start issue
says so. But a coach double-clicking this file sees a tool that appears to know nothing, and
closes it. At t = 12 the same page reads *12 of 14, 86 %, Person 3 off, 81 % matchup
stability*. **Open on the first frame where coverage clears some bar — or on the first tagged
event — and the first impression matches the 88 % the tracker actually achieves.**

**"Zone or junk" is asserted from zero observations.** At 0/14, Mark, Separation and Deep cover
all correctly show "—". Defensive shape is the only card that emits a verdict with no inputs,
in the largest type on the page. The `inferred` chip does not undo a headline. **When the
contributing count is zero, the headline should be an em-dash like its siblings.**

**`inferred` is close to permanent, which will train people to ignore it.** At 88 % recall
nearly every frame has at least one unobserved player, so nearly every card carries
"do not quote it" — at t = 12, with 12 of 14 seen, Defensive shape is still `inferred`. A
warning that is always on stops being a warning. That is my spec's fault, not the build's:
weakest-input provenance is too blunt for a metric aggregating fourteen players.

> **Suggested rule change for `docs/05`.** A metric is `inferred` when an unobserved player
> *could change its answer* — for Defensive shape, when one of the seven defenders being
> classified is unseen; for Deep cover, when an unseen player could be the deepest. Otherwise
> `partial`. And name the player: "inferred — D6 unseen" is actionable, "do not quote it" is
> not.

**The issue queue drowns itself.** 20 open, 15 of them "contested reacquisition" with
near-identical wording, burying the two that are different in kind (cold start, long blind
stretch). Group them into one card with a list, ranked by margin.

**And that card's copy asserts something it has not checked.** Every one reads "barely more
likely than the runner-up", but the quoted margins run from 0.14 to 1.78. At 1.78 it was not
barely. Either scale the wording to the margin or drop the adjective and report the number.

**Smaller:** setting `location.hash` in-page does not re-render — there is no `hashchange`
listener, so the hash is read at boot only. "Copy link to this moment" works on a fresh load,
which is the case that matters, but the in-page path is dead. And at t = 12 the Defensive shape
card says "3 off" but names two defenders, one of them at 3.3 yd, which is inside the 5.5 yd
covering threshold. Count, list and threshold disagree — worth a look.

---

## Two of six readouts are dark, and the fix is two fields

Mark and Separation at release both show "—" on real footage. `work/p0001/events.json` has a
hand-tagged throw at t = 12.0 by O4 **with no `target`**, and a `possession_start` with
`"player": null`.

- Separation at release needs the receiver → one field on one event.
- Mark needs the thrower → `possession_start.player`, then the holder chain follows.

That is two fields and about five minutes, and it turns on two of six cards and two of the five
comprehension questions.

**The note in `events.json` misreads AD-7.** It says the holder "is not inferable — nothing here
has seen the disc (AD-7)". AD-7 says the opposite: events are human-tagged *precisely so* the
disc detector is never needed. The holder is not an inference, it is a tag. The viewer is
disabled on a dependency the architecture deliberately removed.

**So: do not run the comprehension test on the fixture.** The handback is right that running it
on p0001 today would measure the pipeline's gap rather than the viewer — but the answer is to
close the gap, not to move the test. Tag the two fields, then run it on **real footage**, which
is the only version of that test that measures the actual goal. Running it on the fixture would
confirm the prototype works, and that was already known in September.

---

## The three open decisions

### 1. M4's recall threshold — set it at 0.85, and say why

The measurement is 0.8846. I predicted ≥ 0.90 before it was taken, and I was wrong; the
prediction was not evidence and should not now be treated as a target.

The lever to reach 0.90 is readmitting the 14 `weak_team` misses, which are the same detections
that keep referees out of player slots. That trade was examined and declined in
`docs/15-m4-review.md`, and it should not have to be re-litigated every time a round number is
missed. **Do not move the tracker to hit the threshold; move the threshold to where the product
stops being trustworthy, and record the reasoning.**

At 88 % recall with honest evidence states, a working correction flow and a coverage readout
that leads the page, a coach is not misled — they are told 12 of 14 and shown which two are
missing. That is the condition the gate exists to protect. **0.85, with a note that the number
is bounded by a deliberate product choice and that the way to raise it is better team
classification — the tracklet-level vote — not readmitting referees.**

Consider also making it a *regression* gate rather than an absolute one: recall is measured
every run and any drop below the last measurement is investigated. For a proof of concept with
no external standard, that catches what an absolute number cannot.

### 2. M5's jersey gate — accept it and retire the gate

3 of 7 against a gate of 5, with EasyOCR reading 7 % of crops overall and 18.8 % of crops a
human had already judged legible. The handback's diagnosis is right: the policy works, the
reader does not.

But the deeper point is in `docs/07`, which has always named three sources of identity and put
appearance last. UFA numbers are on the back and front of the kit, so a side-on player shows
neither; at this range, on this footage, OCR is not going to be the answer no matter which
reader is used. **The product answer is the one already in the architecture: a human assigns
names once per point, in about thirty seconds, and slots carry the tactical meaning without
names at all.**

Retire the numeric jersey gate to best-effort, keep the vote — it never contradicted a stable
hand reading, which is the property that matters — and spend the effort on M7 instead. Training
a digit recogniser on this project's own crops is a real option, but it is a week that buys
nothing the viewer needs, and M7 buys the answer to "is this a pipeline or a one-off".

### 3. M4's sigma gate — this is the one that deserves the bigger sample

32 of 40 is exactly 80.0 % against a gate of 80 %, Wilson 95 % interval 65.2–89.5 %. That
interval is too wide to call, and this is **the gate that protects the user from being
misled** — if the drawn sigma does not contain the truth, every honest-looking dashed ring on
the overhead view is a lie with a confidence interval drawn around it.

Of the three open results this is the one to spend labelling effort on. n = 120 narrows the
interval enough to call it. Ahead of the jersey reader, and ahead of chasing recall.

---

## Recommended order

1. Tag `possession_start.player` and the throw's `target` — two fields, five minutes, two cards
   and two comprehension questions.
2. Fix the open frame, the zero-input headline, the unguarded `localStorage` read, and group the
   issue queue. All small, all first-impression.
3. **Run the comprehension test with a real person, on p0001.** This is the project's actual
   acceptance criterion and everything above exists to make it meaningful.
4. Set the M4 threshold (§1) and retire the jersey gate (§2) — both are decisions, not work.
5. M7: the second possession, on p0003. It answers the only question left that matters.
6. The sigma sample at n = 120, whenever labelling capacity exists.
