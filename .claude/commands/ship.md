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

## 3. The milestone description carries the board

The **board** is the glance surface: what is done, what can be picked up now, what is
waiting and on what. It lives in the **open milestone's description**, because that is
the page somebody lands on when they want to know where the sprint stands. It was tried
inside the parent plan issue and failed for a plain reason worth not repeating: eighty
lines into a 280-line issue is somewhere nobody scrolls to, and the milestone page then
showed nothing at all.

Rewrite the description from what steps 1 and 2 found. It holds, in this order:

- The sprint's purpose in one sentence, and the ticket it is measured by.
- A count of done against open, and the gate totals from step 1. Say plainly whether any
  failing check is owned by a ticket in **this** milestone; failures owned elsewhere are
  not this sprint's problem and saying so stops them reading as one.
- **Ready now**: every open ticket with no open blocker. Mark the one on the critical
  path and the ones that block the sprint outcome.
- **Blocked**, each with the tickets it waits on, the sprint outcome last.
- **Done**, compactly. Numbers and a few words each, not a table.
- The one path through, in a line: which chain ends at the sprint outcome.
- Anything cut from the milestone since the last run, and where it went.

`gh api repos/:owner/:repo/issues/<n> --jq .issue_dependencies_summary.blocked_by` gives
the live blocker count; an open ticket reading `0` is ready now. Query every ticket
rather than reasoning from the last run's board, because tickets close and move between
runs and only the query knows it.

**GitHub renders a milestone description as plain text.** Markdown tables and links do
not render there. Write it as indented plain text with bare `#N` references, and check
the rendered milestone page rather than trusting the source.

The parent plan issue keeps a pointer to the milestone between its `ship:board` markers
and nothing else. Do not write a second board into it, and if a second board appears
anywhere, delete it: two views of one sprint means one is wrong with no way to tell
which.

### A ticket that cannot move the sprint outcome does not belong in the sprint

Check this every run, because it is how a board silts up. For each open ticket, ask
whether the sprint's measured outcome waits on it, directly or through a chain. A ticket
that serves a different goal is not cancelled, it is in the wrong milestone, and leaving
it there makes the board show work that cannot move the thing the board is about.

On 2026-09-17 that was nine of eighteen open tickets: a four-deep chain and its five
dependents, none of which the sprint outcome waited on. They moved to a milestone of
their own in one pass.

Say what you would move and why, and let the author decide. Moving a ticket between
milestones is theirs, not this step's.

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
