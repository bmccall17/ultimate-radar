"""The frames `docs/32-qa-script.md` needs, derived rather than remembered.

    python -m tools.qa_fixture              # p0003, the reference possession
    python -m tools.qa_fixture work/p0009

A QA script that hard-codes "at f345 the pips read O2 O3 O4 O7 D2 D5 D6" is
correct on the day it is written and wrong the first time somebody repairs
something. The runner then meets a red scenario caused by the data improving,
learns that red means nothing, and the script is worse than none.

So the script carries the *properties* and this prints the *numbers*. Run it
first; use what it says. Every frame here is chosen by a rule, and the rule is
what the QA script actually asserts:

- **a collision** - two slots of one team inside 1.5 yd where one has a detection
  and the other is dead reckoning, which is what makes a roster pass confusing
  and what `detach` is for;
- **a dead frame** - calibration under the floor, where placing from the video
  has to be refused;
- **a clean frame** - the most slots resting on a detection *inside* the lines,
  which is where to read jerseys. Counting matches without asking what they are
  matched to is how f430 was recommended once: fourteen of fourteen, four of
  them on the sideline crowd (#29);
- **a busy frame** - the most slots with any detection at all, for the rail.

It reads the **published** page, not `work/`, because that is what a QA pass
drives and `docs/32` is a script for the live site (AGENTS rule 7).
"""

from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path

SITE = Path("docs")
SAME_PERSON_YD = 1.5
PLACE_MIN_CALIB = 0.5           # viewer/index.html PLACE_MIN_CALIB
HAS_DET = {"observed", "provisional", "weak", "confirmed"}
GHOST = {"predicted", "interpolated"}


def published(pid: str) -> dict:
    txt = (SITE / pid / "possession.js").read_text(encoding="utf-8") \
        if pid != "p0001" else (SITE / "possession.js").read_text(encoding="utf-8")
    m = re.search(r"window\.POSSESSION\s*=\s*", txt)
    doc, _ = json.JSONDecoder().raw_decode(txt[m.end():])
    return doc


def _field_ok(xy, L, W) -> bool:
    return xy is not None and 0 <= xy[0] <= L and 0 <= xy[1] <= W


def fixture(pid: str, work: Path) -> dict:
    doc = published(pid)
    fps = float(doc["possession"]["fps"])
    nf = int(doc["possession"]["frames"])
    pf = doc["camera"]["per_frame"]
    L = doc["field"]["length_yd"]
    W = doc["field"]["width_yd"]
    dets = json.loads((work / "detections.json").read_text(encoding="utf-8"))
    byf = {r["f"]: r["dets"] for r in dets["frames"]}

    def calib(f):
        return (pf[f] or {}).get("confidence", 0.0) or 0.0

    def on_field(p, f):
        di = p["det"][f]
        if di is None or f not in byf or di >= len(byf[f]):
            return False
        return _field_ok(byf[f][di].get("field"), L, W)

    clean = busy = None
    for f in range(nf):
        if calib(f) < 0.6:
            continue
        real = sum(1 for p in doc["players"] if on_field(p, f))
        crowd = sum(1 for p in doc["players"]
                    if p["det"][f] is not None and not on_field(p, f))
        matched = sum(1 for p in doc["players"] if p["det"][f] is not None)
        if clean is None or (real, -crowd) > (clean[0], -clean[1]):
            clean = (real, crowd, f)
        if busy is None or matched > busy[0]:
            busy = (matched, f)

    collision = None
    for f in range(nf):
        if calib(f) < PLACE_MIN_CALIB:
            continue
        for a in doc["players"]:
            if a["state"][f] not in GHOST or not a["est"][f]:
                continue
            for b in doc["players"]:
                if b is a or b["team"] != a["team"] or not b["est"][f]:
                    continue
                if b["state"][f] not in HAS_DET:
                    continue
                gap = math.hypot(*(x - y for x, y in zip(a["est"][f], b["est"][f])))
                if gap < SAME_PERSON_YD:
                    collision = {"f": f, "ghost": a["id"], "real": b["id"],
                                 "yd": round(gap, 2)}
                    break
            if collision:
                break
        if collision:
            break

    dead = next((f for f in range(nf) if calib(f) < 0.01), None)

    seen_at = None
    if busy:
        seen_at = {"f": busy[1],
                   "slots": [p["id"] for p in doc["players"]
                             if p["det"][busy[1]] is not None]}

    return {
        "possession": pid,
        "fps": fps,
        "frames": nf,
        "corrections_applied": len(doc.get("corrections_applied", [])),
        "clean_frame": None if not clean else
            {"f": clean[2], "t": round(clean[2] / fps, 2),
             "slots_on_an_in_field_detection": clean[0],
             "slots_on_the_crowd": clean[1], "calib": round(calib(clean[2]), 2)},
        "busy_frame": seen_at,
        "collision": collision,
        "dead_frame": None if dead is None else
            {"f": dead, "t": round(dead / fps, 2), "calib": round(calib(dead), 2)},
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="tools.qa_fixture")
    p.add_argument("work", nargs="?", default="work/p0003")
    a = p.parse_args(argv)
    work = Path(a.work)
    fx = fixture(work.name, work)

    print(f"\nQA fixture for {fx['possession']} as published "
          f"({fx['corrections_applied']} correction(s) applied)\n")
    c = fx["clean_frame"]
    if c:
        print(f"  clean frame   f{c['f']}  #t={c['t']}   "
              f"{c['slots_on_an_in_field_detection']} of 14 slots on a real "
              f"in-field detection, {c['slots_on_the_crowd']} on the crowd, "
              f"calib {c['calib']}")
        print( "                -> docs/32 sections 4 and 7: placing, and reading jerseys")
    b = fx["busy_frame"]
    if b:
        print(f"  busy frame    f{b['f']}   {len(b['slots'])} slots with a detection: "
              f"{' '.join(b['slots'])}")
        print( "                -> docs/32 section 2: the rail's pips must match this")
    k = fx["collision"]
    if k:
        print(f"  collision     f{k['f']}   {k['ghost']} is dead-reckoning "
              f"{k['yd']} yd from {k['real']}, which has a detection")
        print( "                -> docs/32 section 6: the panel must name "
               f"{k['real']} and enable detach on {k['ghost']}")
    dd = fx["dead_frame"]
    if dd:
        print(f"  dead frame    f{dd['f']}  #t={dd['t']}   calibration "
              f"{dd['calib']}, under {PLACE_MIN_CALIB}")
        print( "                -> docs/32 section 5: a click on the video must "
               "stage nothing")
    print()
    print(json.dumps(fx, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
