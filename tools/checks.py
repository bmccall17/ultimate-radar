"""Two kinds of row, and only one of them can fail.

`python -m tools.gates` prints one line per thing this project knows how to
check. Twenty-four of them were built with an unconditional pass: the fraction of
frames an M1 mean was measured on, the drift of the offence, how many quarters
have a confirmed direction, the longest stretch a reader sees no disc. Each was
written `add(name, True, ...)` with `want="reported, not gated"`, and each then
printed `[PASS]` and was counted into the total at the end.

That total is what a reader trusts, and it was inflated by rows that could not
have done anything else. Worse, `docs/31` says an issue closes when a named check
flips to PASS - so a row that can never flip is a measurement wearing a gate's
clothes, and a ticket pointed at one would have a definition of done it could
never fail to meet.

So:

- a **gate** carries a verdict. `pass` is a real bool, it can be `False`, it
  counts in the failable total, and it moves the exit code.
- a **measurement** carries a number and the reason there is no threshold for it.
  It has **no `pass` key at all** - not `False`, absent - so any code that totals
  `c["pass"]` raises rather than silently counting it. It never moves the exit
  code, and it prints without PASS or FAIL beside it.

`docs/30` § 3 records every measurement and why it cannot be made failable today.
When one of them acquires a defensible threshold it becomes a `gate()` call, the
failable total goes up by one, and that is the whole change.
"""

from __future__ import annotations

from typing import Any, Iterable, NamedTuple

# Wide enough for the longest marker, so the name column lines up whichever kind
# of row it is. A reader scanning for a verdict looks for a bracket; a
# measurement has none.
_MARK_W = 10
_NAME_W = 34
_GOT_W = 52


def gate(name: str, ok: Any, got: Any, want: Any, note: str = "") -> dict:
    """A row that can fail. `ok` is coerced, because numpy gives back np.bool_."""
    return {"name": name, "pass": bool(ok), "got": got, "want": want,
            "note": note}


def measurement(name: str, got: Any, why: str) -> dict:
    """A row that reports a number and claims nothing about it.

    `why` says what stops this being a gate - the missing threshold, the
    measurement it still needs, the queue it counts. It is required: docs/30 has
    to carry that reason for every one of these, and a measurement that will not
    name it is a gate somebody could not be bothered to write.

    There is no `note`, which a gate has for what to do about a failure. A row
    that cannot fail has nothing to tell anybody to do, and `why` is where its
    one sentence goes.
    """
    if not why:
        raise ValueError(f"measurement {name!r} must say why it cannot be gated")
    return {"name": name, "got": got, "why": why}


def _kind(c: dict) -> str:
    if "pass" in c:
        return "gate"
    if "why" in c:
        return "measurement"
    raise ValueError(
        f"row {c.get('name', c)!r} is neither a gate nor a measurement - build it "
        "with tools.checks.gate() or tools.checks.measurement()")


def is_gate(c: dict) -> bool:
    return _kind(c) == "gate"


def is_measurement(c: dict) -> bool:
    return _kind(c) == "measurement"


class Tally(NamedTuple):
    passed: int
    failed: int
    measured: int

    @property
    def failable(self) -> int:
        return self.passed + self.failed

    @property
    def exit_code(self) -> int:
        """Failable checks only. A measurement cannot block a publish."""
        return 1 if self.failed else 0


def tally(reports: Iterable[dict]) -> Tally:
    """Count a run's rows by kind. Raises on a row that is neither."""
    passed = failed = measured = 0
    for r in reports:
        for c in r["checks"]:
            if _kind(c) == "measurement":
                measured += 1
            elif c["pass"]:
                passed += 1
            else:
                failed += 1
    return Tally(passed, failed, measured)


def render(c: dict) -> str:
    """One row, on the same grid whichever kind it is."""
    if _kind(c) == "measurement":
        mark, tail = "[measured]", str(c["why"])
    else:
        mark, tail = f"[{'PASS' if c['pass'] else 'FAIL'}]", f"want {c['want']}"
    return f"  {mark:<{_MARK_W}} {c['name']:<{_NAME_W}} {str(c['got']):<{_GOT_W}} {tail}"


def totals(t: Tally) -> str:
    """The two totals a run ends on, and never one number covering both kinds."""
    first = f"{t.passed} of {t.failable} failable check(s) pass"
    first += (f", {t.failed} failing. docs/30-findings-and-gates.md says which of "
              "those are known and deliberate." if t.failed else ".")
    return (f"\n{first}\n{t.measured} informational row(s) report a measurement "
            "and no verdict; docs/30 section 3 says why each one cannot fail "
            "today.")
