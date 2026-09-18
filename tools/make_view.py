"""Write viewer/live-data.js from a possession working directory.

    python -m tools.make_view work/p0001

The viewer opens from `file://` with no server, and a page loaded that way cannot
`fetch` a sibling JSON file — so the possession is handed over as a script that
assigns `window.POSSESSION`, the same arrangement `viewer/data.js` uses for the
fixture. The video is referenced by relative path rather than copied: it is a
30 MB clip of somebody else's broadcast, `docs/10-getting-the-footage.md` says not
to redistribute it, and `work/` is gitignored for that reason.

Four files go across, because the viewer's four panes need them and a second
request is not available from `file://`:

- `possession.json` — the positions, as `window.POSSESSION`;
- `issues.json` — the "needs a human" queue, as `window.ISSUES`;
- `identities.json` — voted jersey numbers, as `window.IDENTITIES`, and merged
  onto each slot so the overlay can label it;
- `events.json` — hand-tagged and suggested events, onto `POSSESSION.events`,
  and its `observed` block, which carries a confirmed attacking direction.

The attacking direction is also *resolved* here rather than copied, onto
`POSSESSION.possession.attacking_direction_resolved`: it is a property of a
`(quarter, team)` (AD-10), so answering it needs every possession at once and the
page has only itself.

Only the first is required. A working directory that has not reached M5 still
renders; the panes that have nothing say so.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from ur import grading as GV

# Composing a page prints a running commentary, which is the right behaviour for
# a build and the wrong one for `site is current`: that check composes every
# published possession a second time purely to hash it, and six copies of the
# build log in the middle of a gate run reads as though the site were being
# rebuilt. The flag is module-level rather than threaded through six signatures
# because nothing here is concurrent.
_QUIET = False


def _say(msg: str) -> None:
    if not _QUIET:
        print(msg)


def _maybe(work: Path, name: str) -> dict | None:
    p = work / name
    if not p.exists():
        _say(f"[make_view] - {name} not present; that pane will say so")
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def _attacking_direction(work: Path, doc: dict) -> None:
    """Resolve `(quarter, team) -> direction` and bake the answer into the page.

    Resolution is a cross-possession question and the viewer is a single-file
    page with no siblings to read (AD-9), so it is answered here, at build time,
    over every possession beside this one. That is what lets one confirmation in
    p0009 light up the rest of Q1: the page carries the resolved fact and says
    where it came from, rather than carrying a claim of its own.

    Nothing is written back to `work/` - the observations stay the only stored
    thing (AD-10). A quarter nobody has confirmed, or one two people contradict
    each other about, resolves to None, and the viewer says `unverified`.
    """
    from ur import direction as DIR

    q = doc["possession"].get("quarter")
    # Looked up for the team ON OFFENCE, which is the only team this possession
    # names. `offense` is one value for the whole possession and CONTEXT.md says
    # it is wrong after a turnover - but the stored fact is keyed by team and is
    # not, so when the possession model grows a turnover this lookup changes and
    # nothing in `work/` does. That is what AD-10 bought by moving the fact off
    # the possession, and it is bought here whether or not it is spent yet.
    team = doc["possession"]["offense"]
    try:
        table, conflicts = DIR.resolve_work(work.parent)
    except (ValueError, KeyError) as e:
        _say(f"[make_view] ! attacking direction not resolved: {e}")
        doc["possession"]["attacking_direction_resolved"] = None
        return
    got = DIR.for_possession(table, q, team)
    doc["possession"]["attacking_direction_resolved"] = got
    if got:
        _say(f"[make_view] + attacking direction, Q{q}: {DIR.describe(got)}")
    else:
        _say(f"[make_view] - attacking direction: nothing confirmed for Q{q} "
              f"{team}; the page will say unverified")
    for c in conflicts:
        _say(f"[make_view] ! {c['detail']}")


def _bounded(work: Path, doc: dict) -> None:
    """Say whether the accuracy numbers on this page are an upper bound. AD-13.

    A hand-placed position is excluded from every grading sample, and the frames
    a person repairs are the ones the tracker got **wrong** - so what survives
    blinding is the easier part of the possession and the number computed over it
    rises honestly while meaning less. AD-13 calls that a **bounded** number and
    requires the page to say so.

    It is a fact about the possession named in `measured_on`, not about this one.
    Five of the six published pages quote `p0001`, so a repair pass on p0001
    makes p0003's printed figure a ceiling while nothing in p0003 changes at all.
    That is the same shape as the attacking direction above and is answered the
    same way: at build time, across `work/`, baked into the page (AD-9).

    A `measured_on` naming a possession that is not cut leaves the flag null, and
    the viewer treats null as "nobody has looked" rather than as "no".
    """
    from ur import human as HU

    g = doc.get("gates") or {}
    on = g.get("measured_on")
    if not on:
        return
    src = work.parent / on
    if not GV.has(src):
        _say(f"[make_view] - gates were measured on {on}, which is not in "
              "work/; the page cannot say whether they are bounded")
        return
    n = HU.count(GV.read_for_publishing(src))
    g["bounded"], g["bounded_frames"] = n > 0, n
    doc["gates"] = g
    if n:
        _say(f"[make_view] + gates are BOUNDED: {n} hand-placed frame(s) on "
              f"{on} are outside the grading sample")
    else:
        _say(f"[make_view] + gates are not bounded: {on} is 0.0% hand-placed")


def _field_provenance(work: Path, doc: dict) -> None:
    """Say whether this page's goal lines were observed or declared. #7.

    `ur/calibrate/world.py` registers to the soccer centre circle and the
    halfway line, so the yard does not come from the ultimate field's length.
    What `length_yd` decides is where the goal lines sit inside that frame, and
    every `calibration.json` already carries a verdict on it that nothing ever
    read. The page draws those lines, so the page has to say which of two things
    they are.

    Baked in here for the same reason the attacking direction and the bounded
    flag are: it is a fact about the calibration rather than about the possession
    document, and the viewer is a single page with no siblings to read (AD-9).

    A working directory with no calibration leaves the field alone rather than
    asserting `declared`, because "nobody has looked" and "somebody looked and
    found nothing" are different statements and this is the first one.
    """
    from tools import field_length as FLEN

    cal = FLEN.read(work)
    if cal is None:
        _say("[make_view] - no calibration.json; the page cannot say whether its "
             "goal lines were observed")
        return
    fld = doc.get("field") or {}
    fld["length_source"] = FLEN.provenance(cal)
    fld["length_evidence"] = FLEN.evidence(cal)
    doc["field"] = fld
    n = len(fld["length_evidence"]["peaks"])
    _say(f"[make_view] + goal lines are {fld['length_source'].upper()}: "
         f"{fld['length_evidence']['verdict']}, {n} x peak(s) in the paint")


def compose(work: Path, *, quiet: bool = False) -> tuple[dict, dict | None, dict | None]:
    """Build the page document from `work/`, without deciding where it goes.

    Everything `build` does except the video path and the write, which is the
    whole of the difference between "what would this page say" and "put it on
    disk". `tools/site_digest.py` needs the first half on its own: `site is
    current` has to compare the published values against what a rebuild would
    emit *now*, and it cannot do that by writing a second copy of the site
    somewhere and diffing files.

    Returns the document and the two sidecars the site writes beside it
    (`issues.json`, `identities.json`), so `build` can write all three.
    """
    global _QUIET
    was, _QUIET = _QUIET, quiet
    try:
        return _compose(work)
    finally:
        _QUIET = was


def _compose(work: Path) -> tuple[dict, dict | None, dict | None]:
    doc = GV.read_for_publishing(work)

    ident = _maybe(work, "identities.json")
    if ident:
        # A jersey the vote declined to call stays None. docs/04 M5: a wrong
        # number is worse than no number, and the viewer must not paper over it.
        #
        # The number alone is not enough, because the two files this reads are
        # not the same kind of statement. `identities@2` is what a person read
        # off a shirt, against the frame they read it on; `identities@1` is an
        # OCR vote over a tracklet. `ur/provenance.py::derive` will grade a tag
        # against the first and not the second, so a page that renders them
        # identically tells a tagger that truth exists where it does not. The
        # provenance travels with the number.
        by = {s["slot"]: s for s in ident["slots"]}
        named = read = 0
        for p in doc["players"]:
            s = by.get(p["slot"])
            if not s or s.get("jersey") is None:
                continue
            p["jersey"] = s["jersey"]
            # @2 says `source`; @1 says `method` ("ocr_vote"). Anything that is
            # not a human reading is "voted" - the page only has to tell those
            # two apart, and collapsing the rest avoids inventing a vocabulary
            # neither file uses.
            p["jersey_source"] = "read" if s.get("source") == "read" else "voted"
            # `confidence` was read here and it is an @1 field. Every page built
            # from a human's readings carried `jersey_confidence: None`, which
            # nothing could use and nothing did. How many times somebody looked,
            # and whether the looks disagreed, are things a reader can weigh.
            p["jersey_readings"] = s.get("readings")
            p["jersey_conflict"] = s.get("conflict")
            named += 1
            if p["jersey_source"] == "read":
                read += 1
        # The append-only record travels too. The viewer restores it on load -
        # without it every reload claims nobody has read a shirt - and it is
        # what `derive` needs: a reading settles the tag whose span it falls
        # INSIDE, so the frame it was read on is the whole of its value.
        rs = ident.get("readings") or []
        if rs:
            doc["identity_readings"] = rs
        _say(f"[make_view] + identities.json: {named} of {len(doc['players'])} "
              f"slots carry a jersey, {read} read off a shirt, "
              f"{len(rs)} reading(s) carried through")

    ev = _maybe(work, "events.json")
    if ev:
        doc["events"] = ev.get("events", [])
        _say(f"[make_view] + events.json: {len(doc['events'])} event(s)")
        if ev.get("observed"):
            doc["observed"] = ev["observed"]
        # The file's own note travels so the viewer's download can put it back.
        # p0003's is three hundred words on how its identities were arrived at,
        # and a download that dropped it would quietly destroy the only record.
        if ev.get("note"):
            doc["events_note"] = ev["note"]

    _attacking_direction(work, doc)
    _field_provenance(work, doc)
    _bounded(work, doc)

    issues = _maybe(work, "issues.json")
    if issues:
        _say(f"[make_view] + issues.json: {len(issues.get('issues', []))} open")

    return doc, issues, ident


def build(work: Path, out: Path, video: str | None = None) -> Path:
    doc, issues, ident = compose(work)

    clip = work / "clip.mp4"
    if video is None:
        video = os.path.relpath(clip, out.parent).replace("\\", "/")
    # Deliberately set after `compose` and never inside it: where the clip sits
    # relative to the page is a fact about this build's output directory, not
    # about the possession, and `viewer/` and `docs/p0003/` disagree about it
    # while publishing the same page. `tools/site_digest.py` excludes it for that
    # reason, and the cleanest way to keep that true is for `compose` never to
    # have known it.
    doc["video_src"] = video
    if not clip.exists():
        _say(f"[make_view] ! {clip} is missing; the page will show no video")

    out.parent.mkdir(parents=True, exist_ok=True)
    lines = ["// Generated by tools/make_view.py. Do not edit.",
             "// Real measured output. Read the provenance banner in the viewer "
             "before quoting any number.",
             f"window.POSSESSION = {json.dumps(doc, separators=(',', ':'))};"]
    if issues:
        lines.append(f"window.ISSUES = {json.dumps(issues, separators=(',', ':'))};")
    if ident:
        lines.append(f"window.IDENTITIES = {json.dumps(ident, separators=(',', ':'))};")
    out.write_text(chr(10).join(lines) + chr(10), encoding="utf-8")
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="tools.make_view")
    p.add_argument("work")
    p.add_argument("--out", default="viewer/live-data.js")
    p.add_argument("--video", default=None,
                   help="override the relative path to the clip")
    a = p.parse_args(argv)
    out = build(Path(a.work), Path(a.out), a.video)
    _say(f"[make_view] wrote {out} ({out.stat().st_size / 1e6:.2f} MB)")
    print("[make_view] open viewer/index.html directly in a browser")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
