"""M0 - cut one possession out of the broadcast and record where it came from.

Emits, into ``work/<possession_id>/``:

  clip.mp4          the possession at the source framerate, for the viewer
  frames/000000.jpg 15 fps, zero-indexed, the tracking rate
  clip.json         per docs/03-data-contracts.md

The one number that must never be wrong is ``source.start_s``: the offset, in
seconds, of clip frame 0 within the full broadcast. Everything a coach clicks in
the viewer maps back through it. So we do not record the *requested* start time
and hope; we measure which source frame actually became frame 0, and prove it by
comparing pixels against its neighbours.

Usage:

    python -m ur.ingest --source raw/game.mp4 --id p0001 \
        --start 00:25:10 --duration 21 \
        --offense sol --defense chill --attacking-direction +x
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import re
import shutil
import sys
from pathlib import Path

import numpy as np

from .ffprobe import ffmpeg, frame_times, probe_video, run, tool_versions

SCHEMA = "ultimate-radar/clip@1"
TRACKING_FPS = 15
SEED = 20260827  # date of the match; any fixed value would do (AGENTS rule 6)

# UFA 2026 field. docs/01-brief.md sources this from the rulebook; see
# docs/00-footage-report.md for the primary-source check.
FIELD = {
    "length_yd": 120.0,
    "width_yd": 53.333,
    "endzone_yd": 20.0,
    "brick_yd": 20.0,
    "spec": "UFA 2026",
}

TEAMS = {
    "sol": {"name": "Austin Sol", "kit": "light"},
    "chill": {"name": "Minnesota Wind Chill", "kit": "dark"},
}


# --------------------------------------------------------------------------- #
# time parsing
# --------------------------------------------------------------------------- #

_TS = re.compile(r"^(?:(?:(\d+):)?(\d+):)?(\d+(?:\.\d+)?)$")


def parse_timestamp(text: str) -> float:
    """Accept 1510, 25:10, 00:25:10, 00:25:10.5 - return seconds."""
    m = _TS.match(text.strip())
    if not m:
        raise ValueError(f"cannot parse timestamp {text!r}")
    h, mnt, sec = m.groups()
    return (int(h or 0) * 3600) + (int(mnt or 0) * 60) + float(sec)


def fmt_timestamp(seconds: float) -> str:
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h):02d}:{int(m):02d}:{s:06.3f}"


# --------------------------------------------------------------------------- #
# source acquisition
# --------------------------------------------------------------------------- #

YT_FORMAT = "bv*[height<=1080][vcodec^=avc1]+ba/bv*[height<=1080]+ba/b[height<=1080]"


def fetch_source(url: str, dest: Path) -> Path:
    """Download the broadcast once, preferring 1080p avc1 (docs/10 section 2)."""
    if dest.exists():
        print(f"[ingest] source already present: {dest}")
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"[ingest] downloading {url} -> {dest}")
    proc = run(
        [
            sys.executable, "-m", "yt_dlp",
            "-f", YT_FORMAT,
            "--merge-output-format", "mp4",
            "-o", str(dest.with_suffix(".%(ext)s")),
            url,
        ],
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            "yt-dlp failed. If egress is blocked, download by hand and pass "
            f"--source.\n{proc.stderr[-2000:]}"
        )
    if not dest.exists():
        raise RuntimeError(f"yt-dlp reported success but {dest} is missing")
    return dest


# --------------------------------------------------------------------------- #
# the start-offset measurement
# --------------------------------------------------------------------------- #

def resolve_start(source: Path, requested_s: float) -> tuple[float, list[float]]:
    """Find the source frame that an input seek to ``requested_s`` will land on.

    ffmpeg's ``-ss`` before ``-i`` with a re-encode decodes from the preceding
    keyframe and drops frames whose timestamp precedes the target, so clip frame
    0 is the first source frame at or after ``requested_s``. Returns that
    timestamp plus the surrounding frame times, which the caller uses to verify
    the claim rather than trust it.
    """
    window = 6.0
    for _ in range(4):
        times = frame_times(source, max(0.0, requested_s - 0.2), window_s=window)
        at_or_after = [t for t in times if t >= requested_s - 1e-6]
        if at_or_after:
            return at_or_after[0], times
        window *= 2  # keyframe further back than expected; read more
    raise RuntimeError(
        f"no frame at or after {requested_s}s in {source} after probing a "
        f"{window:.0f}s window. Is the start past the end of the file?"
    )


def _read_gray(path: Path) -> np.ndarray:
    import cv2

    img = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise RuntimeError(f"could not read {path}")
    return img.astype(np.float32)


def verify_start(
    source: Path, clip_frame0: Path, start_s: float, neighbours: list[float], scratch: Path,
    fps: float,
) -> dict:
    """Prove clip frame 0 is the source frame at ``start_s``, not its neighbour.

    Extracts the source frames on either side, compares each against clip frame 0
    by mean absolute difference, and reports which one won. A re-encode means the
    match is close but not exact; a *wrong* offset means a different moment of a
    moving image, which is not close at all.
    """
    import cv2

    scratch.mkdir(parents=True, exist_ok=True)
    target = _read_gray(clip_frame0)

    candidates = sorted(t for t in neighbours if abs(t - start_s) < 0.09)
    scores: list[dict] = []
    for i, t in enumerate(candidates):
        probe = scratch / f"probe_{i:02d}.png"
        # Same half-frame back-off the cut uses, so "the frame at t" means the
        # same thing on both sides of the comparison. Without this the probe and
        # the cut disagree by exactly one frame and the check measures nothing.
        seek = max(0.0, t - 0.5 / fps)
        ffmpeg(["-y", "-ss", f"{seek:.6f}", "-i", str(source), "-frames:v", "1", str(probe)])
        img = cv2.imread(str(probe), cv2.IMREAD_GRAYSCALE)
        if img is None:
            continue
        img = img.astype(np.float32)
        if img.shape != target.shape:
            img = cv2.resize(img, (target.shape[1], target.shape[0]))
        scores.append({"t": round(t, 6), "mad": round(float(np.abs(img - target).mean()), 3)})

    if not scores:
        return {"ok": False, "reason": "no comparable source frames extracted"}

    best = min(scores, key=lambda s: s["mad"])
    others = [s for s in scores if s is not best]
    runner_up = min(others, key=lambda s: s["mad"]) if others else None
    margin = (runner_up["mad"] - best["mad"]) if runner_up else None
    return {
        # "ok" means the measurement is *decisive* — one source frame matches
        # clearly better than its neighbours — not that it matched a guess.
        "ok": bool(runner_up is None or margin > 0.5),
        "measured_t": best["t"],
        "intended_t": round(start_s, 6),
        "off_by_s": round(best["t"] - start_s, 6),
        "best_mad": best["mad"],
        "runner_up_mad": runner_up["mad"] if runner_up else None,
        "margin": round(margin, 3) if margin is not None else None,
        "candidates": scores,
        "method": "mean absolute grey-level difference vs clip frame 0",
    }


# --------------------------------------------------------------------------- #
# cutting
# --------------------------------------------------------------------------- #

def cut_clip(source: Path, start_s: float, duration_s: float, out: Path,
             fps: float) -> list[str]:
    """Re-encode the possession, starting on the frame whose pts is ``start_s``.

    Never a stream copy: it can only cut on a keyframe, which silently moves the
    start by up to a couple of seconds.

    The seek target is backed off half a frame. ffmpeg's input seek keeps frames
    strictly *after* the timestamp, so seeking to a frame's exact pts drops that
    very frame and the clip starts one frame late — measured, not assumed; see
    ``verify_start``, which is what caught it.
    """
    out.parent.mkdir(parents=True, exist_ok=True)
    seek = max(0.0, start_s - 0.5 / fps)
    args = [
        "-y",
        "-ss", f"{seek:.6f}",
        "-i", str(source),
        "-t", f"{duration_s:.6f}",
        "-map", "0:v:0",
        "-an",
        # Without this the cut clip's first frame keeps a non-zero pts, and the
        # fps=15 resample then lands one frame late — so clip.mp4 (what the
        # viewer plays) and frames/ (what the pipeline indexes) would disagree
        # by a frame, and the overlay would sit on the wrong moment.
        "-vf", "setpts=PTS-STARTPTS",
        "-c:v", "libx264", "-crf", "16", "-preset", "slow", "-pix_fmt", "yuv420p",
        "-fflags", "+bitexact", "-flags:v", "+bitexact",
        "-map_metadata", "-1",
        str(out),
    ]
    ffmpeg(args)
    return args


def extract_frames(clip: Path, out_dir: Path, fps: int) -> int:
    """15 fps jpegs, **zero-indexed** to match docs/03 (frames/000000.jpg)."""
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)
    ffmpeg(
        [
            "-y", "-i", str(clip),
            "-vf", f"fps={fps}",
            "-q:v", "2",
            "-start_number", "0",
            str(out_dir / "%06d.jpg"),
        ]
    )
    return len(list(out_dir.glob("*.jpg")))


def _best_clip_frame(seq_dir: Path, target: Path, ideal: int, radius: int = 5) -> tuple[int, float]:
    import cv2

    tgt = cv2.imread(str(target), cv2.IMREAD_GRAYSCALE)
    if tgt is None:
        return -1, float("inf")
    tgt = tgt.astype(np.float32)
    best = (-1, float("inf"))
    for k in range(max(0, ideal - radius), ideal + radius + 1):
        img = cv2.imread(str(seq_dir / f"{k:06d}.png"), cv2.IMREAD_GRAYSCALE)
        if img is None:
            continue
        d = float(np.abs(img.astype(np.float32) - tgt).mean())
        if d < best[1]:
            best = (k, d)
    return best


def clip_frame_sync(clip: Path, frames_dir: Path, n_frames: int, track_fps: int,
                    src_fps: float, scratch: Path) -> dict:
    """Measure how clip.mp4 time maps to the frames/ index.

    The viewer plays clip.mp4 and draws an overlay indexed by frames/. If the two
    disagree even by one frame the overlay sits on the wrong moment and nothing
    else in the pipeline would notice.

    ffmpeg's ``fps`` filter resamples 59.94 -> 15 by bucketing each input frame
    into an output slot and keeping the *last* one in the bucket, so frames/n is
    the source frame ``ceil((n + 0.5) * src_fps / track_fps) - 1`` rather than
    the nearest one. That is a sawtooth lag of up to one source frame behind a
    uniform n/track_fps clock, not a constant offset. We assert the model against
    real pixels at two points in the clip and record the worst-case error, so
    anything downstream that cares can use the formula and everything else can
    treat n/track_fps as right to within the stated bound.
    """
    scratch.mkdir(parents=True, exist_ok=True)

    def model(n: int) -> int:
        return math.ceil((n + 0.5) * src_fps / track_fps) - 1

    probes = [0, n_frames // 2] if n_frames > 4 else [0]
    need = max(model(p) for p in probes) + 6
    ffmpeg(["-y", "-i", str(clip), "-frames:v", str(need), "-start_number", "0",
            str(scratch / "%06d.png")])

    results, worst = [], 0.0
    for p in probes:
        predicted = model(p)
        k, mad = _best_clip_frame(scratch, frames_dir / f"{p:06d}.jpg", predicted)
        err = abs(k / src_fps - p / track_fps) if k >= 0 else float("inf")
        worst = max(worst, err)
        results.append({"frame_index": p, "predicted_clip_frame": predicted,
                        "matched_clip_frame": k, "model_ok": k == predicted,
                        "error_vs_uniform_s": round(err, 6), "mad": round(mad, 3)})

    return {
        "model_holds": all(r["model_ok"] for r in results),
        "frames_to_clip_frame": "ceil((n + 0.5) * src_fps / track_fps) - 1",
        "max_error_vs_uniform_s": round(worst, 6),
        "one_source_frame_s": round(1.0 / src_fps, 6),
        "probes": results,
        "method": "nearest clip frame by mean absolute grey-level difference",
    }


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #

def ingest(args: argparse.Namespace) -> dict:
    random.seed(SEED)
    np.random.seed(SEED)

    source = Path(args.source)
    if args.url and not source.exists():
        source = fetch_source(args.url, source)
    if not source.exists():
        raise SystemExit(f"source not found: {source}. Pass --url to download it.")

    info = probe_video(source)
    requested = parse_timestamp(args.start)
    if args.end:
        duration = parse_timestamp(args.end) - requested
    else:
        duration = float(args.duration)
    if duration <= 0:
        raise SystemExit("duration must be positive")

    start_s, neighbours = resolve_start(source, requested)
    delta_ms = 1000 * (start_s - requested)
    print(
        f"[ingest] requested {fmt_timestamp(requested)} -> "
        f"actual frame at {fmt_timestamp(start_s)} (delta {delta_ms:+.1f} ms)"
    )

    work = Path(args.work) / args.id
    clip = work / "clip.mp4"
    cmd = cut_clip(source, start_s, duration, clip, float(info.r_frame_rate))
    clip_info = probe_video(clip)

    n_frames = extract_frames(clip, work / "frames", args.fps)
    expected = round(clip_info.duration_s * args.fps)
    drift = n_frames - expected
    if abs(drift) > 1:
        print(
            f"[ingest] WARNING frame count {n_frames} vs expected {expected} "
            f"(clip {clip_info.duration_s:.3f}s x {args.fps} fps). "
            "Clip boundaries are off; everything downstream inherits this."
        )

    verification = verify_start(
        source, work / "frames" / "000000.jpg", start_s, neighbours, work / "_verify",
        float(info.r_frame_rate),
    )
    shutil.rmtree(work / "_verify", ignore_errors=True)

    # source.start_s is what a coach jumps back through, so it is the *measured*
    # offset of clip frame 0, never the one we asked ffmpeg for.
    measured = verification.get("measured_t", start_s)
    off_by = verification.get("off_by_s", 0.0)
    print(
        f"[ingest] start verification: decisive={verification.get('ok')} "
        f"mad={verification.get('best_mad')} margin={verification.get('margin')} "
        f"off-by={off_by * 1000:+.1f} ms"
    )
    if abs(off_by) > 1.5 / float(info.r_frame_rate):
        print(f"[ingest] WARNING clip frame 0 is {off_by:+.4f}s from the intended frame")
    start_s = measured

    sync = clip_frame_sync(clip, work / "frames", n_frames, args.fps,
                           float(info.r_frame_rate), work / "_sync")
    shutil.rmtree(work / "_sync", ignore_errors=True)
    print(f"[ingest] frames/ vs clip.mp4: model_holds={sync['model_holds']}, "
          f"worst error vs a uniform n/{args.fps} clock "
          f"{sync['max_error_vs_uniform_s'] * 1000:.1f} ms "
          f"(one source frame is {sync['one_source_frame_s'] * 1000:.1f} ms)")
    if not sync["model_holds"]:
        print("[ingest] WARNING frames/ does not map to clip.mp4 as predicted; "
              "the viewer overlay may sit on the wrong moment.")

    doc = {
        "schema": SCHEMA,
        "possession_id": args.id,
        "source": {
            "platform": args.platform,
            "id": args.video_id,
            "file": source.name,
            "start_s": round(start_s, 6),
            "end_s": round(start_s + clip_info.duration_s, 6),
            "requested_start_s": round(requested, 6),
            "video_fps": float(info.r_frame_rate),
            "video_w": info.width,
            "video_h": info.height,
            "video_codec": info.codec,
            "video_duration_s": round(info.duration_s, 3),
            "start_verification": verification,
            "clip_frames_sync": sync,
        },
        "fps": args.fps,
        "frames": n_frames,
        "duration_s": round(clip_info.duration_s, 6),
        "teams": TEAMS,
        "offense": args.offense,
        "defense": args.defense,
        "attacking_direction": args.attacking_direction,
        "field": FIELD,
        "provenance": {
            "seed": SEED,
            "tools": tool_versions(),
            "ffmpeg_cut": " ".join(cmd),
            "clip_sha256": sha256(clip),
            "frame_count_expected": expected,
            "frame_count_drift": drift,
        },
    }
    if args.note:
        doc["note"] = args.note

    (work / "clip.json").write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    print(f"[ingest] wrote {work / 'clip.json'}  ({n_frames} frames, {clip_info.duration_s:.3f}s)")
    return doc


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ur.ingest",
        description="Cut one possession and write clip.json.",
    )
    p.add_argument("--source", default="raw/sol-vs-windchill-2026-semi.mp4",
                   help="local broadcast file")
    p.add_argument("--url", default=None, help="download to --source if it is missing")
    p.add_argument("--id", default="p0001", help="possession id, e.g. p0001")
    p.add_argument("--start", required=True, help="start timestamp, e.g. 00:25:10")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--duration", type=float, help="clip length in seconds")
    g.add_argument("--end", help="end timestamp, e.g. 00:25:31")
    p.add_argument("--fps", type=int, default=TRACKING_FPS, help="tracking framerate")
    p.add_argument("--work", default="work", help="working directory root")
    p.add_argument("--offense", default="sol", choices=sorted(TEAMS))
    p.add_argument("--defense", default="chill", choices=sorted(TEAMS))
    p.add_argument("--attacking-direction", default="+x", choices=["+x", "-x"])
    p.add_argument("--platform", default="youtube")
    p.add_argument("--video-id", default="IDnoyd4cKfM")
    p.add_argument("--note", default=None, help="free text recorded in clip.json")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.offense == args.defense:
        raise SystemExit("offense and defense must differ")
    os.environ.setdefault("PYTHONHASHSEED", "0")
    ingest(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
