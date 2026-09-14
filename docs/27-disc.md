# 27 — The disc

**Status: the machinery is built, the contract is met, and the part that was supposed to
work without a human does not. That last finding is the useful one.**

```bash
python -m ur.disc     work/p0001     # -> disc.json
python -m ur.possess  work/p0001     # carries it into possession.json
```

| gate | required | measured | |
|---|---|---|---|
| Disc position present | every frame | **360 / 360 (100 %)** | pass |
| …each carrying an evidence state | every frame | **360 / 360** | pass |
| Holder inferred without a detector | ≥ 90 % of frames where a holder exists | **not established — the sequence is not a possession** | **fail** |
| A disc sample is ever `observed` | never | **never** | pass, by construction |

---

## The model, and why it is not a detector

`docs/25` Part 3 is right and this follows it. A disc is about 27 cm, motion-blurred at
60 fps, and for most of a possession it is **held** — occluded by a hand and a torso inside
the densest cluster of bodies on the field. That is the hardest version of the problem and
the version nobody needs to solve, because a held disc is not an independent object. It is a
property of whoever is holding it, and the tracker already knows where every player is.

So the disc is a state machine over the possession:

```
HELD(player) --release--> FLIGHT(from, t0) --catch--> HELD(player')
                               |
                               +--incompletion--> LOOSE --pickup--> HELD
```

Only FLIGHT would need pixels — the one phase where the disc is separated from every body,
silhouetted against grass, on a smooth arc, inside a window bounded by two known endpoints.
That stage is not built, and on the evidence below it is also not the bottleneck.

**No disc sample is ever `observed`, and that is structural rather than a shortfall.** Nothing
in this pipeline has detected a disc, so the strongest claim available is `confirmed` — a
human said who was holding it. The ordinary case is `predicted`: the geometry says a
particular player is the thrower and the disc is assumed to be in their hand. A
separation-at-release computed from a guessed holder is not a worse measurement of
separation; it is a measurement of something else, and `docs/05`'s propagation rules already
know what to do with that.

## Holder inference, and the measurement that sank it

The idea is sound on paper. In ultimate the thrower plants a pivot foot, and UFA rule §15.1
requires the marker to be within 3 m — so the thrower and their mark are **both** nearly
still while every other pair on the field is running. It is a sequence problem rather than a
per-frame one, because in person defence *every* offensive player has a defender within a
yard or two on any single frame; what distinguishes the holder is that they persist, and
change only at a catch.

Implemented as a Viterbi pass over the possession: hidden state is which offensive slot holds
the disc or `none` (in flight), emission cost is the combined path length of a candidate and
their nearest defender over one second — in yards, so it is a physical quantity rather than a
score — and **a direct hand-over is forbidden**, because a disc does not move between two
people without being thrown.

It produces a confident, plausible-looking, wrong answer.

There are no labelled holders anywhere in this project, so the sequence cannot be scored
against truth. It can be scored against physics and the sport, which is weaker and was
sufficient:

| | measured on p0001 |
|---|---|
| throws inferred | 7 |
| **throws that reverse the previous throw's direction** | **83 %** |
| net field position gained over the whole possession | +7.9 yd |
| where the disc ends up | x = 65 yd, with the endzone starting at 100 |

The throw sequence gains 27 yd, loses 28, gains 25, loses 21 — a disc oscillating across the
field every second and a half. That is not a team moving a disc; it is a holder estimate
flipping between two candidates whose emission costs are nearly equal. Chance alone would
alternate about 50 % of the time; 83 % is the signature of a two-state oscillation.

**It is not a tuning problem, which was worth checking before concluding anything.** Sweeping
the switch cost over 3, 6, 10, 15, 25, 40 and 60 yd moves the alternation only from 88 % to
75 % and never moves the final disc position off x = 65.3. The signal is not there to be
recovered by weighting it differently.

Three reasons it fails, in order of how much they cost:

1. **Several offence–defence pairs are near-stationary at any moment.** A reset handler, a
   poaching defender, a cutter between accelerations — all look like a thrower and a mark.
2. **The positions it reasons over are the tracker's**, with a median error of 0.39 yd and
   27 % of slot-frames estimated rather than observed. "Stillness" measured over a second is
   comparable to that noise.
3. **The camera follows the disc**, so the holder is nearly always in shot and so are the
   players around them. The one signal that would break the tie — who the camera is centred
   on — is one this stage does not use.

### The system says so itself

`ur/disc.py` scores its own output on the three checks above and, when they fail, **emits
every inferred sample as `unknown`** rather than as a position. On p0001 that is 360 of 360
samples: the file still carries a coordinate for every frame, as `docs/03` requires, and
every one of them says it is not to be believed.

Suppressing the inference entirely was the alternative and is worse: it would leave the
viewer with nothing and no reason. Saying "here is a number and here is why it is not
trustworthy", in the file, is what lets `ur/possess.py` and the viewer decline to use it
without either of them having to re-derive the judgement.

## What actually makes the disc real: two keys

AD-7 decided this five milestones ago — *"a small tagging pass: scrub, press `t` on a throw,
`c` on a catch. Roughly 20 keystrokes per possession"* — and it was right. **The surface was
never built.** That is the finding behind the finding: `ur/disc.py` fell back on inferring
the holder because there was nothing authoritative to work from, and the only human event in
`work/p0001/events.json` turned out to be a schema example that had been carrying
`source: "human"` since M5. Read as truth, it forced O4 as the holder for a single frame in
the middle of another player's possession. It now carries `source: "example"`, and the
`events@1` contract names the three sources explicitly so the next one cannot be mistaken.

The tagging surface now exists in the viewer. Select a player, press `t` on the frame they
release and `c` on the frame they catch; the pane lists what has been tagged and downloads
`events.json`, which goes in the possession directory. `ur.disc` treats a tagged frame as a
**hard constraint** — no other holder is admissible there — and still solves the spans
between tags, so partial tagging degrades gracefully instead of all-or-nothing.

Two clicks per throw fix the disc exactly: held by the thrower up to the release, in flight
between, held by the receiver after. Nine throws is eighteen keystrokes, and it turns an
entire possession from `unknown` to `confirmed`.

## What this changes about the build order

`docs/25` Part 3 proposed: (1) holder inference, (2) two-click tagging, (3) flight detection,
(4) automatic release and catch. Step 1 was expected to reach ≥ 90 % on its own and to
produce the labels step 3 needs.

**Reverse 1 and 2.** Tagging is not the fallback for when inference is not good enough; it is
the source of the only ground truth this problem has. Nothing here can be validated without
it — not the holder inference, not a flight detector, not an automatic release. Twenty
keystrokes on one possession would produce, for the first time, a labelled holder sequence
to measure against; the inference could then be scored honestly rather than argued about, and
tuned against something real.

The visual check that started this points the same way. Rendered at 5× around the inferred
holder, **the disc is plainly visible in hand on some frames** (`eval/m8/holder_check.jpg`) —
so a human can do this quickly and reliably, and so, eventually, could a detector trained on
what the human tags.

## Honest limits

- **One possession, and the holder sequence in it is unverified.** Every number above scores
  the inference against physics, not against a person. It establishes that the sequence is
  wrong; it does not establish which frames are wrong, or that a tagged sequence would be
  right.
- **`z` is a shape, not a measurement.** It exists so the viewer draws a flight rather than a
  ground slide. Never quote it.
- **The flight duration floor is a stand-in.** Where a release happened is exactly what the
  `t` key is for; until it is pressed, a flight shorter than a quarter second is widened
  symmetrically, which is an assumption wearing a number.
- **LOOSE is unimplemented.** A disc on the ground after a turn is rare and needs a turnover
  event to bracket it. Nothing in `p0001` needs it.
