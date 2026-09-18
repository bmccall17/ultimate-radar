"""Run a function out of the published page under node, and read what it prints.

Four modules behind `tools/audit_site.py` read the **rendered page** rather than
the data behind it, against that file's own rule, and each had to: the accuracy
sentence (`tools/gate_sentence.py`, docs/30 section 2.7), the tag list
(`tools/tag_list.py`, section 2.8), the self-pass guard (`tools/tag_guard.py`,
section 2.9) and the openness claim (`tools/openness.py`, section 2.19). Every
one was a correct file and a page saying something the file does not support -
three of them printing a claim, one failing to print a refusal - and no amount of
reading fields can see any of them.

They share the mechanics and nothing else, so the mechanics live here: find the
function in the page, run it under node against a payload, read the string back.
None of the four re-implements what it is checking in Python - a second copy of
the formatting would only ever agree with itself - and this is the seam that
makes not doing so cheap.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

_TAG = re.compile(r"<[^>]*>")


class NoNode(RuntimeError):
    """No JS engine, so nothing can be rendered and nothing is proven."""


# How long one render may take. The slowest of the four is `openness`, which
# sweeps every frame against every attacker - 2771 claims on p0003 - and that
# runs in well under a second. 60 s is not a performance budget, it is the line
# past which the process has hung rather than gone slowly.
TIMEOUT_S = 60


def node() -> str | None:
    """The node executable, or None. Callers decide what an absence means."""
    return shutil.which("node")


def strip_markup(html: str) -> str:
    """What a reader reads, with the tags taken out.

    A tag becomes a space, not nothing. Two adjacent blocks are two things on
    the page and joining them makes a word that is on neither: `8.47s</div>` and
    `<div>From` glued into `8.47sFrom`, which cost `tag_list` a row it had
    rendered correctly and printed right there on the screen.
    """
    return _TAG.sub(" ", html)


def extract(html: str, name: str) -> str:
    """The source of `function <name>(...)`, brace-matched out of the page.

    Brace counting is naive: a `{` or `}` inside a string literal in the body
    would throw it off. Neither function has one, and the template literals they
    do have are balanced. If that ever stops being true the extraction fails
    loudly here rather than rendering something half-correct - and `audit_site`
    turns the failure into one red row rather than a traceback.
    """
    i = html.find(f"function {name}")
    if i < 0:
        # Named rather than described, because two callers depend on this and a
        # message that says "accuracy sentence" for either is a red row pointing
        # at the wrong code.
        raise ValueError(f"no `function {name}` in the page - it has been "
                         "renamed or removed")
    j = html.find("{", i)
    if j < 0:
        raise ValueError(f"`function {name}` has no body")
    depth = 0
    for k in range(j, len(html)):
        if html[k] == "{":
            depth += 1
        elif html[k] == "}":
            depth -= 1
            if depth == 0:
                return html[i:k + 1]
    raise ValueError(f"`function {name}` is never closed")


def run(page_html: str, name: str, harness: str, payload) -> str:
    """Run `function <name>` from the page against `payload`, return its output.

    `harness` is JS with `__FN__` where the function goes; it reads the payload
    from `require(process.argv[2])` and writes the result to stdout.
    """
    return run_source(harness.replace("__FN__", extract(page_html, name)),
                      payload, name)


def run_source(src: str, payload, label: str) -> str:
    """Run already-composed JS against `payload`, return what it writes.

    `run` lifts one function and is the whole of what the first two callers
    needed. A claim built out of several of the page's functions and its state
    constants has to compose its own source - `tools/openness.py` lifts six
    things - and this is where that lands so the node plumbing stays in one
    place. `label` only names the thing in the error.
    """
    exe = node()
    if exe is None:
        raise NoNode("node is not on PATH")
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        (tmp / "render.js").write_text(src, encoding="utf-8")
        (tmp / "in.json").write_text(json.dumps(payload), encoding="utf-8")
        try:
            r = subprocess.run([exe, str(tmp / "render.js"), str(tmp / "in.json")],
                               capture_output=True, text=True, encoding="utf-8",
                               timeout=TIMEOUT_S)
        except subprocess.TimeoutExpired:
            # AGENTS rule 6: same input, same output. A render that hangs makes
            # the suite's answer depend on the machine's mood, and a gate left
            # waiting has not passed (AD-11) - so a hang is a red row with a
            # reason on it, which is what every other failure here already is.
            raise RuntimeError(
                f"node did not finish rendering `{label}` within {TIMEOUT_S}s")
    if r.returncode:
        raise RuntimeError(f"node could not render `{label}`: "
                           + (r.stderr or "").strip()[-400:])
    return r.stdout


# Built by concatenation rather than `.format`, because the day this pattern
# grows a `{n,m}` quantifier a format call turns it into a KeyError.
def _const_re(name: str) -> str:
    return r"^const " + re.escape(name) + r" = (.*);[ \t]*$"


def extract_const(html: str, name: str) -> str:
    """The source of a one-line `const <name> = ...;` declaration in the page.

    `extract` lifts a function; a function that reads a module-level `const`
    needs that too, or the harness has to declare its own copy - and a copy of
    `MEASURABLE` written in the test would agree with the test forever while the
    page quietly changed which states count as seen.

    One line only, and it raises on anything else. Every constant a check has
    wanted so far is a `new Set([...])` on one line, and a multi-line matcher
    would have to know where the declaration ends, which is the brace counting
    `extract` already warns is naive. A `const` that grows a second line fails
    here, loudly, rather than being lifted half-way.
    """
    m = re.search(_const_re(name), html, re.MULTILINE)
    if not m:
        raise ValueError(f"no one-line `const {name} = ...;` in the page - it "
                         "has been renamed, removed, or wrapped onto a second line")
    return m.group(0)
