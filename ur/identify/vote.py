"""M5 — vote a jersey number per tracklet, and say `null` when unsure.

    python -m ur.identify.vote work/p0001        # -> identities.json

`docs/07-licenses.md` sets the expectation this module is built to: appearance
re-ID cannot tell teammates apart, so identity comes from **track continuity**
first, **jersey OCR voted per tracklet** second, and **one human assignment** last.
This is the middle one, and it only works because of the first: a slot is one
person for a long stretch, so a reader that is right 60 % of the time when it
reads anything at all can still be decisive over two hundred frames.

**Voting, not reading.** A single frame's OCR is close to useless here — measured
at 18.8 % accuracy on crops a human had already found legible. What makes the
vote work is that the *errors are scattered* and the truth is not: a wrong read
of 59 for 50 happens on one pose and not the next, while the right answer recurs
whenever the number is square to the camera. So candidates are accumulated over
the whole tracklet, weighted by the reader's own confidence, and the winner has
to clear two bars:

- **support** — enough weight behind it that it is not one lucky frame;
- **margin** — enough more than the runner-up that the two are not a coin flip.

Failing either emits `null`, and `docs/04-milestones.md` M5 asks for exactly
that: "Emit `null` freely rather than guessing." A wrong number on a slot is
worse than no number, because a coach reading a name trusts it.

**A slot is not always one person.** M4 measured two identity switches on this
possession, so a slot can hold two people and the modal number is then the one it
held longest. The runner-up is reported in `alternatives` rather than discarded,
because on a slot that switched, the runner-up is the other player and that is a
signal rather than noise.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np

# A winner needs this much summed confidence behind it. Two confident reads, or
# several hesitant ones.
MIN_SUPPORT = 1.5
# ...and this much more than the runner-up, as a fraction of the winner's weight.
MIN_MARGIN_FRAC = 0.40


def gather(work: Path, *, gpu: bool = True, verbose: bool = True) -> dict:
    from .ocr import MIN_CONF, JerseyReader

    det = json.loads((work / "detections.json").read_text(encoding="utf-8"))
    trk = json.loads((work / "tracks.json").read_text(encoding="utf-8"))
    by = {d["f"]: d["dets"] for d in det["frames"]}
    paths = sorted((work / "frames").glob("*.jpg"))

    # (frame -> [(slot, det index)]) so each frame is decoded once, not 14 times.
    per_frame: dict[int, list[tuple[str, int]]] = defaultdict(list)
    for s in trk["slots"]:
        for smp in s["samples"]:
            if smp["state"] == "observed" and smp["det"] is not None:
                per_frame[smp["f"]].append((s["slot"], smp["det"]))

    reader = JerseyReader(gpu=gpu)
    reads: dict[str, list[dict]] = defaultdict(list)
    n_crops = n_reads = 0
    for k, f in enumerate(sorted(per_frame)):
        img = cv2.imread(str(paths[f]))
        for slot, di in per_frame[f]:
            n_crops += 1
            for c in reader.read(img, by[f][di]["box"]):
                reads[slot].append({"f": f, **c})
                n_reads += 1
        if verbose and k % 40 == 0:
            print(f"[identify] {k}/{len(per_frame)} frames, {n_reads} candidate "
                  f"reads from {n_crops} crops", flush=True)
    return {"reads": reads, "crops": n_crops, "min_conf": MIN_CONF}


def tally(reads: list[dict]) -> dict:
    """Confidence-weighted vote over one tracklet's candidate reads."""
    weight: dict[int, float] = defaultdict(float)
    count: dict[int, int] = defaultdict(int)
    for r in reads:
        weight[r["jersey"]] += r["conf"]
        count[r["jersey"]] += 1
    ranked = sorted(weight.items(), key=lambda kv: (-kv[1], kv[0]))
    if not ranked:
        return {"jersey": None, "method": "none", "support": 0.0,
                "confidence": 0.0, "alternatives": []}
    (top, w_top), *rest = ranked
    w_next = rest[0][1] if rest else 0.0
    margin = (w_top - w_next) / w_top if w_top else 0.0
    ok = w_top >= MIN_SUPPORT and margin >= MIN_MARGIN_FRAC
    return {
        "jersey": top if ok else None,
        "method": "ocr_vote" if ok else "none",
        "support": round(w_top, 3),
        "reads": count[top],
        "margin": round(margin, 3),
        "confidence": round(min(1.0, w_top / 10.0) * margin, 3) if ok else 0.0,
        "why_null": (None if ok else
                     ("no candidate cleared the support bar"
                      if w_top < MIN_SUPPORT else
                      "the top two candidates were too close to separate")),
        "alternatives": [{"jersey": j, "support": round(w, 3), "reads": count[j]}
                         for j, w in ranked[1:4]],
    }


def run(work: Path, *, gpu: bool = True, verbose: bool = True) -> dict:
    trk = json.loads((work / "tracks.json").read_text(encoding="utf-8"))
    g = gather(work, gpu=gpu, verbose=verbose)

    slots = []
    for s in trk["slots"]:
        rs = g["reads"].get(s["slot"], [])
        t = tally(rs)
        slots.append({"slot": s["slot"], "team": s["team"],
                      "frames_observed": s["observed"],
                      "frames_with_a_read": len({r["f"] for r in rs}),
                      **t})

    doc = {
        "schema": "ultimate-radar/identities@1",
        "possession_id": trk["possession_id"],
        "method": {
            "module": "ur.identify.vote",
            "reader": "EasyOCR, English, digits only",
            "min_read_confidence": g["min_conf"],
            "min_support": MIN_SUPPORT,
            "min_margin_fraction": MIN_MARGIN_FRAC,
            "measured": ("single-frame OCR was 18.8 % accurate and 60 % precise on "
                         "48 crops a human had already read (eval/m4). This votes "
                         "over the tracklet because the errors scatter and the "
                         "truth does not."),
            "null_policy": "docs/04 M5: emit null freely rather than guessing. A "
                           "wrong number is worse than no number.",
            "crops_read": g["crops"],
        },
        "slots": slots,
    }
    (work / "identities.json").write_text(json.dumps(doc, indent=1) + chr(10),
                                          encoding="utf-8")
    if verbose:
        named = sum(1 for s in slots if s["jersey"] is not None)
        print(f"\n[identify] {named} of {len(slots)} slots named, "
              f"{len(slots) - named} honestly null")
        for s in slots:
            alt = ", ".join(f"{a['jersey']}({a['support']:.1f})"
                            for a in s["alternatives"][:2])
            print(f"    {s['slot']:>3} {s['team']:>5}  "
                  f"jersey {str(s['jersey']):>4}  support {s['support']:>6.2f}  "
                  f"margin {s['margin'] if s['jersey'] else 0:>5}  "
                  f"reads {s['frames_with_a_read']:>3}/{s['frames_observed']:<3} "
                  f"alt: {alt}")
    return doc


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="ur.identify.vote")
    p.add_argument("work")
    p.add_argument("--cpu", action="store_true")
    a = p.parse_args(argv)
    run(Path(a.work), gpu=not a.cpu)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
