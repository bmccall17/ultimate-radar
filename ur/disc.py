"""M8 — where the disc is, in every frame, and how much of that is known.

    python -m ur.disc work/p0001            # -> disc.json

Read AD-7 and `docs/25-round-2-ghost-audit.md` Part 3 before changing anything
here. AD-7 called disc detection a stretch goal and it was right to: a disc is
about 27 cm, motion-blurred on a 60 fps broadcast, and for most of a possession
it is **held** — occluded by a hand and a torso inside the densest cluster of
bodies on the field. That is the hardest version of the problem.

It is also the version nobody needs to solve. The disc is not an independent
object most of the time; it is a property of whoever is holding it, and the
tracker already knows where every player is. So the disc is modelled as a state
machine over the possession:

    HELD(player) --release--> FLIGHT(from, t0) --catch--> HELD(player')
                                   |
                                   +--incompletion--> LOOSE --pickup--> HELD

and only FLIGHT needs pixels — the one phase where the disc is separated from
every body, silhouetted against grass, on a smooth arc, inside a window bounded
by two known endpoints. That stage is not built yet.

**Nothing in this pipeline has seen the disc, and this module does not pretend
otherwise.** A disc position is never `observed`. The best it gets is
`confirmed`, meaning a human said who was holding it; the ordinary case is
`predicted`, meaning the geometry says a particular player is the thrower and the
disc is assumed to be with them. That distinction is the whole point: a
separation-at-release computed from a guessed holder is not a measurement of
separation, it is a measurement of something else.

## Two sources, and the second one is a human

**Tagged events** (`events.json`) are authoritative. A `throw` by A at t1 and a
`catch` by B at t2 fix the disc exactly: held by A up to t1, in flight between
them, held by B after. Two keystrokes per throw, which AD-7 already budgets for,
and they turn the whole possession `confirmed`.

**Holder inference** fills the rest, and is what you get with no tagging at all.
It is a sequence problem, not a per-frame one: in person defence every offensive
player has a defender within a yard or two, so "near-stationary with a defender
close" does not discriminate on a single frame. What does discriminate is that
the thrower and their mark are **both** nearly still while every other pair is
running — a pivot foot is planted, and UFA rule §15.1 requires the marker to be
within 3 m — and that the holder **persists**, changing only at a catch.

So it is solved with a Viterbi pass over the whole possession, where the hidden
state is which offensive slot holds the disc (or `none`, the disc in flight), and
a direct hand-over from one holder to another is forbidden: every change of holder
must pass through flight, because that is what a throw is.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from ur import grading as GV
SEED = 20260827

ANCHORED = ("observed", "provisional", "confirmed")

# ...and the narrower set: frames where the slot's OWN POSITION was seen, not
# merely re-acquired. `provisional` is in ANCHORED because somebody really was
# detected there, which is enough to let a slot be a *candidate* for the holder.
# It is NOT enough to place the disc, because `provisional` means a
# re-acquisition after a gap and whether it is even the same player is the open
# question (docs/25 R4). Same set as the viewer's MEASURABLE and audit_site's
# DRAWN_DISC_STATES, and for the same reason.
POSITION_SEEN = ("observed", "confirmed")

# UFA rule 15.1: the marker must be within 3 m of the thrower. 3 m = 3.281 yd.
# This is a rule of the sport, not a tuned threshold - a candidate whose nearest
# defender is further away than this is not being marked, so is not the thrower.
MARKER_MAX_YD = 3.281

# The window over which "nearly still" is judged. A pivot holds one foot planted
# for the whole stall count, so a second is long enough to separate a thrower from
# a cutter who is merely between accelerations, and short enough to catch a quick
# give-and-go.
STILL_WINDOW_S = 1.0

# Emission cost is the pair's total path length over that window, in yards, which
# is already in natural units: a thrower and mark cover 1-2 yd between them, a
# running cutter and their defender cover 10-14.
#
# `none` (nobody holding - the disc is in flight) has to compete with that, so its
# cost is the path length at which a candidate stops being credible as a thrower.
# 8 yd of combined movement in a second is two people jogging, which no thrower
# and mark do.
NONE_COST_YD = 8.0

# Switching holders costs a fixed amount, which is what stops the path flickering
# between two similar candidates frame to frame. It is paid once per change, so
# over a 20-frame stretch it is 0.15 yd/frame - small against the emission scale,
# large against the frame-to-frame noise it exists to suppress.
SWITCH_COST_YD = 3.0

# A slot that is not anchored this frame can still be the holder - the camera
# loses the thrower regularly - but the claim is weaker and the state says so.
# The penalty keeps an unobserved slot from winning the holder role against an
# observed one on the strength of a dead-reckoned stillness that is an artefact
# of the motion model damping rather than a planted pivot foot.
UNOBSERVED_PENALTY_YD = 4.0

# Where the disc sits relative to the person holding it. It is in a hand, roughly
# at chest height and up to an arm's length from the body centre, and which
# direction that is cannot be known without seeing it - so the position is the
# holder's and the uncertainty is widened by the arm rather than the position
# being displaced in an invented direction.
HAND_OFFSET_YD = 0.6
HELD_HEIGHT_YD = 1.2          # chest height, in yards

# A thrown disc leaves the hand at chest height and is caught at chest height,
# rising in between. Without seeing it, the height is a shape rather than a
# measurement, and it is emitted so the viewer can draw a flight rather than a
# slide along the ground - never quote it.
FLIGHT_PEAK_YD = 2.2

# A flight cannot last one frame. The Viterbi is forced to pass through `none` to
# change holder, so with nothing stopping it the cheapest path spends the minimum
# possible time there - one frame, 67 ms, during which a disc would have to travel
# the whole throw. That is not a flight, it is the transition showing through.
#
# The shortest real throw is a dump of a few yards at maybe 15 yd/s, so a quarter
# of a second is a floor rather than a typical value. A flight shorter than this
# is widened symmetrically about its centre, taking frames from the holders on
# either side, and the frames taken are marked inferred rather than tagged -
# **where exactly the disc left the hand is precisely what the two human clicks
# are for**, and this is the stand-in until someone makes them.
MIN_FLIGHT_S = 0.25


def _at(p: dict, f: int):
    v = p["est"][f]
    return None if v is None else np.asarray(v, float)


def _path_length(p: dict, f: int, w: int) -> float | None:
    pts = [_at(p, k) for k in range(max(0, f - w), f + 1)]
    pts = [x for x in pts if x is not None]
    if len(pts) < 2:
        return None
    return float(sum(np.hypot(*(pts[i] - pts[i - 1])) for i in range(1, len(pts))))


def emission_costs(doc: dict) -> tuple[list[str], np.ndarray, list[dict]]:
    """Cost of each offensive slot holding the disc, per frame.

    Low is likely. The cost is the combined path length of the candidate and
    their nearest defender over `STILL_WINDOW_S`, which is a physical quantity in
    yards rather than a score - a thrower and their mark cover 1-2 yd of it, a
    cutter and their defender cover 10-14.
    """
    nf = int(doc["possession"]["frames"])
    fps = float(doc["possession"]["fps"])
    off = doc["possession"]["offense"]
    offs = [p for p in doc["players"] if p["team"] == off]
    defs = [p for p in doc["players"] if p["team"] != off]
    ids = [p["id"] for p in offs]
    w = int(round(STILL_WINDOW_S * fps))

    cost = np.full((nf, len(offs) + 1), np.inf)
    detail: list[dict] = []
    for f in range(nf):
        row = {}
        for i, o in enumerate(offs):
            a = _at(o, f)
            if a is None:
                continue
            mark, sep = None, None
            for d in defs:
                b = _at(d, f)
                if b is None:
                    continue
                s = float(np.hypot(*(a - b)))
                if sep is None or s < sep:
                    mark, sep = d, s
            if mark is None or sep > MARKER_MAX_YD:
                continue
            own = _path_length(o, f, w)
            other = _path_length(mark, f, w)
            if own is None or other is None:
                continue
            c = own + other
            if o["state"][f] not in ANCHORED:
                c += UNOBSERVED_PENALTY_YD
            if mark["state"][f] not in ANCHORED:
                c += UNOBSERVED_PENALTY_YD
            cost[f, i] = c
            row[o["id"]] = {"cost": round(c, 2), "mark": mark["id"],
                            "sep_yd": round(sep, 2)}
        cost[f, len(offs)] = NONE_COST_YD
        detail.append(row)
    return ids, cost, detail


def _incoming(prev: np.ndarray, j: int, none: int) -> np.ndarray:
    """Cost of arriving in state `j` from each previous state.

    The constraint is the sport: a disc does not move between two people without
    being thrown. Forbidding a direct hand-over means every change of holder has
    a flight phase between it, which is both true and what makes the output a
    sequence of throws rather than a flicker.
    """
    if j == none:
        # Any holder may release; flight may continue.
        opts = prev + SWITCH_COST_YD
        opts[none] = prev[none]
        return opts
    # A holder may keep holding, or may have just caught it. Nothing else.
    opts = np.full(len(prev), np.inf)
    opts[j] = prev[j]
    opts[none] = prev[none] + SWITCH_COST_YD
    return opts


def _forward(cost: np.ndarray, none: int) -> tuple[np.ndarray, np.ndarray]:
    """`A[f, j]` = cheapest path from frame 0 that is in state j at frame f."""
    nf, n = cost.shape
    A = np.full((nf, n), np.inf)
    back = np.zeros((nf, n), int)
    A[0] = cost[0]
    for f in range(1, nf):
        prev = A[f - 1]
        cur = np.full(n, np.inf)
        for j in range(n):
            opts = _incoming(prev, j, none)
            k = int(np.argmin(opts))
            if np.isfinite(opts[k]) and np.isfinite(cost[f, j]):
                cur[j] = opts[k] + cost[f, j]
                back[f, j] = k
        if not np.isfinite(cur).any():     # nothing playable: stay in flight
            cur = np.full(n, np.inf)
            cur[none] = (np.nanmin(prev[np.isfinite(prev)])
                         if np.isfinite(prev).any() else 0.0) + NONE_COST_YD
            back[f, none] = none
        A[f] = cur
    return A, back


def _backward(cost: np.ndarray, none: int) -> np.ndarray:
    """`B[f, j]` = cheapest completion from state j at frame f to the end."""
    nf, n = cost.shape
    B = np.full((nf, n), np.inf)
    B[nf - 1] = 0.0
    for f in range(nf - 2, -1, -1):
        nxt = cost[f + 1] + B[f + 1]
        for i in range(n):
            # Where can i go? Straight on if it is a holder, into flight always,
            # and out of flight into anybody. Same relation as `_incoming`, read
            # the other way round.
            opts = np.full(n, np.inf)
            opts[none] = nxt[none] + (0.0 if i == none else SWITCH_COST_YD)
            if i == none:
                opts[:none] = nxt[:none] + SWITCH_COST_YD
            else:
                opts[i] = nxt[i]
            B[f, i] = float(np.min(opts))
    return B


def viterbi(cost: np.ndarray, n_holders: int) -> list[int]:
    """Cheapest holder path. See `_incoming` for what a legal transition is."""
    nf, _ = cost.shape
    none = n_holders                      # index of the `none` state
    A, back = _forward(cost, none)
    path = [int(np.argmin(A[nf - 1]))]
    for f in range(nf - 1, 0, -1):
        path.append(int(back[f, path[-1]]))
    return path[::-1]


def margins(cost: np.ndarray, n_holders: int) -> np.ndarray:
    """How much cheaper the winning holder is than the next one, per frame.

    This is the number the active-learning loop in `docs/27` is built on: the
    frames where it is smallest are the frames the solver is least sure about,
    and those are the ones worth a human's two keystrokes. It is a **min-marginal
    margin** - the best whole-possession path forced through each state, not the
    per-frame emission cost - because the question is not "which holder looks
    best here", it is "how much would the whole sequence cost if this frame were
    somebody else". A frame whose emission costs are nearly tied but whose
    neighbours pin it anyway is not an uncertain frame.

    Units are yards, like everything else here, because the emission cost is a
    path length. `inf` where a frame has fewer than two admissible states, which
    is what a human tag makes it.
    """
    none = n_holders
    A, _ = _forward(cost, none)
    B = _backward(cost, none)
    total = A + B
    out = np.full(len(cost), np.inf)
    for f, row in enumerate(total):
        good = np.sort(row[np.isfinite(row)])
        if len(good) >= 2:
            out[f] = good[1] - good[0]
    return out


def _widen_flights(path: list[int], none: int, min_frames: int,
                   tagged: list[int | None]) -> None:
    """Give every holder change a flight long enough to be one.

    Frames a human tagged are never taken: their whole value is that they fix the
    boundary, and a floor derived from a typical throw speed has no business
    overriding somebody who watched it.
    """
    n = len(path)
    f = 0
    while f < n:
        if path[f] != none:
            f += 1
            continue
        a = f
        while f < n and path[f] == none:
            f += 1
        b = f - 1
        need = min_frames - (b - a + 1)
        if need <= 0:
            continue
        lo, hi = a, b
        while need > 0:
            moved = False
            if lo - 1 >= 0 and path[lo - 1] != none and tagged[lo - 1] is None:
                lo -= 1
                path[lo] = none
                need -= 1
                moved = True
            if need > 0 and hi + 1 < n and path[hi + 1] != none                     and tagged[hi + 1] is None:
                hi += 1
                path[hi] = none
                need -= 1
                moved = True
            if not moved:
                break
        f = hi + 1


def from_events(doc: dict, events: dict,
                ids: list[str]) -> tuple[list[int | None], list[bool]]:
    """The holder each frame according to the human tags, where they exist.

    A `throw` by A at t fixes A as the holder up to that frame; a `catch` by B
    fixes B from that frame. Between a throw and the next catch the disc is in
    flight and belongs to nobody. Frames outside any tagged span are left None for
    the inference to fill.

    Returns the holders and, beside them, **which of those frames rest on a name
    nobody read**. A tag may carry `player_inferred`: the moment is a person's
    and so is the reasoning, but the name was arrived at by elimination rather
    than read off a jersey - p0003's 21.27-26.33 s span, whose argument docs/27
    sets out in full. That is a different strength of evidence and it has to
    travel with the holder, because every stage downstream would otherwise read
    a tag as a reading.
    """
    nf = int(doc["possession"]["frames"])
    fps = float(doc["possession"]["fps"])
    idx = {k: i for i, k in enumerate(ids)}
    none = len(ids)
    out: list[int | None] = [None] * nf
    guessed: list[bool] = [False] * nf

    marks = []
    for e in events.get("events", []):
        if e.get("source") != "human" or e.get("type") not in ("throw", "catch",
                                                               "possession_start"):
            continue
        f = int(round(float(e["t"]) * fps))
        if 0 <= f < nf and e.get("player") in idx:
            marks.append((f, e["type"], idx[e["player"]],
                          bool(e.get("player_inferred"))))
    marks.sort()

    for n, (f, kind, who, guess) in enumerate(marks):
        if kind in ("catch", "possession_start"):
            # Held from here until the next throw by this player, or the end.
            release = next(((g, gs) for g, k, w, gs in marks[n + 1:]
                            if k == "throw" and w == who), None)
            end, release_guess = release if release else (nf - 1, False)
            # A span bounded by a catch and a throw is one holder, named twice,
            # and the two names are two statements about the same fact. If
            # either was a guess the span was: a read catch does not become
            # weaker because the release was inferred, but nobody then read the
            # hand the disc left, so the span's identity rests on the weaker of
            # the two. `ur/spans.py` takes the same view at span granularity.
            for g in range(f, min(end, nf - 1) + 1):
                out[g] = who
                guessed[g] = guess or release_guess
        elif kind == "throw":
            # In flight from here to the next catch.
            end = next((g for g, k, _, _ in marks[n + 1:] if k == "catch"), None)
            if end is not None:
                for g in range(f + 1, end):
                    out[g] = none
                    guessed[g] = False
            out[f] = who
            guessed[f] = guessed[f] or guess
    return out, guessed


def build(work: Path, *, verbose: bool = True) -> dict:
    doc = GV.read_for_publishing(work)
    ev_path = work / "events.json"
    events = (json.loads(ev_path.read_text(encoding="utf-8"))
              if ev_path.exists() else {"events": []})

    nf = int(doc["possession"]["frames"])
    fps = float(doc["possession"]["fps"])
    by = {p["id"]: p for p in doc["players"]}

    ids, cost, detail = emission_costs(doc)
    none = len(ids)

    # Human tags are hard constraints: everything else is forced to infinity on a
    # frame a human has spoken for, so the Viterbi path has to go through them and
    # the spans between them are still solved rather than guessed at.
    tagged, guessed_name = from_events(doc, events, ids)
    # **Timing-only tags.** A human who pressed `t` and `c` without naming anybody
    # has given the two facts this module could not get for itself - when the disc
    # is in flight, and for how long - and `ur/spans.py` turns those into an
    # assignment of holders over the spans between them. Its answer is folded in
    # here as if it were a tag, with one difference that matters: the *timing* is
    # a human's and the *identity* is solved, so those frames are `predicted`
    # rather than `confirmed`. See `solved` below.
    solved: list[int | None] = [None] * nf
    if any(e.get("source") == "human" and e.get("type") in ("throw", "catch")
           and not e.get("player") for e in events.get("events", [])):
        from . import spans as SP
        sp = SP.spans_from_events(events, nf, fps, ids)
        if len(sp) >= 2:
            SP.span_costs(doc, sp, ids)
            path, span_margins = SP.solve(doc, sp, ids)
            for seg, who in zip(sp, path):
                for g in range(seg.a, seg.b + 1):
                    if tagged[g] is None:
                        solved[g] = who
            # Between a tagged throw and the next tagged catch nobody holds it.
            for i in range(len(sp) - 1):
                if sp[i].throw_f is None or sp[i + 1].catch_f is None:
                    continue
                for g in range(sp[i].throw_f + 1, sp[i + 1].catch_f):
                    if tagged[g] is None:
                        solved[g] = none
            if verbose:
                thin = min((m for m in span_margins if np.isfinite(m)),
                           default=None)
                print(f"[disc] {len(sp)} held spans from timing-only tags; "
                      f"thinnest margin {thin if thin is None else round(thin, 2)} yd")
    for f, who in enumerate(solved):
        if who is not None and tagged[f] is None:
            tagged[f] = who
    # A tag naming somebody who is not on the offensive roster is dropped by
    # `from_events`, silently, and silence is the wrong answer: it is either a
    # turnover inside the possession (in which case `offense` in clip.json is
    # wrong for part of it) or a mis-click, and both are things to know about
    # before the number that comes out is believed.
    if verbose:
        known = set(ids)
        # `None` is not a stray - it is a timing-only tag, which is the normal
        # case now: the moment is what a person can see and the identity is what
        # `ur/spans.py` is for.
        stray = sorted({e.get("player") for e in events.get("events", [])
                        if e.get("source") == "human"
                        and e.get("type") in ("throw", "catch")
                        and e.get("player") is not None
                        and e.get("player") not in known})
        if stray:
            print(f"[disc] !! {len(stray)} human tag(s) name a player who is not "
                  f"on the offence: {stray}. They are ignored. Either the "
                  f"possession changes hands - in which case `offense` in "
                  f"clip.json is wrong for part of it - or the tag is a mis-click.")
    forced = cost.copy()
    for f, who in enumerate(tagged):
        if who is None:
            continue
        keep = forced[f, who]
        forced[f] = np.inf
        forced[f, who] = 0.0 if not np.isfinite(keep) else min(keep, 0.0)

    path = viterbi(forced, none)
    marg = margins(forced, none)
    _widen_flights(path, none, int(round(MIN_FLIGHT_S * fps)), tagged)

    # Flight spans: a run of `none` between two holders. Its endpoints are the
    # last and first held positions, which is all a flight needs to be drawn.
    samples = []
    for f in range(nf):
        j = path[f]
        human = tagged[f] is not None
        if j != none:
            hid = ids[j]
            p = by[hid]
            xy = p["est"][f]
            st = p["state"][f]
            if xy is None:
                samples.append({"f": f, "xy": None, "z": None, "state": "unknown",
                                "basis": "unknown", "holder": hid,
                                "sigma": 16.0, "source": "inferred",
                                "name_inferred": bool(guessed_name[f])})
                continue
            # The disc is exactly as well located as the player holding it, plus
            # an arm, and no better known than the claim that this is the holder.
            sigma = float(np.hypot(p["sigma"][f], HAND_OFFSET_YD))
            # `confirmed` only when a person named this player AND the slot's
            # own position was seen on this frame. A holder the span solver
            # worked out from a human's *timing* is `predicted` - the moment is
            # observed, the identity is inferred, and collapsing the two would be
            # the same over-claim as calling a mosaic frame observed.
            #
            # The second half of that test is the one that cost something. This
            # used to accept any ANCHORED state, `provisional` included, and on
            # p0003 the tracker lost O2 for 3.1 s, dead-reckoned it, then
            # re-acquired 26.9 yd away on somebody standing over the sideline -
            # a match official, as it turned out. The human tag at 21.27 s was
            # right about WHO caught it and said nothing about where that marker
            # had wandered to, so the disc was drawn on the official at the
            # strongest state the format has. **A tag vouches for the holder, not
            # for the holder's position**, and those are two facts. On a
            # `provisional` frame the disc is now `predicted`, which the viewer
            # declines to draw - it disappears for the stretch instead of
            # asserting a place nothing saw. `source` stays `human`, because a
            # person really did name this holder.
            #
            # The third way a tag can be weaker than it looks, and the one that
            # took longest to see. A tag can carry `player_inferred`: the moment
            # is a person's and so is the reasoning, but the name was settled by
            # elimination rather than read off a jersey. p0003's 21.27-26.33 s
            # span is the case and docs/27 sets out the argument - which rests
            # partly on which slots the TRACKER loses, so it is no stronger
            # evidence than the solver's own. That flag used to stop at span
            # resolution: this stage read the named slot's coordinates, saw they
            # were observed, and emitted `confirmed`, so the Mark card said
            # MEASURED about a holder nobody named. Evidence about WHO and
            # evidence about WHERE are different claims, and the weaker governs -
            # the same rule the paragraph above applies the other way round.
            # `source` stays `human`, because a person really did settle this
            # holder; `name_inferred` is how they settled it. That is why the
            # two are separate variables: `by_name` is who put the name there
            # and drives `source`, `named` is how well they could see it and
            # drives `state`. Collapsing them sent every solver-chosen frame
            # out as `source: "human"`, because the solver's answers are folded
            # into `tagged` above. #15.
            by_name = human and solved[f] is None
            named = by_name and not guessed_name[f]
            state = ("confirmed" if named and st in POSITION_SEEN else
                     "predicted" if st in ANCHORED else "unknown")
            samples.append({"f": f, "xy": [round(v, 3) for v in xy],
                            "z": HELD_HEIGHT_YD,
                            "state": state, "basis": "held", "holder": hid,
                            "sigma": round(sigma, 3),
                            "source": ("human" if by_name else
                                       "solved" if solved[f] is not None
                                       else "inferred"),
                            "name_inferred": bool(guessed_name[f]),
                            "holder_cost": detail[f].get(hid, {}).get("cost"),
                            "mark": detail[f].get(hid, {}).get("mark")})
        else:
            samples.append({"f": f, "xy": None, "z": None, "state": "unknown",
                            "basis": "flight", "holder": None, "sigma": 16.0,
                            "source": "human" if human else "inferred",
                            "name_inferred": False})

    _fill_flight(samples, by, fps, tagged)
    _fill_unknown(samples)
    for s, m in zip(samples, marg):
        s["margin_yd"] = None if not np.isfinite(m) else round(float(m), 3)
    return _write(work, doc, samples, ids, marg, tagged, verbose=verbose)


def ask_next(marg: np.ndarray, tagged: list[int | None], fps: float, *,
             n: int = 5, apart_s: float = 1.5) -> list[dict]:
    """Where a human's next two keystrokes are worth the most.

    `docs/27` step 4: ask where the solver is least sure, not in frame order.
    Frames a human has already spoken for are excluded - their margin is infinite
    by construction - and so is everything within `apart_s` of a moment already
    on the list, because a thin margin is thin over a run of frames and five
    consecutive frames of the same doubt is one question, not five.
    """
    order = [f for f in np.argsort(marg) if np.isfinite(marg[f])
             and tagged[f] is None]
    keep: list[int] = []
    for f in order:
        if all(abs(f - g) > apart_s * fps for g in keep):
            keep.append(int(f))
        if len(keep) >= n:
            break
    return [{"f": f, "t": round(f / fps, 2), "margin_yd": round(float(marg[f]), 3)}
            for f in keep]


def _fill_unknown(samples: list[dict]) -> None:
    """Every frame gets a position, and the ones nobody can vouch for say so.

    `docs/03` requires a sample per frame with no gaps, for the same reason the
    tracker does: a gap is a decision the viewer would have to re-make, and it
    will re-make it worse. So a frame with no holder and no bracketed flight
    carries the last disc position anyone had a reason to believe, at the
    `unknown` sigma - exactly the treatment an unobserved player gets. It is
    carried backwards as well as forwards, because a possession that opens before
    the first inferable holder still has to start somewhere.
    """
    n = len(samples)
    last = None
    for s in samples:
        if s["xy"] is not None:
            last = s["xy"]
        elif last is not None:
            s.update({"xy": list(last), "z": HELD_HEIGHT_YD, "carried": True})
    nxt = None
    for s in reversed(samples):
        if s.get("carried") or s["xy"] is None:
            if s["xy"] is None and nxt is not None:
                s.update({"xy": list(nxt), "z": HELD_HEIGHT_YD, "carried": True})
        else:
            nxt = s["xy"]


def _fill_flight(samples: list[dict], by: dict, fps: float,
                 tagged: list[int | None]) -> None:
    """Straight-line fill between the release and the catch, with an arc on top.

    Exactly the `interpolated` argument `docs/05` makes for players: a gap
    bracketed by two known positions is short and cheap to be right about, so it
    is filled, and the fill is labelled as a fill. A flight nobody bracketed - no
    holder before it or none after - is left `unknown`, because a disc that left a
    hand we did not see and arrived somewhere we did not see is not a path, it is
    two unknowns with a line drawn between them.
    """
    n = len(samples)
    f = 0
    while f < n:
        if samples[f]["basis"] != "flight":
            f += 1
            continue
        a = f
        while f < n and samples[f]["basis"] == "flight":
            f += 1
        b = f - 1
        before = next((k for k in range(a - 1, -1, -1)
                       if samples[k]["basis"] == "held" and samples[k]["xy"]), None)
        after = next((k for k in range(b + 1, n)
                      if samples[k]["basis"] == "held" and samples[k]["xy"]), None)
        if before is None or after is None:
            continue
        p0 = np.asarray(samples[before]["xy"], float)
        p1 = np.asarray(samples[after]["xy"], float)
        span = after - before
        human = any(tagged[k] is not None for k in (before, after))
        for k in range(a, b + 1):
            u = (k - before) / span
            xy = p0 + (p1 - p0) * u
            samples[k].update({
                "xy": [round(float(v), 3) for v in xy],
                "z": round(HELD_HEIGHT_YD + 4.0 * (FLIGHT_PEAK_YD - HELD_HEIGHT_YD)
                           * u * (1 - u), 2),
                "state": "interpolated" if human else "predicted",
                # Half the throw distance: the disc is somewhere on a path between
                # two points and nothing watched it get there, so the honest width
                # is the scale of the throw itself rather than a tidy small number.
                "sigma": round(float(np.hypot(*(p1 - p0))) / 2.0 + 1.0, 3),
            })


def plausibility(samples: list[dict], fps: float) -> dict:
    """See `_plausibility`. Split out so the human-tagged half can be excluded."""
    return _plausibility(samples, fps)


def _plausibility(samples: list[dict], fps: float) -> dict:
    """Does the inferred sequence look like a possession? Measured, not assumed.

    There is no labelled holder anywhere in this project, so the inference cannot
    be scored against truth. It can be scored against **physics and the sport**,
    which is weaker but is not nothing, and on p0001 it is enough to establish
    that the unaided inference does not work:

    - **Throws should not alternate direction.** A possession advances; a sequence
      that gains 27 yd, loses 28, gains 25, loses 21 is not a team moving a disc,
      it is a holder estimate oscillating between two candidates.
    - **Flights should vary.** Every flight sitting exactly on `MIN_FLIGHT_S` means
      the floor is doing all the work and no flight was actually located.
    - **A possession that ends in a goal ends in the endzone.**

    These are reported rather than acted on. Silently suppressing an inference
    that fails them would leave the viewer with nothing and no reason; saying the
    sequence is not trustworthy, in the file, is what lets everything downstream
    decline to use it.
    """
    # **Only inferred throws are judged.** A throw a human tagged is not a
    # hypothesis this module gets to grade - it is the observation everything else
    # is fitted to, and scoring it against a heuristic would let the heuristic
    # overrule the person who watched it. Before this, five tags on p0001 left the
    # module still reporting the possession implausible and still telling the user
    # to "tag the throws and catches", which they had just done.
    runs, cur, start = [], object(), 0
    for s in samples:
        k = (s["holder"], s["basis"])
        if k != cur:
            if start or runs or True:
                runs.append((start, s["f"] - 1, cur))
            cur, start = k, s["f"]
    runs.append((start, len(samples) - 1, cur))
    held = [(a, b, h) for a, b, (h, ba) in runs[1:] if ba == "held"]

    gains, flights = [], []
    prev = None
    for a, b, _ in held:
        if prev is not None and samples[a]["xy"] and prev[1]:
            inferred = (samples[a]["source"] != "human"
                        and samples[prev[0]]["source"] != "human")
            if inferred:
                gains.append(samples[a]["xy"][0] - prev[1][0])
                flights.append((a - prev[0] - 1) / fps)
        prev = (b, samples[b]["xy"])
    alt = (sum(1 for i in range(1, len(gains)) if gains[i] * gains[i - 1] < 0)
           / max(1, len(gains) - 1)) if len(gains) > 1 else 0.0
    floor = (sum(1 for t in flights if abs(t - MIN_FLIGHT_S) < 1e-6)
             / max(1, len(flights))) if flights else 0.0
    return {
        "throws": len(gains),
        "alternating_direction_fraction": round(float(alt), 3),
        "net_gain_yd": round(float(sum(gains)), 1) if gains else None,
        "flights_at_the_minimum_fraction": round(float(floor), 3),
        "median_flight_s": (round(float(np.median(flights)), 3) if flights
                            else None),
        "final_disc_x_yd": samples[-1]["xy"][0] if samples[-1]["xy"] else None,
    }


def _write(work: Path, doc: dict, samples: list[dict], ids: list[str],
           marg: np.ndarray, tagged: list[int | None], *,
           verbose: bool) -> dict:
    fps = float(doc["possession"]["fps"])
    plaus = plausibility(samples, fps)
    # Fewer than two inferred throws means there is nothing to judge, not that the
    # judgement passed - so the inference is not trusted, and a fully tagged
    # possession is unaffected either way because its samples are human-sourced.
    trustworthy = bool(
        plaus["throws"] >= 2
        and plaus["alternating_direction_fraction"] <= 0.5
        and plaus["flights_at_the_minimum_fraction"] <= 0.5)
    if not trustworthy:
        for s in samples:
            if s["source"] != "human" and s["basis"] in ("held", "flight"):
                s["state"] = "unknown"
                s["untrustworthy"] = True
    states = [s["state"] for s in samples]
    bases = [s["basis"] for s in samples]
    held = [s for s in samples if s["basis"] == "held"]
    changes = sum(1 for i in range(1, len(samples))
                  if samples[i]["holder"] != samples[i - 1]["holder"]
                  and samples[i]["holder"] is not None)
    out = {
        "schema": "ultimate-radar/disc@1",
        "possession_id": doc["possession"]["id"],
        "method": {
            "module": "ur.disc",
            "model": "HELD / FLIGHT / LOOSE state machine over the possession "
                     "(docs/25 Part 3). Only FLIGHT would need pixels, and that "
                     "stage is not built.",
            "nothing_has_seen_the_disc": (
                "No disc sample is ever `observed`, because no stage of this "
                "pipeline has detected a disc. `confirmed` means a human said who "
                "was holding it; `predicted` means the geometry says a particular "
                "player is the thrower and the disc is assumed to be in their "
                "hand. A metric built on a `predicted` disc is not a measurement "
                "of the thing it names."),
            "holder_inference": (
                "Viterbi over the possession. Emission cost is the combined path "
                f"length of a candidate and their nearest defender over "
                f"{STILL_WINDOW_S} s, in yards; a change of holder must pass "
                "through flight, because that is what a throw is."),
            "marker_max_yd": MARKER_MAX_YD,
            "marker_rule": "UFA 15.1 - the marker must be within 3 m of the "
                           "thrower. A candidate with no defender that close is "
                           "not being marked and is not the thrower.",
            "still_window_s": STILL_WINDOW_S,
            "none_cost_yd": NONE_COST_YD,
            "switch_cost_yd": SWITCH_COST_YD,
            "unobserved_penalty_yd": UNOBSERVED_PENALTY_YD,
            "hand_offset_yd": HAND_OFFSET_YD,
            "height_note": "z is a shape, not a measurement - it exists so the "
                           "viewer can draw a flight rather than a ground slide.",
            "human_tags_are_hard": "a frame a human has spoken for admits no other "
                                   "holder; the spans between tags are still solved "
                                   "rather than guessed",
            "seed": SEED,
        },
        "diagnostics": {
            "frames": len(samples),
            "position_present": sum(1 for s in samples if s["xy"] is not None),
            "position_fraction": round(sum(1 for s in samples if s["xy"] is not None)
                                       / max(len(samples), 1), 4),
            "states": {k: states.count(k) for k in sorted(set(states))},
            "basis": {k: bases.count(k) for k in sorted(set(bases))},
            "holder_changes": changes,
            "held_frames": len(held),
            "holders": {k: sum(1 for s in held if s["holder"] == k) for k in ids
                        if any(s["holder"] == k for s in held)},
            "human_tagged_frames": sum(1 for s in samples if s["source"] == "human"),
            "plausibility": plaus,
            "inference_trustworthy": trustworthy,
            "plausibility_note": (
                "Scored against physics and the sport, not against labels - there "
                "are no labelled holders anywhere in this project. Throws should "
                "not alternate direction, flights should not all sit on the "
                f"{MIN_FLIGHT_S} s floor, and a possession that scores ends in the "
                "endzone. Failing these does not prove which frames are wrong; it "
                "proves the sequence as a whole is not a possession."),
            "margin_yd_median": (round(float(np.median(marg[np.isfinite(marg)])), 3)
                                 if np.isfinite(marg).any() else None),
            "ask_next": ask_next(marg, tagged, fps),
            "ask_next_note": (
                "Where the solver's own second-best whole-possession path is "
                "closest to its best, excluding frames a human has already "
                "spoken for. docs/27: ask for the next tag where the margin is "
                "thinnest, not in frame order. A margin is not a probability - "
                "`tools/disc_score.py` is what turns it into one, by holding out "
                "tags and measuring how often the solver recovers them."),
        },
        "samples": samples,
    }
    (work / "disc.json").write_text(json.dumps(out, indent=1) + "\n",
                                    encoding="utf-8")
    if verbose:
        d = out["diagnostics"]
        print(f"[disc] {d['frames']} frames, position present "
              f"{d['position_fraction']:.1%}")
        print(f"[disc] basis {d['basis']}")
        print(f"[disc] states {d['states']}")
        print(f"[disc] {d['holder_changes']} holder changes; "
              f"held frames by slot {d['holders']}")
        print(f"[disc] human-tagged frames {d['human_tagged_frames']}")
        p = d["plausibility"]
        print(f"[disc] plausibility: {p['throws']} throws, "
              f"{p['alternating_direction_fraction']:.0%} alternate direction, "
              f"net gain {p['net_gain_yd']} yd, "
              f"{p['flights_at_the_minimum_fraction']:.0%} of flights at the floor")
        tagged = d["human_tagged_frames"]
        if not d["inference_trustworthy"] and tagged >= d["frames"]:
            pass                      # nothing was inferred; nothing to warn about
        elif not d["inference_trustworthy"]:
            print(f"[disc] !! the {d['frames'] - tagged} frames NOT covered by a "
                  "human tag are inferred, and that inference is not a plausible "
                  "possession. They are emitted as `unknown`. Tag the throws and "
                  "catches either side of them and re-run.")
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="ur.disc")
    p.add_argument("work")
    a = p.parse_args(argv)
    build(Path(a.work))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
