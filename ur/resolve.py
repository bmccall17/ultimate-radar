"""M5 — apply `corrections.json` over immutable tracks. AD-6.

    python -m ur.resolve work/p0001              # -> possession.json, corrected
    python -m ur.resolve work/p0001 --dry-run    # print what would change

**`tracks.json` is never edited.** AD-6 is the reason this module exists as a
separate stage rather than as a mutation: a coach who cannot undo will not
correct at all, and the correction log is the highest-value training data this
project can produce — every anchor is a human-verified field position on real
broadcast footage, and no public dataset of those exists for ultimate.

So corrections are an **append-only log** replayed in order over a fresh read of
the tracks. Three operations, and `docs/05-uncertainty.md` says to resist adding
more:

- **anchor** — a human places a slot at a position on a frame.
- **swap** — exchange two slots' trajectories from a frame onward.
- **confirm** — affirm an estimate is right; collapses sigma.

And one that is not an operation so much as a property of the log:

- **revert** — neutralise an earlier correction by id. It does not delete the
  entry, because the log is a history; it marks it inert on replay. Reverting
  every correction must reproduce the uncorrected output **byte for byte**, and
  that is an acceptance criterion rather than a hope, so `--verify-revert`
  checks it.

## How an anchor is applied

Straight from `docs/05`, and the reason for every step is that the corrected path
has to meet the machine's real observations at both ends — otherwise the fix
introduces a discontinuity, which is a new error dressed as a correction:

1. Find `lo`, the last frame ≤ f that is `observed` or `confirmed`, and `hi`, the
   first ≥ f. These bracket the estimated span the anchor belongs to.
2. Take the offset between the anchor and the current estimate at `f`.
3. Apply it across `[lo, hi]` with a weight ramping 0→1 from `lo` to `f` and
   1→0 from `f` to `hi`.
4. Scale sigma by the same weight; set frame `f` to `confirmed`, sigma 0.3.

At `lo` and `hi` the weight is zero, so those samples are untouched and the path
is continuous by construction rather than by tuning. When no observation brackets
the anchor on one side — the span runs to the start or the end of the possession
— the ramp on that side is flat at 1, because there is nothing to meet.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

CONFIRMED_SIGMA = 0.3          # docs/05
ANCHORED = {"observed", "confirmed"}


# --------------------------------------------------------------------------- #
# the log


def empty_log(possession_id: str) -> dict:
    return {"schema": "ultimate-radar/corrections@1",
            "possession_id": possession_id,
            "note": "Append-only. `revert` neutralises an earlier entry by id; it "
                    "does not delete it, because the log is a history. Order "
                    "matters - ur/resolve.py replays in sequence.",
            "corrections": []}


def load_log(work: Path) -> dict:
    p = work / "corrections.json"
    if not p.exists():
        clip = json.loads((work / "clip.json").read_text(encoding="utf-8"))
        return empty_log(clip["possession_id"])
    return json.loads(p.read_text(encoding="utf-8"))


def active(log: dict) -> list[dict]:
    """The corrections that still apply, in order, after replaying reverts."""
    reverted = {c["target"] for c in log["corrections"] if c["op"] == "revert"}
    return [c for c in log["corrections"]
            if c["op"] != "revert" and c["id"] not in reverted]


# --------------------------------------------------------------------------- #
# the operations


def _bracket(player: dict, f: int) -> tuple[int | None, int | None]:
    """The last anchored frame at or before f, and the first at or after."""
    st = player["state"]
    lo = next((k for k in range(f, -1, -1) if st[k] in ANCHORED), None)
    hi = next((k for k in range(f, len(st)) if st[k] in ANCHORED), None)
    return lo, hi


def apply_anchor(player: dict, f: int, xy) -> dict:
    """docs/05's ramped re-fit. Returns what changed, for the dry run."""
    est = player["est"]
    if est[f] is None:
        # An `unknown` sample states no position at all, so there is no offset to
        # ramp. The anchor becomes the position outright and the ramp still runs,
        # so the span either side meets its observations.
        cur = np.asarray(xy, float)
    else:
        cur = np.asarray(est[f], float)
    target = np.asarray(xy, float)
    delta = target - cur
    lo, hi = _bracket(player, f)

    touched = []
    span_lo = 0 if lo is None else lo
    span_hi = len(est) - 1 if hi is None else hi
    for k in range(span_lo, span_hi + 1):
        if k == f:
            w = 1.0
        elif k < f:
            w = 1.0 if lo is None or f == lo else (k - lo) / (f - lo)
        else:
            w = 1.0 if hi is None or hi == f else (hi - k) / (hi - f)
        if w <= 0.0:
            continue
        if est[k] is None:
            if k != f:
                continue                      # nothing to shift
            est[k] = [round(float(v), 3) for v in target]
        else:
            p = np.asarray(est[k], float) + delta * w
            est[k] = [round(float(v), 3) for v in p]
        # A human's knowledge shrinks the doubt in proportion to how near it is.
        player["sigma"][k] = round(float(player["sigma"][k] * (1.0 - w)
                                         + CONFIRMED_SIGMA * w), 3)
        if k != f and player["state"][k] not in ANCHORED:
            touched.append(k)
    player["state"][f] = "confirmed"
    player["sigma"][f] = CONFIRMED_SIGMA
    player["est"][f] = [round(float(v), 3) for v in target]
    return {"lo": lo, "hi": hi, "reshaped": len(touched)}


def apply_swap(players: dict, a: str, b: str, from_f: int) -> dict:
    """Exchange two slots' trajectories from `from_f` to the end.

    Everything that describes where a slot was goes across together — position,
    state, sigma, the detection index and the association record. Swapping the
    positions alone would leave each slot pointing at the other's detections,
    which is a subtler wrong than the one being fixed.
    """
    A, B = players[a], players[b]
    if A["team"] != B["team"]:
        raise ValueError(f"{a} is {A['team']} and {b} is {B['team']}; AD-3 forbids "
                         "association across teams, so a cross-team swap is never "
                         "the right fix")
    n = 0
    for key in ("est", "state", "sigma", "det", "assoc"):
        if key not in A or key not in B:
            continue
        A[key][from_f:], B[key][from_f:] = B[key][from_f:], A[key][from_f:]
        n = len(A[key]) - from_f
    return {"frames": n}


def apply_confirm(player: dict, f: int) -> dict:
    before = player["state"][f]
    if player["est"][f] is None:
        raise ValueError(f"cannot confirm {player['id']} at frame {f}: it states "
                         "no position. Place it with an anchor instead.")
    player["state"][f] = "confirmed"
    player["sigma"][f] = CONFIRMED_SIGMA
    return {"was": before}


# --------------------------------------------------------------------------- #


def resolve(doc: dict, log: dict, *, verbose: bool = True) -> dict:
    players = {p["id"]: p for p in doc["players"]}
    applied = []
    for c in active(log):
        op = c["op"]
        if op == "anchor":
            r = apply_anchor(players[c["slot"]], int(c["f"]), c["xy"])
        elif op == "swap":
            r = apply_swap(players, c["slots"][0], c["slots"][1], int(c["from_f"]))
        elif op == "confirm":
            r = apply_confirm(players[c["slot"]], int(c["f"]))
        else:
            raise ValueError(f"unknown correction op {op!r}")
        applied.append({**c, "effect": r})
        if verbose:
            print(f"    {c['id']:>4} {op:<8} {r}")

    obs = np.array([[x in ANCHORED for x in p["state"]] for p in doc["players"]])
    doc["derived"]["coverage"] = obs.sum(axis=0).tolist()
    doc["corrections_applied"] = [
        {k: v for k, v in c.items() if k != "effect"} for c in applied]
    doc["notice"] = (doc.get("notice", "") +
                     (f" {len(applied)} human correction(s) applied by ur.resolve; "
                      "tracks.json is unchanged (AD-6)." if applied else
                      " No corrections applied."))
    return doc


def load_uncorrected(work: Path) -> dict:
    """Rebuild possession.json from tracks.json, with no corrections."""
    from .possess import build
    return build(work, verbose=False)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="ur.resolve")
    p.add_argument("work")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--verify-revert", action="store_true",
                   help="check that reverting every correction reproduces the "
                        "uncorrected file byte for byte")
    a = p.parse_args(argv)
    work = Path(a.work)
    log = load_log(work)

    if a.verify_revert:
        base = json.dumps(load_uncorrected(work), indent=1, sort_keys=True)
        allrev = dict(log)
        allrev["corrections"] = list(log["corrections"]) + [
            {"id": f"r-{c['id']}", "op": "revert", "target": c["id"]}
            for c in log["corrections"] if c["op"] != "revert"]
        got = json.dumps(resolve(load_uncorrected(work), allrev, verbose=False),
                         indent=1, sort_keys=True)
        same = base == got
        print(f"[resolve] revert-everything reproduces the uncorrected file: "
              f"{'YES, byte for byte' if same else 'NO'}")
        return 0 if same else 1

    n = len(active(log))
    print(f"[resolve] {len(log['corrections'])} correction(s) in the log, "
          f"{n} active after reverts")
    doc = resolve(load_uncorrected(work), log)
    if a.dry_run:
        print("[resolve] dry run; nothing written")
        return 0
    (work / "possession.json").write_text(json.dumps(doc, indent=1) + chr(10),
                                          encoding="utf-8")
    print(f"[resolve] wrote {work / 'possession.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
