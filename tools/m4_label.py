"""Identity ground truth at 1 Hz, read off jersey numbers.

    python -m tools.m4_label render work/p0001    # -> eval/m4/ident_00.png ...
    python -m tools.m4_label score  work/p0001    # reads eval/m4/identity_labels.json

The M4 gate asks for at most two identity switches over the possession. Measuring
that means knowing which real person each slot was holding, frame by frame — and
the cheap way to get that is **not** to follow players from frame to frame by eye,
which is slow and compounds its own mistakes. It is to read the number off the
jersey, which makes every label independent of every other one.

**How well that works was measured before relying on it.** Probing three frames,
roughly half the crops show a readable number: UFA §3.2.3 puts a number on the
back *and* the front of the uniform, so a player facing either way is legible and
a player side-on shows neither. Half is enough. A switch shows up as a change in
which number a slot is holding, and a slot whose observations are all unlabelled
simply contributes no evidence — which lowers the sensitivity of the measurement,
and is reported rather than papered over.

Labels are per detection, not per slot, so they are independent of the tracker
and survive a re-run of it:

    {"f": 180, "i": 4, "jersey": 28}          # legible
    {"f": 180, "i": 7, "jersey": null}        # a player, number not readable
    {"f": 105, "i": 6, "jersey": null, "not_player": "ref"}

`not_player` is how the referees `ur/team.py` could not catch get counted: they
reach the tracker as ordinary dark-kit detections, and the only way to know how
often one occupies a defender's slot is to mark them here.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

import cv2
import numpy as np

LABEL_HZ = 1.0
ZOOM = 6
CELL_W, CELL_H = 250, 330
COLS, ROWS = 8, 5


def label_frames(work: Path) -> list[int]:
    clip = json.loads((work / "clip.json").read_text(encoding="utf-8"))
    step = int(round(float(clip["fps"]) / LABEL_HZ))
    return list(range(0, int(clip["frames"]), step))


def candidates(work: Path) -> list[tuple[int, int]]:
    """(frame, det index) for every detection the tracker is allowed to use."""
    det = json.loads((work / "detections.json").read_text(encoding="utf-8"))
    by = {d["f"]: d["dets"] for d in det["frames"]}
    out = []
    for f in label_frames(work):
        for i, d in enumerate(by.get(f, [])):
            if (d.get("in_bounds") and not d.get("non_player")
                    and not d.get("weak_team") and d.get("field") is not None):
                out.append((f, i))
    return out


def cmd_render(a) -> int:
    work, out = Path(a.work), Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    det = json.loads((work / "detections.json").read_text(encoding="utf-8"))
    by = {d["f"]: d["dets"] for d in det["frames"]}
    paths = sorted((work / "frames").glob("*.jpg"))

    cells, cur, img = [], None, None
    for f, i in candidates(work):
        if f != cur:
            img = cv2.imread(str(paths[f]))
            cur = f
        d = by[f][i]
        x0, y0, x1, y1 = [int(round(v)) for v in d["box"]]
        h, w = y1 - y0, x1 - x0
        # The torso, where a number lives, with a little slack either side.
        a0, b0 = y0 + int(0.12 * h), y0 + int(0.55 * h)
        c0, d0 = x0 - int(0.06 * w), x1 + int(0.06 * w)
        crop = img[max(0, a0):b0, max(0, c0):min(img.shape[1], d0)]
        cell = np.full((CELL_H, CELL_W, 3), 22, np.uint8)
        if crop.size:
            z = cv2.resize(crop, None, fx=ZOOM, fy=ZOOM,
                           interpolation=cv2.INTER_LANCZOS4)
            z = z[:CELL_H - 22, :CELL_W]
            cell[22:22 + z.shape[0], :z.shape[1]] = z
        cv2.putText(cell, f"f{f} #{i} {str(d.get('team'))[:2]}", (4, 15),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.46, (235, 235, 235), 1, cv2.LINE_AA)
        cells.append(cell)

    per = COLS * ROWS
    n = (len(cells) + per - 1) // per
    for s in range(n):
        chunk = cells[s * per:(s + 1) * per]
        rows = (len(chunk) + COLS - 1) // COLS
        sheet = np.full((rows * CELL_H, COLS * CELL_W, 3), 22, np.uint8)
        for k, c in enumerate(chunk):
            r, cc = divmod(k, COLS)
            sheet[r * CELL_H:(r + 1) * CELL_H, cc * CELL_W:(cc + 1) * CELL_W] = c
        p = out / f"ident_{s:02d}.png"
        cv2.imwrite(str(p), sheet)
        print(f"[m4_label] {p}  ({len(chunk)} crops)")
    print(f"[m4_label] {len(cells)} detections over {len(label_frames(work))} "
          f"frames at {LABEL_HZ} Hz -> {n} sheets")
    return 0


def cmd_score(a) -> int:
    """Count identity switches, and everything else the labels can answer."""
    work, out = Path(a.work), Path(a.out)
    trk = json.loads((work / "tracks.json").read_text(encoding="utf-8"))
    truth_doc = json.loads((out / "identity_labels.json").read_text(encoding="utf-8"))
    truth = {(int(r["f"]), int(r["i"])): r for r in truth_doc["labels"]}
    frames = set(label_frames(work))

    # slot -> [(frame, jersey)] over the labelled frames
    seen: dict[str, list[tuple[int, int]]] = defaultdict(list)
    nonplayer_hits: dict[str, list[tuple[int, str]]] = defaultdict(list)
    n_obs_labelled = 0
    for s in trk["slots"]:
        for smp in s["samples"]:
            if smp["state"] != "observed" or smp["f"] not in frames:
                continue
            lab = truth.get((smp["f"], smp["det"]))
            if lab is None:
                continue
            n_obs_labelled += 1
            if lab.get("not_player"):
                nonplayer_hits[s["slot"]].append((smp["f"], lab["not_player"]))
            elif lab.get("jersey") is not None:
                seen[s["slot"]].append((smp["f"], int(lab["jersey"])))

    switches, per_slot = [], {}
    for s in trk["slots"]:
        seq = sorted(seen.get(s["slot"], []))
        runs = [(f, j) for k, (f, j) in enumerate(seq)
                if k == 0 or j != seq[k - 1][1]]
        n_sw = max(0, len(runs) - 1)
        for f, j in runs[1:]:
            prev = [x for x in seq if x[0] < f][-1]
            switches.append({"slot": s["slot"], "at_frame": f,
                             "from_jersey": prev[1], "to_jersey": j,
                             "from_frame": prev[0]})
        per_slot[s["slot"]] = {
            "labelled_observations": len(seq),
            "distinct_jerseys": sorted({j for _, j in seq}),
            "modal_jersey": (Counter(j for _, j in seq).most_common(1)[0][0]
                             if seq else None),
            "switches": n_sw,
            "non_player_observations": len(nonplayer_hits.get(s["slot"], [])),
        }

    # Is any real person in two slots at once? That is the other identity failure
    # and the roster constraint does not prevent it.
    dupes = []
    per_frame: dict[int, dict[int, list[str]]] = defaultdict(lambda: defaultdict(list))
    for slot, seq in seen.items():
        for f, j in seq:
            per_frame[f][j].append(slot)
    for f, js in sorted(per_frame.items()):
        for j, slots_ in js.items():
            if len(slots_) > 1:
                dupes.append({"frame": f, "jersey": j, "slots": sorted(slots_)})

    labelled = [r for r in truth_doc["labels"]]
    legible = sum(1 for r in labelled if r.get("jersey") is not None)
    nonplayers = sum(1 for r in labelled if r.get("not_player"))

    res = {
        "schema": "ultimate-radar/m4-identity-acceptance@1",
        "possession": trk["possession_id"],
        "labelled_by": truth_doc.get("labelled_by"),
        "caveats": truth_doc.get("caveats"),
        "labelled_frames": sorted(frames),
        "detections_labelled": len(labelled),
        "jersey_legible": legible,
        "jersey_legible_fraction": round(legible / max(len(labelled), 1), 3),
        "labelled_as_non_player": nonplayers,
        "tracker_observations_with_a_label": n_obs_labelled,
        "gate": {"identity_switches": 2},
        "identity_switches": len(switches),
        "pass_switches": bool(len(switches) <= 2),
        "switch_detail": switches,
        "same_person_in_two_slots": dupes,
        "non_player_in_a_slot": {k: v for k, v in nonplayer_hits.items()},
        "per_slot": per_slot,
    }
    (out / "m4_identity_acceptance.json").write_text(
        json.dumps(res, indent=2) + chr(10), encoding="utf-8")

    print(f"  labelled          : {len(labelled)} detections over {len(frames)} frames "
          f"at {LABEL_HZ} Hz")
    print(f"  jersey legible    : {legible} ({legible / max(len(labelled),1):.0%})")
    print(f"  non-players found : {nonplayers}")
    print(f"  tracker obs with a readable number: {n_obs_labelled}")
    print(f"  identity switches : {len(switches)}   (gate <= 2)  "
          f"{'PASS' if res['pass_switches'] else 'FAIL'}")
    for sw in switches:
        print(f"      {sw['slot']:>3}  f{sw['from_frame']:>3} #{sw['from_jersey']} "
              f"-> f{sw['at_frame']:>3} #{sw['to_jersey']}")
    if dupes:
        print(f"  same person in two slots at once: {len(dupes)}")
        for d in dupes[:10]:
            print(f"      f{d['frame']:>4} #{d['jersey']} in {', '.join(d['slots'])}")
    if nonplayer_hits:
        print("  non-player occupying a slot:")
        for k, v in sorted(nonplayer_hits.items()):
            print(f"      {k}: {len(v)} labelled frames ({v[0][1]})")
    print()
    for s in trk["slots"]:
        p = per_slot[s["slot"]]
        print(f"    {s['slot']:>3} {s['team']:>5}  labelled {p['labelled_observations']:>3}  "
              f"modal #{str(p['modal_jersey']):>4}  distinct {p['distinct_jerseys']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="tools.m4_label")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("render")
    r.add_argument("work")
    r.add_argument("--out", default="eval/m4")
    r.set_defaults(fn=cmd_render)
    s = sub.add_parser("score")
    s.add_argument("work")
    s.add_argument("--out", default="eval/m4")
    s.set_defaults(fn=cmd_score)
    a = p.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
