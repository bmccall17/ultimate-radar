"""Thin, honest wrappers around ffprobe/ffmpeg.

Every function here shells out to the system binaries and returns parsed data or
raises. Nothing here guesses: if ffprobe will not tell us a number, we do not
invent one.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path


class ToolMissing(RuntimeError):
    pass


def _bin(name: str) -> str:
    found = shutil.which(name)
    if not found:
        raise ToolMissing(
            f"{name} not found on PATH. Install it (winget install Gyan.FFmpeg) and retry."
        )
    return found


def run(argv: list[str], *, check: bool = True) -> subprocess.CompletedProcess:
    """Run a command, capturing both streams as text."""
    return subprocess.run(
        argv, check=check, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )


def ffmpeg(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess:
    return run([_bin("ffmpeg"), "-hide_banner", "-nostdin", *args], check=check)


def ffprobe_json(args: list[str]) -> dict:
    proc = run([_bin("ffprobe"), "-v", "error", "-of", "json", *args])
    return json.loads(proc.stdout)


def tool_versions() -> dict[str, str]:
    """Record exactly which binaries produced an artefact (AGENTS rule 6)."""
    out = {}
    for name in ("ffmpeg", "ffprobe"):
        try:
            line = run([_bin(name), "-version"], check=False).stdout.splitlines()[0]
        except (ToolMissing, IndexError):
            line = "unknown"
        out[name] = line.strip()
    return out


@dataclass(frozen=True)
class VideoInfo:
    path: Path
    width: int
    height: int
    codec: str
    r_frame_rate: Fraction
    avg_frame_rate: Fraction
    duration_s: float
    nb_frames: int | None
    bit_rate: int | None

    @property
    def fps(self) -> float:
        """The rate we quote. r_frame_rate is the container's nominal rate."""
        return float(self.r_frame_rate)


def probe_video(path: Path) -> VideoInfo:
    data = ffprobe_json(
        [
            "-select_streams", "v:0",
            "-show_entries",
            "stream=width,height,codec_name,r_frame_rate,avg_frame_rate,nb_frames,bit_rate:"
            "format=duration",
            str(path),
        ]
    )
    st = data["streams"][0]
    fmt = data.get("format", {})
    nb = st.get("nb_frames")
    br = st.get("bit_rate")
    return VideoInfo(
        path=path,
        width=int(st["width"]),
        height=int(st["height"]),
        codec=st["codec_name"],
        r_frame_rate=Fraction(st["r_frame_rate"]),
        avg_frame_rate=Fraction(st["avg_frame_rate"]),
        duration_s=float(fmt["duration"]),
        nb_frames=int(nb) if nb not in (None, "N/A") else None,
        bit_rate=int(br) if br not in (None, "N/A") else None,
    )


def frame_times(path: Path, start_s: float, window_s: float = 6.0) -> list[float]:
    """Presentation timestamps of video frames at and after ``start_s``.

    ffprobe seeks to the keyframe at or before ``start_s`` and then reads
    ``window_s`` of decoded output *from that keyframe*, not from the requested
    time. With keyframes several seconds apart a short window can therefore stop
    before it ever reaches ``start_s``, so the default here is generous and
    callers filter the result.
    """
    data = ffprobe_json(
        [
            "-select_streams", "v:0",
            "-read_intervals", f"{start_s:.6f}%+{window_s:.6f}",
            "-show_entries", "frame=best_effort_timestamp_time,pts_time",
            str(path),
        ]
    )
    times: list[float] = []
    for fr in data.get("frames", []):
        t = fr.get("best_effort_timestamp_time", fr.get("pts_time"))
        if t in (None, "N/A"):
            continue
        times.append(float(t))
    return sorted(times)
