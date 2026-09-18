"""What a stranger will find on the page, written down before anybody reads it.

    python -m tools.cold_read p0003
    python -m tools.cold_read p0003 --json

#24 is the sprint: a named person who knows ultimate and has never seen the tool
answers the five questions in `docs/01-brief.md` off the live page, unaided, and
question 5 has to be right. The ticket was amended on 2026-09-17 to read the page
**unrepaired**, and that amendment is what makes this module necessary.

A stranger reading a page somebody spent hours hand-placing tells you what a
person can make the pipeline look like. A stranger reading the page as it stands
tells you what the pipeline produces, with its gaps showing. The second is the
useful fact, and it only stays useful if the gaps are written down **before** the
read: afterwards, every answer invites an argument about whether the page was
showing that at the time.

So this is a snapshot, taken at a commit, of the things the five questions turn
on:

- **the disc**, because question 4 asks about the last throw and a stretch with
  no disc drawn is a stretch where the reader has to work it out;
- **what the cards admit**, because question 5 is entirely about whether the page
  was believed when it said it was guessing;
- **the repair queue**, because the ticket asks what it *would* have held;
- **the jerseys, the direction and the goal lines**, because each is a place the
  page either names its own uncertainty or does not.

It measures nothing new. Every number here is read off the published page or off
the modules that already check it, which is the point: a snapshot that computed
its own version of the truth would be describing a page nobody is about to read.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from tools import audit_site as AS
from tools import corrections_line as CL
from tools import field_length as FLEN
from tools import openness as OP
from tools import page_js as PJ

WORK = Path("work")

# What the viewer will draw a disc for. The same set `tools/audit_site.py` holds,
# imported rather than restated so a change to one cannot leave the other
# describing a page that no longer exists.
DRAWN = AS.DRAWN_DISC_STATES


def _runs(flags: list[bool], fps: float, *, want: bool) -> list[tuple[float, float]]:
    """Contiguous stretches where `flags` equals `want`, as (start_s, end_s)."""
    out, start = [], None
    for i, v in enumerate(flags):
        if v == want and start is None:
            start = i
        elif v != want and start is not None:
            out.append((start / fps, i / fps))
            start = None
    if start is not None:
        out.append((start / fps, len(flags) / fps))
    return out


def disc(doc: dict) -> dict:
    """Where a reader sees a disc, and where they are on their own."""
    meta = doc.get("disc_meta") or {}
    state = meta.get("state") or []
    fps = float(doc["possession"]["fps"])
    drawn = [s in DRAWN for s in state]
    blind = _runs(drawn, fps, want=False)
    return {
        "frames": len(state),
        "drawn": sum(drawn),
        "blind_stretches": [{"from_s": round(a, 2), "to_s": round(b, 2),
                             "len_s": round(b - a, 2)} for a, b in blind],
        "longest_blind_s": round(max((b - a for a, b in blind), default=0.0), 2),
        "from_an_inferred_name": len(AS.inferred_name_frames(doc)[0]),
    }


def cards(page_html: str, doc: dict) -> dict:
    """How often the openness cards reach a measured badge, and how often not.

    Read through `tools/openness.py`, which runs the page's own card builder, so
    this is what a reader will actually see rather than a second opinion about
    what they ought to.
    """
    s = OP.scan(page_html, doc)
    return {"claims": s.claims, "measured": s.measured,
            "inferred": s.claims - s.measured,
            "measured_share": round(s.measured / s.claims, 4) if s.claims else None}


def queue(work: Path) -> dict:
    """What repair mode would have put in front of somebody. #24 asks for it by
    name, and the answer on an unrepaired page is the whole of it."""
    p = work / "issues.json"
    if not p.exists():
        return {"total": 0, "by_kind": {}, "note": "no issues.json"}
    issues = json.loads(p.read_text(encoding="utf-8")).get("issues", [])
    by: dict[str, int] = {}
    for i in issues:
        by[i.get("kind") or "unknown"] = by.get(i.get("kind") or "unknown", 0) + 1
    return {"total": len(issues),
            "by_kind": dict(sorted(by.items(), key=lambda kv: -kv[1]))}


def names(doc: dict) -> dict:
    """Jerseys, which #24 says are deliberately not a blocker: the brief's
    non-goals put the tactical meaning on the slot, so `D3` is an acceptable
    answer to question 2. Recorded anyway, because what the page offers and what
    the reader needed are two different facts and only one of them is known now.
    """
    pl = doc.get("players") or []
    read = [p["slot"] for p in pl if p.get("jersey_source") == "read"]
    voted = [p["slot"] for p in pl if p.get("jersey_source") == "voted"]
    return {"slots": len(pl), "read": sorted(read), "voted": sorted(voted),
            "unnamed": sorted(p["slot"] for p in pl if not p.get("jersey"))}


def claims(doc: dict) -> dict:
    """The three things the page says about its own provenance."""
    g = doc.get("gates") or {}
    fld = doc.get("field") or {}
    return {
        "attacking_direction_resolved":
            doc["possession"].get("attacking_direction_resolved"),
        "accuracy_measured_on": g.get("measured_on"),
        "accuracy_on_this_possession":
            g.get("per_player_recall") if g.get("measured_on") == doc["possession"]["id"]
            else None,
        "goal_lines": fld.get("length_source"),
        "human_corrections": len(doc.get("corrections_applied") or []),
        # Counted through `tools/corrections_line.py`, which counts the whole
        # roster and the disc. Reading `disc_meta.human` alone was the first
        # version of this and it reported 0 over a possession with 181 placed
        # positions in it - the same undercount, in the tool written to expose
        # it. docs/30 section 2.22.
        "human_placed_positions": CL.cells(doc),
        "human_touched_frames": CL.touched(doc),
    }


def snapshot(pid: str) -> dict:
    doc = AS.published(pid)
    if doc is None:
        raise SystemExit(f"docs/ carries no {pid}; run tools.build_site")
    idx = AS.site_path(pid, "index.html")
    html = idx.read_text(encoding="utf-8") if idx.exists() else None
    out = {
        "possession": pid,
        "frames": doc["possession"]["frames"],
        "fps": doc["possession"]["fps"],
        "duration_s": round(doc["possession"]["frames"]
                            / float(doc["possession"]["fps"]), 2),
        "events": len(doc.get("events") or []),
        "disc": disc(doc),
        "queue": queue(WORK / pid),
        "jerseys": names(doc),
        "claims": claims(doc),
    }
    if html and PJ.node():
        out["cards"] = cards(html, doc)
        out["field_sentence"] = PJ.strip_markup(
            FLEN.render(html, doc.get("field") or {})).strip()
    else:
        out["cards"] = {"note": "node is not on PATH; the cards were not rendered"}
    return out


def markdown(s: dict) -> str:
    """The snapshot as a block to paste into `docs/30`, which is where #24 says
    the result goes."""
    d, q, j, c = s["disc"], s["queue"], s["jerseys"], s["claims"]
    L = []
    A = L.append
    repaired = c["human_placed_positions"] > 0
    A(f"**{s['possession']} as it stands.** "
      f"{s['frames']} frames at {s['fps']} fps ({s['duration_s']} s), "
      f"{s['events']} published tags, **{c['human_corrections']} human "
      f"corrections placing {c['human_placed_positions']} positions across "
      f"{c['human_touched_frames']} of {s['frames']} frames**"
      + (f" ({round(100 * c['human_touched_frames'] / s['frames'])} %). "
         "**#24's first acceptance criterion asks for a page with no repair "
         "pass, and this is not one.**" if repaired
         else ". Nothing here was hand-placed, which is what #24 asks for."))
    A("")
    A(f"**The disc.** Drawn on {d['drawn']} of {d['frames']} frames. "
      f"{len(d['blind_stretches'])} stretch(es) with no disc at all, the longest "
      f"{d['longest_blind_s']} s. A reader asked about the last throw is reading "
      "the video through those.")
    A("")
    if d["blind_stretches"]:
        A("| from | to | length |")
        A("|---|---|---|")
        for b in d["blind_stretches"]:
            A(f"| {b['from_s']} s | {b['to_s']} s | {b['len_s']} s |")
        A("")
    if "claims" in s.get("cards", {}):
        cd = s["cards"]
        A(f"**What the cards admit.** {cd['measured']} of {cd['claims']} openness "
          f"claims reach a measured badge; the other {cd['inferred']} say inferred "
          "and name the slot they could not see (AD-15). Question 5 is about "
          "whether that is believed.")
        A("")
    A(f"**The repair queue, unopened: {q['total']} items.** "
      + ", ".join(f"{v} x `{k}`" for k, v in q["by_kind"].items()) + ".")
    A("")
    A(f"**Jerseys.** {len(j['read'])} of {j['slots']} slots carry a number read "
      f"off a shirt ({', '.join(j['read']) or 'none'}), {len(j['voted'])} a voted "
      f"one, {len(j['unnamed'])} none at all. Not a blocker: the brief's "
      "non-goals put the tactical meaning on the slot, so `D3` answers "
      "question 2.")
    A("")
    A(f"**What the page says about itself.** Attacking direction "
      f"{c['attacking_direction_resolved'] or '**unverified**'}. Accuracy "
      f"measured on `{c['accuracy_measured_on']}` and **unmeasured here**. "
      f"Goal lines **{c['goal_lines']}**.")
    return "\n".join(L)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="tools.cold_read")
    ap.add_argument("possession", nargs="?", default="p0003")
    ap.add_argument("--json", action="store_true", help="the snapshot, unformatted")
    a = ap.parse_args(argv)
    s = snapshot(a.possession)
    print(json.dumps(s, indent=1) if a.json else markdown(s))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
