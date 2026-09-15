# 06 — Viewer specification

A working prototype exists, built on `fixtures/possession_demo.json`. It is the behavioural
reference for this milestone. Where this document and the prototype disagree, this document
wins; where it is silent, copy the prototype.

The prototype fakes one thing only: with no real footage available, it renders the camera
view by projecting the synthetic positions through a simulated pinhole broadcast camera.
That means the overlay and the overhead view are genuinely two renderings of one geometry —
the same relationship they will have with real video and a real homography. Replacing the
render with `<video>` plus an overlay canvas changes the source of the projection, nothing
else.

## Layout

- **Header** — possession label, the two teams and which is on offence, theme control,
  "copy link to this moment".
- **Provenance banner** — while data is synthetic, say so at the top, plainly. When real,
  replace with the source video, timestamp, and how much of the possession was human-corrected.
- **Camera view** (larger, left) — video with overlay. Toggles: overlay on/off, matchup
  lines, off-frame arrows.
- **Overhead view** (right) — the field, the camera frustum, players, trails, disc.
  Toggles: space control, trails, pin moment.
- **Transport** — scrub bar with event ticks and a coverage strip; play/pause, frame step,
  speed (1× / 0.6× / 0.35×), jump to previous/next throw.
- **Readouts** — six cards, each with an evidence label.
- **Roster** — 14 rows: slot, jersey, evidence now, share of possession seen, speed, who
  they are guarding and at what range.
- **Needs a human** — auto-detected issues with one-click fixes.
- **Corrections** — the log, with undo.

Both views stack to one column below ~980 px. Everything must work at 400 px wide.

## Camera-view overlay

- A **ground ring** at each player's feet, in their team colour — an ellipse in image space,
  drawn by projecting a circle of ~0.95 yd radius, so it sits on the grass rather than
  floating. Solid for observed, dashed for estimated.
- **Labels** only for the selected player, their matchup, and the disc holder. Labelling all
  fourteen is unreadable; this was tested.
- **Matchup lines** between each defender and their nearest opponent, on toggle.
- **Edge chevrons** for players outside the frame: a chevron at the border pointing where the
  system thinks they are, labelled with the sigma. Non-negotiable — without it the overlay
  implies the off-frame players do not exist.
- Selecting a player dims everyone except them and their matchup.

## Overhead view

- Field to scale: 120 × 53⅓ yd, endzones tinted, 10-yard lines, brick marks, an
  "attacking →" label that says where it got the arrow from — `confirmed` by a
  human, `derived` from a confirmation elsewhere in the same quarter, or
  `unverified`, dimmed, when neither (AD-10, `docs/30` § 2.0). Underneath it, the
  control that settles it: one click says which way, and it settles the whole
  quarter. It rides out with the tags in `events.json`.
- **The camera frustum**, dashed, with everything outside it scrimmed. This is the most
  important element on the page.
- Players per the evidence conventions in `docs/05-uncertainty.md`.
- **Trails**, last 2.6 s, fading with age, switching solid/dashed segment by segment so the
  trail itself shows which parts of the run were observed.
- **Space control** (toggle): nearest-player Voronoi at 1 yd resolution, tinted by team,
  hatched where the owning player's position is a guess.
- **Pin moment** (toggle): freeze the current formation as a light outline and keep it drawn
  as time moves, so two moments can be compared directly. This is the comparison feature —
  side-by-side players is a worse answer than one overlaid on the other.
- Click to select; **drag any estimated marker to correct it**.

## The six readouts

Each card: label, value, one line of context, an evidence chip (`measured` / `partial` /
`inferred`), and one sentence of plain-English explanation. Cards whose evidence is
`inferred` are dimmed and say so in words.

| Card | Value | Why a coach cares |
|---|---|---|
| **Coverage** | *n* of 14 in shot, with a sparkline over the possession | Sets the trust level for everything else. It goes first for that reason. |
| **Defensive shape** | `Person` / `Person, n off` / `Zone or junk`, plus matchup stability % | The headline tactical read. |
| **Mark** | which side of the thrower the mark stands, and the gap | Determines what throws are available. |
| **Separation at release** | yards between receiver and nearest defender at the last throw | The most decision-relevant number in ultimate. |
| **Deep cover** | distance from the deepest threat to the nearest defender, and whether anyone is goal-side of them | Whether a huck is on. |
| **Shape lag** | cross-field offset between the defensive and offensive centroids, with a sparkline | A spike on a swing is the defence failing to shift with the disc. |

### Scheme classification, specified

Two measured quantities, both shown, never collapsed into a verdict alone:

- **Assignment stability** — for each defender, the most frequent nearest-opponent over a
  2-second window, and the fraction of frames matching it.
- **Assignment distance** — current distance to that nearest opponent.

A defender is *covering* when stability > 0.6 **and** distance < 5.5 yd. Then: ≥ 6 of 7
covering → `Person`; ≤ 3 → `Zone or junk`; otherwise `Person, n off`, naming the defenders
who are adrift and by how much.

Distance is the half most implementations omit, and omitting it is why they report a clean
person defence while a defender stands ten yards from anybody. That defender is the whole
story of the possession.

### Force, stated honestly

Report the geometry: which side of the thrower the mark occupies, and which sideline the
disc is therefore pushed toward. Do **not** report "forehand force" or "backhand force" —
that depends on the thrower's handedness, which broadcast video does not reliably show. Say
what was measured and let the coach supply the name.

## Interaction

- Space play/pause; ←/→ step a frame, shift for a half-second; Esc clears selection.
- Click a player in either view, or a roster row, to follow them.
- Drag an estimated marker on the overhead view to place a player. On release, the
  surrounding estimated span re-fits and the correction is logged.
- Issue cards jump to the moment and pre-select the player involved.
- Undo reverses the last correction.
- The URL carries the timestamp; "copy link to this moment" is the share mechanism.

## Copy rules

The viewer's words are part of the product. Say what was measured and what was not, in a
coach's vocabulary, without hedging into uselessness. "3 players are outside the frame or
hidden — their markers are the system's best guess, not an observation" is right.
"Confidence: 0.72" is not.

## Non-functional

- No framework required, no build step, opens from `file://`.
- Light and dark themes both designed, following the viewer's own setting.
- 15 fps playback with all layers on, on a laptop, without dropping frames. Memoise anything
  whose inputs only change when corrections do.
- Keyboard reachable, visible focus, honours `prefers-reduced-motion`.
