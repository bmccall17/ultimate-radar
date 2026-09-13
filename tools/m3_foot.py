"""Measure the foot-point error the whole position estimate rests on.

    python -m tools.m3_foot render work/p0001     # -> eval/m3/foot_00.png ...
    python -m tools.m3_foot score  work/p0001     # reads eval/m3/foot_labels.json

`ur.detect.run` positions a player by back-projecting the **bottom centre of the
detection box** and calls that the feet. It then states a `sigma_yd` built on an
*assumed* 3 px of foot error. Nobody has checked either. That assumption is load
bearing: sigma is what the viewer draws as its uncertainty disc, and
`docs/05-uncertainty.md` makes the whole honesty argument rest on that disc
containing the truth. An assumed sigma that does not is worse than no sigma.

**What counts as the truth here.** A player's ground position is taken as the
point midway between where their two feet touch the ground; when only one foot is
down, or the player is airborne mid-stride, it is the point under the supporting
foot, or under the hips if neither foot is down. That convention is arbitrary in
the third decimal place and it is stated so the number can be argued with. It is
also the convention a tracker wants, because it is the thing that moves smoothly
while the feet swing either side of it.

**What this measures and what it does not.** The error reported is
box-bottom-centre against a hand-read foot point, carried through the *same*
homography. It is therefore the foot-point term alone - the bit M2 guessed at.
It is not the total position error, which also carries M1's calibration error
(mean 0.0996 yd on held-out correspondences). The two are close to independent
and the write-up adds them in quadrature rather than pretending either is the
whole story.

The render draws a labelled grid in **source pixels** around the assumed foot
point, so the label is read off as an offset rather than estimated. Reading an
offset from a grid is the difference between a measurement and an impression.

The label format records only what a human read:

    {"f": 174, "i": 3, "dx": -2, "dy": 3, "note": "mid-stride, right foot down"}

dx is positive to the right, dy positive **downward**, both in source pixels,
both offsets from the drawn crosshair. Everything else - yards, medians, the
distance breakdown - is derived from that plus calibration.json.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np

SEED = 20260827
N_SAMPLES = 50
COLS, ROWS = 3, 3
GRID_STEP = 2          # source pixels between grid lines
GRID_HALF = 16         # grid extends this many source pixels each way.
                       # First pass used 10 and several true foot points fell
                       # outside it - a box tight round a running body puts its
                       # bottom centre well away from a mid-stride foot.
ZOOM = 8               # so one source pixel is comfortably resolvable
MAX_HALF_W = 38        # source px each side; keeps a sheet under 2000 px wide
MAX_ABOVE = 64         # source px of leg shown above the foot point


def sample(work: Path, n: int = N_SAMPLES, seed: int = SEED) -> list[tuple[int, int]]:
    """A seeded sample of positioned, player-classified detections.

    Drawn uniformly rather than stratified by distance: stratifying would make the
    headline median a weighted average of bands chosen here rather than an estimate
    of the error on a real frame. The distance breakdown is reported separately,
    from the same sample.
    """
    det = json.loads((work / "detections.json").read_text(encoding="utf-8"))
    pool = []
    for fr in det["frames"]:
        for i, d in enumerate(fr["dets"]):
            if (d.get("in_bounds") and not d.get("non_player")
                    and d.get("team") and d.get("soccer") is not None
                    and (d["box"][3] - d["box"][1]) >= 40):
                pool.append((fr["f"], i))
    rng = np.random.default_rng(seed)
    idx = rng.choice(len(pool), size=min(n, len(pool)), replace=False)
    return sorted(pool[int(k)] for k in idx)


def cmd_render(a) -> int:
    work, out = Path(a.work), Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    det = json.loads((work / "detections.json").read_text(encoding="utf-8"))
    by = {d["f"]: d["dets"] for d in det["frames"]}
    paths = sorted((work / "frames").glob("*.jpg"))

    picks = sample(work, a.n)
    cells = []
    cur_f, img = None, None
    for f, i in picks:
        if f != cur_f:
            img = cv2.imread(str(paths[f]))
            cur_f = f
        d = by[f][i]
        fx, fy = d["foot"]
        cx, cy = int(round(fx)), int(round(fy))
        h = d["box"][3] - d["box"][1]

        # Show the lower part of the figure: enough leg to tell which foot is
        # down, not so much that the feet shrink.
        half_w = min(MAX_HALF_W, max(GRID_HALF + 4, int(round(0.42 * h))))
        top = int(round(cy - min(MAX_ABOVE, 0.55 * h)))
        x0, x1 = max(0, cx - half_w), min(img.shape[1], cx + half_w)
        y0, y1 = max(0, top), min(img.shape[0], cy + GRID_HALF + 6)
        crop = img[y0:y1, x0:x1].copy()
        if crop.size == 0:
            continue
        z = cv2.resize(crop, None, fx=ZOOM, fy=ZOOM, interpolation=cv2.INTER_NEAREST)
        ox, oy = (cx - x0) * ZOOM, (cy - y0) * ZOOM

        # Grid in source pixels, labelled, centred on the assumed foot point.
        for k in range(-GRID_HALF, GRID_HALF + 1, GRID_STEP):
            gx, gy = ox + k * ZOOM, oy + k * ZOOM
            major = (k % 4 == 0)
            faint = (70, 240, 240) if k == 0 else ((120, 120, 120) if major else (70, 70, 70))
            if 0 <= gx < z.shape[1]:
                cv2.line(z, (gx, 0), (gx, z.shape[0]), faint, 1)
                if major:
                    cv2.putText(z, f"{k:+d}" if k else "0", (gx + 2, 16),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, faint, 1, cv2.LINE_AA)
            if 0 <= gy < z.shape[0]:
                cv2.line(z, (0, gy), (z.shape[1], gy), faint, 1)
                if major:
                    cv2.putText(z, f"{k:+d}" if k else "0", (4, gy - 4),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, faint, 1, cv2.LINE_AA)
        # The detection box, so it is never ambiguous whose feet are being read.
        # Without it a crop containing two players asks the labeller to guess, and
        # a guess here is indistinguishable from a measurement.
        bx0 = int(round((d["box"][0] - x0) * ZOOM))
        bx1 = int(round((d["box"][2] - x0) * ZOOM))
        by1 = int(round((d["box"][3] - y0) * ZOOM))
        cv2.rectangle(z, (bx0, 0), (bx1, by1), (120, 200, 120), 2)
        cv2.circle(z, (ox, oy), 5, (60, 230, 255), 2, cv2.LINE_AA)

        ypp = d.get("yd_per_px")
        ban = np.full((26, z.shape[1], 3), 20, np.uint8)
        cv2.putText(ban, f"f{f} #{i}   h{h:.0f}px   {ypp:.3f} yd/px"
                    if ypp else f"f{f} #{i}   h{h:.0f}px",
                    (6, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (240, 240, 240), 1,
                    cv2.LINE_AA)
        cells.append(np.vstack([ban, z]))

    per = COLS * ROWS
    n_sheets = (len(cells) + per - 1) // per
    for s in range(n_sheets):
        chunk = cells[s * per:(s + 1) * per]
        ch = max(c.shape[0] for c in chunk)
        cw = max(c.shape[1] for c in chunk)
        rows = (len(chunk) + COLS - 1) // COLS
        sheet = np.full((rows * (ch + 6), COLS * (cw + 6), 3), 25, np.uint8)
        for k, c in enumerate(chunk):
            r, cc = divmod(k, COLS)
            sheet[r * (ch + 6):r * (ch + 6) + c.shape[0],
                  cc * (cw + 6):cc * (cw + 6) + c.shape[1]] = c
        p = out / f"foot_{s:02d}.png"
        cv2.imwrite(str(p), sheet)
        print(f"[m3_foot] {p}  ({len(chunk)} crops)")
    print(f"[m3_foot] {len(cells)} detections -> {n_sheets} sheets. "
          "Now write eval/m3/foot_labels.json: one {f, i, dx, dy} per crop, "
          "in source pixels, dy positive downward.")
    return 0


def cmd_score(a) -> int:
    """Carry each hand-read offset through the same homography, in yards."""
    import numpy as _np

    from ur.calibrate import fit as CFIT
    from ur.detect.run import load_calibration

    work, out = Path(a.work), Path(a.out)
    det = json.loads((work / "detections.json").read_text(encoding="utf-8"))
    by = {d["f"]: d["dets"] for d in det["frames"]}
    cal, cam, poses, confs = load_calibration(work)
    labels = json.loads((out / "foot_labels.json").read_text(encoding="utf-8"))

    rows = []
    for lab in labels["labels"]:
        f, i = int(lab["f"]), int(lab["i"])
        d = by[f][i]
        pose = poses[f]
        fx, fy = d["foot"]
        tx, ty = fx + float(lab["dx"]), fy + float(lab["dy"])
        pts = _np.array([[fx, fy], [tx, ty]])
        w, ok = CFIT.backproject(cam, pose, pts)
        if not (ok[0] and ok[1]):
            continue
        err = float(_np.hypot(*(w[1] - w[0])))
        rows.append({
            "f": f, "i": i,
            "dx": lab["dx"], "dy": lab["dy"],
            "px_error": round(float(_np.hypot(lab["dx"], lab["dy"])), 2),
            "yd_per_px": d.get("yd_per_px"),
            "error_yd": round(err, 4),
            "sigma_yd_claimed": d.get("sigma_yd"),
            "box_h": round(d["box"][3] - d["box"][1], 1),
            "note": lab.get("note", ""),
        })

    e = np.array([r["error_yd"] for r in rows])
    px = np.array([r["px_error"] for r in rows])
    dy = np.array([float(r["dy"]) for r in rows])
    dx = np.array([float(r["dx"]) for r in rows])
    ypp = np.array([r["yd_per_px"] or np.nan for r in rows])
    claimed = np.array([r["sigma_yd_claimed"] or np.nan for r in rows])

    # Does the sigma the pipeline states actually contain the truth? That is the
    # question docs/05 says the product's honesty rests on, and it is cheap to ask.
    inside = float(np.mean(e <= claimed))

    # The assumed 3 px becomes whatever the data says. Use the RMS of the pixel
    # offset, since sigma multiplies it as a radius.
    px_rms = float(np.sqrt(np.mean(px ** 2)))

    order = np.argsort(ypp)
    ter = np.array_split(order, 3)
    bands = []
    for k, idx in enumerate(ter):
        bands.append({"band": ["near", "middle", "far"][k],
                      "n": len(idx),
                      "yd_per_px": [round(float(ypp[idx].min()), 3),
                                    round(float(ypp[idx].max()), 3)],
                      "median_error_yd": round(float(np.median(e[idx])), 4),
                      "p95_error_yd": round(float(np.percentile(e[idx], 95)), 4),
                      "median_px_error": round(float(np.median(px[idx])), 2)})

    res = {
        "schema": "ultimate-radar/m3-foot-acceptance@1",
        "possession": det["possession_id"],
        "labelled_by": labels.get("labelled_by"),
        "convention": labels.get("convention"),
        "caveats": labels.get("caveats"),
        "n": len(rows),
        "gate": {"median_error_yd": 0.6},
        "median_error_yd": round(float(np.median(e)), 4),
        "mean_error_yd": round(float(e.mean()), 4),
        "p95_error_yd": round(float(np.percentile(e, 95)), 4),
        "max_error_yd": round(float(e.max()), 4),
        "pass": bool(np.median(e) < 0.6),
        "pixel_offset": {
            "median": round(float(np.median(px)), 2),
            "rms": round(px_rms, 2),
            "mean_dx": round(float(dx.mean()), 2),
            "mean_dy": round(float(dy.mean()), 2),
            "assumed_by_m2": 3.0,
            "note": "mean_dx / mean_dy are the systematic part - a bias the box "
                    "bottom has against the real foot point, which is correctable; "
                    "rms is what sigma should be built on.",
        },
        "sigma_check": {
            "fraction_inside_claimed_sigma": round(inside, 3),
            "note": "docs/05 asks for >= 80 % of truths inside the drawn sigma. That "
                    "is an M4 gate on tracked positions, measured here early on "
                    "detections because the same sigma is what M4 inherits.",
        },
        "by_distance": bands,
        "samples": rows,
    }
    (out / "m3_foot_acceptance.json").write_text(json.dumps(res, indent=2) + chr(10),
                                                 encoding="utf-8")
    print(f"  n                    : {len(rows)} hand-checked detections")
    print(f"  pixel offset         : median {np.median(px):.2f} px, rms {px_rms:.2f} px "
          f"(M2 assumed 3.0)")
    print(f"  systematic bias      : dx {dx.mean():+.2f} px, dy {dy.mean():+.2f} px")
    print(f"  foot-point error     : median {np.median(e):.4f} yd   (gate < 0.6)  "
          f"{'PASS' if res['pass'] else 'FAIL'}")
    print(f"                         p95 {np.percentile(e, 95):.4f}, max {e.max():.4f}")
    print(f"  inside claimed sigma : {inside:.1%}")
    for b in bands:
        print(f"    {b['band']:>6}: {b['yd_per_px'][0]:.3f}-{b['yd_per_px'][1]:.3f} yd/px  "
              f"median {b['median_error_yd']:.3f} yd  p95 {b['p95_error_yd']:.3f}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="tools.m3_foot")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("render")
    r.add_argument("work")
    r.add_argument("--out", default="eval/m3")
    r.add_argument("-n", type=int, default=N_SAMPLES)
    r.set_defaults(fn=cmd_render)
    s = sub.add_parser("score")
    s.add_argument("work")
    s.add_argument("--out", default="eval/m3")
    s.set_defaults(fn=cmd_score)
    a = p.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
