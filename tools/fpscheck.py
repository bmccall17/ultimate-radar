"""Is the 60 fps real, or a 30 fps broadcast doubled?

Runs ffmpeg's mpdecimate over several stretches and counts how many frames
survive. Duplicated frames get dropped, so a doubled 30 fps feed keeps about
half; a genuine 60 fps feed keeps nearly all.

One caveat worth stating: mpdecimate drops *near*-identical frames, so a static
crowd shot or a frozen replay card will also show a high drop rate without the
footage being doubled. Sample several stretches of live play, not one.

    python -m tools.fpscheck --at 1200 2400 3600 4800 --window 10
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ur.ffprobe import ffmpeg, probe_video  # noqa: E402

_FRAME = re.compile(r"frame=\s*(\d+)")


def kept_frames(source: Path, t: float, window: float) -> int:
    proc = ffmpeg(
        ["-ss", f"{t:.3f}", "-i", str(source), "-t", f"{window:.3f}",
         "-an", "-sn", "-vf", "mpdecimate", "-fps_mode", "vfr", "-f", "null", "-"],
        check=False,
    )
    hits = _FRAME.findall(proc.stderr)
    return int(hits[-1]) if hits else -1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="tools.fpscheck")
    p.add_argument("--source", default="raw/sol-vs-windchill-2026-semi.mp4")
    p.add_argument("--at", type=float, nargs="+", required=True)
    p.add_argument("--window", type=float, default=10.0)
    p.add_argument("--out", default=None)
    args = p.parse_args(argv)

    source = Path(args.source)
    info = probe_video(source)
    fps = float(info.r_frame_rate)
    expected = round(fps * args.window)

    rows = []
    for t in args.at:
        kept = kept_frames(source, t, args.window)
        ratio = kept / expected if expected else 0.0
        rows.append({"t": t, "expected": expected, "kept": kept, "kept_ratio": round(ratio, 4)})
        print(f"t={t:8.1f}s  expected {expected:4d}  kept {kept:4d}  ({ratio * 100:5.1f}%)")

    ratios = [r["kept_ratio"] for r in rows if r["kept"] >= 0]
    mean = sum(ratios) / len(ratios) if ratios else 0.0
    verdict = (
        "60 fps appears GENUINE (few duplicate frames)" if mean > 0.85 else
        "60 fps appears DOUBLED from ~30 fps (about half the frames are duplicates)"
        if 0.40 <= mean <= 0.62 else
        f"inconclusive: mean kept ratio {mean:.3f}"
    )
    print(f"\nmean kept ratio {mean:.3f} -> {verdict}")
    result = {"source": source.name, "container_fps": fps, "window_s": args.window,
              "samples": rows, "mean_kept_ratio": round(mean, 4), "verdict": verdict}
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
