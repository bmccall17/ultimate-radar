"""Run every stage for one possession, in order, and stop at the first failure.

    python -m tools.pipeline work/p0002
    python -m tools.pipeline work/p0002 --from detect

The stages already run alone — that is `AGENTS.md`'s working style and it is right.
What was missing is the *order*, which lived only in a handful of write-ups, so
bringing a second possession up to the state of the first meant reading three
documents to find out what to run after what. A possession that is one command
behind is a possession nobody re-runs.

Calibration is excluded from the default chain because it is the slow one —
several minutes over every frame — and because it is the stage whose output
everything else is keyed to. Pass `--from calibrate` to include it.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

# (key, module, what it writes, how to name its per-possession evidence)
#
# The evidence path matters as much as the order. Every acceptance stage here
# defaults its output to p0001's directory - `eval/m1`, `eval/m4` - so running
# one on another possession would overwrite the evidence the write-ups cite.
# `extra` gives each stage a directory of its own, keyed on the possession.
#
# `ur.calibrate.accept` is in the chain, not beside it. It is the only check in
# the project that compares a frame against geometry whose position is known
# exactly, and it was never run on the second or third possession - both of which
# were wrong by 4.6 and 6.8 yd while every in-possession signal looked healthy,
# with one of them published for a fortnight. A gate that has to be remembered is
# a gate that will be forgotten. See docs/28-calibration-confidence.md.
#
# `ur.possess` appears twice, and that is not a mistake. `ur.disc` reads
# possession.json and `ur.possess` reads disc.json, so on a possession that has
# never been through the chain the first pass writes a possession.json with no
# disc in it, `ur.disc` then solves the disc, and nothing carries it back. The
# viewer reads `possession.json`, so the symptom is a page that says "no disc
# position in this data" on a possession whose disc.json is sitting right there.
# The second pass is cheap (it reads files, it does not re-track) and the loop is
# not circular: `ur.disc` uses only the player positions, which the second pass
# does not change, so possess -> disc -> possess is a fixed point.
# `tools.m4_structure` joins them for the same reason as `ur.calibrate.accept`:
# it costs a second, it needs no ground truth, it is the gate `docs/04` says
# should never be interesting, and until this it was only ever run by hand on
# p0001. Both of them also used to print FAIL and exit 0, which meant the chain
# ran straight past a possession that had failed its gate.
STAGES = [
    ("calibrate", "ur.calibrate.run", "calibration.json",
     lambda w: ["--eval-dir", f"eval/m1-{w.name}"]),
    ("accept", "ur.calibrate.accept", "m1_acceptance.json (the known-geometry gate)",
     lambda w: ["--eval-dir", f"eval/m1-{w.name}"]),
    ("detect", "ur.detect.run", "detections.json", None),
    ("team", "ur.team", "detections.json (team fields)", None),
    ("track", "ur.track.run", "tracks.json", None),
    ("possess", "ur.possess", "possession.json", None),
    ("structure", "tools.m4_structure", "m4_structure_acceptance.json (the roster gate)",
     lambda w: ["--out", f"eval/m4-{w.name}/m4_structure_acceptance.json"]),
    ("disc", "ur.disc", "disc.json", None),
    ("repossess", "ur.possess", "possession.json (now carrying the disc)", None),
    ("issues", "ur.issues", "issues.json", None),
]

DEFAULT_FROM = "detect"


def run(work: Path, start: str, *, dry: bool = False) -> int:
    names = [k for k, _, _, _ in STAGES]
    if start not in names:
        print(f"[pipeline] --from must be one of {names}", file=sys.stderr)
        return 2
    begin = names.index(start)
    for _, mod, writes, extra in STAGES[begin:]:
        cmd = [sys.executable, "-m", mod, str(work)]
        if extra is not None:
            cmd += extra(work)
        print(f"\n[pipeline] === {mod} -> {writes}")
        if dry:
            continue
        t0 = time.time()
        r = subprocess.run(cmd)
        if r.returncode != 0:
            print(f"[pipeline] {mod} failed with {r.returncode}; stopping here so "
                  "the failure is the last thing on screen rather than the first "
                  "thing scrolled past", file=sys.stderr)
            return r.returncode
        print(f"[pipeline] {mod} ok in {time.time() - t0:.0f}s")
    print(f"\n[pipeline] {work} is up to date")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="tools.pipeline")
    p.add_argument("work")
    p.add_argument("--from", dest="start", default=DEFAULT_FROM,
                   help=f"first stage to run (default {DEFAULT_FROM}; "
                        "calibrate is excluded by default because it is slow)")
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args(argv)
    return run(Path(a.work), a.start, dry=a.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
