"""M5 — events, tagged by hand. AD-7.

    python -m ur.events work/p0001 list
    python -m ur.events work/p0001 suggest
    python -m ur.events work/p0001 add --t 4.2 --type throw --player O1 --target O4

AD-7 decides this: **events are tagged by hand and disc detection is a stretch
goal.** So this module is mostly a well-shaped place to put a human's knowledge,
not an inference engine, and that is deliberate rather than unfinished.

`suggest` emits only what the tracks can actually support, which is very little
without the disc:

- `possession_start` at the first frame anything was observed.

It does **not** guess throws and catches from player motion. A throw is an event
about the disc, and nothing in this pipeline has seen the disc; a "suggested
throw" derived from two players changing direction would be a plausible-looking
invention, and `docs/05` is built around not making those. Every suggestion
carries `source: "suggested"` so the viewer can show it differently until a human
confirms it, exactly as `docs/03-data-contracts.md` specifies.

The real tagging surface is the viewer (M6), where a human watches and presses a
key. This CLI is the same vocabulary, usable now and scriptable.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ur import grading as GV
TYPES = ("possession_start", "throw", "catch", "drop", "block", "turnover",
         "stall", "goal")


def empty(possession_id: str) -> dict:
    return {"schema": "ultimate-radar/events@1",
            "possession_id": possession_id,
            "note": "source is 'human' or 'suggested'. A suggested event is shown "
                    "differently in the viewer until a human confirms it (docs/03).",
            "events": []}


def load(work: Path) -> dict:
    p = work / "events.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    clip = json.loads((work / "clip.json").read_text(encoding="utf-8"))
    return empty(clip["possession_id"])


def save(work: Path, doc: dict) -> None:
    doc["events"].sort(key=lambda e: (e["t"], e["type"]))
    (work / "events.json").write_text(json.dumps(doc, indent=1) + chr(10),
                                      encoding="utf-8")


def suggest(work: Path) -> list[dict]:
    poss = GV.read_for_publishing(work)
    fps = float(poss["possession"]["fps"])
    cov = poss["derived"]["coverage"]
    first = next((f for f, c in enumerate(cov) if c > 0), None)
    if first is None:
        return []
    return [{"t": round(first / fps, 3), "type": "possession_start",
             "player": None, "source": "suggested",
             "note": f"first frame with any observation (f{first}). The player "
                     "holding the disc is not inferable - nothing here has seen "
                     "the disc (AD-7)."}]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="ur.events")
    p.add_argument("work")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    sub.add_parser("suggest")
    a = sub.add_parser("add")
    a.add_argument("--t", type=float, required=True)
    a.add_argument("--type", required=True, choices=TYPES)
    a.add_argument("--player", default=None)
    a.add_argument("--target", default=None)
    a.add_argument("--note", default=None)
    ns = p.parse_args(argv)

    work = Path(ns.work)
    doc = load(work)

    if ns.cmd == "list":
        if not doc["events"]:
            print("[events] none tagged yet")
        for e in doc["events"]:
            extra = f" -> {e['target']}" if e.get("target") else ""
            print(f"  {e['t']:>7.2f}s  {e['type']:<17} {e.get('player') or '-':>4}"
                  f"{extra}   [{e['source']}]")
        return 0

    if ns.cmd == "suggest":
        have = {(e["t"], e["type"]) for e in doc["events"]}
        new = [e for e in suggest(work) if (e["t"], e["type"]) not in have]
        doc["events"].extend(new)
        save(work, doc)
        print(f"[events] {len(new)} suggestion(s) added, "
              f"{len(doc['events'])} total")
        for e in new:
            print(f"    {e['t']:>7.2f}s  {e['type']}  [suggested]")
        print("[events] throws and catches are not suggested: nothing here has "
              "seen the disc (AD-7). Tag them by hand.")
        return 0

    ev = {"t": round(ns.t, 3), "type": ns.type, "player": ns.player,
          "source": "human"}
    if ns.target:
        ev["target"] = ns.target
    if ns.note:
        ev["note"] = ns.note
    doc["events"].append(ev)
    save(work, doc)
    print(f"[events] added {ns.type} at {ns.t:.2f}s; {len(doc['events'])} total")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
