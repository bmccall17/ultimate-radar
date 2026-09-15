"""Audit the published site - the thing a reader actually gets.

    python -m tools.audit_site            # every published possession
    python -m tools.audit_site p0009

`tools/gates.py` checks the pipeline: does the calibration accept, does the
roster hold together, does the solver get the holder right. Every one of those
reads `work/`. **None of them look at `docs/`**, which is the only artefact
anybody sees, and `docs/30` § 2.6 already records three defects that printed
success while being wrong. A site can be stale, can publish evidence it then
ignores, and can carry one possession's numbers on another's page, and the
entire gate suite would stay green.

This was written after clicking through the live site on 2026-09-15 and finding
two of those three. The checks below are the findings turned into tests.

**These read the published JSON, not the rendered page.** A browser audit found
the problems; a string match against rendered HTML is not the test, because the
first version of that flagged the phrase "the huck is on" as a live claim when it
survived only inside a code comment. What a page *asserts* lives in its data.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SITE = Path("docs")
WORK = Path("work")

# States the viewer will draw a disc for. Anything else it suppresses, which is
# the behaviour check D locks in.
DRAWN_DISC_STATES = {"observed", "confirmed"}

# How far outside the lines an OBSERVED player may be before it is a defect
# rather than a sideline. Measured: across the six published possessions 374
# observed positions are outside the field and the furthest is 2.5 yd, which is
# where people stand. The boards at Breese Stevens are a few yards further out,
# so 5 yd is past anywhere a player can be and still be on camera as a player.
OFF_FIELD_LIMIT_YD = 5.0


def published(pid: str) -> dict | None:
    """Read a published possession back out of the site, as a reader's browser does."""
    p = SITE / "possession.js" if pid == "p0001" else SITE / pid / "possession.js"
    if not p.exists():
        return None
    txt = p.read_text(encoding="utf-8")
    # The file carries several assignments (POSSESSION, ISSUES, IDENTITIES), so a
    # greedy match to the last brace swallows all of them. Decode from the start
    # of the object and let the decoder find its own end.
    i = txt.find("POSSESSION")
    if i < 0:
        return None
    i = txt.find("{", i)
    return json.JSONDecoder().raw_decode(txt[i:])[0] if i >= 0 else None


def audit(pid: str) -> list[dict]:
    out: list[dict] = []

    def add(name, ok, got, want, note=""):
        out.append({"name": name, "pass": bool(ok), "got": got, "want": want,
                    "note": note})

    doc = published(pid)
    if doc is None:
        add("is published", False, "no possession.js under docs/", "the site carries it")
        return out

    # ---- A. the site is not behind the pipeline ------------------------------
    # Tags live in work/<id>/events.json, NOT in possession.json - make_view reads
    # them from there and injects them. Comparing against possession.json's own
    # `events`, which stays empty until ur.possess is re-run, made this check fail
    # the moment any tag existed. A gate that fires on the wrong thing is worse
    # than no gate: it trains you to ignore it.
    ev_p = WORK / pid / "events.json"
    live_n = (len(json.loads(ev_p.read_text(encoding="utf-8")).get("events", []))
              if ev_p.exists() else 0)
    src = WORK / pid / "possession.json"
    if src.exists():
        live = json.loads(src.read_text(encoding="utf-8"))
        same = (len(doc.get("events", [])) == live_n
                and doc["possession"]["frames"] == live["possession"]["frames"])
        add("site is current", same,
            f"{len(doc.get('events', []))} events published, {live_n} in work/",
            "the published page matches the pipeline",
            "run tools.build_site - the site is the deliverable (AGENTS rule 7)")

    # ---- B. published evidence is actually used ------------------------------
    # The point of tagging is that the artefact changes. p0003 and p0009 were
    # found publishing 14 and 12 human tags while every disc frame was still
    # `inferred`, because ur.disc had not been re-run since the tags landed. The
    # tags were in the file, visible to nobody, buying nothing.
    tags = [e for e in doc.get("events", [])
            if e.get("source") == "human" and e.get("player")]
    meta = doc.get("disc_meta") or {}
    human_frames = sum(1 for s in (meta.get("source") or []) if s == "human")
    add("published tags are used", not tags or human_frames > 0,
        f"{len(tags)} human tags naming a player -> {human_frames} disc frames from them",
        "tags change the artefact, or they bought nothing",
        "re-run `python -m ur.disc work/<id>` then tools.build_site")

    # ---- C. no page wears another possession's numbers -----------------------
    # The brief is explicit: never quote p0001's numbers over other footage.
    # Every page currently ships p0001's tracker gates in its data. The viewer
    # does not render them today, which makes this a loaded gun rather than a
    # live misstatement - and the fix is the same either way.
    g = doc.get("gates") or {}
    on = g.get("measured_on")
    NUMERIC = ("per_player_recall", "sigma_containment", "identity_switches_caught")
    carried = [k for k in NUMERIC if g.get(k) is not None]
    add("no borrowed gate numbers", on in (None, pid) or not carried,
        f"measured_on = {on!r}; numbers present: {carried or 'none'}",
        "numbers only on the possession they were measured on",
        "another possession's tracker numbers are readable off this page")

    # ---- D. nothing is drawn from an inference that failed its gate ----------
    # Behavioural, not textual: count the frames the viewer would draw a disc
    # for, and require every one of them to rest on a human tag rather than on
    # the holder inference, which `docs/27` measures at 33 % held out.
    states = meta.get("state") or []
    sources = meta.get("source") or []
    drawn = [i for i, s in enumerate(states) if s in DRAWN_DISC_STATES]
    bad = [i for i in drawn
           if i < len(sources) and sources[i] not in ("human", "solved")]
    add("no disc drawn from the failed inference", not bad,
        f"{len(drawn)} frames drawn, {len(bad)} of them from inference alone",
        "every drawn disc frame rests on a human tag",
        "docs/27: unaided holder inference scores 33 % held out")

    # ---- E. nobody is observed somewhere there is no field --------------------
    # Ultimate is played with people standing just out of bounds, so being outside
    # the lines is not by itself wrong, and the measurement says so: across all six
    # published possessions, 374 `observed` positions sit outside the field and the
    # furthest is 2.5 yd. That is a player on the sideline, not a defect. So this
    # is not a finding - it is a floor, set where the stands begin. Dead reckoning
    # is exempt: docs/05 argues a ghost that drifts is more honest than one frozen,
    # and `predicted` is allowed to wander.
    fld = doc.get("field") or {}
    L, W = fld.get("length_yd", 120.0), fld.get("width_yd", 53.333)
    worst, n_bad = 0.0, 0
    for pl in doc.get("players", []):
        for st, e in zip(pl.get("state", []), pl.get("est", [])):
            if not e or st not in ("observed", "confirmed"):
                continue
            d = max(0.0, -e[0], e[0] - L) ** 2 + max(0.0, -e[1], e[1] - W) ** 2
            d = d ** 0.5
            worst = max(worst, d)
            n_bad += d > OFF_FIELD_LIMIT_YD
    add("nobody observed in the stands", n_bad == 0,
        f"{n_bad} observed positions over {OFF_FIELD_LIMIT_YD} yd out, worst {worst:.1f} yd",
        f"0 beyond {OFF_FIELD_LIMIT_YD} yd outside the field",
        "an observed position that far out is a calibration failure, not a sideline")

    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="tools.audit_site")
    p.add_argument("possession", nargs="*")
    a = p.parse_args(argv)
    ids = a.possession or sorted(
        {"p0001"} | {q.name for q in SITE.iterdir()
                     if q.is_dir() and re.fullmatch(r"p\d{4}", q.name)})
    failed = 0
    for pid in ids:
        print(f"\n=== {pid} (as published)")
        for c in audit(pid):
            mark = "PASS" if c["pass"] else "FAIL"
            failed += not c["pass"]
            print(f"  [{mark}] {c['name']:<34} {str(c['got']):<52} want {c['want']}")
            if c["note"] and not c["pass"]:
                print(f"         {c['note']}")
    print(f"\n{failed} site check(s) failing.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
