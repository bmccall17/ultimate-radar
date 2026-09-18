"""Are the published goal lines observed off the grass, or declared from a rulebook?

    python -m tools.field_length            # every cut in work/
    python -m tools.field_length p0003

`docs/08-risks.md` open question 5 asked whether Breese Stevens is a 120 yd
field or the 110 yd venue exception, and read as though every field coordinate
turned on the answer. It does not, and `ur/calibrate/world.py` is why: M1
registers to the **soccer centre circle** (`CENTRE_CIRCLE_R = 10.0066 yd`, a FIFA
dimension) and the halfway line, so the yard comes from the circle and not from
the ultimate field's length. What `length_yd` decides is where the ultimate goal
lines sit inside that frame, because `goal_lines` returns `(20, length - 20)`.

So separations, speeds, spacing and every relative shape are untouched by the
answer. What the answer moves is anything measured against an endzone: deep and
goal-side, the brick, how far a receiver is from scoring, a throw quoted as
ground gained.

## What this module is for

`ur/calibrate/venue.py::decide_field_length` already looks for the goal lines in
each possession's pooled paint map, and every `calibration.json` carries its
verdict. Nothing read those verdicts together, and nothing put the answer on the
page. This does both:

- `evidence(cal)` reduces one calibration to what a reader needs: the verdict,
  the lines of constant x that were actually found, how far each sits from each
  hypothesis, and the sample it all rests on.
- `provenance(cal)` reduces that to the one word the page has to print,
  `observed` or `declared`, which `tools/make_view.py` bakes into `field`.
- the CLI prints the lot across `work/`, which is what turned up the pair of
  recurring peaks written down in `docs/30` section 2.21.

## The caution this exists to honour

#7's own warning: the endzone-framed footage is the footage where the
calibration is weakest, so any measurement here has to report how many frames it
rests on. `decide_field_length` did not record that until 2026-09-18, so a
calibration written before then carries the verdict and not the sample, and this
module says `not recorded` rather than inventing one or quietly leaving it out.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from tools import checks as C
from tools import page_js as PJ

WORK = Path("work")

# The two hypotheses, as distances from the halfway line to a goal line, for a
# field laid centred on the pitch. `world.field_length_from_goal_line` carries
# the same two numbers and the argument for them.
EXPECTED = {"120": 40.0, "110": 35.0}

# How far a peak may sit from a hypothesis and still vote for it. The same 1.0 yd
# `world.field_length_from_goal_line` uses, restated so the report can say what
# the bar was without importing a decision it is only describing.
TOLERANCE_YD = 1.0

# A peak this close to zero is the halfway line, which is what the fit registered
# to and is not a candidate for anything.
HALFWAY_YD = 6.0

# What the page has to print. One word, because a reader deciding whether to
# trust a number about the endzone needs to know which of two things they are
# looking at and nothing else.
OBSERVED, DECLARED = "observed", "declared"


def _field_length(cal: dict) -> dict:
    return cal.get("field_length") or {}


def provenance(cal: dict) -> str:
    """`observed` when this possession's paint settled the goal lines, else
    `declared`. Anything short of a clean verdict is `declared`: a page that
    cannot say which line it saw is a page reading a rulebook."""
    fl = _field_length(cal)
    return OBSERVED if fl.get("field_length_yd") else DECLARED


def peaks(cal: dict) -> list[dict]:
    """Every line of constant x the paint map found, bar the halfway line, with
    its distance from each hypothesis attached.

    `all_x_peaks` is the raw evidence and `candidates` is `decide_field_length`'s
    reading of it. This reports off the raw list on purpose: the rejection rule
    (under 5 % of the halfway line's support) is a judgement about noise, and a
    report that showed only what survived it would hide the thing that turned out
    to matter, which is that the same two rejected peaks recur across eight
    possessions.
    """
    out = []
    raw = _field_length(cal).get("all_x_peaks") or []
    strongest = max((p["count"] for p in raw if abs(p["x_yd"]) < HALFWAY_YD),
                    default=0.0)
    for p in raw:
        if abs(p["x_yd"]) < HALFWAY_YD:
            continue
        d = abs(p["x_yd"])
        row = {"x_yd": p["x_yd"], "count": p["count"],
               "prominence": p["prominence"],
               "share_of_halfway": (p["count"] / strongest) if strongest else None}
        for name, exp in EXPECTED.items():
            row["err_if_" + name + "_yd"] = round(abs(d - exp), 3)
        row["votes"] = next((n for n, e in EXPECTED.items()
                             if abs(d - e) <= TOLERANCE_YD), None)
        out.append(row)
    return sorted(out, key=lambda r: r["x_yd"])


def sample(cal: dict) -> dict:
    """What the verdict rests on, and an honest gap where it does not say.

    Two denominators, because they answer different questions. `frames` and
    `paint_points` are the paint map's own and are what #7 asked for; they are
    absent from every calibration written before 2026-09-18. `calibrated_frames`
    and `confident_frames` come from the calibration itself and are an upper
    bound on the first, since the map takes every second frame above 0.5
    confidence that has paint in it. So they are labelled as a bound and never
    as the number.
    """
    fl = _field_length(cal)
    got = fl.get("sample") or {}
    frames = cal.get("frames") or []
    conf = sum(1 for f in frames if (f.get("confidence") or 0.0) >= 0.5)
    return {
        "frames": got.get("frames"),
        "paint_points": got.get("paint_points"),
        "recorded": bool(got),
        "calibrated_frames": len(frames),
        "confident_frames": conf,
        "upper_bound_frames": (conf + 1) // 2,
    }


def evidence(cal: dict) -> dict:
    """One possession's whole answer, small enough to bake into a page."""
    fl = _field_length(cal)
    return {
        "source": provenance(cal),
        "verdict": fl.get("verdict"),
        "field_length_yd": fl.get("field_length_yd"),
        "why": fl.get("why"),
        "tolerance_yd": TOLERANCE_YD,
        "expected_yd": EXPECTED,
        "peaks": peaks(cal),
        "sample": sample(cal),
    }


def read(work: Path) -> dict | None:
    p = work / "calibration.json"
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# the rows
# --------------------------------------------------------------------------- #

FUNC = "fieldSentence"

# `D` is the name the sentence closes over in the page; here it carries only the
# field block, which is all `fieldSentence` reads.
_HARNESS = """globalThis.window = globalThis;
const D = { field: require(process.argv[2]) };
__FN__
process.stdout.write(fieldSentence(D.field));
"""


def render(page_html: str, field: dict) -> str:
    """Run the page's own sentence about its goal lines, return its HTML.

    Lifted and executed rather than restated in Python, for the reason
    `tools/gate_sentence.py` gives at length: a Python copy of the wording would
    agree with itself forever while the page quietly said something else.
    """
    return PJ.run(page_html, FUNC, _HARNESS, field)


def rows(pid: str, field: dict | None, page_html: str | None = None) -> list[dict]:
    """The site's rows about the goal lines, off a published `field` block.

    `field` is what the page carries, not what `work/` holds, because the page is
    the deliverable (AGENTS rule 7) and a reader can only be misled by what is in
    front of them.
    """
    out: list[dict] = []
    f = field or {}
    src = f.get("length_source")
    ev = f.get("length_evidence") or {}

    # The gate. It does not ask for the answer, because nobody has it. It asks
    # the page to say which of the two kinds of statement its goal lines are,
    # and it refuses `observed` from a page carrying no measurement - otherwise
    # the label is a word somebody typed. A page that draws a goal line and says
    # nothing is asserting an observation it never made, which is AGENTS rule 3
    # applied to a line instead of to a position.
    named = src in (OBSERVED, DECLARED)
    backed = src != OBSERVED or bool(ev.get("field_length_yd"))
    out.append(C.gate(
        "goal lines say which they are",
        named and backed,
        f"{src!r}, {f.get('length_yd')} yd, verdict {ev.get('verdict')!r}"
        + (f", {len(ev.get('peaks') or [])} x peak(s)" if ev else ""),
        f"{OBSERVED!r} or {DECLARED!r}, and {OBSERVED!r} only with the line it saw",
        "tools.make_view bakes it from calibration.json - rebuild the site"))

    # ...and the one that asks whether a reader is told. The field can be right
    # and the page silent, which is docs/30 section 2.7 in its other direction,
    # so this runs the page's own sentence. The ablation is what makes it a test
    # rather than a string match: take `length_source` away and the sentence has
    # to go with it, or it is prose somebody typed that happens to be true.
    if page_html is not None:
        try:
            said = PJ.strip_markup(render(page_html, f))
            gone = PJ.strip_markup(render(page_html, {k: v for k, v in f.items()
                                                      if k != "length_source"}))
        except PJ.NoNode:
            out.append(C.gate("the page says which they are", False,
                              "node is not on PATH", "the sentence renders",
                              "install node - docs/07 carries the row"))
        except (RuntimeError, ValueError) as e:
            out.append(C.gate("the page says which they are", False, str(e)[:120],
                              "the sentence renders", "the page has changed shape"))
        else:
            ok = bool(src) and src in said.lower() and not gone.strip()
            out.append(C.gate(
                "the page says which they are",
                ok,
                (f"says {src!r}" if src and src in said.lower()
                 else f"the word {src!r} is not in what the page prints")
                + ("; survives the field being removed" if gone.strip()
                   else "; and says nothing without it"),
                "the reader is told, and only because the data says so",
                "fieldSentence must print length_source and nothing when it is absent"))

    # A measurement. There is no threshold: no possession has ever resolved it,
    # and a gate demanding one would be demanding footage that does not exist.
    s = ev.get("sample") or {}
    near = [p for p in (ev.get("peaks") or []) if p.get("votes")]
    out.append(C.measurement(
        "...goal lines found in the paint",
        f"{len(near)} of {len(ev.get('peaks') or [])} x peak(s) within "
        f"{TOLERANCE_YD} yd of a goal line; paint map "
        + (f"{s.get('frames')} frame(s), {s.get('paint_points')} point(s)"
           if s.get("recorded")
           else f"sample not recorded, at most {s.get('upper_bound_frames')} frames"),
        "no threshold: the camera never frames an endzone and the halfway line "
        "together, so demanding a goal line demands footage that does not exist "
        "(docs/30 section 2.21)"))
    return out


# --------------------------------------------------------------------------- #
# the report
# --------------------------------------------------------------------------- #

def _report(pid: str, cal: dict) -> None:
    ev = evidence(cal)
    s = ev["sample"]
    print(f"\n=== {pid}: {ev['source']} ({ev['verdict']})")
    print(f"  calibrated {s['calibrated_frames']} frames, "
          f"{s['confident_frames']} at confidence >= 0.5; paint map "
          + (f"{s['frames']} frames, {s['paint_points']} points"
             if s["recorded"] else
             f"sample NOT RECORDED (at most {s['upper_bound_frames']} frames)"))
    if not ev["peaks"]:
        print("  no line of constant x outside the halfway line")
        return
    for p in ev["peaks"]:
        share = p["share_of_halfway"]
        pct = f"{share * 100:.2f}% of halfway" if share else ""
        print(f"  x = {p['x_yd']:+8.2f} yd  count {p['count']:9.1f}  {pct:>18s}"
              f"  err120 {p['err_if_120_yd']:5.2f}  err110 {p['err_if_110_yd']:5.2f}"
              + ("  VOTES " + p["votes"] if p["votes"] else ""))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="tools.field_length")
    ap.add_argument("possession", nargs="*",
                    help="ids to report; default every cut in work/")
    a = ap.parse_args(argv)
    ids = a.possession or sorted(d.name for d in WORK.glob("p0*") if d.is_dir())
    seen = resolved = 0
    for pid in ids:
        cal = read(WORK / pid)
        if cal is None:
            print(f"\n=== {pid}: no calibration.json")
            continue
        seen += 1
        resolved += provenance(cal) == OBSERVED
        _report(pid, cal)
    print(f"\n{resolved} of {seen} cut(s) observe a goal line."
          + (" The published goal lines are declared from the UFA rulebook."
             if resolved == 0 else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
