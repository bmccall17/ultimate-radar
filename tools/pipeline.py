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

# (module, what it writes, whether it takes a per-possession --eval-dir)
#
# `ur.calibrate.accept` is in the chain, not beside it. It is the only check in
# the project that compares a frame against geometry whose position is known
# exactly, and it was never run on the second or third possession - both of which
# were wrong by 4.6 and 6.8 yd while every in-possession signal looked healthy,
# with one of them published for a fortnight. A gate that has to be remembered is
# a gate that will be forgotten. See docs/28-calibration-confidence.md.
STAGES = [
    ("ur.calibrate.run", "calibration.json", True),
    ("ur.calibrate.accept", "m1_acceptance.json (the known-geometry gate)", True),
    ("ur.detect.run", "detections.json", False),
    ("ur.team", "detections.json (team fields)", False),
    ("ur.track.run", "tracks.json", False),
    ("ur.possess", "possession.json", False),
    ("ur.disc", "disc.json", False),
    ("ur.issues", "issues.json", False),
]

# Calibration evidence is per possession and must not be shared. Both M1 stages
# default to `eval/m1`, which is p0001's, so running them for another possession
# would overwrite the evidence `docs/12-m1-calibration.md` cites. One directory
# per possession; `eval/m1` stays as p0001's historical M1 artefacts.
def eval_dir(work: Path) -> str:
    return f"eval/m1-{work.name}"
DEFAULT_FROM = "detect"


def _key(mod: str) -> str:
    parts = mod.split(".")
    return parts[-1] if parts[-1] not in ("run",) else parts[1]


def run(work: Path, start: str, *, dry: bool = False) -> int:
    names = [_key(m) for m, _, _ in STAGES]
    if start not in names:
        print(f"[pipeline] --from must be one of {names}", file=sys.stderr)
        return 2
    begin = names.index(start)
    for mod, writes, per_possession_eval in STAGES[begin:]:
        cmd = [sys.executable, "-m", mod, str(work)]
        if per_possession_eval:
            cmd += ["--eval-dir", eval_dir(work)]
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
