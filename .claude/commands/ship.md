---
description: Close out a sprint session - verify the live site, the ADRs and the board, then name the frontier.
allowed-tools: Bash, Read, Edit, Write, Grep, Glob, WebFetch
---

# /ship

Four steps, in this order: the world first, the board second, so the milestone
describes what is true rather than what was intended.

Report each step's verdict as it lands, and say plainly when a step could not be
verified rather than reporting a pass nobody observed.

## 1. The live site is the truth

AGENTS rule 7. <https://bmccall17.github.io/ultimate-radar/> is what gets judged, and
a stale site has already cost this project a review round.

- `git status --short` and `git log --oneline -1`: the tree is clean, HEAD is known.
- `git fetch && git status -sb`: local `main` and `origin/main` sit on the same commit.
- `gh run list --limit 5 --json name,status,conclusion,headSha`: the newest
  `pages build and deployment` run concluded `success`, on HEAD's sha.
- Fetch the live root page and compare it against `docs/index.html`, stripping every
  carriage return from both first: what the world serves is what the repo holds. The
  working tree is CRLF and Pages serves LF, so a raw byte compare reports a difference
  of exactly one byte per line and means nothing.
- `./.venv/Scripts/python.exe -m tools.gates`: record both totals, failable and
  informational, and which ticket owns each failure. Only the failable total moves.
  Use the venv's
  interpreter: a bare `python` is missing scipy and dies partway through with a
  traceback that reads like a defect in the check rather than the wrong python.

Done when all five carry a verdict and any drift between HEAD, `origin/main` and the
live site is named with the commit it is stuck on. Unpushed commits touching `docs/`
are a stale site even when the root page matches, because `docs/` is the Pages root and
carries the documentation too. Push them, and run `python -m tools.build_site` first
when the pipeline output moved, before going on - every step below describes a site
that is live.

## 2. Every ADR still says something true

Decisions live in `docs/adr/` as `AD-n`. `CONTEXT.md` is the glossary that quotes them;
`docs/30-findings-and-gates.md` holds the findings that retire them.

For each ADR, answer one question: does a finding, an open issue or a closed one
contradict it?

- An ADR a finding retired carries a **WITHDRAWN** line naming that finding and the
  issue that replaces it. AD-10 is the worked example - attacking direction belongs to
  a `(point, team)`, and #5 carries the replacement.
- An ADR that `CONTEXT.md` quotes says the same thing in both places.
- A decision taken this sprint and written nowhere gets its own file, numbered next.

Done when every ADR is accounted for: current, withdrawn with its replacement named, or
newly written.

## 3. The plan issue carries the orchestrator view

The **board** is the glance surface: who is done, what can be picked up now, what is
waiting and on what. It lives in the parent plan issue the tickets were cut from, under
its **`## Orchestrator View`** heading, between the `ship:board` markers. Rewrite
everything between those markers from what steps 1 and 2 found, and touch nothing else
in the issue: the heading, the note under it, and every outcome below the rule are the
author's, not this step's.

**Find the markers; never guess the position.** `<!-- ship:board -->` and
`<!-- /ship:board -->` are the only anchors. If they are missing, put them under the
`## Orchestrator View` heading and create it if it does not exist — directly under the
issue's opening paragraph, above the rule that starts the outcomes. Do not write a
second board anywhere else in the issue, and if you find one, delete it: two views of
one sprint means one of them is wrong and no way to tell which. That has happened
once already, a board at the very top and an empty `Orchestrator View` placeholder
eight lines below it, each looking like the real one.

The board holds, in this order:

- A heading counting done against total, and one line: the gate totals from step 1, and
  whether the site is live and current.
- **Done**, each with the outcome it served.
- **Ready now**: every open ticket with no open blocker. Mark the one on the critical
  path and the ones that block the sprint outcome.
- **Blocked**, each with the tickets it waits on, the sprint outcome last.
- The chains, in one short paragraph: which is the critical path, and which is merely
  long.

`gh api repos/:owner/:repo/issues/<n> --jq .issue_dependencies_summary.blocked_by`
gives the live blocker count; an open ticket reading `0` is ready now. Query every
ticket rather than reasoning from the last run's board — tickets close between runs,
and a blocker count is the only thing that knows it.

The milestone description **points at the board and does not copy it**. One sentence on
what the sprint is for, one on the outcome it is measured by, and a link. Two copies of
a board means one of them is wrong and no way to tell which.

### A triage label names a call that has not been made yet

`docs/agents/triage-labels.md`: each of the five names the next thing to type. So a
label whose call has already been made is a standing instruction to redo work that is
already done, which is worse than no label — `ready-for-tickets` on a plan whose
tickets exist sends the next reader to cut them a second time.

Clear those, and say what the call produced:

- `ready-for-tickets`, once the tickets exist → comment listing them by number,
  then remove the label.
- `ready-for-triage`, once the issue has been triaged → the triage verdict is already
  a comment; remove the label.
- `ready-for-questionnaire`, once the questions have been put → comment saying who was
  asked and when, then remove the label. Waiting on a reply is waiting, not ready.
- `ready-for-implement` and `ready-for-human` stay until the work lands, because the
  call they name is the work itself.

Done when the board names every ticket in the milestone exactly once under the right
heading, every triage label in the milestone names a call still waiting to be made, and
a reader who saw none of this session can tell what to pick up from the board alone.

## 4. The next immediate steps

Recommend at most three, drawn from the frontier and ranked. Each names its ticket, why
it is next, and the gate in `python -m tools.gates` that will close it.

Prefer the ticket that unblocks the most others, and the under-an-hour ticket that is
currently blocking the sprint outcome. Name the ticket on the critical path even when
it is not the one to start.

Done when every recommendation carries a ticket number and a gate, and a ticket
labelled `needs-gate` says that defining its check is the first task.
