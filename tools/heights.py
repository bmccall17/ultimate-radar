"""Player pixel height as a function of depth in frame (M0 question 3).

Takes the blob dump from tools.measure, keeps the blobs whose shape is
person-like, and reports height against the image row the feet sit on. Depth in
the frame is the only proxy for distance available before calibration exists,
and it is the right one: the whole point of the number is to say how small a
detector has to cope with, and that is set by image row.

The filter is deliberately loose and the tool prints how many blobs it dropped,
because the honest version of this measurement is "here is the distribution and
here is the annotated frame it came from", not a single number.

    python -m tools.heights --blobs eval/m0/blobs_live/blobs.json \
        --only 005,006,008,013,014,015,026,033,034,035,038
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

# A standing or running person, boxed: clearly taller than wide, and the box is
# mostly filled. Referees and players both pass; line fragments and litter do not.
MIN_ASPECT, MAX_ASPECT = 1.5, 5.0
MIN_FILL, MAX_FILL = 0.30, 0.90
MIN_H = 12


def person_like(b: dict) -> bool:
    return (
        MIN_ASPECT <= b["aspect"] <= MAX_ASPECT
        and MIN_FILL <= b["fill"] <= MAX_FILL
        and b["h"] >= MIN_H
    )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="tools.heights")
    p.add_argument("--blobs", required=True)
    p.add_argument("--only", default=None, help="comma-separated frame prefixes")
    p.add_argument("--bands", type=int, default=6)
    p.add_argument("--out", default=None)
    args = p.parse_args(argv)

    records = json.loads(Path(args.blobs).read_text(encoding="utf-8"))
    keep = set(args.only.split(",")) if args.only else None

    rows: list[tuple[str, int, int]] = []  # frame, foot_y, h
    dropped = 0
    for rec in records:
        name = rec["frame"]
        if keep and not any(name.startswith(k) for k in keep):
            continue
        for b in rec["blobs"]:
            if person_like(b):
                rows.append((name, b["foot_y"], b["h"]))
            else:
                dropped += 1

    if not rows:
        raise SystemExit("no person-like blobs matched")

    foot = np.array([r[1] for r in rows])
    h = np.array([r[2] for r in rows])
    print(f"{len(rows)} person-like blobs across "
          f"{len({r[0] for r in rows})} frames ({dropped} blobs rejected by shape)\n")

    print(f"{'foot row band':>16} {'n':>5} {'min':>5} {'p10':>5} {'med':>6} {'p90':>6} {'max':>5}")
    edges = np.linspace(0, 1080, args.bands + 1)
    bands = []
    for lo, hi in zip(edges, edges[1:]):
        m = (foot >= lo) & (foot < hi)
        if not m.any():
            continue
        sel = h[m]
        band = {
            "row_lo": int(lo), "row_hi": int(hi), "n": int(m.sum()),
            "min": int(sel.min()), "p10": int(np.percentile(sel, 10)),
            "median": float(np.median(sel)), "p90": int(np.percentile(sel, 90)),
            "max": int(sel.max()),
        }
        bands.append(band)
        print(f"{int(lo):>7}-{int(hi):<8} {band['n']:>5} {band['min']:>5} "
              f"{band['p10']:>5} {band['median']:>6.0f} {band['p90']:>6} {band['max']:>5}")

    overall = {
        "n": len(rows),
        "min": int(h.min()), "p5": int(np.percentile(h, 5)),
        "p25": int(np.percentile(h, 25)), "median": float(np.median(h)),
        "p75": int(np.percentile(h, 75)), "p95": int(np.percentile(h, 95)),
        "max": int(h.max()),
        "frac_under_32px": round(float((h < 32).mean()), 4),
        "frac_under_48px": round(float((h < 48).mean()), 4),
    }
    print("\noverall: " + json.dumps(overall))

    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(
            json.dumps({"bands": bands, "overall": overall,
                        "filter": {"aspect": [MIN_ASPECT, MAX_ASPECT],
                                   "fill": [MIN_FILL, MAX_FILL], "min_h": MIN_H}},
                       indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
