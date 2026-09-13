"""Pull stills out of the broadcast for the M0 footage report.

Frames come out as PNG, not JPEG: every measurement in the report (player pixel
height, torso colour, digit legibility) is taken off these, and a second lossy
generation would quietly bias all three.

Extraction is seek-based rather than a single decode pass, which turns a 2h22m
decode into a few seconds per frame.

    python -m tools.survey uniform --every 240 --out survey/uniform
    python -m tools.survey random --n 30 --seed 20260827 --out survey/random
    python -m tools.survey at --times 1510.0 1511.5 --out survey/probe
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ur.ffprobe import ffmpeg, probe_video  # noqa: E402

DEFAULT_SOURCE = "raw/sol-vs-windchill-2026-semi.mp4"


def grab(source: Path, t: float, dest: Path) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    proc = ffmpeg(
        ["-y", "-ss", f"{t:.3f}", "-i", str(source), "-frames:v", "1", str(dest)],
        check=False,
    )
    return proc.returncode == 0 and dest.exists() and dest.stat().st_size > 0


def extract(source: Path, times: list[float], out: Path, tag: str) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    entries = []
    for i, t in enumerate(times):
        name = f"{i:03d}_t{t:.1f}.png"
        ok = grab(source, t, out / name)
        entries.append({"i": i, "t": round(t, 3), "file": name, "ok": ok})
        print(f"  [{i + 1:>3}/{len(times)}] t={t:9.1f}s -> {name} {'' if ok else 'FAILED'}")
    manifest = {
        "source": source.name,
        "mode": tag,
        "count": len(entries),
        "frames": entries,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="tools.survey")
    p.add_argument("--source", default=DEFAULT_SOURCE)
    sub = p.add_subparsers(dest="mode", required=True)

    u = sub.add_parser("uniform", help="one frame every N seconds across the game")
    u.add_argument("--every", type=float, default=240.0)
    u.add_argument("--out", default="survey/uniform")

    r = sub.add_parser("random", help="seeded random timestamps in a range")
    r.add_argument("--n", type=int, default=30)
    r.add_argument("--seed", type=int, default=20260827)
    r.add_argument("--start", type=float, default=None)
    r.add_argument("--end", type=float, default=None)
    r.add_argument("--out", default="survey/random")

    a = sub.add_parser("at", help="explicit timestamps")
    a.add_argument("--times", type=float, nargs="+", required=True)
    a.add_argument("--out", default="survey/probe")

    s = sub.add_parser("span", help="every N seconds between start and end")
    s.add_argument("--start", type=float, required=True)
    s.add_argument("--end", type=float, required=True)
    s.add_argument("--every", type=float, default=1.0)
    s.add_argument("--out", required=True)

    args = p.parse_args(argv)
    source = Path(args.source)
    if not source.exists():
        raise SystemExit(f"source not found: {source}")
    info = probe_video(source)
    dur = info.duration_s
    print(f"[survey] {source.name}: {info.width}x{info.height} {float(info.r_frame_rate):.3f} fps, {dur:.1f}s")

    if args.mode == "uniform":
        times = [t for t in _frange(args.every / 2, dur, args.every)]
        tag = f"uniform/{args.every}s"
    elif args.mode == "random":
        lo = args.start if args.start is not None else 0.0
        hi = args.end if args.end is not None else dur
        rng = random.Random(args.seed)
        times = sorted(rng.uniform(lo, hi) for _ in range(args.n))
        tag = f"random/n={args.n}/seed={args.seed}/range=[{lo:.0f},{hi:.0f}]"
    elif args.mode == "span":
        times = list(_frange(args.start, args.end, args.every))
        tag = f"span/[{args.start},{args.end}]/{args.every}s"
    else:
        times = list(args.times)
        tag = "explicit"

    m = extract(source, times, Path(args.out), tag)
    ok = sum(1 for e in m["frames"] if e["ok"])
    print(f"[survey] {ok}/{m['count']} frames written to {args.out}")
    return 0


def _frange(start: float, stop: float, step: float):
    t = start
    while t < stop:
        yield t
        t += step


if __name__ == "__main__":
    raise SystemExit(main())
