"""Hide frames whose pose is known, re-derive them with the mosaic, measure.

    python -m tools.mosaic_check work/p0001 --out eval/m9

`ur/calibrate/mosaic.py` fills in the frames the paint cannot reach. Nothing
about the frames it fills can be checked against paint, by construction - that
is why they needed filling. So the accuracy is measured somewhere it *can* be
checked: take a possession that calibrated well, black out a contiguous block of
its frames, hand the mosaic the rest, and compare what comes back against what
the paint said.

**A contiguous block, not a random sample.** Hiding every third frame would
leave every hidden frame a neighbour of a source and measure nothing - the case
that matters is the end of p0005, where the camera has been somewhere else for
five seconds. The block is scanned across the possession at several widths, and
the error is reported against **how far the frame sits from the nearest surviving
source**, which is the quantity that actually predicts it.

The error is in yards on the field, measured over the patch of ground the frame
can see, because that is what everything downstream consumes.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np

from ur.calibrate import camera as C
from ur.calibrate import mask as M
from ur.calibrate import mosaic


def _burnt_in_region(work: Path, paths: list[Path]) -> np.ndarray:
    """Everything except the graphics painted on top of the broadcast."""
    static, _ = M.static_region(paths)
    region = np.full(static.shape, 255, np.uint8)
    region[static > 0] = 0
    return region


def _pose(rec: dict) -> C.Pose:
    c = rec["camera"]
    return C.Pose(pan=np.radians(c["pan_deg"]), tilt=np.radians(c["tilt_deg"]),
                  f=float(c["focal_px"]), roll=np.radians(c.get("roll_deg", 0.0)))


def _field_error(cam: C.FixedCamera, a: C.Pose, b: C.Pose,
                 probe: np.ndarray) -> float:
    """Yards on the ground between where two poses put the same pixels."""
    pa, oka = mosaic.ground_points(cam, a, probe)
    pb, okb = mosaic.ground_points(cam, b, probe)
    ok = oka & okb
    if ok.sum() < 4:
        return float("nan")
    return float(np.median(np.hypot(*(pa[ok] - pb[ok]).T)))


def _H_error(a: np.ndarray, b: np.ndarray, probe: np.ndarray) -> float:
    """Yards between where two image->field homographies put the same pixels."""
    out = []
    for H in (a, b):
        hom = np.column_stack([probe, np.ones(len(probe))]) @ H.T
        w = hom[:, 2]
        if np.any(np.abs(w) < 1e-9):
            return float("nan")
        out.append(hom[:, :2] / w[:, None])
    return float(np.median(np.hypot(*(out[0] - out[1]).T)))


def check(work: Path, widths=(15, 30, 45, 75), stride: int = 60) -> dict:
    cal = json.loads((work / "calibration.json").read_text(encoding="utf-8"))
    clip = json.loads((work / "clip.json").read_text(encoding="utf-8"))
    fld = clip["field"]
    paths = sorted((work / "frames").glob("*.jpg"))
    frames = cal["frames"]
    cam = C.FixedCamera(C=np.asarray(cal["camera"]["position_yd"], float),
                        image_w=cal["camera"]["image_w"],
                        image_h=cal["camera"]["image_h"])
    region = _burnt_in_region(work, paths)

    trusted = {i for i, r in enumerate(frames)
               if r.get("camera") and r.get("confidence", 0) >= mosaic.SOURCE_MIN_CONFIDENCE
               and (r.get("known_geometry_err_yd") is None
                    or r["known_geometry_err_yd"] <= mosaic.SOURCE_MAX_KNOWN_GEOMETRY_ERR_YD)}
    print(f"[mosaic_check] {work.name}: {len(trusted)} of {len(frames)} frames are "
          "paint-solved and can be used as truth")
    if len(trusted) < 120:
        return {"possession_id": cal.get("possession_id", work.name),
                "verdict": "too few paint-solved frames to hold any out"}

    # Image pixels below the horizon, back-projected under each pose and
    # compared in yards. Not field points projected to pixels - see
    # `mosaic.ground_points` for why that measured the wrong thing.
    probe = mosaic._image_probe(cam, n=8)

    rows = []
    for width in widths:
        for start in range(min(trusted), max(trusted) - width, stride):
            hidden = {i for i in range(start, start + width) if i in trusted}
            if len(hidden) < width * 0.8:
                continue                      # not a solid block of truth
            sources = trusted - hidden
            got = mosaic.fill(paths, frames, cam, region, fld,
                              sources=sources, targets=hidden, verbose=False)
            for i, s in got.items():
                gap = min(abs(i - j) for j in sources)
                truth = np.asarray(frames[i]["H"], float)
                e = _H_error(s.H, truth, probe)
                e_model = _field_error(cam, s.pose, _pose(frames[i]), probe)
                if np.isfinite(e):
                    rows.append({"frame": i, "block": width, "gap": gap,
                                 "err_yd": round(e, 4),
                                 "err_via_camera_model_yd": (round(e_model, 4)
                                                             if np.isfinite(e_model)
                                                             else None),
                                 "spread_yd": (round(s.spread_yd, 4)
                                               if np.isfinite(s.spread_yd) else None),
                                 "n_sources": s.n_sources})
            print(f"  block {width:>3} at {start:>4}: filled {len(got)}/{len(hidden)}")

    by_gap = {}
    for r in rows:
        b = 1 if r["gap"] <= 1 else 5 if r["gap"] <= 5 else 10 if r["gap"] <= 10 \
            else 20 if r["gap"] <= 20 else 30 if r["gap"] <= 30 else 45
        by_gap.setdefault(b, []).append(r["err_yd"])
    by_gap_model = {}
    for r in rows:
        if r.get("err_via_camera_model_yd") is None:
            continue
        b = 1 if r["gap"] <= 1 else 5 if r["gap"] <= 5 else 10 if r["gap"] <= 10             else 20 if r["gap"] <= 20 else 30 if r["gap"] <= 30 else 45
        by_gap_model.setdefault(b, []).append(r["err_via_camera_model_yd"])
    curve = [{"gap_frames_at_most": k, "gap_s": round(k / 15, 2), "n": len(v),
              "median_yd": round(float(np.median(v)), 4),
              "p90_yd": round(float(np.percentile(v, 90)), 4),
              "median_via_camera_model_yd": (
                  round(float(np.median(by_gap_model[k])), 4)
                  if by_gap_model.get(k) else None)}
             for k, v in sorted(by_gap.items())]

    # Does the module's own reported spread predict its error? If it does, the
    # confidence can be driven by it on the real frames, where there is no truth.
    pairs = [(r["spread_yd"], r["err_yd"]) for r in rows if r["spread_yd"] is not None]
    corr = (float(np.corrcoef([p[0] for p in pairs], [p[1] for p in pairs])[0, 1])
            if len(pairs) > 8 else None)

    return {"possession_id": cal.get("possession_id", work.name),
            "held_out_frames": len(rows),
            "error_by_gap": curve,
            "spread_vs_error_correlation": (round(corr, 3) if corr is not None
                                            else None),
            "spread_note": "mosaic_spread_yd is what the module can see at run "
                           "time; this says whether it predicts the error it "
                           "cannot see",
            "per_frame": rows}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="tools.mosaic_check")
    p.add_argument("work")
    p.add_argument("--out", default=None)
    a = p.parse_args(argv)
    work = Path(a.work)
    res = check(work)
    if "verdict" in res:
        print(f"[mosaic_check] {res['verdict']}")
        return 1
    print(f"\n  held-out frames re-derived: {res['held_out_frames']}")
    print(f"  {'gap <=':>8}{'s':>7}{'n':>7}{'median yd':>12}{'p90 yd':>10}"
          f"{'via model':>12}")
    for r in res["error_by_gap"]:
        m = r.get("median_via_camera_model_yd")
        print(f"  {r['gap_frames_at_most']:>8}{r['gap_s']:>7.2f}{r['n']:>7}"
              f"{r['median_yd']:>12.3f}{r['p90_yd']:>10.3f}"
              f"{(m if m is not None else float('nan')):>12.3f}")
    print(f"\n  the module's own spread predicts its error at r = "
          f"{res['spread_vs_error_correlation']}")
    if a.out:
        out = Path(a.out)
        out.mkdir(parents=True, exist_ok=True)
        dest = out / f"mosaic_check_{res['possession_id']}.json"
        dest.write_text(json.dumps(res, indent=2) + "\n", encoding="utf-8")
        print(f"[mosaic_check] -> {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
