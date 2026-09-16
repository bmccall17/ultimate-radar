# AD-11 — A row that cannot fail is not a check

`python -m tools.gates` carries two kinds of row and totals them apart. A **gate**
holds a measurement to a threshold and returns PASS or FAIL; it counts in the failable
total and it moves the exit code. A **measurement** reports a number, names the reason
it has no threshold, and returns no verdict at all. Only a gate can close an issue.

`tools/checks.py` is where a new check picks its kind, and the choice is enforced
rather than documented: a measurement has **no `pass` key — absent, not `False`** — so
any code totalling `c["pass"]` raises rather than quietly counting a row that could
never have failed.

*Why.* `docs/31` closes an issue when a named check flips to PASS. That rule is this
project's whole defence against the three things the brief asks not to happen, and it
has one weak point: a row that can never flip. Twenty-four of the run's 132 rows were
built `add(name, True, ...)` with `want="reported, not gated"`. Each printed `[PASS]`,
each counted into a single total, and that total was the number a reader trusted.

The inflated total was the smaller problem. The larger one is that a ticket pointed at
such a row would carry a definition of done it could never fail to meet — which is the
exact failure `docs/31` exists to prevent, one level up, wearing the uniform of the
thing that prevents it.

*Why not just delete them.* All four measure something worth seeing: the denominator
that qualifies a gated mean (§ 2.1), a drift that § 2.0 proved is not the attacking
direction it was read as, the queue of unconfirmed quarters, and the stretch where a
reader sees no disc. Deleting them loses real information. Gating them means choosing a
constant that makes current output pass, which is the first of the brief's three traps
and the reason § 2.0 cost what it did. Reporting without a verdict is the only honest
third option.

*What it costs.* Every new check must choose a kind, and a measurement must say in one
line why it has no threshold or `tools/checks.py` refuses to build it. `docs/30` § 3
carries the longer answer for each and what would make it failable. The day one
acquires a defensible threshold it becomes a `gate()` call, the failable total goes up
by one, and that is the whole change.
