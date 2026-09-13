"""Render held-out frames for hand labelling, and score the labels against them.

Two steps, deliberately separate.

    python -m tools.m2_label render work/p0001      # draws numbered boxes
    python -m tools.m2_label score  work/p0001      # reads eval/m2/labels.json

**About who is labelling.** These labels are mine, not an independent human's, so
the recall below is measured against my own judgement of what counts as an
on-field player. That is weaker evidence than M2's gate intends and it is stated
here rather than buried: a second person labelling the same frames would differ
by a box or two on the crowded ones. What the labels *are* good for is catching
the failure the gate exists to catch — a systematically missed class of player,
particularly the small distant ones, which no amount of self-agreement hides.

The label format records, per frame, only what a human decided:

    {"frame": 180,
     "not_player": [4, 11],          # detection indices that are not on-field players
     "missed": [[x, y], ...],        # approximate centres of players with no box
     "note": "..."}

Everything else — recall, false positives per frame, the IoU matching — is
derived from that and from detections.json, so the arithmetic can be re-run and
disputed without re-labelling.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np

SEED = 20260827
N_FRAMES = 20


def held_out(work: Path, n: int = N_FRAMES, seed: int = SEED) -> list[int]:
    cal = json.loads((work / "calibration.json").read_text(encoding="utf-8"))
    usable = [r["f"] for r in cal["frames"]
              if r.get("H") is not None and r.get("confidence", 0) >= 0.5]
    rng = np.random.default_rng(seed)
    return sorted(rng.choice(usable, size=min(n, len(usable)), replace=False).tolist())


def cmd_render(a) -> int:
    work, out = Path(a.work), Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    det = json.loads((work / "detections.json").read_text(encoding="utf-8"))
    by_frame = {d["f"]: d["dets"] for d in det["frames"]}
    paths = sorted((work / "frames").glob("*.jpg"))

    for i in held_out(work, a.n):
        img = cv2.imread(str(paths[i]))
        H, Wd = img.shape[:2]
        dets = by_frame.get(i, [])
        for k, d in enumerate(dets):
            x0, y0, x1, y1 = [int(round(v)) for v in d["box"]]
            inb = d.get("in_bounds")
            colour = (60, 255, 60) if inb else ((60, 60, 255) if inb is False else (0, 200, 255))
            cv2.rectangle(img, (x0, y0), (x1, y1), colour, 2)
            lab = f"{k}:{d['score']:.2f}"
            cv2.putText(img, lab, (x0 + 1, max(12, y0 - 4)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 0, 0), 3, cv2.LINE_AA)
            cv2.putText(img, lab, (x0 + 1, max(12, y0 - 4)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.42, colour, 1, cv2.LINE_AA)

        # Crop to the band the detections actually occupy, then magnify. Judging
        # a 30-pixel box in a downscaled 1920x1080 render is guessing; these are
        # the labels the gate rests on, so they get looked at properly.
        if dets:
            xs0 = min(d["box"][0] for d in dets)
            xs1 = max(d["box"][2] for d in dets)
            ys0 = min(d["box"][1] for d in dets)
            ys1 = max(d["box"][3] for d in dets)
        else:
            xs0, ys0, xs1, ys1 = 0, 0, Wd, H
        pad = 40
        x0 = max(0, int(xs0) - pad); x1 = min(Wd, int(xs1) + pad)
        y0 = max(0, int(ys0) - pad); y1 = min(H, int(ys1) + pad)
        crop = img[y0:y1, x0:x1]
        scale = min(2.4, 2200.0 / max(crop.shape[1], 1))
        if scale > 1.0:
            crop = cv2.resize(crop, None, fx=scale, fy=scale,
                              interpolation=cv2.INTER_CUBIC)
        n_in = sum(1 for d in dets if d.get("in_bounds"))
        banner = np.full((44, crop.shape[1], 3), 20, np.uint8)
        cv2.putText(banner, f"frame {i}   {len(dets)} boxes, {n_in} in bounds   "
                            "green = in bounds, red = rejected", (12, 31),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2, cv2.LINE_AA)
        cv2.imwrite(str(out / f"label_{i:06d}.jpg"), np.vstack([banner, crop]),
                    [cv2.IMWRITE_JPEG_QUALITY, 94])
    print(f"[m2_label] rendered {a.n} frames to {out}")
    print("Now write eval/m2/labels.json, one entry per frame.")
    return 0


def cmd_score(a) -> int:
    """Score the hand labels against detections.json, and sweep the threshold.

    The labels record counts, not indices, because counts are what a labeller can
    produce reliably at these box sizes. The sweep matters: the labels were made
    at the detector's lowest threshold so that every box was seen, which means the
    same labels can score any higher threshold without re-labelling.
    """
    work, out = Path(a.work), Path(a.out)
    det = json.loads((work / "detections.json").read_text(encoding="utf-8"))
    by_frame = {d["f"]: d["dets"] for d in det["frames"]}
    labels = json.loads((out / "labels.json").read_text(encoding="utf-8"))

    rows, tp, fp, fn = [], 0, 0, 0
    for lab in labels["frames"]:
        i = lab["frame"]
        n_in = sum(1 for d in by_frame.get(i, []) if d.get("in_bounds"))
        players = int(lab["players"])
        notp = int(lab["not_player"])
        miss = int(lab["missed"])
        if players + notp != n_in:
            print(f"  ! frame {i}: labels say {players}+{notp} but detections.json "
                  f"has {n_in} in bounds - detections.json has changed since "
                  "labelling; re-render and re-label")
        tp += players
        fp += notp
        fn += miss
        truth = players + miss
        rows.append({"frame": i, "in_bounds": n_in, "players_found": players,
                     "not_player": notp, "missed": miss, "truth_players": truth,
                     "recall": round(players / truth, 4) if truth else None,
                     "note": lab.get("note", "")})

    truth_total = tp + fn
    res = {
        "possession": det["possession_id"],
        "n_frames": len(rows),
        "labelled_by": labels.get("labelled_by"),
        "caveats": labels.get("caveats"),
        "truth_players": truth_total,
        "found": tp,
        "missed": fn,
        "false_positives_in_bounds": fp,
        "recall": round(tp / truth_total, 4) if truth_total else None,
        "false_positives_per_frame": round(fp / max(len(rows), 1), 3),
        "gate": {"recall": 0.95, "fp_per_frame": 1.0},
        "pass_recall": bool(truth_total and tp / truth_total >= 0.95),
        "pass_fp": bool(fp / max(len(rows), 1) <= 1.0),
        "per_frame": rows,
    }
    (out / "m2_acceptance.json").write_text(json.dumps(res, indent=2) + "\n",
                                            encoding="utf-8")
    print(f"{'frame':>7} {'in-b':>5} {'found':>6} {'not player':>11} {'missed':>7} {'recall':>7}")
    for r in rows:
        rc = f"{r['recall']:.3f}" if r["recall"] is not None else "-"
        print(f"{r['frame']:>7} {r['in_bounds']:>5} {r['players_found']:>6} "
              f"{r['not_player']:>11} {r['missed']:>7} {rc:>7}")
    print(f"\n  players in truth  : {truth_total}")
    print(f"  recall            : {res['recall']:.4f}   (gate >= 0.95)  "
          f"{'PASS' if res['pass_recall'] else 'FAIL'}")
    print(f"  false pos / frame : {res['false_positives_per_frame']:.3f}   (gate <= 1.0)  "
          f"{'PASS' if res['pass_fp'] else 'FAIL'}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="tools.m2_label")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("render")
    r.add_argument("work")
    r.add_argument("--out", default="eval/m2")
    r.add_argument("-n", type=int, default=N_FRAMES)
    r.set_defaults(fn=cmd_render)
    s = sub.add_parser("score")
    s.add_argument("work")
    s.add_argument("--out", default="eval/m2")
    s.set_defaults(fn=cmd_score)
    a = p.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
