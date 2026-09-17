"""Run a function out of the published page under node, and read what it prints.

Two checks in `tools/audit_site.py` read the **rendered page** rather than the
data behind it, against that file's own rule, and both had to: the accuracy
sentence (`tools/gate_sentence.py`, docs/30 section 2.7) and the tag list
(`tools/tag_list.py`, section 2.8). Both defects were a correct file and a lying
render, and no amount of reading fields can see one.

They share the mechanics and nothing else, so the mechanics live here: find the
function in the page, run it under node against a payload, read the string back.
Neither module re-implements what it is checking in Python - a second copy of the
formatting would only ever agree with itself - and this is the seam that makes
not doing so cheap.
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
    exe = node()
    if exe is None:
        raise NoNode("node is not on PATH")
    src = harness.replace("__FN__", extract(page_html, name))
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        (tmp / "render.js").write_text(src, encoding="utf-8")
        (tmp / "in.json").write_text(json.dumps(payload), encoding="utf-8")
        r = subprocess.run([exe, str(tmp / "render.js"), str(tmp / "in.json")],
                           capture_output=True, text=True, encoding="utf-8")
    if r.returncode:
        raise RuntimeError(f"node could not render `{name}`: "
                           + (r.stderr or "").strip()[-400:])
    return r.stdout
