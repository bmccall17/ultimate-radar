"""Render every in-bounds detection in the M2 held-out frames for hand labelling.

    python -m tools.m3_label render work/p0001     # -> eval/m3/sheet_00.png ...
    python -m tools.m3_label score  work/p0001     # reads eval/m3/team_labels.json

One labelling pass answers both of M3's open questions at once, which is why it is
a single tool:

- **team accuracy**, the M3 gate, needs a per-detection team for each of the 233
  players M2 counted. M2's labels are counts, not identities, so they cannot be
  reused for this.
- **M2's deferred false-positive gate** needs to know which in-bounds boxes are
  referees and which are camera crew. The same crops say so.

Crops are drawn at a fixed magnification with nearest-neighbour interpolation and
pinned top-left, for the reason `tools/jerseysheet.py` gives: rescaling a 55-pixel
player to match a 113-pixel one destroys the evidence the label rests on. The box
is shown whole rather than cropped to the torso, because kit, shorts, cap and
posture together are what make a referee or a camera operator recognisable, and a
torso patch alone loses that.

**The crop is padded and the box outline drawn on it.** A box tight around two
overlapping players looks identical to a box around either one of them, so a crop
cut exactly at the box edges asks the labeller to guess which person is being
labelled. Showing the surroundings and the box together removes the guess - and
the overlapping pair is precisely the case M2 measured as its only miss, so it is
common enough here to matter.

The label file records one class per (frame, detection index):

    {"f": 115, "i": 8, "cls": "ref"}

`cls` is one of `sol` (light kit), `chill` (dark kit), `ref` (on-field official),
`crew` (camera operator, photographer, anyone else not playing), `unsure`.
Everything else - accuracy, the confusion matrix, the recomputed false-positive
rate - is derived from that plus `detections.json`, so the arithmetic can be
re-run and disputed without re-labelling.

**These labels are the agent's own, not an independent human's.** Same caveat as
`eval/m2/labels.json`, and it matters more here, because a 99 % gate on 233 items
means two mistakes is the whole budget.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np

MAX_ZOOM = 5.0
CELL_W, CELL_H = 200, 420
COLS, ROWS = 10, 3
PAD = 0.22          # fraction of box size shown around it, so the box is legible in context


def label_frames(work: Path, m2: Path) -> list[int]:
    labels = json.loads((m2 / "labels.json").read_text(encoding="utf-8"))
    return [int(r["frame"]) for r in labels["frames"]]


def in_bounds_index(work: Path, m2: Path) -> list[tuple[int, int]]:
    """(frame, detection index) for every in-bounds box, in a stable order."""
    det = json.loads((work / "detections.json").read_text(encoding="utf-8"))
    by = {d["f"]: d["dets"] for d in det["frames"]}
    out = []
    for f in label_frames(work, m2):
        for i, d in enumerate(by.get(f, [])):
            if d.get("in_bounds"):
                out.append((f, i))
    return out


def cmd_render(a) -> int:
    work, out, m2 = Path(a.work), Path(a.out), Path(a.m2)
    out.mkdir(parents=True, exist_ok=True)
    det = json.loads((work / "detections.json").read_text(encoding="utf-8"))
    by = {d["f"]: d["dets"] for d in det["frames"]}
    paths = sorted((work / "frames").glob("*.jpg"))

    items = in_bounds_index(work, m2)
    cells, cur_f, img = [], None, None
    for f, i in items:
        if f != cur_f:
            img = cv2.imread(str(paths[f]))
            cur_f = f
        d = by[f][i]
        x0, y0, x1, y1 = [int(round(v)) for v in d["box"]]
        px, py = int(round(PAD * (x1 - x0))), int(round(PAD * (y1 - y0)))
        cx0, cy0 = max(0, x0 - px), max(0, y0 - py)
        cx1, cy1 = min(img.shape[1], x1 + px), min(img.shape[0], y1 + py)
        crop = img[cy0:cy1, cx0:cx1].copy()
        cell = np.full((CELL_H, CELL_W, 3), 25, np.uint8)
        zoom = 1.0
        if crop.size:
            # Fit the whole padded box in the cell rather than magnifying a fixed
            # amount and clipping it. The judgement here is kit and role, which
            # needs the whole figure - stance, shorts, cap - not a magnified
            # torso. The true box height is printed so the loss is never hidden.
            zoom = min(MAX_ZOOM, (CELL_W - 2) / crop.shape[1],
                       (CELL_H - 24) / crop.shape[0])
            z = cv2.resize(crop, None, fx=zoom, fy=zoom,
                           interpolation=cv2.INTER_NEAREST if zoom >= 1
                           else cv2.INTER_AREA)
            cv2.rectangle(z, (int((x0 - cx0) * zoom), int((y0 - cy0) * zoom)),
                          (int((x1 - cx0) * zoom) - 1, int((y1 - cy0) * zoom) - 1),
                          (60, 230, 255), 2)
            z = z[:CELL_H - 24, :CELL_W]
            ox = (CELL_W - z.shape[1]) // 2
            cell[24:24 + z.shape[0], ox:ox + z.shape[1]] = z
        cv2.putText(cell, f"f{f} #{i} h{y1 - y0} x{zoom:.1f}", (3, 16),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.44, (235, 235, 235), 1, cv2.LINE_AA)
        cells.append(cell)

    per = COLS * ROWS
    n_sheets = (len(cells) + per - 1) // per
    for s in range(n_sheets):
        chunk = cells[s * per:(s + 1) * per]
        rows = (len(chunk) + COLS - 1) // COLS
        sheet = np.full((rows * CELL_H, COLS * CELL_W, 3), 25, np.uint8)
        for k, c in enumerate(chunk):
            r, cc = divmod(k, COLS)
            sheet[r * CELL_H:(r + 1) * CELL_H, cc * CELL_W:(cc + 1) * CELL_W] = c
        p = out / f"sheet_{s:02d}.png"
        cv2.imwrite(str(p), sheet)
        print(f"[m3_label] {p}  ({len(chunk)} crops)")
    print(f"[m3_label] {len(cells)} in-bounds detections over "
          f"{len(label_frames(work, m2))} frames -> {n_sheets} sheets")
    print("Now write eval/m3/team_labels.json: one {f, i, cls} per crop.")
    return 0


def cmd_zoom(a) -> int:
    """Blow up named detections with a lot of context, to settle close calls.

    The sheet is sized for volume; a handful of boxes each frame resist it -
    two players sharing a box, or a figure near the far boards who could be a
    player standing out of play or a photographer sitting behind the line. Those
    get looked at properly rather than guessed, and which ones were looked at
    stays in the command line that produced the answer.
    """
    work, out = Path(a.work), Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    det = json.loads((work / "detections.json").read_text(encoding="utf-8"))
    by = {d["f"]: d["dets"] for d in det["frames"]}
    paths = sorted((work / "frames").glob("*.jpg"))

    picks = []
    for tok in a.picks:
        f, i = tok.split(":")
        picks.append((int(f), int(i)))

    cells = []
    for f, i in picks:
        img = cv2.imread(str(paths[f]))
        d = by[f][i]
        x0, y0, x1, y1 = [int(round(v)) for v in d["box"]]
        px, py = int(round(a.context * (x1 - x0))), int(round(a.context * (y1 - y0)))
        cx0, cy0 = max(0, x0 - px), max(0, y0 - py)
        cx1, cy1 = min(img.shape[1], x1 + px), min(img.shape[0], y1 + py)
        crop = img[cy0:cy1, cx0:cx1].copy()
        z = cv2.resize(crop, None, fx=a.zoom, fy=a.zoom, interpolation=cv2.INTER_CUBIC)
        cv2.rectangle(z, (int((x0 - cx0) * a.zoom), int((y0 - cy0) * a.zoom)),
                      (int((x1 - cx0) * a.zoom) - 1, int((y1 - cy0) * a.zoom) - 1),
                      (60, 230, 255), 2)
        sy = d.get("soccer")
        tag = (f"f{f} #{i} h{y1 - y0}"
               + (f"  soccer y={sy[1]:.1f}" if sy else "")
               + (f"  hr={d['height_ratio']:.2f}" if d.get("height_ratio") else ""))
        banner = np.full((30, z.shape[1], 3), 20, np.uint8)
        cv2.putText(banner, tag, (8, 21), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                    (255, 255, 255), 1, cv2.LINE_AA)
        cells.append(np.vstack([banner, z]))

    h = max(c.shape[0] for c in cells)
    padded = [np.vstack([c, np.full((h - c.shape[0], c.shape[1], 3), 25, np.uint8)])
              for c in cells]
    sheet = np.hstack([np.hstack([p, np.full((h, 6, 3), 25, np.uint8)]) for p in padded])
    dst = out / a.name
    cv2.imwrite(str(dst), sheet)
    print(f"[m3_label] {dst}  ({len(cells)} crops at {a.zoom}x)")
    return 0


def cmd_score(a) -> int:
    """Score ur.team against the hand labels, and report both M3 gates.

    Two gates, kept separate on purpose. Team accuracy is measured on **players
    only** - a referee has no team, so scoring one as a team error would count the
    reject test twice. The reject gate is M2's deferred false-positive gate,
    re-measured now that appearance is available.
    """
    from ur.team import assign_frame, fit_kits

    work, out = Path(a.work), Path(a.out)
    det = json.loads((work / "detections.json").read_text(encoding="utf-8"))
    cal = json.loads((work / "calibration.json").read_text(encoding="utf-8"))
    by = {d["f"]: d["dets"] for d in det["frames"]}
    paths = sorted((work / "frames").glob("*.jpg"))
    truth_doc = json.loads((out / "team_labels.json").read_text(encoding="utf-8"))
    truth = {(int(r["f"]), int(r["i"])): r["cls"] for r in truth_doc["labels"]}

    vt = cal.get("venue_transform", {})
    far = -float(vt["y_offset"]) + 160.0 / 3.0 if "y_offset" in vt else None
    kit = fit_kits(work)

    pred: dict[tuple[int, int], str] = {}
    for f in sorted({k[0] for k in truth}):
        img = cv2.imread(str(paths[f]))
        res = assign_frame(img, by[f], kit=kit, far_sideline_y=far)
        for i, r in enumerate(res):
            if (f, i) in truth:
                pred[(f, i)] = r.get("non_player") or r.get("team") or "unknown"

    keys = sorted(truth)
    players = [k for k in keys if truth[k] in ("sol", "chill")]
    nonplayers = [k for k in keys if truth[k] in ("ref", "crew")]
    unsure = [k for k in keys if truth[k] == "unsure"]

    correct = sum(1 for k in players if pred.get(k) == truth[k])
    acc = correct / max(len(players), 1)

    classes = ["sol", "chill", "ref", "crew", "unknown"]
    conf = {t: {p: 0 for p in classes} for t in ("sol", "chill", "ref", "crew", "unsure")}
    for k in keys:
        conf[truth[k]][pred.get(k, "unknown")] += 1

    caught = {c: sum(1 for k in nonplayers if truth[k] == c
                     and pred.get(k) in ("ref", "crew")) for c in ("ref", "crew")}
    n_ref = sum(1 for k in nonplayers if truth[k] == "ref")
    n_crew = sum(1 for k in nonplayers if truth[k] == "crew")
    rejected_np = caught["ref"] + caught["crew"]
    lost = [k for k in players if pred.get(k) in ("ref", "crew")]

    n_frames = len({k[0] for k in keys})
    before = len(nonplayers) / max(n_frames, 1)
    after = (len(nonplayers) - rejected_np) / max(n_frames, 1)

    res = {
        "schema": "ultimate-radar/m3-team-acceptance@1",
        "possession": det["possession_id"],
        "labelled_by": truth_doc.get("labelled_by"),
        "caveats": truth_doc.get("caveats"),
        "n_frames": n_frames,
        "n_labelled": len(keys),
        "kits": kit.as_dict(),
        "team_gate": {
            "players_in_truth": len(players),
            "correct": correct,
            "accuracy": round(acc, 4),
            "gate": 0.99,
            "pass": bool(acc >= 0.99),
            "excluded_unsure": len(unsure),
            "unsure_note": "boxes bounding a Sol and a Chill player together; no "
                           "team assignment for them can be right",
        },
        "reject_gate": {
            "note": "M2 deferred its false-positive gate to M3. This is that gate, "
                    "re-measured with appearance available. The denominator is this "
                    "pass's per-box count of non-players, not M2's per-frame count; "
                    "they differ by four and eval/m3/team_labels.json says why.",
            "non_players_in_truth": len(nonplayers),
            "referees": {"in_truth": n_ref, "rejected": caught["ref"]},
            "crew": {"in_truth": n_crew, "rejected": caught["crew"]},
            "false_positives_per_frame_before": round(before, 3),
            "false_positives_per_frame_after": round(after, 3),
            "gate": 1.0,
            "pass": bool(after <= 1.0),
            "real_players_wrongly_rejected": len(lost),
        },
        "confusion": conf,
        "errors": [{"f": k[0], "i": k[1], "truth": truth[k], "pred": pred.get(k, "unknown")}
                   for k in keys if truth[k] != "unsure" and pred.get(k, "unknown") != truth[k]],
    }
    (out / "m3_team_acceptance.json").write_text(json.dumps(res, indent=2) + chr(10),
                                                 encoding="utf-8")

    print(f"{chr(10)}  labelled          : {len(keys)} in-bounds boxes over {n_frames} frames")
    print(f"  players in truth  : {len(players)}   ({len(nonplayers)} non-players, "
          f"{len(unsure)} unsure and excluded)")
    print(f"  team accuracy     : {acc:.4f}  ({correct}/{len(players)})   "
          f"(gate >= 0.99)  {'PASS' if res['team_gate']['pass'] else 'FAIL'}")
    print(f"  referees rejected : {caught['ref']}/{n_ref}")
    print(f"  crew rejected     : {caught['crew']}/{n_crew}")
    print(f"  false pos / frame : {before:.3f} -> {after:.3f}   (gate <= 1.0)  "
          f"{'PASS' if res['reject_gate']['pass'] else 'FAIL'}")
    print(f"  real players lost : {len(lost)}   (the expensive error)")
    if res["errors"]:
        print(chr(10) + "  disagreements:")
        for e in res["errors"]:
            print(f"    f{e['f']:>4} #{e['i']:<3} truth={e['truth']:<6} pred={e['pred']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="tools.m3_label")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("render")
    r.add_argument("work")
    r.add_argument("--out", default="eval/m3")
    r.add_argument("--m2", default="eval/m2")
    r.set_defaults(fn=cmd_render)
    z = sub.add_parser("zoom")
    z.add_argument("work")
    z.add_argument("picks", nargs="+", help="frame:index, e.g. 194:14")
    z.add_argument("--out", default="eval/m3")
    z.add_argument("--name", default="zoom.png")
    z.add_argument("--zoom", type=float, default=8.0)
    z.add_argument("--context", type=float, default=0.6)
    z.set_defaults(fn=cmd_zoom)
    s = sub.add_parser("score")
    s.add_argument("work")
    s.add_argument("--out", default="eval/m3")
    s.add_argument("--m2", default="eval/m2")
    s.set_defaults(fn=cmd_score)
    a = p.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
