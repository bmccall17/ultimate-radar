"""Find possessions worth cutting, and reject the rest before anything expensive.

`docs/10-getting-the-footage.md` § 4 names the two filters, and both were learned
the expensive way: p0002 was cut, calibrated, detected, tracked and published
before anyone said out loud that it was an out-of-bounds pull with no play in it.

  1. **Something happens.** A real sequence of throws, ideally ending in a score.
  2. **The camera shows the paint.** Calibration needs the centre circle and the
     halfway line; a possession where they are rarely in shot cannot be rescued
     downstream.

Both are measurable off the broadcast without cutting anything.

    python -m tools.scout goals  --out eval/m9/goals.json
    python -m tools.scout score  --goals eval/m9/goals.json --out eval/m9
    python -m tools.scout sheet  --start 7092 --end 7122 --out eval/m9/sheets

## Filter 1 is the scoreboard

Every goal is a score change, and the score is rendered in a fixed box at the
bottom of the frame. Scanning **keyframes only** reads the whole 2 h 22 m in
about a minute (a keyframe every 4.6 s, which is finer than the thing being
measured), and a second 4 fps pass around each change pins it to a quarter
second. That gives 52 timestamps at which a point ended, and the thirty seconds
before one of them is a possession that ended in a goal.

The digits are not OCR'd. They are clustered by pixel pattern - the bug is
rendered identically every time, so identical scores produce identical bitmaps -
and the clusters are labelled once, by eye, from a contact sheet. `SCORE_L` and
`SCORE_R` below are that labelling. A reading is only used when two consecutive
keyframes agree, which drops single-frame misreads, and the reconstruction is
checked by the one thing that can contradict it: **every change must move exactly
one team by exactly one**, and the totals must add up to the number of changes.

The score box is also a **shot detector for free**. It is absent during replays,
timeouts and graphics, so a window where it flickers is a window with a cut in
it, and the pipeline assumes one shot per possession.

## Filter 2 is the paint, measured the way calibration will measure it

Not "is there white on the grass" - the same detector M1 uses, asked the same
question: does `find_centre_circle_ransac` find a conic, and does
`find_halfway_line` find the line through it. A frame where both are found is a
frame that can be calibrated; the fraction over a window is what M1's confidence
will have to work with. This is a *pre*-check and cannot promise M1 will pass -
`docs/28` is the story of a calibration that looked healthy and was 6.8 yd out -
but it is very cheap and it rejects the hopeless.

The sheet is the point. A number ranks candidates; a person confirms them.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ur.calibrate import features as F  # noqa: E402
from ur.calibrate import paint  # noqa: E402
from ur.calibrate.mask import BOOTSTRAP_HORIZON as HORIZON_ROW  # noqa: E402
from ur.ffprobe import _bin  # noqa: E402

DEFAULT_SOURCE = "raw/sol-vs-windchill-2026-semi.mp4"

# The score box, in the 1920x1080 broadcast: both teams' numbers and nothing
# else. Measured off survey/uniform/004_t1080.0.png. Height is rounded to 64 by
# ffmpeg's crop on a 4:2:0 stream, which is why the constant is 64 and not 65.
BOX = (890, 930, 140, 64)          # x, y, w, h
INK = 190                          # a digit stroke is near-white
CORE = slice(10, 58)               # rows inside the box, clear of grass bleed
DIGIT_L = slice(2, 68)             # the left team's number within the box
DIGIT_R = slice(72, 138)           # the right team's

# The game clock, at the right-hand end of the same bug. It is not read - only
# watched for the moment it stops changing, which is the moment of the goal:
# UFA stops the clock on a score and restarts it on the pull. Checked against the
# two possessions that were already cut by hand, whose notes were written by
# watching: p0003's clip.json says the goal is at ~1617 and the clock freezes at
# 1616.85; p0001's says ~7330 and it freezes at 7329.57.
CLOCK = (1285, 944, 80, 40)

# The score bug trails the goal by 9 to 15 seconds - it updates over the replay,
# not over the catch - so it is useless as a moment and only ever used to find
# roughly where to look for the freeze.
CLOCK_LOOKBACK_S = 45.0

# What counts as the clock changing, and what counts as it having stopped.
#
# Both are pixel counts over the binarised clock box, and both were already here
# as bare 60s inside `clock_freeze`. The _PX matters: `INK` above is a grey level
# and these are counts of pixels above it, which is close enough in a name to be
# worth spelling out. A digit's worth of changed pixels is CLOCK_CHANGE_PX; below
# CLOCK_LIT_PX nothing is lit at all, so a change into an empty box is the bug
# being wiped off for a graphic rather than a tick.
#
# CLOCK_TICK_GAP_S is the new one. A running clock changes once a second, and
# over the twelve goals in `fixtures/clock_freeze.json` the widest gap *inside*
# a ticking run is 2.25 s - a tick whose frame the 4 fps sample missed. Three
# seconds sits above that and far below the gaps that separate a run from the
# events after it (6.00, 7.75, 9.00, 11.25, 15.00 s in that same fixture), so
# nothing observed lands near the boundary. docs/30 section 2.24.
CLOCK_CHANGE_PX = 60
CLOCK_LIT_PX = 60
CLOCK_TICK_GAP_S = 3.0

# How many changes in a row make a clock rather than a coincidence. The events
# that used to win were one frame (a wipe, a re-render, a change one pixel over
# CLOCK_CHANGE_PX) or two together (the bug drawing itself back on, 0.25 s apart);
# the shortest real ticking run in the fixture is 10. Three separates them with
# nothing observed in between, and a run of three at a second's cadence is a
# clock that visibly ran for two seconds. docs/30 section 2.24.
CLOCK_MIN_TICKS = 3

# How far past the flip to keep looking. Unchanged at the 2.0 that was inline
# here before, and now measured rather than inherited. Two goals' clocks are
# still ticking where this window closes, and widening it to reach them is the
# obvious move and the wrong one - over the 52, against a corrected `goal_t`:
#
#   tail   goals with a freeze   smallest lead   goals where the freeze
#                                                follows the flip
#    2.0        50 of 52            1.25 s              0
#    3.0        50 of 52            0.50 s              0
#    5.0        48 of 52            0.50 s              0
#    8.0        49 of 52           -4.75 s              2
#   20.0        51 of 52          -15.25 s              9
#
# The clock stops a median of 3.38 s BEFORE the flip, so everything past it is
# the pull restarting and the graphics over it. Buying two more goals costs the
# ordering on nine. docs/30 section 2.24.
CLOCK_TAIL_S = 2.0

# The window has to sit inside one shot: the pipeline assumes one shot per
# possession and calibration initialises each frame from its neighbour.
#
# Cuts come from `eval/m0/cuts_full`, which M0 already scanned over the whole
# broadcast, at the threshold M0 chose - 0.35. Re-deriving it here would be a
# second opinion with no more evidence behind it, and `tools/cuts.py` explains
# why the number is arguable at all: a hard cut scores high and so does a whip
# pan, so no threshold separates them cleanly on this footage. Two thresholds
# are used for two different jobs. Above CUT_HARD a window is rejected. Between
# CUT_SOFT and CUT_HARD it is flagged, because that band contains both the
# dissolve into p0003's replay (0.235, a real boundary) and three camera moves
# inside p0001's single 104 s shot (0.23-0.29, not boundaries) - which is
# exactly why a person looks at the sheet.
CUTS_SCAN = "eval/m0/cuts_full/events.json"
CUT_HARD = 0.35
CUT_SOFT = 0.20

# Cluster labels, read once by eye off the contact sheet `goals` writes. The
# order is by cluster size, which is stable for a given scan because the
# clustering is a single deterministic pass. `None` is a cluster that is not a
# number - the bug half-covered by a graphic wipe.
SCORE_L = [12, 18, 19, 4, 3, 23, 6, 11, 1, 16, 21, 14, 22, 2, 20, 5, 7, 15, 0,
           10, 17, 24, 9, None]
SCORE_R = [11, 25, 3, 18, 10, 7, 15, 26, 16, 20, 12, 17, 1, 19, 22, 5, 21, 24,
           4, 28, 9, 23, 14, 0, 6, 27, None, 2]

# 8 and 3, 13 and 18, 14 and 19 differ by two short strokes at this size, and
# the scan above never produced a stable cluster for 8 or 13 - so those readings
# come back as their look-alike. It does not matter for finding goals (the
# change is still at the right time) and it would matter a great deal for
# reporting a scoreline, so the reconstruction repairs it from the constraint
# that a score only ever goes up by one, and says so when it cannot.
LOOKALIKE = {3: 8, 18: 13, 19: 14}


# --------------------------------------------------------------------------- #
# filter 1 - the scoreboard
# --------------------------------------------------------------------------- #

def _crop_stream(source: Path, args: list[str]) -> tuple[np.ndarray, list[float]]:
    """Decode the score box only, and return the frames with their timestamps."""
    x, y, w, h = BOX
    cmd = [_bin("ffmpeg"), "-hide_banner", "-nostdin", *args,
           "-an", "-sn", "-fps_mode", "passthrough",
           "-vf", f"crop={w}:{h + 1}:{x}:{y},format=gray,showinfo",
           "-f", "rawvideo", "-"]
    p = subprocess.run(cmd, capture_output=True)
    a = np.frombuffer(p.stdout, np.uint8)
    n = len(a) // (w * h)
    frames = a[: n * w * h].reshape(n, h, w)
    times = [float(s.split(b"pts_time:")[1].split()[0])
             for s in p.stderr.split(b"\n") if b"pts_time:" in s]
    return frames, times[:n]


def _binary(frames: np.ndarray) -> np.ndarray:
    return (frames[:, CORE, :] > INK).astype(np.int16)


def _present(frames: np.ndarray) -> np.ndarray:
    """Is the score bug on screen? It is not, during replays and breaks."""
    core = frames[:, CORE, :]
    ink = (core > INK).reshape(len(core), -1).sum(1)
    dark = (core < 70).mean(axis=(1, 2))
    return (ink > 150) & (ink < 3000) & (dark > 0.4)


def _cluster(box: np.ndarray, present: np.ndarray, thr: int = 90):
    """One deterministic pass: a frame joins the first exemplar close enough."""
    ex: list[np.ndarray] = []
    lab = np.full(len(box), -1)
    for i, f in enumerate(box):
        if not present[i]:
            continue
        d = [int(np.abs(f - e).sum()) for e in ex]
        k = int(np.argmin(d)) if d else -1
        if d and d[k] < thr:
            lab[i] = k
        else:
            ex.append(f)
            lab[i] = len(ex) - 1
    return ex, lab


def _templates(box: np.ndarray, lab: np.ndarray, min_count: int = 8):
    order = sorted({int(k) for k in lab if k >= 0},
                   key=lambda k: -int((lab == k).sum()))
    keep = [k for k in order if int((lab == k).sum()) >= min_count]
    return [(box[lab == k].mean(0) > 0.5).astype(np.int16) for k in keep]


def _repair(seq: list[tuple[float, int, int]]) -> list[tuple[float, int, int]]:
    """Undo the look-alike misreads, using the only constraint available.

    A score never falls and never jumps. Where a reading breaks that and its
    look-alike does not, the look-alike is the reading.
    """
    out = [seq[0]]
    for t, l, r in seq[1:]:
        pl, pr = out[-1][1], out[-1][2]
        for a, b in ((l, r), (LOOKALIKE.get(l, l), r), (l, LOOKALIKE.get(r, r)),
                     (LOOKALIKE.get(l, l), LOOKALIKE.get(r, r))):
            if a >= pl and b >= pr and (a - pl) + (b - pr) <= 1:
                out.append((t, a, b))
                break
        else:
            out.append((t, l, r))
    return out


def find_goals(source: Path, out: Path | None) -> list[dict]:
    frames, times = _crop_stream(source, ["-skip_frame", "nokey", "-i", str(source)])
    present = _present(frames)
    b = _binary(frames)
    print(f"[scout] {len(frames)} keyframes, score bug present on "
          f"{int(present.sum())} ({present.mean():.0%})")

    reading = {}
    for name, sl, labels in (("L", DIGIT_L, SCORE_L), ("R", DIGIT_R, SCORE_R)):
        box = b[:, :, sl]
        ex, lab = _cluster(box, present)
        tpl = _templates(box, lab)
        if len(tpl) != len(labels):
            print(f"[scout] !! {name}: {len(tpl)} templates but {len(labels)} "
                  f"labels in SCORE_{name}. The labelling is stale - re-run with "
                  "--dump-templates and relabel by eye.", file=sys.stderr)
        vals = np.full(len(box), -1)
        for i in range(len(box)):
            if not present[i]:
                continue
            d = np.array([int(np.abs(box[i] - t).sum()) for t in tpl])
            k = int(d.argmin())
            if d[k] < 120 and k < len(labels) and labels[k] is not None:
                vals[i] = labels[k]
        reading[name] = vals

    ok = (reading["L"] >= 0) & (reading["R"] >= 0)
    seq = [(times[i], int(reading["L"][i]), int(reading["R"][i]))
           for i in range(len(times)) if ok[i]]
    # A reading counts only when the next keyframe agrees with it.
    conf = [seq[i] for i in range(len(seq) - 1) if seq[i][1:] == seq[i + 1][1:]]
    conf = _repair(conf)

    goals = []
    for i in range(1, len(conf)):
        (ta, la, ra), (tb, lb, rb) = conf[i - 1], conf[i]
        if (lb, rb) == (la, ra):
            continue
        goals.append({"after_t": round(ta, 2), "before_t": round(tb, 2),
                      "from": [la, ra], "to": [lb, rb],
                      "scorer": "ATX" if lb > la else "MIN" if rb > ra else "?"})

    steps = [(g["to"][0] - g["from"][0]) + (g["to"][1] - g["from"][1]) for g in goals]
    final = conf[-1][1:]
    consistent = all(s == 1 for s in steps) and sum(final) == len(goals)
    print(f"[scout] {len(goals)} score changes, final {final[0]}-{final[1]}. "
          f"Every change moves one team by one and the totals add up: "
          f"{'yes' if consistent else 'NO - the reconstruction is wrong'}")
    if not consistent:
        for g, s in zip(goals, steps):
            if s != 1:
                print(f"   {g['from']} -> {g['to']} at {g['after_t']}", file=sys.stderr)

    goals = _refine(source, goals)
    # The freeze belongs beside the flip. It existed only in `windows.json`, a
    # by-product of the window-ranking pass, so anything wanting both the goal
    # and the moment it happened had to read two files and join them on a float.
    # #16 task 2: the index reads one file.
    for g in goals:
        g["clock_freeze_t"] = (clock_freeze(source, g["goal_t"])
                               if g["goal_t"] is not None else None)
    got = sum(g["clock_freeze_t"] is not None for g in goals)
    print(f"[scout] clock freeze found for {got} of {len(goals)} changes")

    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(
            {"source": source.name, "final_score": {"ATX": final[0], "MIN": final[1]},
             "reconstruction_consistent": consistent,
             "note": "goal_t is when the score bug flips and clock_freeze_t is "
                     "the last second the game clock ticked before it, which is "
                     "the goal. The flip trails it; over this scan the gap runs "
                     "4.50-16.75 s. Look at the stills.",
             "goals": goals}, indent=1) + "\n", encoding="utf-8")
        print(f"[scout] -> {out}")
    return goals


def _refine(source: Path, goals: list[dict]) -> list[dict]:
    """Pin each change to a quarter second with a short 4 fps pass.

    The box is compared against the score either side of the change rather than
    against a fixed distance from its own first frame, which is what this used to
    do: it wanted a frame more than 200 from the opening state, and an 8 becoming
    a 9 is two short strokes worth about 90, so on a clean goal nothing qualified
    and only a frame mid-wipe ever did. It reproduced 1 of its own 52 answers and
    put 49 of them outside the bracket on the line above. #16, docs/30 s 2.24.
    """
    for g in goals:
        t0, t1 = g["after_t"] - 1.0, g["before_t"] + 2.0
        frames, _ = _crop_fps(source, t0, t1 - t0, 4)
        b = _binary(frames).astype(np.int16)
        if len(b) < 9:
            g["goal_t"] = None
            continue
        # Four frames a side, not one: the single frame this used as a reference
        # could itself be mid-graphic, and then every distance behind it is
        # measured from a wipe.
        old_box, new_box = np.median(b[:4], axis=0), np.median(b[-4:], axis=0)
        d_old = [int(np.abs(x - old_box).sum()) for x in b]
        d_new = [int(np.abs(x - new_box).sum()) for x in b]
        k = flip_index(d_old, d_new)
        g["goal_t"] = round(t0 + k / 4.0, 2) if k is not None else None
    return goals


def flip_index(d_old, d_new) -> int | None:
    """The frame the score bug changed on, given how far it sits from each score.

    `d_old` and `d_new` are per-frame distances from the box to the score it
    showed before the change and the one it showed after. The answer is the
    first frame of the **last** unbroken stretch that reads as the new score.
    """
    if not d_old or d_new[-1] >= d_old[-1]:
        return None
    i = len(d_new) - 1
    while i > 0 and d_new[i - 1] < d_old[i - 1]:
        i -= 1
    return i


def _crop_fps(source: Path, start: float, dur: float, fps: int,
              box: tuple[int, int, int, int] = BOX):
    x, y, w, h = box
    # h + 1 because ffmpeg rounds a crop height down to even on a 4:2:0 stream;
    # asking for one more and reading back h keeps the two in step.
    cmd = [_bin("ffmpeg"), "-hide_banner", "-nostdin", "-ss", f"{start:.3f}",
           "-i", str(source), "-t", f"{dur:.3f}", "-an", "-sn",
           "-fps_mode", "passthrough",
           "-vf", f"fps={fps},crop={w}:{h + (h % 2)}:{x}:{y},format=gray",
           "-f", "rawvideo", "-"]
    p = subprocess.run(cmd, capture_output=True)
    a = np.frombuffer(p.stdout, np.uint8)
    n = len(a) // (w * h)
    return a[: n * w * h].reshape(n, h, w), None


# --------------------------------------------------------------------------- #
# when the goal actually happened, and which shot it happened in
# --------------------------------------------------------------------------- #

def freeze_index(delta, ink, *, fps: int,
                 max_gap_s: float = CLOCK_TICK_GAP_S) -> int | None:
    """The frame the clock last ticked on, given what each frame measured.

    `delta` is how much the binarised clock box changed from the frame before it
    and `ink` how much of it is lit, both per frame. The decision is separated
    from the ffmpeg pass above it so it can be tested on the frames it was
    actually wrong on without opening 2 h 22 m of broadcast - `docs/10` says the
    footage is not redistributed, so `fixtures/clock_freeze.json` carries these
    two series and no pixels.
    """
    q = [i for i in range(len(delta))
         if delta[i] > CLOCK_CHANGE_PX and ink[i] > CLOCK_LIT_PX]
    if not q:
        return None
    gap = max_gap_s * fps
    runs: list[list[int]] = [[q[0]]]
    for a, b in zip(q, q[1:]):
        if b - a > gap:
            runs.append([])
        runs[-1].append(b)
    ticking = [r for r in runs if len(r) >= CLOCK_MIN_TICKS]
    if not ticking:
        return None
    last = ticking[-1][-1]
    # The clock has to be *seen* to stop. A run still going when the window
    # closes has not stopped inside it, and its final tick is only where the
    # looking ran out - reporting that as the freeze reports the window as a
    # measurement. docs/30 section 2.6.
    return last if len(delta) - 1 - last >= gap else None


def clock_freeze(source: Path, bug_t: float, *, fps: int = 4) -> float | None:
    """The last second the game clock ticked before the score bug flipped.

    That is the goal, to within the clock's own one-second resolution. The bug
    itself is late because it updates over the replay, and a window anchored to
    it walks straight through the cut into a celebration close-up - which is the
    mistake `docs/22-m7-preflight.md` records p0003 making the first time it was
    cut.

    This does the looking; `freeze_index` does the deciding. It used to do both,
    and returned the **last** qualifying change in the window rather than the
    moment ticking stopped, so a graphic wipe or the bug re-rendering after the
    replay won and the answer landed at the window edge. #16, docs/30 s 2.24.
    """
    t0 = bug_t - CLOCK_LOOKBACK_S
    fr, _ = _crop_fps(source, t0, CLOCK_LOOKBACK_S + CLOCK_TAIL_S, fps, CLOCK)
    if len(fr) < 4:
        return None
    b = (fr > INK).astype(np.int16)
    ink = [int(x) for x in b.reshape(len(b), -1).sum(1)]
    delta = [0] + [int(x) for x in
                   np.abs(np.diff(b, axis=0)).reshape(len(b) - 1, -1).sum(1)]
    i = freeze_index(delta, ink, fps=fps)
    return round(t0 + i / fps, 2) if i is not None else None


def load_cuts(root: Path) -> list[tuple[float, float]]:
    """M0's whole-broadcast scene scan: (time, score), already committed."""
    p = root / CUTS_SCAN
    if not p.exists():
        raise SystemExit(f"{CUTS_SCAN} is missing. Run: python -m tools.cuts scan "
                         "--whole --out eval/m0/cuts_full")
    ev = json.loads(p.read_text(encoding="utf-8"))["events"]
    return sorted((float(e["t"]), float(e["score"])) for e in ev)


def shot_around(cs: list[tuple[float, float]], t: float,
                threshold: float = CUT_HARD) -> tuple[float | None, float | None]:
    """The shot `t` falls in, bounded by the nearest cuts above `threshold`."""
    before = [c for c, s in cs if s >= threshold and c <= t]
    after = [c for c, s in cs if s >= threshold and c > t]
    return (before[-1] if before else None, after[0] if after else None)


# --------------------------------------------------------------------------- #
# filter 2 - the paint, and the shot
# --------------------------------------------------------------------------- #

def grab(source: Path, t: float) -> np.ndarray | None:
    p = subprocess.run([_bin("ffmpeg"), "-hide_banner", "-nostdin", "-ss",
                        f"{t:.3f}", "-i", str(source), "-frames:v", "1",
                        "-f", "image2pipe", "-vcodec", "png", "-"],
                       capture_output=True)
    if not p.stdout:
        return None
    return cv2.imdecode(np.frombuffer(p.stdout, np.uint8), cv2.IMREAD_COLOR)


def paint_at(args) -> dict:
    """Ask M1's own detector M1's own question, on one frame.

    **Everything above the horizon is blacked out first, and the first version of
    this did not do that.** Calibration never sees the crowd: `ur.calibrate.mask`
    builds a registration mask and zeroes everything above row
    `BOOTSTRAP_HORIZON`. Without it the detectors are looking at banners, tents
    and a video board full of white, and `find_centre_circle_ransac` will fit a
    conic to them.

    It matters more than it sounds. Scored against the six possessions whose
    calibrations are now known, the unmasked version cannot tell a good
    possession from a bad one - p0003 (72 % of frames calibrate) and p0006
    (26 %) both score 0.62. Masked, the four that calibrate score 0.50-0.62 and
    the two that do not score 0.12 and 0.25:

    | | unmasked | masked | frames that calibrate |
    |---|---|---|---|
    | p0001 | 0.88 | 0.50 | 92 % |
    | p0003 | 0.62 | 0.62 | 72 % |
    | p0004 | 0.75 | 0.62 | 64 % |
    | p0005 | 0.50 | 0.62 | 71 % |
    | p0006 | 0.62 | **0.12** | **26 %** |
    | p0007 | 0.50 | **0.25** | **38 %** |

    Six possessions is a thin calibration and p0001 is under-predicted at 0.50
    against 92 %, so this ranks and rejects; it does not estimate. Anything at or
    below 0.25 has never yet been worth cutting.
    """
    source, t = args
    bgr = grab(Path(source), t)
    if bgr is None:
        return {"t": t, "ok": False}
    bgr[:HORIZON_ROW] = 0
    region = cv2.bitwise_not(F.player_mask(bgr))
    region[:HORIZON_ROW] = 0
    pm = paint.largest_components(paint.paint_mask(bgr, region=region), min_area=60)
    ell = F.find_centre_circle_ransac(pm)
    line = F.find_halfway_line(pm, ell) if ell is not None else None
    return {"t": round(t, 2), "ok": True, "paint_px": int((pm > 0).sum()),
            "circle": ell is not None, "line": line is not None}


def score_window(source: Path, start: float, end: float, *, n: int = 8,
                 rows: list[dict] | None = None) -> dict:
    if rows is None:
        rows = [paint_at((str(source), float(t)))
                for t in np.linspace(start, end, n)]
    both = [r for r in rows if r.get("circle") and r.get("line")]
    frames, _ = _crop_fps(source, start, end - start, 2)
    present = _present(frames)
    return {
        "start": round(start, 2), "end": round(end, 2),
        "calibratable_fraction": round(len(both) / max(1, len(rows)), 3),
        "circle_fraction": round(sum(1 for r in rows if r.get("circle"))
                                 / max(1, len(rows)), 3),
        "median_paint_px": int(np.median([r.get("paint_px", 0) for r in rows])),
        "one_shot_fraction": round(float(present.mean()), 3),
        "per_frame": rows,
    }


def sheet(source: Path, start: float, end: float, out: Path, *, n: int = 6,
          label: str = "") -> Path:
    """A contact sheet. The numbers rank candidates; this is what confirms one."""
    out.mkdir(parents=True, exist_ok=True)
    tiles = []
    for t in np.linspace(start, end, n):
        bgr = grab(source, float(t))
        if bgr is None:
            continue
        tile = cv2.resize(bgr, (640, 360))
        cv2.rectangle(tile, (0, 0), (639, 26), (0, 0, 0), -1)
        cv2.putText(tile, f"t={t:.1f}s  (+{t - start:.1f})", (8, 19),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA)
        tiles.append(tile)
    cols = 3
    rows_ = (len(tiles) + cols - 1) // cols
    grid = np.full((rows_ * 360, cols * 640, 3), 20, np.uint8)
    for k, t in enumerate(tiles):
        r_, c_ = divmod(k, cols)
        grid[r_ * 360:(r_ + 1) * 360, c_ * 640:(c_ + 1) * 640] = t
    name = (label or f"{start:.0f}-{end:.0f}") + ".jpg"
    cv2.imwrite(str(out / name), grid, [cv2.IMWRITE_JPEG_QUALITY, 88])
    return out / name


# --------------------------------------------------------------------------- #

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="tools.scout")
    p.add_argument("--source", default=DEFAULT_SOURCE)
    sub = p.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("goals", help="scan the broadcast for score changes")
    g.add_argument("--out", default="eval/m9/goals.json")

    s = sub.add_parser("score", help="rank the window before each goal")
    s.add_argument("--goals", default="eval/m9/goals.json")
    s.add_argument("--lead", type=float, default=30.0,
                   help="seconds of play before the goal to consider")
    s.add_argument("--tail", type=float, default=0.4,
                   help="seconds after the clock froze. Small on purpose: the "
                        "broadcast cuts to a replay a second or two after a "
                        "goal, and p0003's first cut ran 6.4 s past that "
                        "boundary into a celebration close-up (docs/22)")
    s.add_argument("--min-window", type=float, default=22.0,
                   help="reject a goal with less unbroken shot than this")
    s.add_argument("--out", default="eval/m9")
    s.add_argument("--frames", type=int, default=8)
    s.add_argument("--workers", type=int, default=8)

    h = sub.add_parser("sheet", help="contact sheet for one window")
    h.add_argument("--start", type=float, required=True)
    h.add_argument("--end", type=float, required=True)
    h.add_argument("--out", default="eval/m9/sheets")
    h.add_argument("--label", default="")
    h.add_argument("--frames", type=int, default=6)

    a = p.parse_args(argv)
    src = Path(a.source)
    if a.cmd == "goals":
        find_goals(src, Path(a.out))
    elif a.cmd == "score":
        goals = json.loads(Path(a.goals).read_text(encoding="utf-8"))["goals"]
        out = Path(a.out)
        out.mkdir(parents=True, exist_ok=True)
        live = [gl for gl in goals if gl.get("goal_t") is not None]
        cs = load_cuts(Path(__file__).resolve().parent.parent)
        # Step 1, cheap: where the goal really was, and which shot it was in.
        plan = []
        for gl in live:
            bug = gl["goal_t"]
            fz = clock_freeze(src, bug)
            if fz is None:
                plan.append({**gl, "reject": "the game clock could not be read "
                                             "near this goal"})
                continue
            s0, s1 = shot_around(cs, fz)
            t1 = fz + a.tail
            if s1 is not None:
                t1 = min(t1, s1 - 0.4)
            t0 = t1 - a.lead
            if s0 is not None:
                t0 = max(t0, s0 + 0.4)
            soft = [round(c, 2) for c, sc in cs
                    if CUT_SOFT <= sc < CUT_HARD and t0 < c < t1]
            row = {**gl, "bug_t": bug, "clock_freeze_t": fz,
                   "shot": [s0, s1], "shot_len_s": (round(s1 - s0, 2)
                                                    if s0 and s1 else None),
                   "start": round(t0, 2), "end": round(t1, 2),
                   "window_s": round(t1 - t0, 2),
                   "soft_scene_changes_inside": soft}
            if t1 - t0 < a.min_window:
                row["reject"] = (f"only {t1 - t0:.1f}s of unbroken shot before "
                                 "the goal")
            plan.append(row)
        keep = [r for r in plan if "reject" not in r]
        print(f"[scout] {len(keep)} of {len(live)} goals sit at the end of a "
              f"shot long enough to hold a {a.min_window:.0f}s possession")

        # Step 2, expensive: the paint, on the windows that survived. One pool
        # for every frame in every window - on Windows a worker pays a couple of
        # seconds to import cv2, and a pool per window pays it once each.
        tasks, spans = [], []
        for r in keep:
            spans.append(len(tasks))
            tasks += [(str(src), float(t))
                      for t in np.linspace(r["start"], r["end"], a.frames)]
        with ProcessPoolExecutor(max_workers=a.workers) as pool:
            done = list(pool.map(paint_at, tasks, chunksize=2))
        for i, (r, off) in enumerate(zip(keep, spans)):
            r.update(score_window(src, r["start"], r["end"],
                                  rows=done[off:off + a.frames]))
            soft = r["soft_scene_changes_inside"]
            print(f"[{i:>2}] {r['start']:7.1f}-{r['end']:7.1f}s {r['scorer']:>3} "
                  f"{r['from']}->{r['to']}  "
                  f"calibratable {r['calibratable_fraction']:.2f}  "
                  f"bug-on {r['one_shot_fraction']:.2f}  "
                  f"paint {r['median_paint_px']:>6}"
                  + (f"  soft scene change at {soft}" if soft else ""))
        for r in plan:
            if "reject" in r:
                print(f"[--] {r['goal_t']:8.1f}s {r['scorer']:>3} rejected: "
                      f"{r['reject']}")
        rows = plan
        (out / "windows.json").write_text(json.dumps(rows, indent=1) + "\n",
                                          encoding="utf-8")
        print(f"[scout] -> {out / 'windows.json'}")
    else:
        print(sheet(src, a.start, a.end, Path(a.out), n=a.frames, label=a.label))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
