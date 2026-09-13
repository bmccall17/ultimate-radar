"""M5's correction gates: an anchor joins cleanly, and revert is byte-identical.

    python -m tools.m5_resolve work/p0001

`docs/04-milestones.md` M5 asks for two things this checks:

- **"`resolve.py` applied to an anchor produces a path continuous at both ends."**
  The anchor is placed in a real estimated span — one the issue queue actually
  raised, not a contrived one — and the check is made at the joins: the samples
  that bracket the span must be **untouched**, and the corrected path must not
  introduce a step larger than the motion it is correcting. A fix that leaves a
  jump at the join is a new error wearing a correction's clothes.
- **"`revert` restores byte-identical output."** Not "equivalent", not "within
  tolerance" — the same bytes. Reverting is the thing that makes a coach willing
  to correct at all, so it gets the strictest available test.

The anchor's displacement is deliberately large (4 yd). A small one would pass a
continuity check by being indistinguishable from no correction.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from ur.issues import find
from ur.resolve import active, empty_log, load_uncorrected, resolve

ANCHOR_OFFSET_YD = 4.0
ESTIMATED = {"predicted", "unknown", "interpolated"}


def pick_span(doc: dict) -> tuple[str, int, int, int]:
    """A real estimated span with an observation on both sides.

    Preference goes to a span the issue queue flagged, because that is the span a
    human would actually be correcting.
    """
    flagged = {(i["slots"][0], i["frame"]) for i in find(doc)["issues"]
               if len(i["slots"]) == 1}
    best = None
    for p in doc["players"]:
        st = p["state"]
        f = 0
        while f < len(st):
            if st[f] in ESTIMATED:
                start = f
                while f < len(st) and st[f] in ESTIMATED:
                    f += 1
                lo, hi = start - 1, f
                if lo >= 0 and hi < len(st) and st[lo] == "observed" \
                        and st[hi] == "observed" and p["est"][start] is not None:
                    mid = (start + f - 1) // 2
                    score = (f - start) + (50 if (p["id"], hi) in flagged else 0)
                    if best is None or score > best[0]:
                        best = (score, p["id"], mid, lo, hi)
            else:
                f += 1
    if best is None:
        raise SystemExit("no bracketed estimated span found")
    _, slot, mid, lo, hi = best
    return slot, mid, lo, hi


def check(work: Path) -> dict:
    base = load_uncorrected(work)
    slot, f, lo, hi = pick_span(base)
    p0 = next(p for p in base["players"] if p["id"] == slot)
    xy0 = np.asarray(p0["est"][f], float)
    target = (xy0 + np.array([ANCHOR_OFFSET_YD, 0.0])).round(3).tolist()

    log = empty_log(base["possession"]["id"])
    log["corrections"] = [{"id": "c1", "at": "2026-09-13T00:00:00Z", "op": "anchor",
                           "slot": slot, "f": f, "xy": target,
                           "note": "acceptance test: a deliberately large displacement"}]
    fixed = resolve(load_uncorrected(work), log, verbose=False)
    p1 = next(p for p in fixed["players"] if p["id"] == slot)

    def step_profile(p):
        e = p["est"]
        out = []
        for k in range(max(lo, 1), min(hi + 2, len(e))):
            a, b = e[k - 1], e[k]
            out.append(None if a is None or b is None
                       else float(np.hypot(b[0] - a[0], b[1] - a[1])))
        return out

    before, after = step_profile(p0), step_profile(p1)
    pairs = [(a, b) for a, b in zip(before, after) if a is not None and b is not None]
    worst_before = max((a for a, _ in pairs), default=0.0)
    worst_after = max((b for _, b in pairs), default=0.0)

    # The largest step over the whole span is the wrong statistic: this span
    # contains O6's 25 yd re-acquisition snap, which swamps anything the anchor
    # does. A discontinuity from the ramp would appear *at the joins*, so measure
    # there - the first step inside the span and the last one.
    def join_steps(p):
        e = p["est"]
        def d(i, j):
            a, b = e[i], e[j]
            return None if a is None or b is None else float(
                np.hypot(b[0] - a[0], b[1] - a[1]))
        return d(lo, lo + 1), d(hi - 1, hi)
    jb, ja = join_steps(p0), join_steps(p1)
    join_delta = max(abs((y or 0) - (x or 0)) for x, y in zip(jb, ja))

    ends_untouched = (p0["est"][lo] == p1["est"][lo]
                      and p0["est"][hi] == p1["est"][hi]
                      and p0["sigma"][lo] == p1["sigma"][lo]
                      and p0["sigma"][hi] == p1["sigma"][hi]
                      and p0["state"][lo] == p1["state"][lo]
                      and p0["state"][hi] == p1["state"][hi])
    moved = float(np.hypot(*(np.asarray(p1["est"][f], float) - xy0)))
    anchored_ok = (p1["state"][f] == "confirmed"
                   and abs(p1["sigma"][f] - 0.3) < 1e-9
                   and np.allclose(p1["est"][f], target))

    # A discontinuity would show as a single step far larger than the motion the
    # span already had. The ramp spreads the offset over the span instead.
    span = hi - lo
    # Each frame inside the span absorbs at most offset / (half the span) of the
    # correction, so that is the most a single step can legitimately grow.
    expected_extra = ANCHOR_OFFSET_YD / max(span / 2.0, 1.0)
    continuous = (join_delta <= expected_extra * 1.5
                  and worst_after <= worst_before + expected_extra * 1.5)

    # Revert everything, and demand the same bytes. The baseline is resolve() on
    # an EMPTY log, not the raw build: resolve annotates the document it returns
    # (`notice`, `corrections_applied`), so comparing against the raw build would
    # be testing those annotations rather than the revert.
    rev = dict(log)
    rev["corrections"] = list(log["corrections"]) + [
        {"id": "r1", "at": "2026-09-13T00:00:01Z", "op": "revert", "target": "c1"}]
    empty = empty_log(base["possession"]["id"])
    a = json.dumps(resolve(load_uncorrected(work), empty, verbose=False),
                   indent=1, sort_keys=True)
    b = json.dumps(resolve(load_uncorrected(work), rev, verbose=False),
                   indent=1, sort_keys=True)
    byte_identical = a == b

    # And separately: resolving an empty log must leave the tracks alone. That is
    # a different property from revert and it is worth its own assertion, because
    # a resolve() that quietly corrupted every document would pass the revert test.
    raw = load_uncorrected(work)
    noop = resolve(load_uncorrected(work), empty, verbose=False)
    differing = sorted(k for k in set(raw) | set(noop)
                       if json.dumps(raw.get(k), sort_keys=True)
                       != json.dumps(noop.get(k), sort_keys=True))

    return {
        "schema": "ultimate-radar/m5-resolve-acceptance@1",
        "possession": base["possession"]["id"],
        "anchor": {"slot": slot, "frame": f, "span": [lo, hi],
                   "span_frames": span,
                   "displacement_yd": ANCHOR_OFFSET_YD,
                   "moved_yd": round(moved, 3),
                   "states_in_span": sorted({s for s in p0["state"][lo:hi + 1]})},
        "continuity_gate": {
            "requirement": "a path continuous at both ends",
            "bracketing_samples_untouched": bool(ends_untouched),
            "anchor_frame_confirmed_sigma_0_3": bool(anchored_ok),
            "join_step_change_yd": round(join_delta, 4),
            "largest_frame_step_before_yd": round(worst_before, 4),
            "largest_frame_step_after_yd": round(worst_after, 4),
            "allowed_extra_yd": round(expected_extra * 1.5, 4),
            "pass": bool(ends_untouched and anchored_ok and continuous),
        },
        "revert_gate": {
            "requirement": "revert restores byte-identical output",
            "baseline": "resolve() over an empty log, so the comparison is the "
                        "revert rather than resolve's own annotations",
            "bytes_before": len(a), "bytes_after": len(b),
            "pass": bool(byte_identical),
        },
        "no_op_check": {
            "requirement": "resolving an empty log changes nothing but its own "
                           "annotations",
            "top_level_keys_that_differ": differing,
            "pass": bool(set(differing) <= {"notice", "corrections_applied"}),
        },
        "corrections_log_used": log["corrections"],
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="tools.m5_resolve")
    p.add_argument("work")
    p.add_argument("--out", default="eval/m5/m5_resolve_acceptance.json")
    a = p.parse_args(argv)
    res = check(Path(a.work))
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=2) + chr(10), encoding="utf-8")

    an, cg, rg = res["anchor"], res["continuity_gate"], res["revert_gate"]
    print(f"  anchor            : {an['slot']} at frame {an['frame']}, inside an "
          f"estimated span f{an['span'][0]}-f{an['span'][1]} "
          f"({an['span_frames']} frames, {an['states_in_span']})")
    print(f"  displaced         : {an['displacement_yd']} yd")
    print()
    print(f"  bracketing samples untouched : {cg['bracketing_samples_untouched']}")
    print(f"  anchor frame confirmed, 0.3  : {cg['anchor_frame_confirmed_sigma_0_3']}")
    print(f"  step change AT THE JOINS     : {cg['join_step_change_yd']:.4f} yd "
          f"(allowed {cg['allowed_extra_yd']:.4f})")
    print(f"  largest step anywhere in span: {cg['largest_frame_step_before_yd']:.4f} "
          f"-> {cg['largest_frame_step_after_yd']:.4f} yd  "
          f"(dominated by a pre-existing re-acquisition snap)")
    print(f"  GATE continuity at both ends : {'PASS' if cg['pass'] else 'FAIL'}")
    print()
    print(f"  GATE revert byte-identical   : {'PASS' if rg['pass'] else 'FAIL'} "
          f"({rg['bytes_before']} bytes)")
    nz = res["no_op_check"]
    print(f"  empty log changes only       : {nz['top_level_keys_that_differ']}  "
          f"{'OK' if nz['pass'] else 'UNEXPECTED'}")
    print(f"\n  -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
