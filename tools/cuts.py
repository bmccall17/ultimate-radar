"""Find the camera cuts, and say how often they happen.

M0 question 7 asks for cuts per minute, because that number is the price of M1:
each shot costs one set of human correspondence clicks (AD-4), so a possession
with four cuts costs four times a possession with one.

Method: ffmpeg's own scene-change score, computed on a 320-wide downscale (the
score is a normalised inter-frame difference, so the downscale changes it very
little and makes the pass many times faster). Frames above a loose threshold are
dumped with their scores; thresholding properly happens afterwards in Python, so
the expensive decode runs once and the threshold stays arguable.

A hard cut scores high. A fast pan or a whip also scores high, which is why the
tool reports the score distribution and writes out candidate frames to look at,
rather than just printing a count.

    python -m tools.cuts scan --start 1200 --duration 600 --out eval/m0/cuts
    python -m tools.cuts scan --whole --out eval/m0/cuts_full
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ur.ffprobe import _bin, probe_video, run  # noqa: E402

DEFAULT_SOURCE = "raw/sol-vs-windchill-2026-semi.mp4"
LOOSE = 0.08  # dump anything above this; decide the real threshold later

_PTS = re.compile(r"pts_time:([0-9.]+)")
_SCORE = re.compile(r"lavfi\.scene_score=([0-9.]+)")


def scan(source: Path, start: float | None, duration: float | None,
         threshold: float, hwaccel: str) -> list[dict]:
    argv = [_bin("ffmpeg"), "-hide_banner", "-nostdin"]
    if hwaccel != "none":
        argv += ["-hwaccel", hwaccel]
    if start is not None:
        argv += ["-ss", f"{start:.3f}"]
    argv += ["-i", str(source)]
    if duration is not None:
        argv += ["-t", f"{duration:.3f}"]
    argv += [
        "-an", "-sn",
        "-vf", f"scale=320:-2,select='gt(scene,{threshold})',metadata=print:file=-",
        "-f", "null", "-",
    ]
    proc = run(argv, check=False)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr[-3000:])

    # metadata=print writes to stdout; ffmpeg's own log goes to stderr.
    events: list[dict] = []
    pending_t = None
    for line in proc.stdout.splitlines():
        m = _PTS.search(line)
        if m:
            pending_t = float(m.group(1))
            continue
        m = _SCORE.search(line)
        if m and pending_t is not None:
            events.append({"t": round(pending_t + (start or 0.0), 3),
                           "score": round(float(m.group(1)), 4)})
            pending_t = None
    return events


def summarise(events: list[dict], span_s: float, cut_threshold: float) -> dict:
    cuts = [e for e in events if e["score"] >= cut_threshold]
    gaps = [round(b["t"] - a["t"], 2) for a, b in zip(cuts, cuts[1:])]
    gaps_sorted = sorted(gaps)
    def pct(p: float):
        if not gaps_sorted:
            return None
        return gaps_sorted[min(len(gaps_sorted) - 1, int(p * len(gaps_sorted)))]
    return {
        "span_s": round(span_s, 1),
        "cut_threshold": cut_threshold,
        "candidates_above_loose": len(events),
        "cuts": len(cuts),
        "cuts_per_minute": round(60.0 * len(cuts) / span_s, 3) if span_s else None,
        "median_shot_s": pct(0.5),
        "p10_shot_s": pct(0.10),
        "p90_shot_s": pct(0.90),
        "shots_under_5s": sum(1 for g in gaps if g < 5),
        "shots_over_30s": sum(1 for g in gaps if g > 30),
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="tools.cuts")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("scan")
    s.add_argument("--source", default=DEFAULT_SOURCE)
    s.add_argument("--start", type=float, default=None)
    s.add_argument("--duration", type=float, default=None)
    s.add_argument("--whole", action="store_true")
    s.add_argument("--loose", type=float, default=LOOSE)
    s.add_argument("--cut-threshold", type=float, default=0.35)
    s.add_argument("--hwaccel", default="cuda", choices=["cuda", "d3d11va", "none"])
    s.add_argument("--out", required=True)
    args = p.parse_args(argv)

    source = Path(args.source)
    info = probe_video(source)
    start = None if args.whole else args.start
    duration = None if args.whole else args.duration
    span = duration if duration is not None else info.duration_s - (start or 0.0)

    print(f"[cuts] scanning {span:.0f}s from {start or 0:.0f}s (hwaccel={args.hwaccel})...")
    events = scan(source, start, duration, args.loose, args.hwaccel)
    summary = summarise(events, span, args.cut_threshold)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "events.json").write_text(
        json.dumps({"source": source.name, "start": start, "duration": duration,
                    "loose_threshold": args.loose, "events": events}, indent=1) + "\n",
        encoding="utf-8")
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
