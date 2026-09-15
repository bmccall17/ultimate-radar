# 31 — How work is organised: tickets, sprints, and the one rule

Issues: <https://github.com/bmccall17/ultimate-radar/issues>

## The one rule

**An issue closes when a named check in `python -m tools.gates` flips to PASS.**

Not when the work feels done, not when the output looks better, not when a
summary says so. The brief this project started from asked for three things not
to happen — tuning a constant to make something pass, publishing something that
failed its gate because it was close, and a summary that reads better than the
measurements. All three are the same failure, and all three are prevented by the
same rule: the definition of done is a check somebody else can run.

`tools/gates.py` prints the ticket number beside every failing check and totals
them by ticket at the end, so the gate output *is* the sprint board:

```
  [FAIL] span identity accuracy   8/17 = 47%   want >= 75% over at least 8 spans  #1

by ticket - each closes when its checks all pass:
  https://github.com/bmccall17/ultimate-radar/issues/1   1 failing check(s)
  https://github.com/bmccall17/ultimate-radar/issues/6   12 failing check(s)
```

If a failing check has no ticket, the run says so. Open one, or write in
`docs/30` why the failure is permanent. A failing check that nobody owns and
nobody has justified is the thing this is built to prevent.

## Sprints are milestones

| | |
|---|---|
| **Sprint 1 — Make the disc real** | Goal 2. The two disc gates. Nothing else closes it. |
| **Sprint 2 — Know which way is downfield** | Attacking direction, unverified on every possession. |
| **Sprint 3 — Six good possessions, or four** | Decide p0006–p0010: publish or retire. No possession sits half-done. |

Ordered by dependency, not by appetite. Sprint 2's cheapest route was ruled out
by a Sprint 1 measurement (scores happen where the tracking fails), which is the
kind of thing that only shows up when the order is honest.

## Labels that mean something

- **`needs-gate`** — the ticket has no named check yet, so it has no definition of
  done. *Defining the check is the first task*, before any of the work. Two
  tickets carry this today and neither should be started without it.
- **`needs-human`** — blocked on tagging, or on a judgement only somebody watching
  the footage can make. These are the ones to raise early, because everything
  around them can be built while they wait.
- `goal-2`, `calibration`, `publishing` — which of the project's threads it serves.

## Writing a ticket

Four things, in this order:

1. **Done when** — the exact check name and threshold, copied from `tools/gates.py`.
2. **Where it stands** — the current measurement, with its denominator.
   `docs/30` § 2.1: a number without its denominator is not a result.
3. **Known not to work** — every approach already measured and abandoned, with the
   number that killed it. This is the most valuable part of a ticket here. Three
   still-based pre-filters, the phase-correlation pan, stillness-only emission and
   flight-speed-only ranking have all been tried and measured; a ticket that does
   not say so invites the next session to spend a day rediscovering it.
4. **Reading** — the doc section carrying the evidence.

## What does not go in a ticket

A finding. Findings go in `docs/30` and `docs/27`, because they outlive the work
and a closed issue is hard to search. A ticket points at the finding; it does not
hold it.
