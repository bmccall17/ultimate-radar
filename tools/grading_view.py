"""The check that nobody reads a possession around the grading view.

    python -m tools.grading_view

AD-13's probe (`tools/human_positions.py`) runs each grader and requires a
person's hand not to move the number. It is the right check and it has a hole one
level up: it can only run the graders its `graders()` registry names, and that
registry is a hand-written list of three. `tools/disc_score.py` reads
`possession.json` and `events.json` raw, applies neither exclusion, and is in no
registry. The probe reports `1 of 1 grader run(s)` and passes, which is true and
says nothing about the scorer it never saw.

An `unreachable` row at least admits the probe could not get there. An absence
prints nothing.

## How this closes it without a second list to maintain

`ur/grading.py` is the only supported way to get a possession, and
`read_for_publishing` is the confession a renderer makes. So the rule needs no
allowlist at all:

> **Only `ur/grading.py` may build a path to `possession.json`.**

Nothing to register, nothing to remember, and adding a grader cannot quietly
opt out of the exclusions - the only way to get the document is a call that
already applied them, or a call named to be uncomfortable in review.

## Why reading source is defensible here, given AD-13

AD-13 says plainly that "a check that read the source for the word would pass on
a call that had been commented out", and builds a behavioural probe instead. That
reasoning is about whether an exclusion **ran**, and the probe still answers it.

This asks a different question: does a bypass **exist**. Source is the only place
that can be answered, because a module nobody calls in a gate run is exactly the
one the probe cannot reach. The two checks are complements, not substitutes:
delete the exclusion from the view and the probe goes red; add a grader that
never asks the view and this goes red.

## Fail open

A file that will not parse, or a path that cannot be read, is a **finding**, not
a skip. A scanner that silently drops what it cannot read reproduces the silence
it exists to end, and `docs/30` § 2.6 is the standing lesson that a tool
reporting success while the defect stands is worse than one that says nothing.
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

from tools import checks as C
from ur import grading as GV

# Where the only legitimate read lives. A path, not a module name, because the
# point is that there is exactly one file and it is this one.
VIEW = Path("ur") / "grading.py"

# Directories that hold code which could grade. Tests are excluded: they build
# invented documents and never read work/, and a fixture writing a possession to
# a temp dir is not a bypass.
SCANNED = ("ur", "tools")

# **The path, not the read, and not the mention.** Two earlier versions of this
# were wrong in opposite directions and both are worth keeping written down.
#
# Looking for the read - `(work / "possession.json").read_text(...)` - had exactly
# the hole it exists to close. `tools/audit_site.py` and `tools/make_view.py`
# assign the path to a variable and read it three lines later, and both walked
# straight past. A check that has to recognise *how* somebody reached the file
# will always be one spelling behind.
#
# Looking for the name anywhere was then too wide. A gate is *called* `every
# active correction is replayed into possession.json`, `ur/issues.py` says it in
# `--help`, and `tools/pipeline.py` lists it as a stage's output. Making those
# illegal asks prose to route around a check, which is how a check gets disabled.
#
# What is left is the middle: a literal used to **build a path**. Matched on the
# syntax tree, so a comment (absent from an AST entirely) and a docstring are free
# to say it, and `GV.POSSESSION` everywhere else means the name itself lives once.
NAME = GV.POSSESSION


def _is_name(node) -> bool:
    """The filename, however it is spelled.

    **Both spellings, and the second one is the lesson.** The first version of
    this matched only the string literal. The same change that introduced it
    also replaced every literal in the repo with `GV.POSSESSION` — so within one
    commit the check matched nothing anywhere, passed `no bypass`, and sat green
    over three live bypasses in `tools/audit_site.py`, `tools/m4_label.py` and
    `ur/issues.py`. A check whose author has just taught everybody the one
    spelling it cannot see is AD-11's row that cannot fail, written by the ticket
    against it.

    So a constant holding the name and an attribute called `POSSESSION` both
    count. The constant lives once, in the view, so any `X.POSSESSION` is that
    constant.
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return NAME in node.value
    return isinstance(node, ast.Attribute) and node.attr == "POSSESSION"


def opens_the_file(src: str) -> bool:
    """Does this source build a **path** to the possession file?

    Not "does it mention the name". A gate is called `every active correction is
    replayed into possession.json`, `ur/issues.py` says so in its `--help`, and
    `tools/pipeline.py` lists it as a stage's output. All three are somebody
    writing about the file, and a check that made them illegal would be asking
    prose to route around it.

    What is a bypass is reaching the file: the literal on either side of a `/`,
    or handed to `Path(...)` or `open(...)`. Those are the three ways anybody in
    this repo has ever opened it, and `tools/audit_site.py`'s
    `WORK / pid / GV.POSSESSION` is the shape that walked past the first version.

    It will not stop somebody splitting the string in half to evade it. Nothing
    short of a sandbox would, and that is not the failure this guards: the
    failure is a new grader whose author never thought about AD-13 at all.
    """
    tree = ast.parse(src)
    for n in ast.walk(tree):
        if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Div):
            if _is_name(n.left) or _is_name(n.right):
                return True
        if isinstance(n, ast.Call):
            f = n.func
            who = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")
            if who in ("Path", "open") and any(_is_name(a) for a in n.args):
                return True
    return False


def bypasses(root: Path, allow: Path = VIEW) -> list[Path]:
    """Every file under `root` naming the possession file outside the view.

    Sorted, so the row reads the same on every run: AGENTS rule 6 says a number
    that moves between runs is not a measurement, and neither is a list.
    """
    root = Path(root)
    out: list[Path] = []
    for p in sorted(root.rglob("*.py")):
        rel = p.relative_to(root)
        if "__pycache__" in rel.parts:
            continue
        if root.name == allow.parent.name and rel.as_posix() == allow.name:
            continue                    # the view itself, the one place it lives
        try:
            if opens_the_file(p.read_text(encoding="utf-8")):
                out.append(p)
        except (OSError, UnicodeDecodeError, SyntaxError):
            out.append(p)          # fail open: unreadable is a finding
    return out


def check(root: Path | None = None) -> dict:
    """One gate: every possession read goes through the view."""
    root = Path(root or ".")
    found: list[Path] = []
    for d in SCANNED:
        if (root / d).is_dir():
            found += bypasses(root / d)
        else:
            found.append(root / d)   # fail open: a missing tree is a finding
    names = sorted(str(Path(d) / p.relative_to(root / d))
                   if (root / d) in p.parents else str(p)
                   for d in SCANNED for p in found if str(p).startswith(str(root / d)))
    return {"possession": "grading view", "checks": [C.gate(
        "every possession read goes through the view",
        not found,
        "no bypass" if not found else f"{len(found)}: {', '.join(names)}",
        f"only {VIEW.as_posix()} may build a path to {GV.POSSESSION}",
        "take the document from ur.grading.load, or say read_for_publishing "
        "and mean it; for the filename alone, GV.POSSESSION")]}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("root", nargs="?", default=".", type=Path)
    a = ap.parse_args(argv)
    r = check(a.root)
    for row in r["checks"]:
        print(C.render(row))
    return 0 if all(c["pass"] for c in r["checks"]) else 1


if __name__ == "__main__":
    sys.exit(main())
