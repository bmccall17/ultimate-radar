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
# `ur.resolve` appears twice, and that is not a mistake. `ur.disc` reads
# possession.json and `ur.possess` reads disc.json, so on a possession that has
# never been through the chain the first pass writes a possession.json with no
# disc in it, `ur.disc` then solves the disc, and nothing carries it back. The
# viewer reads `possession.json`, so the symptom is a page that says "no disc
# position in this data" on a possession whose disc.json is sitting right there.
#
# It is `ur.resolve` on both passes rather than `ur.possess`, and the order
# matters more than it looks. `resolve` is `possess.build` with AD-6's log
# replayed over it - byte for byte the same document on a possession with no
# corrections, which is checked - so it is a free substitution, and it puts the
# corrections in front of `ur.disc` rather than behind it. That is the whole
# point: the disc's position IS the holder's position, so a person who places a
# lost holder has placed the disc, and `ur.disc` has to be the stage that finds
# out. Running it on the uncorrected positions instead leaves the correction in
# the file and the disc still missing from the picture - which is exactly what
# #8's repair mode is for, and what running it the other way round silently
# undoes. Measured on p0003: repairing the two holders the tracker loses takes
# the longest stretch a reader sees no disc from 3.1 s to 0.5 s, and only with
# `ur.disc` downstream of the corrections.
#
# The second pass is cheap (it reads files, it does not re-track) and the loop is
# not circular: `ur.disc` uses only the player positions, and the second resolve
# rebuilds them from the same tracks and the same log, so they are identical to
# what `ur.disc` was given. resolve -> disc -> resolve is a fixed point.
# `tools.m4_structure` joins them for the same reason as `ur.calibrate.accept`:
# it costs a second, it needs no ground truth, it is the gate `docs/04` says
# should never be interesting, and until this it was only ever run by hand on
# p0001. Both of them also used to print FAIL and exit 0, which meant the chain
# ran straight past a possession that had failed its gate.
STAGES = [
    ("calibrate", "ur.calibrate.run", "calibration.json",
     lambda w: ["--eval-dir", f"eval/m1-{w.name}"]),
    # Between the solve and the gate: the mosaic fills frames the paint could not
    # reach, and the gate then judges the possession as it will actually be used.
    # It is idempotent - a re-run throws away what a previous run filled first -
    # so `--from mosaic` is a cheap way to redo just this part.
    ("mosaic", "ur.calibrate.mosaic", "calibration.json (frames with no paint)", None),
    ("accept", "ur.calibrate.accept", "m1_acceptance.json (the known-geometry gate)",
     lambda w: ["--eval-dir", f"eval/m1-{w.name}"]),
    ("detect", "ur.detect.run", "detections.json", None),
    ("team", "ur.team", "detections.json (team fields)", None),
    ("track", "ur.track.run", "tracks.json", None),
    ("possess", "ur.possess", "possession.json", None),
    ("structure", "tools.m4_structure", "m4_structure_acceptance.json (the roster gate)",
     lambda w: ["--out", f"eval/m4-{w.name}/m4_structure_acceptance.json"]),
    # AD-6's layer, and it belongs in the chain rather than beside it. A person
    # saves a repair keyframe out of the viewer into `corrections.json` and the
    # only thing standing between that file and the published page is this
    # stage; leaving it to be remembered meant a coach's work sat in a file
    # nobody replayed. It is a no-op on a possession with no corrections - the
    # document it writes is byte for byte what `ur.possess` wrote, apart from
    # the empty `human` lists - so it costs nothing to have here always.
    ("correct", "ur.resolve", "possession.json (corrections applied, AD-6)", None),
    ("disc", "ur.disc", "disc.json (solved on the CORRECTED positions)", None),
    ("resolve", "ur.resolve", "possession.json (now carrying the disc)", None),
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
