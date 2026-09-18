"""What a published page *says*, reduced to a hash, and the diff when two differ.

`site is current` used to count things: how many events the page carries, how
many frames, and which way the resolved direction points. The outside audit on
2026-09-16 changed one event's time by a second and one event's player in an
in-memory copy of a published `possession.js`, and all eight site checks still
passed. Counting is blind to a value: the same number of events, each of them
different, is the same count.

So the check compares content instead. `tools.make_view.compose` builds the page
document a rebuild would emit right now, this module reduces both it and the
published copy to a digest, and `site is current` fails when they disagree.

## Why a digest rather than a diff

A possession document is a few megabytes of position arrays. Comparing them
directly is fine in Python and useless in a gate row, which has one line to say
what is wrong. So the document is split into named **parts**, each hashed on its
own: a failure says `events differ` rather than `something differs`, and only the
part that failed is walked to name the field.

## What is excluded, and why exactly one thing is

`video_src` alone. It is the relative path from the page to its clip, so
`viewer/live-data.js` says `../work/p0003/clip.mp4` and `docs/p0003/possession.js`
says `clip.mp4` for the same possession. Including it would make every published
page permanently stale against a viewer build.

Everything else is in, including the position arrays. The temptation is to hash
only the events and the resolved claims - that is what the ticket asks for - but
a pipeline re-run that moves every player and no event is exactly the staleness
this row exists to catch, and a check that would not see it has the same hole in
a smaller place.
"""

from __future__ import annotations

import hashlib
import json

# The page as a reader's browser holds it, split into the things that can go
# stale independently. `rest` is not a catch-all for convenience: it is there so
# that a field added to the document tomorrow is covered by this check the day it
# lands, rather than the day somebody remembers to name it here.
PARTS = ("possession", "players", "disc_meta", "events", "observed",
         "gates", "identity_readings", "rest")

# The path from the page to its clip, which is a fact about where the page was
# written and not about what it says. See the module note.
EXCLUDED = ("video_src",)


def _canon(value) -> bytes:
    """One byte string per value, stable across runs and machines.

    `sort_keys` because dict order is an artefact of how the document was built
    and two builds may legitimately disagree about it. `default=str` so an
    unexpected type is hashed rather than raising - a digest that crashes on a
    new field turns a staleness check into an outage.
    """
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      default=str).encode("utf-8")


def digest(doc: dict) -> dict[str, str]:
    """Part name -> sha256 of that part of the page."""
    named = set(PARTS) - {"rest"}
    rest = {k: v for k, v in doc.items()
            if k not in named and k not in EXCLUDED}
    out = {}
    for part in PARTS:
        value = rest if part == "rest" else doc.get(part)
        out[part] = hashlib.sha256(_canon(value)).hexdigest()
    return out


def _fmt(v) -> str:
    """A value short enough for a gate row."""
    s = json.dumps(v, default=str) if not isinstance(v, str) else v
    return s if len(s) <= 40 else s[:37] + "..."


def _event_diff(pub: list, now: list) -> list[str]:
    """Name the first few events that differ, field by field.

    The audit's two changes - a time moved by a second, a player swapped - are
    both one field of one element, and a message that said "events differ" would
    leave whoever reads it opening two multi-megabyte files. Position is by
    index, because the events travel as an ordered array and a rebuild that
    reorders them is itself a difference worth printing.
    """
    out = []
    if len(pub) != len(now):
        out.append(f"{len(pub)} events published, {len(now)} in work/")
    for i in range(min(len(pub), len(now))):
        a, b = pub[i], now[i]
        if a == b:
            continue
        keys = sorted(set(a) | set(b))
        for k in keys:
            if a.get(k) != b.get(k):
                out.append(f"event {i} {k}: published {_fmt(a.get(k))}, "
                           f"work/ {_fmt(b.get(k))}")
        if len(out) >= 6:
            out.append("...")
            break
    return out


def _shallow_diff(label: str, pub, now) -> list[str]:
    """Name the differing keys of a flat dict, or say the whole part differs."""
    if isinstance(pub, dict) and isinstance(now, dict):
        keys = sorted(set(pub) | set(now))
        out = [f"{label}.{k}: published {_fmt(pub.get(k))}, work/ {_fmt(now.get(k))}"
               for k in keys if pub.get(k) != now.get(k)]
        if out:
            return out[:6]
    return [f"{label} differs"]


def differences(pub: dict, now: dict) -> list[str]:
    """Every part whose digest disagrees, said in terms a reader can act on.

    Empty means the published page is what a rebuild would emit. The order is
    `PARTS`, so the cheapest thing to look at comes first.
    """
    dp, dn = digest(pub), digest(now)
    out: list[str] = []
    for part in PARTS:
        if dp[part] == dn[part]:
            continue
        if part == "events":
            out += _event_diff(pub.get("events") or [], now.get("events") or [])
        elif part in ("possession", "gates", "observed"):
            out += _shallow_diff(part, pub.get(part), now.get(part))
        elif part == "players":
            a, b = pub.get("players") or [], now.get("players") or []
            if len(a) != len(b):
                out.append(f"players: {len(a)} published, {len(b)} in work/")
            else:
                slots = [p.get("slot") for p, q in zip(a, b) if p != q]
                out.append("player tracks differ: "
                           + ", ".join(str(s) for s in slots[:6]))
        else:
            out.append(f"{part} differs")
    return out


def summarise(diffs: list[str], limit: int = 3) -> str:
    """The one line a gate row has room for."""
    if not diffs:
        return "the published page is what a rebuild would emit"
    head = "; ".join(diffs[:limit])
    return head + (f" (+{len(diffs) - limit} more)" if len(diffs) > limit else "")
