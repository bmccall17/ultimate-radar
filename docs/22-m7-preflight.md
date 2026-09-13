# 22 — M7 pre-flight: p0003 is not a possession, and the cut detector's threshold is too high

Checked before spending a GPU run on it. Two findings, one of which outlives this clip.

---

## p0003 as cut spans a goal and two camera cuts

`work/p0003/clip.json` covers 1598.0–1624.0 s. Frames at t = 0, 8.7, 17.3 and 25.3 s show:

| t | What is on screen |
|---|---|
| 0.0 s | live play, ATX 3 – MIN 5, clock 1st 4:09 |
| 8.7 s | live play, camera panned right, disc in flight |
| 17.3 s | live play near the endzone, few players in shot |
| **25.3 s** | **a tight celebration close-up. No field. Score now ATX 4 – MIN 5.** |

The possession ends in a Sol goal and the broadcast cuts to a reaction shot. The last several
seconds contain no field, no calibratable geometry and no trackable 7 v 7.

Its own note says it was cut to settle the 120-vs-110 yard question and "doubles as the second
possession M7 asks for". It does the first job. It does not do the second.

## The cut detector already knew, and M1's threshold would have missed it

`eval/m0/cuts_full/events.json` has scene-change candidates inside the clip window:

```
  1617.60 s   score=0.2347     rel t = +19.6 s   <- the goal / cut to celebration
  1622.64 s   score=0.2525     rel t = +24.6 s
  1622.65 s   score=0.1458     rel t = +24.7 s
```

**Both real cuts score 0.23–0.25, against M1's threshold of 0.35.** That threshold was
validated against four hand-checked cuts in M0 and is too high for cuts of this kind — a pan
into a same-brightness close-up moves fewer pixels than a cut between two wide field shots.

Run p0003 as it stands and the pipeline treats 26 s spanning three shots as one: one camera
solve fitted across a cut, tracks continued into a close-up, and six seconds of confident
output describing a celebration as a defensive set. Nothing would error.

**This is the seventh instance of the shape in HANDOFF § 8** — something reports success while
being wrong — and the only reason it was caught is that a human looked at four frames.

### What to do about the threshold

Not simply lower it: the same file shows dozens of candidates at 0.08–0.15 during ordinary
panning, so 0.35 was protecting against a flood of false positives. Better options:

1. **Gate on field visibility rather than pixel change.** A cut that matters is one after which
   the calibration cannot solve. M1 already computes a per-frame confidence — a sustained
   collapse in it *is* a shot boundary, measured on the thing we actually care about, and it
   costs nothing new to compute.
2. Cross-check candidates between 0.15 and 0.35 against that confidence before accepting or
   rejecting them.
3. Keep 0.35 as the standalone threshold and record that it is tuned for wide-to-wide cuts.

Whatever is chosen, `docs/12-m1-calibration.md` should carry the two counter-examples above, so
the next person sees that the threshold has known misses.

---

## The clip to run instead

The shot containing 1598 s runs **1560.54 → 1617.60 s**, 57.1 s of unbroken single-shot
footage. p0003 straddles its end by 6.4 s.

Re-cut to stop before the cut:

```powershell
.\.venv\Scripts\python.exe -m ur.ingest --source raw\sol-vs-windchill-2026-semi.mp4 `
    --id p0003 --start 1598.0 --duration 19.4 --offense sol --defense chill
```

19.4 s of live play inside one shot, ending on a Sol goal — a complete possession, and a
genuinely different one from p0001: first quarter rather than fourth, endzone-framed rather
than midfield, and a scoring possession rather than an open one.

If a longer possession is wanted, the shot has 37 s of headroom before 1598. Sample a frame at
1565 and 1580 and check whether the score and game clock say it is the same possession before
extending — a turnover inside the window would make it two.

Then the rest of M7 as planned:

```powershell
.\.venv\Scripts\python.exe -m ur.calibrate.run work\p0003   # the existing calib is pre-M3 and stale
.\.venv\Scripts\python.exe -m ur.detect.run    work\p0003
.\.venv\Scripts\python.exe -m ur.track.run     work\p0003
.\.venv\Scripts\python.exe -m tools.make_view  work\p0003
```

**What M7 is actually asking.** Not "does it produce output" — it will. The question is whether
those four commands run without hand-holding on footage the code has never seen. Every
per-possession constant is now suspect: the kit fit, `BREESE_STEVENS_NEAR_SIDELINE_Y`, the
calibration seed, the team-separation floor. Record which ones needed touching. That list is
the answer to whether this is a pipeline or a one-off.
