"""Which end a team attacks, held once per (quarter, team). AD-10.

**AD-10 IS WITHDRAWN (2026-09-16), AND THIS MODULE STILL IMPLEMENTS IT.** Ends
change every point: after a goal the scoring team pulls from the end it just
scored in, so it now defends the end it was attacking. A quarter-wide direction
is therefore wrong about the sport, and the same-sign drift in `docs/30`
section 2.0 that appeared to contradict the old per-possession model was never a
contradiction at all - two possessions in consecutive points drift the same way,
legitimately. **So the finding this module was built on measured nothing.**

What survives: the storage shape, and the three provenance words. An observation
is written where it was made and the fact is resolved at read time; `confirmed`,
`derived` and `declared` mean what they say below. What does not survive is the
key. Issue #5 re-keys this to `(point, team)`, seeded from goal-line crossings
in the review sitting (#19), with every further score a *check* rather than a
new input.

Until that lands: do not add confirmations through this module, and do not read
a passing `Qn: opposite teams disagree` as evidence that a direction is known.
Nothing is confirmed today, which is the only reason those checks are green.

    python -m ur.direction                        # what is known, across work/
    python -m ur.direction confirm work/p0003 --direction=+x
    python -m ur.direction confirm work/p0009 --direction=-x --team chill
    python -m ur.direction clear work/p0003

Write `--direction=-x` with the equals sign. Without it argparse reads `-x` as a
flag of its own and refuses, which is a wart of the value starting with a dash
rather than anything meaningful.

`ur.possess` used to answer this by fitting the drift of the offence along x, and
on 2026-09-15 that was measured not to be the attacking direction: in three of
the four quarters cut, **both** teams' offences drift the same way, which no
arrangement of the sport allows (`docs/30` section 2.0). So the machine cannot
supply this and a human does - the viewer's overhead has a toggle, and `confirm`
above is the same statement from a shell.

Three things follow from AD-10 and they are the whole design:

**The observation is written where it was made; the fact is never written.** A
person confirms a direction while watching one possession, so it lands in that
possession's `events.json`, which is the file for human statements about the
game. What a `(quarter, team)` attacks is *resolved* from every observation at
read time. Nothing is stored twice, so nothing can disagree with its own copy.

**One confirmation settles a quarter.** The other team attacks the other end, and
every possession in the quarter follows - including ones not yet cut. That is
four answers instead of ten.

**A derived direction is never confirmed.** `resolve` marks it `derived` and says
which possession it came from. Writing it back as an observation would be the
brief's second trap - a solver's own output returning as its own constraint - and
it would also destroy the only check there is, which is that two independent
confirmations in one quarter must disagree about the end.

A contradiction is not resolved here by preferring one observation. It is
reported, and the key it contaminates is left **unknown**, because a coin toss
between two people who watched the same footage is not a fact. `tools.gates`
fails on it; a human settles it by watching again.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable

DIRECTIONS = ("+x", "-x")


def opposite(d: str) -> str:
    if d not in DIRECTIONS:
        raise ValueError(f"direction must be one of {DIRECTIONS}, got {d!r}")
    return "-x" if d == "+x" else "+x"


# --------------------------------------------------------------------------- #
# reading the observation
# --------------------------------------------------------------------------- #

def read_observation(clip: dict, events: dict) -> dict | None:
    """The human's statement about one possession, or None if nobody has said.

    Two shapes are accepted under `events.json:observed`:

        "attacking_direction": "+x"
        "attacking_direction": {"team": "chill", "direction": "-x"}

    The object form is canonical because it names *whose* direction it is, and
    that is what survives a turnover: `clip.json:offense` is one value for the
    whole possession, so after a turnover it is wrong, and an observation that
    inherited its team from it would be wrong with it. The bare string is the
    form #5 was written in and means the team `clip.json` has on offence.
    """
    raw = (events.get("observed") or {}).get("attacking_direction")
    if raw is None:
        return None
    if isinstance(raw, str):
        raw = {"team": clip["offense"], "direction": raw}
    if not isinstance(raw, dict):
        raise ValueError("observed.attacking_direction must be a string or an "
                         f"object, got {type(raw).__name__}")

    d = raw.get("direction")
    if d not in DIRECTIONS:
        raise ValueError("observed.attacking_direction.direction must be one of "
                         f"{DIRECTIONS}, got {d!r}")
    teams = sorted(clip["teams"])
    team = raw.get("team", clip["offense"])
    if team not in teams:
        raise ValueError(f"observed.attacking_direction.team {team!r} is not "
                         f"playing in this possession ({teams})")
    q = clip.get("quarter")
    if q is None:
        raise ValueError(
            f"{clip.get('possession_id')} has a confirmed direction but no "
            "quarter, and direction is a property of a quarter (AD-10). Read the "
            "quarter off the broadcast score bug and put it in clip.json.")
    return {"possession": clip.get("possession_id"), "quarter": int(q),
            "team": team, "direction": d, "teams": teams,
            "note": raw.get("note", "")}


def observations(works: Iterable[Path]) -> list[dict]:
    """Every confirmation across a set of working directories, in id order."""
    out = []
    for w in sorted(works, key=lambda p: p.name):
        cp, ep = w / "clip.json", w / "events.json"
        if not (cp.exists() and ep.exists()):
            continue
        clip = json.loads(cp.read_text(encoding="utf-8"))
        ev = json.loads(ep.read_text(encoding="utf-8"))
        o = read_observation(clip, ev)
        if o is not None:
            out.append(o)
    return out


# --------------------------------------------------------------------------- #
# resolving the fact
# --------------------------------------------------------------------------- #

def resolve(obs: list[dict]) -> tuple[dict[tuple[int, str], dict], list[dict]]:
    """`(quarter, team) -> direction`, plus every contradiction found.

    A key that any contradiction touches is left out of the table entirely, and
    so is everything derived from it. Silence is the honest answer there: the
    viewer goes back to saying `unverified`, which is what it says today.
    """
    table: dict[tuple[int, str], dict] = {}
    conflicts: list[dict] = []

    # 1. A team told two different things about one quarter contradicts itself.
    said: dict[tuple[int, str], dict[str, list[str]]] = {}
    teams_in: dict[int, set[str]] = {}
    for o in obs:
        said.setdefault((o["quarter"], o["team"]), {}) \
            .setdefault(o["direction"], []).append(o["possession"])
        teams_in.setdefault(o["quarter"], set()).update(o["teams"])

    for (q, team), by_dir in sorted(said.items()):
        if len(by_dir) > 1:
            detail = "; ".join(f"{d} in {', '.join(sorted(p))}"
                               for d, p in sorted(by_dir.items()))
            conflicts.append({
                "quarter": q, "kind": "one team, two directions",
                "detail": f"Q{q} {team} is confirmed both ways - {detail}"})
            continue
        d, pids = next(iter(by_dir.items()))
        table[(q, team)] = {"quarter": q, "team": team, "direction": d,
                            "source": "confirmed", "from": sorted(pids)}

    # 2. Two teams cannot attack the same end at the same time. This is the one
    #    statement about the sport that needs no rule about switching ends or who
    #    receives the pull, and it is the only independent check a confirmation
    #    can be put to - so it survives the move off the drift, it just consumes
    #    confirmations now instead of a measurement that was never direction.
    for q in sorted(teams_in):
        here = {t: table[(q, t)] for t in sorted(teams_in[q]) if (q, t) in table}
        clash = [(a, b) for a in sorted(here) for b in sorted(here)
                 if a < b and here[a]["direction"] == here[b]["direction"]]
        for a, b in clash:
            conflicts.append({
                "quarter": q, "kind": "both teams, one end",
                "detail": f"Q{q}: {a} ({', '.join(here[a]['from'])}) and "
                          f"{b} ({', '.join(here[b]['from'])}) are both confirmed "
                          f"{here[a]['direction']} - two teams cannot attack the "
                          "same endzone at the same time"})
        for t in {t for pair in clash for t in pair}:
            table.pop((q, t), None)

    # 3. Derive the other end for whoever has no confirmation of their own.
    #    Never written back, never called confirmed: `source` says where it came
    #    from and `from` names the possession somebody actually watched.
    for q in sorted(teams_in):
        confirmed = {t: table[(q, t)] for t in sorted(teams_in[q])
                     if (q, t) in table and table[(q, t)]["source"] == "confirmed"}
        if not confirmed:
            continue
        src = confirmed[sorted(confirmed)[0]]
        for t in sorted(teams_in[q]):
            if (q, t) in table:
                continue
            table[(q, t)] = {"quarter": q, "team": t,
                             "direction": opposite(src["direction"]),
                             "source": "derived", "from": list(src["from"]),
                             "why": f"{src['team']} is confirmed "
                                    f"{src['direction']} in Q{q}, and the two "
                                    "teams attack opposite ends"}
    return table, conflicts


def describe(e: dict) -> str:
    """`sol +x (confirmed p0003)` / `chill -x (derived from p0003)`.

    One formatter, because the source must never be left off. A derived
    direction that reads like a confirmed one is the trap AD-10 names, and the
    surest way to print it is to let five call sites each compose their own.
    """
    via = "derived from " if e["source"] == "derived" else "confirmed "
    return f"{e['team']} {e['direction']} ({via}{', '.join(e['from'])})"


def for_possession(table: dict, quarter, team: str) -> dict | None:
    """What a possession's attacking direction is, or None if nobody knows."""
    if quarter is None:
        return None
    return table.get((int(quarter), team))


def resolve_work(root: Path = Path("work")) -> tuple[dict, list[dict]]:
    """Resolve over every possession under `root`. The usual entry point."""
    works = [d for d in root.iterdir() if d.is_dir() and (d / "clip.json").exists()]
    return resolve(observations(works))


# --------------------------------------------------------------------------- #
# writing one
# --------------------------------------------------------------------------- #

def write_observation(work: Path, direction: str, team: str | None = None,
                      note: str = "") -> dict:
    """Record a human's confirmation in this possession's events.json."""
    from ur import events as EV

    if direction not in DIRECTIONS:
        raise ValueError(f"direction must be one of {DIRECTIONS}, got {direction!r}")
    clip = json.loads((work / "clip.json").read_text(encoding="utf-8"))
    team = team or clip["offense"]
    doc = EV.load(work)
    doc.setdefault("observed", {})["attacking_direction"] = {
        "team": team, "direction": direction, "source": "human",
        **({"note": note} if note else {})}
    EV.save(work, doc)
    return read_observation(clip, doc)


def clear_observation(work: Path) -> bool:
    """Remove this possession's confirmation. Returns whether there was one."""
    from ur import events as EV

    doc = EV.load(work)
    gone = (doc.get("observed") or {}).pop("attacking_direction", None) is not None
    if not doc.get("observed"):
        doc.pop("observed", None)
    EV.save(work, doc)
    return gone


# --------------------------------------------------------------------------- #

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="ur.direction",
        description="Which end a team attacks, held once per (quarter, team).")
    p.add_argument("--work-root", default="work")
    sub = p.add_subparsers(dest="cmd")
    c = sub.add_parser("confirm")
    c.add_argument("work")
    # `--direction=-x`, with the equals: a bare `-x` parses as a flag.
    c.add_argument("--direction", required=True, choices=list(DIRECTIONS),
                   metavar="=+x|=-x")
    c.add_argument("--team", default=None, help="defaults to clip.json:offense")
    c.add_argument("--note", default="")
    z = sub.add_parser("clear")
    z.add_argument("work")
    a = p.parse_args(argv)

    if a.cmd == "confirm":
        o = write_observation(Path(a.work), a.direction, a.team, a.note)
        print(f"[direction] {a.work}: Q{o['quarter']} {o['team']} attacks "
              f"{o['direction']} - written to events.json")
    elif a.cmd == "clear":
        print(f"[direction] {a.work}: "
              + ("confirmation removed" if clear_observation(Path(a.work))
                 else "nothing was confirmed here"))

    table, conflicts = resolve_work(Path(a.work_root))
    if not table and not conflicts:
        print("[direction] nothing confirmed anywhere. Confirm one possession per "
              "quarter in the viewer, or with `confirm` above.")
    for (q, team) in sorted(table):
        print(f"  Q{q} {describe(table[(q, team)])}")
    for c_ in conflicts:
        print(f"  !! {c_['detail']}")
    return 1 if conflicts else 0


if __name__ == "__main__":
    raise SystemExit(main())
