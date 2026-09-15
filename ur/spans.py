"""Who threw to whom, when a human has tagged only *when*.

    python -m ur.spans work/p0001

## The observation this is built on

Tagging was specified as a player and a moment — AD-7's "select a player, press
`t` on the release and `c` on the catch". In use the two halves are nowhere near
equally hard. **The moment is easy to see and the player is not**: identifying a
jersey at this range on a broadcast angle is the same problem M5's OCR failed at,
reading 7 % of crops, and a human scrubbing frame by frame is not much better
placed.

So take the moment alone and ask what it buys. It is most of it, because it turns
the two things `ur/disc.py` was guessing into facts:

- **When the disc is in flight.** `MIN_FLIGHT_S` exists because the unaided
  solver, forced to pass through flight to change holder, spent the minimum
  possible time there — "an assumption wearing a number", as `docs/27` puts it.
  A tagged pair of moments replaces it outright.
- **How long the flight lasted.** Which, with the two positions, is a *speed* —
  and a disc has a speed range. That constraint did not exist before because
  neither endpoint was known.

## What is left, and why it is a much smaller problem

With the flights fixed, the possession is a sequence of **held spans** separated
by flights, and the only unknown is which offensive slot holds each span. That is
an assignment over spans rather than a path over frames — eleven or so decisions
instead of five hundred — and three things constrain it:

1. **The chain.** The receiver of one throw is the thrower of the next. Not a
   preference; it is what a possession *is*. It couples every span to its
   neighbours, so a span the geometry is sure about pins the ones either side.
2. **A disc has a speed.** The thrower's position at the release and the
   receiver's at the catch, over the tagged flight time, must be a speed a disc
   can fly. `FLIGHT_SPEED_YD_S` is a range from the sport, not a tuned window,
   and it rules out most pairs on a long throw.
3. **Nobody throws to themselves.** A held span and the next one are different
   players.

The emission cost is the one `ur/disc.py` already uses and already justifies —
the combined path length of a candidate and their nearest defender, in yards,
over a window where a thrower and their mark are both nearly still. What changes
is that it is now averaged over a span whose boundaries are known, instead of
being asked to find the boundaries too.

## What it does not do

It does not make the identities certain, and it reports how uncertain they are:
`margin_yd` per span is the cost of the best alternative assignment for that span
against the chosen one. Where that is thin, the honest move is to ask — and the
question is now "who caught the one at 12.4 s", one span at a time, which is a far
cheaper thing to ask a person than a jersey number.

A human tag that *does* name a player is a hard constraint and overrides all of
this, which is the point of leaving it available.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .disc import ANCHORED, MARKER_MAX_YD, STILL_WINDOW_S, _at, _path_length

# A disc in flight. The slow end is a dump at walking pace, the fast end is a
# full-power huck; UFA throws sit inside this and nothing physical does not.
# It is a range from the sport, used to rule pairs out, not a fitted window.
FLIGHT_SPEED_YD_S = (2.0, 40.0)

# What breaking the speed range costs, per yard per second outside it. Large
# enough that a physically impossible pair loses to any possible one, which is
# the only property it needs.
SPEED_PENALTY_PER_YD_S = 25.0

# Throwing to yourself is not a throw. Forbidden rather than penalised.
SELF_PASS_COST = float("inf")

# What a span costs when a candidate has no admissible emission on it at all -
# never seen, or never marked. Not zero, which is what the first version used and
# which made *impossible* alternatives free and produced negative margins. A
# margin is how much worse the possession gets if this span were somebody else,
# so it cannot be below zero, and one that is says the cost model is broken.
NO_EMISSION_COST_YD = 40.0


@dataclass
class Span:
    """One stretch where a single, unknown player holds the disc."""

    a: int                      # first frame held
    b: int                      # last frame held
    throw_f: int | None = None  # the release that ends it, if tagged
    catch_f: int | None = None  # the catch that starts it, if tagged
    fixed: int | None = None    # slot index, when a human named one
    cost: np.ndarray = field(default_factory=lambda: np.zeros(0))


def spans_from_events(events: dict, nf: int, fps: float,
                      ids: list[str]) -> list[Span]:
    """Turn tagged moments into held spans, whether or not they name a player.

    A `throw` ends a span and a `catch` starts one. Everything between a throw
    and the next catch is flight and belongs to nobody.
    """
    idx = {k: i for i, k in enumerate(ids)}
    marks = []
    for e in events.get("events", []):
        if e.get("source") != "human" or e.get("type") not in ("throw", "catch"):
            continue
        f = int(round(float(e["t"]) * fps))
        if 0 <= f < nf:
            marks.append((f, e["type"], idx.get(e.get("player"))))
    marks.sort()
    if not marks:
        return []

    spans: list[Span] = []
    cur = Span(a=0, b=nf - 1)
    for f, kind, who in marks:
        if kind == "throw":
            cur.b = f
            cur.throw_f = f
            if who is not None:
                cur.fixed = who
            spans.append(cur)
            cur = Span(a=f + 1, b=nf - 1)      # flight, closed by the next catch
            cur.a = None                        # marks this as the flight gap
        else:                                   # catch
            cur = Span(a=f, b=nf - 1, catch_f=f)
            if who is not None:
                cur.fixed = who
    if cur.a is not None:
        spans.append(cur)
    # Close each span at the next one's start.
    for i in range(len(spans) - 1):
        if spans[i].throw_f is None:
            spans[i].b = min(spans[i].b, spans[i + 1].a - 1)
    return [s for s in spans if s.a is not None and s.b >= s.a]


def span_costs(doc: dict, spans: list[Span], ids: list[str]) -> None:
    """Average emission cost per candidate over each span, in yards.

    The same quantity `ur/disc.py` uses and defends - a thrower plants a pivot
    and UFA 15.1 keeps their mark within 3 m, so the pair's combined path length
    over a second is small while every other pair on the field is running. The
    difference here is that it is averaged over a span whose ends are known.
    """
    fps = float(doc["possession"]["fps"])
    off = doc["possession"]["offense"]
    offs = [p for p in doc["players"] if p["team"] == off]
    defs = [p for p in doc["players"] if p["team"] != off]
    w = int(round(STILL_WINDOW_S * fps))

    for s in spans:
        cost = np.full(len(offs), np.inf)
        frames = list(range(s.a, s.b + 1))
        probe = frames[:: max(1, len(frames) // 12)] or frames
        for i, o in enumerate(offs):
            vals = []
            for f in probe:
                a = _at(o, f)
                if a is None:
                    continue
                sep, mark = None, None
                for d in defs:
                    b = _at(d, f)
                    if b is None:
                        continue
                    v = float(np.hypot(*(a - b)))
                    if sep is None or v < sep:
                        sep, mark = v, d
                if mark is None or sep > MARKER_MAX_YD:
                    continue
                own = _path_length(o, f, w)
                other = _path_length(mark, f, w)
                if own is None or other is None:
                    continue
                c = own + other
                if o["state"][f] not in ANCHORED:
                    c += 4.0
                vals.append(c)
            if vals:
                cost[i] = float(np.mean(vals))
        s.cost = cost


def _flight_penalty(doc: dict, prev: Span, nxt: Span, a: int, b: int) -> float:
    """Could a disc have got from player `a` to player `b` in the tagged time?

    This constraint only exists because the timing was tagged. Without it the
    flight duration is `MIN_FLIGHT_S`, a stand-in, and no speed can be computed
    at all.
    """
    fps = float(doc["possession"]["fps"])
    off = doc["possession"]["offense"]
    offs = [p for p in doc["players"] if p["team"] == off]
    t0 = prev.throw_f
    t1 = nxt.catch_f
    if t0 is None or t1 is None or t1 <= t0:
        return 0.0
    pa, pb = _at(offs[a], t0), _at(offs[b], t1)
    if pa is None or pb is None:
        return 0.0
    dt = (t1 - t0) / fps
    speed = float(np.hypot(*(pb - pa))) / max(dt, 1e-6)
    lo, hi = FLIGHT_SPEED_YD_S
    if speed < lo:
        return (lo - speed) * SPEED_PENALTY_PER_YD_S
    if speed > hi:
        return (speed - hi) * SPEED_PENALTY_PER_YD_S
    return 0.0


def _first(s: Span, n: int) -> np.ndarray:
    """Starting costs for the first span, with no candidate ever made free."""
    cost = np.where(np.isfinite(s.cost), s.cost, NO_EMISSION_COST_YD)
    if s.fixed is None:
        return cost.astype(float)
    out = np.full(n, np.inf)
    out[s.fixed] = float(cost[s.fixed])
    return out


def solve(doc: dict, spans: list[Span], ids: list[str]
          ) -> tuple[list[int], list[float]]:
    """Cheapest assignment of a slot to every span, with the margin for each.

    A Viterbi again, but over spans rather than frames, so the transition is
    where the sport lives: you cannot throw to yourself, and the flight has to
    have been possible.
    """
    n = len(ids)
    best = _first(spans[0], n)
    back = [np.zeros(n, int)]
    for k in range(1, len(spans)):
        prev, cur = spans[k - 1], spans[k]
        nxt = np.full(n, np.inf)
        bk = np.zeros(n, int)
        for j in range(n):
            if cur.fixed is not None and j != cur.fixed:
                continue
            opts = np.full(n, np.inf)
            for i in range(n):
                if i == j or not np.isfinite(best[i]):
                    continue                                   # no self-pass
                opts[i] = best[i] + _flight_penalty(doc, prev, cur, i, j)
            m = int(np.argmin(opts))
            e = (cur.cost[j] if np.isfinite(cur.cost[j])
                 else NO_EMISSION_COST_YD)
            if np.isfinite(opts[m]):
                nxt[j] = opts[m] + e
                bk[j] = m
        best, _ = nxt, back.append(bk)
    path = [int(np.argmin(best))]
    for k in range(len(spans) - 1, 0, -1):
        path.append(int(back[k][path[-1]]))
    path = path[::-1]

    # The margin: how much worse the possession gets if this one span is
    # somebody else and everything else adapts. Re-solved per span rather than
    # read off the emission, because the chain is what makes a span certain and
    # an emission difference alone would not see that.
    margins = []
    total = float(np.min(best))
    for k, sp in enumerate(spans):
        if sp.fixed is not None:
            margins.append(float("inf"))
            continue
        alt = float("inf")
        for j in range(n):
            if j == path[k]:
                continue
            forced = [Span(a=x.a, b=x.b, throw_f=x.throw_f, catch_f=x.catch_f,
                           fixed=(j if i == k else x.fixed), cost=x.cost)
                      for i, x in enumerate(spans)]
            try:
                _, sub = _solve_total(doc, forced, ids)
            except ValueError:
                continue
            alt = min(alt, sub)
        margins.append(alt - total if np.isfinite(alt) else float("inf"))
    return path, margins


def _solve_total(doc: dict, spans: list[Span], ids: list[str]
                 ) -> tuple[list[int], float]:
    n = len(ids)
    best = _first(spans[0], n)
    for k in range(1, len(spans)):
        prev, cur = spans[k - 1], spans[k]
        nxt = np.full(n, np.inf)
        for j in range(n):
            if cur.fixed is not None and j != cur.fixed:
                continue
            opts = [best[i] + _flight_penalty(doc, prev, cur, i, j)
                    for i in range(n) if i != j and np.isfinite(best[i])]
            if not opts:
                continue
            e = (cur.cost[j] if np.isfinite(cur.cost[j])
                 else NO_EMISSION_COST_YD)
            nxt[j] = min(opts) + e
        best = nxt
    if not np.isfinite(best).any():
        raise ValueError("no admissible assignment")
    return [], float(np.min(best))


def build(work: Path, *, events_path: Path | None = None,
          verbose: bool = True) -> dict:
    doc = json.loads((work / "possession.json").read_text(encoding="utf-8"))
    ev_path = events_path or (work / "events.json")
    events = (json.loads(ev_path.read_text(encoding="utf-8"))
              if ev_path.exists() else {"events": []})
    nf = int(doc["possession"]["frames"])
    fps = float(doc["possession"]["fps"])
    off = doc["possession"]["offense"]
    ids = [p["id"] for p in doc["players"] if p["team"] == off]

    spans = spans_from_events(events, nf, fps, ids)
    out = {
        "schema": "ultimate-radar/spans@1",
        "possession_id": doc["possession"]["id"],
        "method": {
            "module": "ur.spans",
            "what_the_human_gave": "moments, and a player only where they were "
                                   "sure. The moment is the half a person can "
                                   "see; the player is the half the tracking "
                                   "might be able to work out.",
            "constraints": [
                "the receiver of one throw is the thrower of the next",
                "nobody throws to themselves",
                f"a disc flies between {FLIGHT_SPEED_YD_S[0]} and "
                f"{FLIGHT_SPEED_YD_S[1]} yd/s, which is only checkable because "
                "the flight time was tagged",
            ],
            "emission": "combined path length of a candidate and their nearest "
                        "defender over the span, in yards (ur/disc.py)",
        },
    }
    if len(spans) < 2:
        out["verdict"] = (f"{len(spans)} held span(s) from the tags - nothing to "
                          "assign. Tag at least one throw and its catch.")
        if verbose:
            print(f"[spans] {out['verdict']}")
        return _write(work, out, verbose=verbose)

    span_costs(doc, spans, ids)
    path, margins = solve(doc, spans, ids)
    out["spans"] = [
        {"from_f": s.a, "to_f": s.b,
         "from_t": round(s.a / fps, 2), "to_t": round(s.b / fps, 2),
         "holder": ids[p], "fixed_by_human": s.fixed is not None,
         "margin_yd": (None if not np.isfinite(m) else round(float(m), 2)),
         "emission_yd": (None if not np.isfinite(s.cost[p])
                         else round(float(s.cost[p]), 2))}
        for s, p, m in zip(spans, path, margins)]
    out["throws"] = [
        {"t": round(spans[i].throw_f / fps, 2),
         "from": ids[path[i]], "to": ids[path[i + 1]],
         "flight_s": round((spans[i + 1].catch_f - spans[i].throw_f) / fps, 2)
         if spans[i].throw_f is not None and spans[i + 1].catch_f is not None
         else None,
         "least_sure_of": ("thrower" if (margins[i] < margins[i + 1]) else "receiver"),
         "margin_yd": (None if not np.isfinite(min(margins[i], margins[i + 1]))
                       else round(float(min(margins[i], margins[i + 1])), 2))}
        for i in range(len(spans) - 1) if spans[i].throw_f is not None]
    thin = sorted((s for s in out["spans"] if s["margin_yd"] is not None),
                  key=lambda s: s["margin_yd"])[:3]
    out["ask_next"] = [
        {"t": s["from_t"], "holder_guessed": s["holder"], "margin_yd": s["margin_yd"],
         "question": f"who has the disc at {s['from_t']:.1f} s?"}
        for s in thin]
    if verbose:
        print(f"[spans] {len(spans)} held spans from {len(events.get('events', []))} "
              f"tagged event(s)")
        for s in out["spans"]:
            fix = " (human)" if s["fixed_by_human"] else ""
            print(f"  {s['from_t']:6.2f}-{s['to_t']:6.2f}s  {s['holder']}{fix}"
                  f"   margin {s['margin_yd']}")
        for t in out["throws"]:
            print(f"  throw at {t['t']:6.2f}s  {t['from']} -> {t['to']}  "
                  f"flight {t['flight_s']}s  margin {t['margin_yd']} yd")
    return _write(work, out, verbose=verbose)


def _write(work: Path, out: dict, *, verbose: bool) -> dict:
    (work / "spans.json").write_text(json.dumps(out, indent=1) + "\n",
                                     encoding="utf-8")
    if verbose:
        print(f"[spans] -> {work / 'spans.json'}")
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="ur.spans")
    p.add_argument("work")
    p.add_argument("--events", default=None,
                   help="read tags from here instead of <work>/events.json")
    a = p.parse_args(argv)
    build(Path(a.work), events_path=Path(a.events) if a.events else None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
