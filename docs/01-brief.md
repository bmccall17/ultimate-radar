# 01 — Brief

## The outcome

A coach or a curious player watches one possession and comes away able to say, out loud,
what the defence did: what shape it started in, who was guarding whom, where it bent, who
left their matchup, and whether the throw that beat it was open or forced. They can pause,
step back, replay the same three seconds, pin one moment against another, and send the
sequence to someone else to argue about.

The person this is for does not want to configure anything. They want to watch film and
be less wrong about it.

## Two things most tracking demos get wrong, and we will not

**1. Pretending to know.** A single broadcast camera on a 120 × 53⅓ yd field sees roughly
two thirds of the players at any instant, and the ones it misses are disproportionately the
deep defenders — exactly the players whose position decides whether a huck is on. A radar
view that draws fourteen confident dots is lying about ten of them. Ours renders what the
camera can see as a shape on the field, draws unseen players as explicitly uncertain, and
refuses to report a tactical number that depends on players it could not observe.

**2. Being unfixable.** Trackers swap identities when same-team players cross. This is not
a bug to be engineered away; it is the expected behaviour of every appearance model on
players in identical jerseys. So the product assumes it will happen, detects it, and lets a
human fix it in one click — and keeps the correction separate from the raw output so it can
always be undone, audited, and later reused as training data.

Those two commitments are the product. The tracking is in service of them.

## Definition of done for round one

One possession from the Sol / Wind Chill semifinal, end to end, with a viewer someone can
be handed cold. The gate is a **comprehension test**, not a metric. Sit a person who knows
ultimate but has never seen the tool in front of one possession and ask:

1. Did the defence start in person or zone?
2. Which Wind Chill player was guarding the thrower, and which side were they marking?
3. Did any defender leave their matchup during the possession? When, and to do what?
4. At the moment of the last throw, how open was the receiver?
5. Which parts of your answers are you confident about, and which did the tool tell you it
   was guessing at?

Five for five, without help, without the tool having misled them on question 5. That last
question is the one that matters most: a viewer that admits its blind spots and is believed
is worth more than one that is quietly wrong.

Supporting numeric gates are in `docs/04-milestones.md`.

## Non-goals for round one

- Automatic disc tracking. Throws and catches are tagged by hand (two keystrokes each).
  A disc is 8–20 px, motion-blurred, and often occluded; a detector for it is a research
  project, and the events it would produce are cheap to get from a human.
- Whole-game processing. The unit of work is one possession.
- Player names. Slots (`O1`–`O7`, `D1`–`D7`) and jersey numbers carry all the tactical
  meaning. Real names are an optional, manual, per-point mapping.
- Live or near-real-time. Offline batch is fine.
- Any hosted service, account, or database.
- Automatic tactical judgement ("bad poach"). The tool measures and displays; the coach
  judges. Every number shown must be traceable to positions the user can inspect.

## The sport, as the code must model it

**Verified in M0 against the primary source**: UFA Rule Book Version 13.0 (2025 season),
`eval/ufa-rulebook-2025-v13.pdf`, §2.1.1 — "The field is a rectangle measuring 53 ⅓ yards
wide by 80 yards long plus 20-yard end zones on each end" — and §2.3.1 for the 20 yd brick
mark. The table below is correct.

Two things the rulebook adds that the docs did not have:

- **§2.3.3** permits a **110-yard field** "if a special exception has been granted … due to
  venue limitations", with the brick mark moving to 15 yd. Whether Breese Stevens is a full
  120 yd could not be settled from the broadcast; see `docs/00-footage-report.md` Q2 and the
  open questions in `docs/08-risks.md`. **Every field coordinate depends on the answer.**
- **§2.3.2** defines **reverse brick marks**, 10 yd *behind* each goal line. That is a
  seventh marked point on the centreline and a free calibration correspondence.

| | UFA (this footage) | USAU (for reference) |
|---|---|---|
| Total length | 120 yd | 110 yd |
| Goal line to goal line | 80 yd | 70 yd |
| Endzone depth | 20 yd | 20 yd |
| Width | 53⅓ yd (160 ft) | 40 yd |
| Players on field | 7 v 7 | 7 v 7 |

A UFA field has the same footprint as an American football field with deeper endzones, so the
hope was that the venue would already carry football yard lines and hash marks.

**Answered in M0: it does not.** Breese Stevens Field is a **soccer** pitch. There are no
yard lines and no hash marks. What it carries instead is a full set of association football
markings — centre circle, halfway line, penalty and goal areas, corner arcs — under the
temporary ultimate paint and pylons. That turns out to be *better* than gridiron lines for
calibration, because the centre circle is a conic of exactly specified radius (9.15 m).
See `docs/00-footage-report.md` Q2 for the evidence and the resulting M1 plan.

## Vocabulary the UI must speak

The tool describes geometry; the coach supplies the label. Some terms it does use:

- **Mark** — the defender on the thrower. Its position sets the **force**: standing on one
  side of the thrower takes away that side. Whether that is a forehand or backhand force
  depends on the thrower's handedness, which video does not reliably show, so the tool
  reports the side and the sideline the disc is pushed toward and stops there.
- **Person vs zone** — person defence shows stable one-to-one assignment at short range;
  zone shows defenders holding position relative to each other and the disc rather than to
  any opponent. The tool separates them with two measured quantities, assignment stability
  and assignment distance, and shows both rather than only a verdict.
- **Poach** — a defender leaving their matchup to cover space or another threat. Reads as
  stable-assignment-but-large-distance, or an assignment flip with a big jump.
- **Last back / deep deterrent** — whether any defender is goal-side of the deepest threat.
  A single boolean that a coach reads instantly.
- **Separation at release** — distance from the receiver to their nearest defender at the
  frame the disc leaves the hand. The most decision-relevant number in the sport.
- **Reset space** — the area behind and beside the thrower. Not measured in round one.
