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

- **anchor** — a human places a slot, or the disc, at a position on a frame.
  `slot: "disc"` is the disc; AD-2's fourteen are players and cannot collide
  with it, so the disc needs no operation and no file of its own.
- **swap** — exchange two slots' trajectories from a frame onward.
- **detach** — a human says this slot is on nobody over a span; it becomes
  `unknown`. #26.
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

from . import human as HU
from ur import grading as GV

CONFIRMED_SIGMA = 0.3          # docs/05
# What brackets an anchor's ramp: a real observation of the slot, which docs/05
# says is `observed` or `confirmed` and nothing else.
ANCHORED = {"observed", "confirmed"}
# What counts as a slot being in shot, and a different question. `ur/possess.py`
# answers it with `observed`, `provisional` and `weak` - a re-acquisition is an
# observation of somebody and a weak sample is a player seen on a weakly placed
# frame; both were seen. This module used to recompute `derived.coverage` over
# ANCHORED instead, so running the resolver over a possession with no
# corrections in it at all dropped p0003's coverage to 0 on 67 frames the
# pipeline had counted. The viewer's own `coverage()` agrees with possess, so
# the page and the file it was built from disagreed the moment anybody resolved.
COVERAGE_STATES = {"observed", "provisional", "weak", "confirmed"}

# The disc is a fourth thing a person can place, and it is not a slot. AD-2's
# fourteen are *players*, never created and never destroyed; `"disc"` cannot be
# mistaken for one of `O1`-`D7`, so it rides the same `anchor` operation and the
# same file rather than earning a schema of its own. #8 asked for no new
# decision, no new file and no schema change, and this is what that costs.
DISC = "disc"
# What brackets a disc anchor. The disc's only real observations are the frames a
# human tagged a catch or a throw on - `interpolated` is the straight line drawn
# BETWEEN two of those, so treating it as an observation would pin the ramp to
# the estimate it is meant to correct.
DISC_ANCHORED = {"confirmed"}


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


def _flags(obj: dict, n: int) -> list[bool]:
    """`obj`'s human-touched marks as a per-frame array, created if absent.

    `resolve()` normalises these on the way in and serialises them back to frame
    indices on the way out, so everything between here and there can just index
    them. A stage that calls an operation directly still gets the marks.
    """
    cur = obj.get(HU.KEY)
    if not isinstance(cur, list) or len(cur) != n or not all(
            isinstance(v, bool) for v in cur):
        cur = HU.as_flags(obj, n)
        obj[HU.KEY] = cur
    return cur


def _ramp(f: int, lo: int | None, hi: int | None, n: int):
    """docs/05's weights, yielded `(frame, weight)` over the whole bracket.

    Pulled out of `apply_anchor` when the disc grew the same operation. The two
    differ only in what counts as a bracketing observation and in what they carry
    per frame; a second copy of the ramp would have been a second place for the
    arithmetic to drift.
    """
    for k in range(0 if lo is None else lo, (n - 1 if hi is None else hi) + 1):
        if k == f:
            w = 1.0
        elif k < f:
            w = 1.0 if lo is None or f == lo else (k - lo) / (f - lo)
        else:
            w = 1.0 if hi is None or hi == f else (hi - k) / (hi - f)
        if w > 0.0:
            yield k, w


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
    mark = _flags(player, len(est))
    for k, w in _ramp(f, lo, hi, len(est)):
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
        # Every frame this moved is now partly a person's, whatever its evidence
        # state still says. ur/human.py is why that has to be written down: the
        # ramp's output keeps reading `predicted` and would otherwise be counted
        # as the tracker's own work one frame away from the anchor.
        mark[k] = True
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
    # `human` goes across with the rest. A mark left behind would say the
    # tracker's own output had been hand-placed, which is the accusation running
    # backwards - and would then exclude it from the very metrics it belongs in.
    _flags(A, len(A["est"]))
    _flags(B, len(B["est"]))
    for key in ("est", "state", "sigma", "det", "assoc", HU.KEY):
        if key not in A or key not in B:
            continue
        A[key][from_f:], B[key][from_f:] = B[key][from_f:], A[key][from_f:]
        n = len(A[key]) - from_f
    return {"frames": n}


def apply_disc_anchor(doc: dict, f: int, xy, z=None) -> dict:
    """Place the disc itself, with the same ramp and the same marks.

    A person watching can see where the disc is on a frame the solver only
    interpolated through, and `docs/27` is clear that nothing in this pipeline
    has ever detected one - so this is the only way a disc position can become
    anything better than a straight line between two tags.

    Two differences from a slot, both of them about what the disc has instead of
    an observation. It brackets against `confirmed` only (`DISC_ANCHORED`), and
    its height is left alone unless stated: a person clicking on the grass is
    saying where the disc is over the field, not how high it is, and inventing a
    `z` from that click would be a measurement nobody took.
    """
    disc, meta = doc.get("disc"), doc.get("disc_meta")
    if not disc or not meta:
        raise ValueError(
            f"cannot place the disc on frame {f}: this possession has no disc. "
            "Run `python -m ur.disc` first - there is nothing to correct.")
    n = len(disc)
    st = meta["state"]
    lo = next((k for k in range(f, -1, -1) if st[k] in DISC_ANCHORED), None)
    hi = next((k for k in range(f, n) if st[k] in DISC_ANCHORED), None)
    target = np.asarray(xy, float)
    cur = np.asarray(disc[f][:2], float) if disc[f] else target
    delta = target - cur
    height = float(z) if z is not None else (
        disc[f][2] if disc[f] and len(disc[f]) > 2 else 1.0)

    mark = _flags(meta, n)
    reshaped = 0
    for k, w in _ramp(f, lo, hi, n):
        if disc[k] is None:
            if k != f:
                continue
            disc[k] = [0.0, 0.0, height]
        q = np.asarray(disc[k][:2], float) + delta * w
        disc[k] = [round(float(q[0]), 3), round(float(q[1]), 3), disc[k][2]]
        meta["sigma"][k] = round(float(meta["sigma"][k] * (1.0 - w)
                                       + CONFIRMED_SIGMA * w), 3)
        mark[k] = True
        reshaped += k != f
    disc[f] = [round(float(target[0]), 3), round(float(target[1]), 3), height]
    meta["state"][f] = "confirmed"
    meta["sigma"][f] = CONFIRMED_SIGMA
    # `source` is what the disc stage calls provenance, and a placed disc is a
    # human's however the frame was reached. docs/03 already has `human` there
    # for a tagged frame; this is the same claim about the position instead of
    # about the holder.
    meta["source"][f] = "human"
    return {"lo": lo, "hi": hi, "reshaped": reshaped}


# The sigma an `unknown` sample carries: the tracker's own, so a detached frame
# is shaped exactly like one the tracker never had.
UNKNOWN_SIGMA = 16.0


def apply_detach(player: dict, from_f: int, to_f: int | None) -> dict:
    """A human says this slot is on nobody, from `from_f` until it re-acquires.

    **The commonest thing a person has to say, and until #26 there was no way to
    say it.** A slot that loses its player keeps dead reckoning, and on 11-33 %
    of frames of every published possession one of them drifts within 1.5 yd of
    a slot that has a real detection - two labels on one person, which is what
    makes a roster pass unreadable. Neither existing operation fits. `swap`
    claims a real player is under the wrong name; `anchor` needs somewhere to
    put them, and the reason the slot is lost is usually that they left frame.

    The span becomes `unknown`, which is what the rest of the pipeline already
    means by "this slot states no position": no marker (docs/25 R5), no
    contribution to coverage, nothing for the disc to rest on. AD-2 is intact -
    the slot is neither created nor destroyed, it stops claiming.

    **It refuses to cross an observation.** A frame the camera actually saw
    somebody on is evidence, and removing it is not a correction but a deletion;
    AD-6 keeps the tracks for exactly that reason. If a person believes an
    `observed` frame is on the wrong person, that is a `swap`, and the refusal
    says so rather than quietly dropping the frame.
    """
    st, est = player["state"], player["est"]
    n = len(st)
    # An open-ended detach stops where the slot re-acquires, not at the end of
    # the possession. "This one is on nobody" is a claim about the stretch the
    # tracker is guessing through, and it ends the moment the camera sees
    # somebody again - the same boundary the viewer's relabel already uses, so a
    # person says *from here* and does not have to go and find the other end.
    if to_f is None:
        end = next((k - 1 for k in range(from_f, n) if st[k] in ANCHORED), n - 1)
    else:
        end = int(to_f)
    kept = [k for k in range(from_f, end + 1) if st[k] in ANCHORED]
    if kept:
        raise ValueError(
            f"cannot detach {player['id']} over frames {from_f}-{end}: "
            f"{len(kept)} of them are {st[kept[0]]} (first at {kept[0]}). The "
            "camera saw somebody there and AD-6 keeps what it saw. If that "
            "somebody is under the wrong label, swap it.")
    mark = _flags(player, n)
    for k in range(from_f, end + 1):
        est[k] = None
        st[k] = "unknown"
        player["sigma"][k] = UNKNOWN_SIGMA
        # As human-sourced as a placed frame. A person removing the frames the
        # tracker got wrong would otherwise raise its recall, which is #8's trap
        # running backwards.
        mark[k] = True
    return {"from": from_f, "to": end, "cleared": end - from_f + 1}


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
        if op == "anchor" and c.get("slot") == DISC:
            r = apply_disc_anchor(doc, int(c["f"]), c["xy"], c.get("z"))
        elif op == "anchor":
            r = apply_anchor(players[c["slot"]], int(c["f"]), c["xy"])
        elif op == "swap":
            r = apply_swap(players, c["slots"][0], c["slots"][1], int(c["from_f"]))
        elif op == "detach":
            r = apply_detach(players[c["slot"]], int(c["from_f"]),
                             c.get("to_f"))
        elif op == "confirm":
            r = apply_confirm(players[c["slot"]], int(c["f"]))
        else:
            raise ValueError(f"unknown correction op {op!r}")
        applied.append({**c, "effect": r})
        if verbose:
            print(f"    {c['id']:>4} {op:<8} {r}")

    # Back to the stored shape. Frame indices rather than a per-frame array,
    # because the list is empty on everything the pipeline produced alone and a
    # 555-long run of `false` would ride onto every published page for nothing.
    for obj in [*doc["players"]] + ([doc["disc_meta"]] if doc.get("disc_meta")
                                    else []):
        obj[HU.KEY] = HU.from_flags(_flags(obj, len(doc["players"][0]["est"])))

    obs = np.array([[x in COVERAGE_STATES for x in p["state"]]
                    for p in doc["players"]])
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
        # The baseline is resolve() over an EMPTY log, not the raw rebuild. resolve
        # annotates the document it returns (`notice`, `corrections_applied`), so
        # comparing against the rebuild would test those annotations rather than
        # the revert - and would report a failure that is not one. Same baseline
        # as tools/m5_resolve.py, because two checks of one property that
        # disagree are worse than one check.
        base = json.dumps(resolve(load_uncorrected(work),
                                  empty_log(log["possession_id"]), verbose=False),
                          indent=1, sort_keys=True)
        allrev = dict(log)
        allrev["corrections"] = list(log["corrections"]) + [
            {"id": f"r-{c['id']}", "op": "revert", "target": c["id"]}
            for c in log["corrections"] if c["op"] != "revert"]
        got = json.dumps(resolve(load_uncorrected(work), allrev, verbose=False),
                         indent=1, sort_keys=True)
        same = base == got
        n = len([c for c in log["corrections"] if c["op"] != "revert"])
        print(f"[resolve] reverting all {n} correction(s) reproduces the "
              f"uncorrected output: {'YES, byte for byte' if same else 'NO'}")
        return 0 if same else 1

    n = len(active(log))
    print(f"[resolve] {len(log['corrections'])} correction(s) in the log, "
          f"{n} active after reverts")
    doc = resolve(load_uncorrected(work), log)
    if a.dry_run:
        print("[resolve] dry run; nothing written")
        return 0
    print(f"[resolve] wrote {GV.write(work, doc)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
