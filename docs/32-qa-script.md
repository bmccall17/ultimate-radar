# 32 — QA script: driving the repair surface as a digital twin

For an agent or a person to run against **the published site**, not a local build. AGENTS
rule 7: the live page is the deliverable, and every defect this project has found in the
viewer was found by clicking the thing that is actually served.

```
https://bmccall17.github.io/ultimate-radar/p0003/
```

p0003 is the reference possession: it is the one with hand tags, hand corrections, a
sideline crowd, a disc hole and the worst calibration stretch, so it exercises everything.

`tools/qa_fixture.py` takes any possession, and p0009 is worth a second pass — its clean
frame is **14 of 14** slots on a real in-field detection with none on the crowd, which
p0003 never reaches. A scenario that passes on p0003 and fails on p0009 is a finding.

## Run this first, and use what it prints

```
.venv/Scripts/python.exe -m tools.qa_fixture
```

**The frame numbers below are not in this document.** A QA script that hard-codes "at f345
the pips read O2 O3 O4 O7" is right on the day it is written and wrong the first time
somebody repairs something — and a runner who meets a red scenario caused by the data
*improving* learns that red means nothing. So this script carries the properties and
`tools/qa_fixture.py` derives the numbers from the page as currently published. It names
four frames by rule:

| name | the rule | used by |
|---|---|---|
| **clean frame** | most slots on a detection *inside* the lines | § 4 placing, § 7 jerseys |
| **busy frame** | most slots with any detection at all | § 2 the rail |
| **collision** | two same-team slots inside 1.5 yd, one with a detection and one dead reckoning | § 6 detach |
| **dead frame** | calibration under the floor | § 5 the refusal |

Wherever a scenario says *the clean frame* or *the collision*, it means the one the fixture
just printed.

## What this covers, and what it does not

It covers **the human-in-the-loop surface** — the rail, repair mode, the correction
operations, the jersey readings, the three downloads, and the round trip from a download
back to a published page. That surface has no unit tests worth the name, because what it
does is render and accept clicks, and eight of the nine defects in `HANDOFF` § 8 were
things that *rendered plausibly and were wrong*.

It does not cover the pipeline. That is `python -m tools.gates`, and § 7 below is the
part of this script that runs it.

## 0. The oracle — what must be true after any session, whatever was clicked

Check these first and last. A scenario that passes while one of these is broken has not
passed.

| invariant | how to check |
|---|---|
| the correction log round-trips | `python -m ur.resolve work/p0003 --verify-revert` says **YES, byte for byte** |
| corrections reach the page | `corrections reached the page` is PASS for every possession |
| no hand-placed frame reaches a metric | `no human position in a metric` is PASS, and reports at least one grader **excluded** |
| the suite is green | `python -m unittest discover -s tests -t .` |
| the page renders its own contradiction check | `window.__urSelfCheck.ok` is `true`, never `false` |
| nothing throws | the console has no errors after a full pass |

**Use the venv**: `.venv/Scripts/python.exe`, not whatever `python` resolves to. `scipy` is
an M0 dependency and the gate suite needs it.

## 1. The harness, and four things that will waste an hour

Paste this before each scenario. It is written from the mistakes made building these
features, and every line of it is load-bearing.

```js
const $ = id => document.getElementById(id);
const btn = id => [...$('rail').querySelectorAll('[data-slot]')]
                    .find(b => b.dataset.slot === id);

// (1) SELECTION TOGGLES. Clicking the selected slot DESELECTS it. A script that
// clicks blind works the first time and silently does the opposite the second.
const pick = id => { if (!btn(id).className.includes('on')) btn(id).click(); };

const setf = n => { $('scrub').value = n;
                    $('scrub').dispatchEvent(new Event('input', {bubbles:true})); };

// (2) RE-MEASURE THE CANVAS BEFORE EVERY EVENT. The panels re-render on each
// draw and this layout is a single column at narrow widths, so the canvas MOVES
// between a pointerdown and the pointermove that follows it. Caching the rect
// sends the second event to the wrong yard.
const yd2client = (x, y) => {
  const D = window.POSSESSION, r = $('radar').getBoundingClientRect();
  const k = $('radar').width / r.width, P = 10 * k;
  const cl = (v,a,b) => v<a?a:v>b?b:v;
  return [r.left + (P + cl(x,0,D.field.length_yd)/D.field.length_yd *
                        ($('radar').width - 2*P)) / k,
          r.top  + (P + (D.field.width_yd - cl(y,0,D.field.width_yd)) /
                        D.field.width_yd * ($('radar').height - 2*P)) / k];
};
const ev = (t, x, y) => $('radar').dispatchEvent(
  new PointerEvent(t, {clientX:x, clientY:y, bubbles:true, pointerId:1}));

// (3) POINTER CAPTURE refuses a synthetic pointerId. Stub it or every drag ends
// at pointerdown.
$('radar').setPointerCapture = () => {};

// (4) THE DOWNLOADS never touch the disk under automation. Intercept the blob.
async function grab(buttonId) {
  const caught = [], rc = URL.createObjectURL, ac = HTMLAnchorElement.prototype.click;
  URL.createObjectURL = b => { caught.push(b); return "blob:stub"; };
  URL.revokeObjectURL = () => {};
  HTMLAnchorElement.prototype.click = function () {};
  $(buttonId).click();
  URL.createObjectURL = rc; HTMLAnchorElement.prototype.click = ac;
  return JSON.parse(await caught[0].text());
}
```

**Run each scenario in one evaluation.** Page state does not reliably survive between
separate tool calls, and a scenario split across two is a scenario whose setup may have
evaporated.

## 2. The rail

`setf(<the busy frame>)`, then read every `[data-slot]` button.

- **14 buttons**, `O1`–`O7` then `D1`–`D7`, in that order.
- Each carries one of three classes: `seen` (a detection is matched on this frame),
  `guess` (dead reckoning), `lost` (no position at all).
- The classes must agree with the data: `seen` ⇔ `POSSESSION.players[i].det[f] !== null`.
  A pip that disagrees with `det` is the readout lying, which is the whole family of
  defect this project exists to prevent.
- `title` on each names the state, whether a detection is matched, and either the position
  and sigma or how long since anything saw it.
- The set of `seen` slots matches the fixture's `busy_frame.slots` exactly.

**Defect if:** fewer than 14, an order that is not roster order, or a pip that contradicts
`det`.

## 3. Repair mode

`$('tRepair').click()` with the clip playing.

- Playback **stops**. A moving picture cannot be placed on, and a keyframe about "whatever
  frame the clock reached" is a keyframe about nothing.
- The video carries a banner naming who is being placed, or telling you to pick somebody.
- With a slot selected, a **dashed ring** marks where the tracker currently has them, so a
  person can see what they are overruling.
- The field-paint crosses are **off**. They were on by default once and the first person to
  use the mode read two unlabelled crosses in empty grass as places to put a player.
- `$('repPaint').click()` turns them on, and every cross carries its landmark name
  (`goal line +x @ y0`). An unnamed cross is a defect: it cannot be dragged onto the line
  it is meant to be on.

## 4. Placing from the video

`setf(<the clean frame>)`, `pick('O3')`, then click the overlay:

```js
const o = $('over').getBoundingClientRect();
$('over').dispatchEvent(new MouseEvent('click',
  {clientX: o.left + o.width*0.5, clientY: o.top + o.height*0.6, bubbles:true}));
```

- The repair panel reads **Save keyframe (1)**.
- `$('repSave').click()`, then `grab('dl')` → exactly one `anchor`, `slot: "O3"`, the clean
  frame's `f`, and `xy` inside the field.
- The correction panel shows **one row**, not fourteen: `keyframe 1 anchor(s) @ f<n> · O3`.

**The three regressions this scenario exists for**, each of which shipped once:

- **A click must not nudge.** Press and release 2 yd off a marker's centre with no movement
  between: the staged count stays **0** and no position changes. The hit test reaches 4 yd,
  so staging on the press moved a marker four yards every time somebody clicked it to see
  who it was.
- **A save writes to the frame the placements were made on.** Stage on the clean frame,
  scrub somewhere else, save: the anchor carries the **clean frame's** number, and the panel
  warns that the staged work belongs to another frame.
- **Undo steps back.** Save two keyframes on different frames, press Undo twice: **both**
  come back reverted. Undo used to re-revert the most recent one forever.

## 5. The calibration refusal

`setf(<the dead frame>)` — the fixture prints its calibration beside it.

- The panel says so, names the number, and offers **a button to the nearest frame that
  clears 0.5**. Telling somebody to go and find one is not help; p0003 reads 0.00 across
  several seconds.
- A click on the video stages **nothing**.
- The overhead drag still works, because it reads yards off the radar and never touches the
  homography.

**Defect if:** a click at calibration 0.00 produces an anchor. That is the worst thing this
mode can do — it turns an honest look at the right player into a `confirmed` position with
sigma 0.3 in the wrong part of the field, indistinguishable downstream from a good one.

## 6. Saying a label is wrong

Take the fixture's **collision**: `setf(<f>)`, `pick(<the ghost>)`. That slot is dead
reckoning onto the player the other one has.

- The panel names the other slot and the distance, and says which of the two the camera can
  vouch for: the one with a detection.
- **`This is nobody, from here`** is enabled. Click it: the ghost's span becomes `unknown`,
  the log reads `detach <slot> @ f<a>–<b>`, and Undo restores it exactly.
- On a frame where the slot **has** a detection, the same button is disabled and says to
  swap instead. A detach may never cross an `observed` frame — the camera saw somebody
  there, and removing that is a deletion, not a correction.
- `this is actually…` writes **two** entries, a swap and a swap back, and the panel names
  the span before you commit.

## 7. Jerseys — and the check hiding inside them

A slot has no referent of its own. `CONTEXT.md`: it *"is not a person: it is a label the
tracker maintains"*. A jersey read off a shirt is the only reference there is.

```js
setf(CLEAN);  pick('D5'); $('jerseyIn').value = 7;  $('jerseyGo').click();
setf(LATER);  pick('D5'); $('jerseyIn').value = 12; $('jerseyGo').click();
const ident = await grab('dlIdent');
```

`CLEAN` is the fixture's clean frame; `LATER` is any frame where D5 still has a position.
The numbers are invented on purpose — this scenario tests the contradiction machinery, not
the footage.

- Two readings, each carrying **the frame it was read on**.
- `slots` resolves `D5` to `jersey: null` with a `conflict` — **not** to one of the two.
  Two numbers on one slot is not a tie to break, it is proof the label moved between two
  people, and the stretch between is what needs splitting.
- The panel and the rail tooltip both say so.

**Defect if:** a conflict resolves to a number. Picking one would manufacture the exact
kind of false certainty `docs/04` M5 forbids, and would destroy the only automatic
identity-switch detector this project has.

## 8. The three stores must stay apart

After a session that has placed a marker, dragged a paint landmark and read a jersey:

```js
const corr  = await grab('dl');        // corrections.json
const paint = await grab('dlPaint');   // calibration_truth.json
const ident = await grab('dlIdent');   // identities.json
```

- `corrections.json` — `anchor`/`swap`/`detach`/`confirm`/`revert` only. It must contain no
  `landmark` and no `jersey`.
- `calibration_truth.json` — `landmark`, `field`, `image`. No `anchor`.
- `identities.json` — `readings` and `slots`. No positions.

**Defect if any field crosses.** They are gathered in one session with one gesture and they
answer to different stages: a paint reading replayed as a player anchor puts a person on a
line they were nowhere near, and it poisons the log AD-6 wants to be a training set of
human-verified player positions.

## 9. The round trip — the one that matters

Everything above is a click. This is whether the click reaches the reader.

1. Save a keyframe on the live page and `grab('dl')`.
2. **Append** it to `work/p0003/corrections.json`, renumbering the `id`s past the ones
   already there — that file holds a real roster pass and is tracked in git. Replacing it
   destroys somebody's work, which is what `docs/30` § 2.8 is about.
3. `.venv/Scripts/python.exe -m tools.pipeline work/p0003 --from correct`
4. `.venv/Scripts/python.exe -m ur.resolve work/p0003 --verify-revert` → **YES, byte for byte**
5. `.venv/Scripts/python.exe -m tools.build_site`
6. `.venv/Scripts/python.exe -m tools.gates` → no new failures, and
   `corrections reached the page` reports **n applied, n active**
7. Push, wait for Pages, and re-read the published `possession.js` **with a cache-buster**:
   `fetch("possession.js?cb=" + Date.now(), {cache: "no-store"})`. The page's own
   `<script src>` will serve a stale copy from the browser cache long after the CDN has
   updated, and a reload does not revalidate it.

**The stage order is load-bearing.** `--from correct` runs resolve → disc → resolve, so the
disc stage sees the corrected positions. Running `ur.disc` before the corrections leaves the
repair in the file and the disc still missing from the picture — measured on p0003: the
longest stretch a reader sees no disc goes 3.1 s → 0.5 s only in this order.

**Watch for the silent one.** Any run of `ur.possess` — a parallel session, an earlier
`--from` stage, a stray command — rewrites `possession.json` without corrections and
nothing in the artefact shows it. That is what `corrections reached the page` is for, and it
has caught it twice.

## 10. Reporting a defect

Into `docs/30-findings-and-gates.md`, not into a ticket — findings outlive the work and a
closed issue is hard to search (`docs/31`). A ticket points at the finding.

And before writing it up, **check it is not the measurement that is wrong**. `docs/30`
§ 2.10 is a gate that reported a slot crossing 55 yd in one frame, which turned out to be a
hand-placed anchor compared against the tracker's own observation of a different person.
Two of this session's findings died that way. The question to ask first is always: is this
the tracker's output, or is it somebody's correction being measured against it?
