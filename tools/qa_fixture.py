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

It reads the **published** page and nothing else, because that is what a QA pass
drives (AGENTS rule 7) and because a QA tool that needs `work/` cannot run from a
clone - `work/` is gitignored, it holds the footage, and regenerating
`detections.json` means having the broadcast. The first version needed it and the
QA pass reported that as a finding against its own docstring (docs/30 § 2.15).

The one thing `work/` had that the page does not is each detection's own field
position, used to ask whether a matched slot is resting on somebody inside the
lines or on the sideline crowd. The slot's **estimate** answers the same question:
across p0003's 4053 matched slot-frames the two disagree on 5, or 0.12 %, and all
five are within inches of a line. A fifth of a percent of boundary cases is not
worth a dependency that stops the tool running at all.
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


def fixture(pid: str) -> dict:
    doc = published(pid)
    fps = float(doc["possession"]["fps"])
    nf = int(doc["possession"]["frames"])
    pf = doc["camera"]["per_frame"]
    L = doc["field"]["length_yd"]
    W = doc["field"]["width_yd"]

    def calib(f):
        return (pf[f] or {}).get("confidence", 0.0) or 0.0

    def on_field(p, f):
        return p["det"][f] is not None and _field_ok(p["est"][f], L, W)

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

    # Two kinds of dead frame and § 5 must refuse both, in different words. A
    # low confidence still has a homography; a collapsed one does not invert at
    # all, and that is the case that slipped through (docs/30 § 2.14) precisely
    # because it looked like the absence of a problem rather than the worst one.
    def collapsed(f):
        H = (pf[f] or {}).get("H")
        if not H:
            return True
        a, b, c = H
        det3 = (a[0]*(b[1]*c[2] - b[2]*c[1]) - a[1]*(b[0]*c[2] - b[2]*c[0])
                + a[2]*(b[0]*c[1] - b[1]*c[0]))
        return abs(det3) < 1e-12

    dead = next((f for f in range(nf) if calib(f) < 0.01), None)
    dead_collapsed = next((f for f in range(nf)
                           if calib(f) < PLACE_MIN_CALIB and collapsed(f)), None)
    dead_intact = next((f for f in range(nf)
                        if calib(f) < PLACE_MIN_CALIB and not collapsed(f)), None)

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
            {"f": dead, "t": round(dead / fps, 2), "calib": round(calib(dead), 2),
             "projection_collapsed": collapsed(dead)},
        # § 5 has to see both, because they take different wording and the
        # collapsed one is the one that was silently passing.
        "dead_frame_collapsed": None if dead_collapsed is None else
            {"f": dead_collapsed, "t": round(dead_collapsed / fps, 2)},
        "dead_frame_low_confidence": None if dead_intact is None else
            {"f": dead_intact, "t": round(dead_intact / fps, 2),
             "calib": round(calib(dead_intact), 2)},
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="tools.qa_fixture")
    # A possession id, or a `work/<id>` path, because both spellings are in
    # docs/32 and neither is worth correcting somebody over.
    p.add_argument("possession", nargs="?", default="p0003")
    a = p.parse_args(argv)
    fx = fixture(Path(a.possession).name)

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
        print(f"                {'the homography does not invert' if dd['projection_collapsed'] else 'the homography inverts, the fit is poor'}")
        print( "                -> docs/32 section 5: a click on the video must "
               "stage nothing")
    for label, key in (("collapsed", "dead_frame_collapsed"),
                       ("low-confidence", "dead_frame_low_confidence")):
        v = fx.get(key)
        if v:
            print(f"  dead ({label:<15}) f{v['f']}  #t={v['t']}")
    print()
    print(json.dumps(fx, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
