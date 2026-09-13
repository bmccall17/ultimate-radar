# 21 — Three viewer defects found by using it

Found by a person clicking the published viewer, then confirmed by measurement. All three are
small. The first is wrong output, not cosmetics.

---

## 1. The overhead view is mirrored across the field's short axis

**`viewer/index.html:613`**

```js
function ry(y){ return RPAD + y/FW*(radar.height-2*RPAD) }        // field y=0 at the TOP
```

Field `y = 0` is the near sideline — the one the camera stands on, at
`position_yd_soccer` y ≈ −50. Projecting through the frame-93 homography:

| Field point | Image v |
|---|---|
| near sideline, `y = 0` | **1164** — below the 1080-px frame, i.e. off the bottom |
| far sideline, `y = 53.3` | **432** — upper third of the frame |

So in the video, `y` increases **upward**. On the overhead view it increases **downward**. A
cutter on the far side appears at the top of the video and the bottom of the radar. That is
the mirror.

The long axis is fine — correlation between field `x` and image `u` over the fourteen players
at f = 93 is **+0.995**, so "attacking →" pointing right is correct. Only the short axis is
inverted.

**Fix:**

```js
function ry(y){ return RPAD + (FW-y)/FW*(radar.height-2*RPAD) }
```

Two call sites follow from it:

- `:665` — `"attacking →"` is positioned at `ry(0)-3*RK`, which becomes the bottom edge. Use
  `ry(FW)-3*RK`.
- `:706`/`:713` — `drawSpace` computes `ch = ry(1)-ry(0)+1`, now negative, and anchors each
  cell at its top-left. Use `ch = Math.abs(ry(1)-ry(0))+1` and `fillRect(rx(x), ry(y)-ch+1, …)`
  or the space layer shifts by one cell.

`fillRect`/`strokeRect` accept negative heights, so the field, endzone and frustum rectangles
need no change.

> Worth a permanent check rather than a fix and forget. This is the same class as the six in
> HANDOFF § 8: it rendered plausibly and was wrong. A cheap contradiction — project two known
> field points, assert that the sign of their image-v difference matches the sign of their
> radar-y difference — would have caught it and would catch the next one.

## 2. Matchup lines draw, and cannot be seen

`--dim` resolves to `#6b7364`, drawn at `lineWidth 1.2` dashed, over sunlit grass. Toggling
the control changes **434 lit pixels** on the overlay canvas, so the geometry is right and the
contrast is not. On a screenshot with the toggle on, no line is discernible anywhere.

The overlay canvas sits on video, not on the page background, so it cannot take colours from
the UI palette. Give the line its own treatment: a dark halo under a near-white stroke.

```js
octx.save(); octx.strokeStyle="rgba(10,14,10,.55)"; octx.lineWidth=4.4*k;
octx.beginPath(); octx.moveTo(…); octx.lineTo(…); octx.stroke(); octx.restore();
octx.strokeStyle="rgba(255,255,255,.92)"; octx.lineWidth=2.2*k;
```

The same applies to anything else on that canvas that reads from `css(--…)`.

## 3. Off-frame arrows work, but never at the moment anyone looks

The control does exactly what it should. Projecting every slot through each frame's homography
across the possession:

| | slot-frames | share |
|---|---|---|
| projects inside the video frame | 4306 | 85.4 % |
| projects outside → a chevron is due | 565 | 11.2 % |
| no position at all → nothing can be drawn | 169 | 3.4 % |

At least one chevron is due on **196 of 360 frames**. Toggling the control at t = 6.9 s moves
259 lit pixels — it draws.

But **zero are due at t = 12.0 s**, which is where a `#t=12` link opens, and none at t = 0
either. Someone opening the page, pressing the control and seeing nothing concludes it is
broken. It is not; there is simply nothing off-frame at that instant.

The gap is feedback, not geometry. Options, cheapest first: label the control with a live count
(`Off-frame 2`), disable it when the count is zero, or mark the frames where chevrons are due
on the coverage strip so the moments are findable.

**And 3.4 % of slot-frames have no position at all** — a slot `unknown` long enough that dead
reckoning was abandoned. Those players get no ring, no chevron, no mark of any kind. They are
the only case where the viewer silently shows nothing rather than showing uncertainty, which
is the one thing `docs/05` says it must never do. A chevron at the last known bearing, or a
roster row flagged "position unknown", would close it.

---

## Also confirmed, carried from `docs/20`

Setting `location.hash` does not re-render. A hash-only navigation is same-document, so the
page keeps its state and never re-seeks; only a fresh load reads `#t=`. One `hashchange`
listener fixes it.

## Verification these fixes were given

All three were applied to the hosted copy and re-tested in Chromium: no page errors, matchup
lines legible against grass, overhead orientation matching the video, space layer aligned.
`eval/m6/viewer-fixes-verified.png` is the result. The repo copy is **unchanged** — these
changes should land through the normal loop with the project's own checks re-run, not be
hand-edited in from outside it, for the reason recorded in HANDOFF § 6 about the venue
transform.
