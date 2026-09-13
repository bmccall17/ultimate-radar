# 19 — M6, the viewer

**Status: built. Two of three acceptance criteria are met here; the third needs a person and
cannot be run by the thing that wrote the page.**

| M6 criterion | Required | Result | |
|---|---|---|---|
| Runs from `file://` with no build step | — | no build, no framework, no dependency; **`file://` itself unverified in this environment** | see below |
| Renders the fixture correctly | — | matches `viewer/prototype.html` frame for frame | pass |
| Passes the comprehension test with a real person | 5 of 5 | **not run** — needs a human | open |

One number that was not asked for but is a stated non-functional requirement: a full redraw
with **every layer on** — space control at 1 yd, trails, matchup lines, both sparklines, the
roster and all six cards — takes **10.6 ms**, measured over 20 consecutive frames on the real
possession. The gate is 15 fps, i.e. 66 ms. There is a factor of six in hand.

Code: `viewer/index.html`, one file, 1100 lines. Data: `viewer/data.js` (fixture, committed)
and `viewer/live-data.js` (real, gitignored, written by `tools/make_view.py`).

---

## How it loads, and why that shape

```html
<script src="data.js"></script>
<script src="live-data.js"></script>
```

Both are plain `<script>` tags assigning `window.POSSESSION`, and the second wins. A fresh
clone has no `live-data.js`, gets a 404 that costs nothing, and renders the fixture. A working
copy has one and renders the real possession. Neither case needs a server, and a page opened
from `file://` cannot `fetch` a sibling JSON file, which is the whole reason the data arrives
as a script rather than as data.

`tools/make_view.py` now carries four files across instead of one, because the viewer's four
panes need them and a second request is not available: `possession.json`, `issues.json` (the
"needs a human" queue), `identities.json` (voted jerseys, merged onto the slots so the overlay
can label them) and `events.json`. Only the first is required; a working directory that has
not reached M5 still renders, and the panes that have nothing say so rather than sitting empty.

## One projector, two backends

`docs/06` says the prototype fakes exactly one thing — with no footage, it projects synthetic
positions through a simulated pinhole — and that replacing it with `<video>` plus a real
homography "changes the source of the projection, nothing else". That is true, and it is worth
making structurally true rather than just conceptually true, so everything above the projection
is written once:

- **`pinhole`** — the fixture. `camera.per_frame[i].aim` and `focal_px`, ported verbatim from
  the prototype.
- **`homography`** — real footage. `inv(H)` for field→image, `H` itself for image→field.

Both expose `project`, `unproject` and `border`. Nothing downstream knows which is in use.

### The two traps in the homography backend

**The sign of `w`, again.** `H` is normalised on `H[2][2]`, which fixes `w`'s sign for
image→field but leaves the inverse's overall scale free — and on this footage every point
genuinely in front of the camera comes back with `w` **negative**. This is the same trap
recorded in `docs/08` and in the M3 handoff; it is written down here too because the viewer is
the third place it has had to be solved. The sign is taken per frame from the image's
bottom-centre pushed through `H` and back.

**The horizon.** This one was new, and it was found by looking at the page rather than by
reading the code. `w = H₂₀u + H₂₁v + H₂₂` vanishes along a line in the image, and rows on the
far side of that line map to points *behind* the camera. Sampling the image's top edge to
build the frustum — which is what the prototype does, correctly, because its `unproj` clamps
such rays to a far cap — hands the homography a polygon that folds through infinity. On
frame 150 the image's top row mapped to field y ≈ −75 to −82 yd, the clipped polygon came back
degenerate, and **the overhead view scrimmed the entire field**. The symptom was not an error;
it was a page that looked plausible and was wrong. The frustum walk now stops one pixel short
of the horizon on the visible side.

The fix is checked rather than assumed: at frame 150, all nine slots the tracker reports
`observed` sample unscrimmed field colour on the overhead canvas, and none sample the scrim.
If the frustum were wrong in either direction that test would fail.

## Corrections, and the thing this had to prove

The page holds an append-only log in memory and replays it over pristine copies of the tracks,
so `tracks.json` is never touched (AD-6) and nothing compounds. Anchor, swap, confirm and
revert are implemented to the same rules as `ur/resolve.py` — the ramped re-fit from `docs/05`
included, so a dragged marker meets the machine's observations at both ends.

A `file://` page cannot write to disk. Pretending otherwise loses a coach's work, so the
honest answer is a **Download log** button that hands back `corrections.json`.

**That file was round-tripped through `ur.resolve`, and this is the criterion that matters
most**, because a correction the pipeline cannot read is a correction that does not exist. A
log produced entirely by clicking and dragging in the page — one `confirm` from an issue card,
one `anchor` from a drag, one `revert` from Undo, one `swap` from an issue card's dropdown —
went into `work/p0001/corrections.json` untouched:

```
[resolve] 5 correction(s) in the log, 3 active after reverts
      c1 confirm  {'was': 'observed'}
      c4 confirm  {'was': 'confirmed'}
      c5 swap     {'frames': 317}
[resolve] reverting all 4 correction(s) reproduces the uncorrected output: YES, byte for byte
```

## What the viewer cannot tell you, and says so

The comprehension test in `docs/01-brief.md` asks five questions. On the **fixture** the page
answers all five — question 2 (*which player was marking the thrower, and which side*) reads
`2.1 yd, far sideline side · D5 marking O5`, and question 4 (*how open was the receiver at the
last throw*) reads `2.8 yd · O6 from D6 at the release, 17.4 s`.

**On real footage it cannot answer questions 2 or 4, and this is structural, not a bug.**

- Question 2 needs the disc. Nothing in this pipeline has seen the disc — AD-7 makes disc
  detection a stretch goal — so the Mark card reads `—` and says why.
- Question 4 needs a throw with a tagged receiver. `ur/events.py` emits `possession_start` and
  nothing else, deliberately, and the one hand-tagged throw on p0001 carries a thrower but no
  target.

So: **run the comprehension test on the fixture, or hand-tag a throw and its target in
`events.json` first.** Running it on p0001 as it stands would fail two of five questions for
reasons that have nothing to do with the viewer, and would tell you nothing about the viewer.

Question 5 — *which parts are you confident about, and which did the tool tell you it was
guessing at* — is the one `docs/01` calls the one that matters most, and it is the one the page
is actually built around: the scrim over everything outside the frustum, dashed rings and
dashed trail segments for estimated positions, sigma discs at true field scale, hatched space
control where the owning player is a guess, chevrons for players off the frame labelled with
their sigma, and an evidence chip on every card with cards marked `inferred` dimmed and saying
in words that they should not be quoted.

## Changes outside the viewer this forced

- **`ur/possess.py` now carries the measured gates** instead of `gates_measured: false` and a
  notice saying nothing is established. That notice was written before M4 measured anything and
  was still there afterwards, so the viewer's provenance banner was telling the truth about a
  file that was out of date. It now reports recall 0.8846 and sigma containment 0.80, and says
  which gate is marginal and why.
- **`camera.position_yd` was in the wrong coordinate frame.** `calibration.json` keeps the
  camera centre in the *soccer* frame, which is correct there — that is where the venue was
  solved — but `possess.py` copied it verbatim into a document whose every other coordinate is
  ultimate-frame yards. Nothing read it yet, which is exactly why it was worth fixing before
  something did. It is now converted through `venue_transform`, and the original is kept beside
  it as `position_yd_soccer`.
- **`ur/standin.py` and `viewer/live.html` are deleted.** The stand-in was scheduled for
  deletion the moment `possession.json` came from the tracker, which happened in M4;
  `live.html` was M3's working page and `index.html` strictly supersedes it. Two viewers in one
  folder is an invitation to look at the wrong one.

## The acceptance criterion that is not met here

**`file://` was not verified in this environment.** The browser available to this session
renders local files as static snapshots and cannot load sibling scripts; the extension path to a
real browser had no file-URL access. Everything below was verified over `http://localhost`
instead, which exercises the same code:

- both data scripts load and the second overrides the first;
- both projector backends, the fixture and the real possession;
- light and dark themes, and the 400 px layout with no horizontal overflow;
- Space, ←/→, shift-←/→, Escape, roster selection, issue cards jumping to their moment;
- the correction round-trip above.

Two `file://`-specific differences are known and handled: `navigator.clipboard` is unavailable
from `file://`, so "copy link to this moment" falls back to a prompt containing the URL rather
than flashing "Copied" over a copy that never happened; and `localStorage` may throw on an
opaque origin, so every read and write of the theme setting is wrapped.

One difference is *not* a `file://` problem but will look like one: Python's `http.server` does
not serve range requests, so **the video cannot be seeked over it** — `video.seekable` comes
back `[0, 0]`. From `file://` the browser reads the file directly and seeking works. If you
test through a server, use one that supports ranges or the scrub bar will appear broken.

**So the first criterion needs one minute of a human's time**: open
`viewer/index.html` by double-clicking it, and check that the page draws. If it does, M6's
first criterion is met. If it does not, the failure will be visible immediately and loud.

## Reproducing

```bash
python -m ur.possess   work/p0001            # -> possession.json (gates recorded)
python -m ur.issues    work/p0001            # -> issues.json
python -m ur.events    work/p0001 suggest    # -> events.json
python -m tools.make_view work/p0001         # -> viewer/live-data.js
# then open viewer/index.html directly in a browser
```

With no `work/` at all, open `viewer/index.html` anyway: it renders the committed fixture.
