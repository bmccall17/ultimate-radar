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
- Fetch the live root page and compare it against `docs/index.html`: what the world
  serves is what the repo holds.
- `python -m tools.gates`: record the failable total and which ticket owns each failure.

Done when all five carry a verdict and any drift between HEAD, `origin/main` and the
live site is named with the commit it is stuck on. When the site is behind, run
`python -m tools.build_site`, commit and push before going on - every step below
describes a site that is live.

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

## 3. The milestone carries the orchestrator view

The open milestone's description is the single page somebody reads to know where the
sprint stands. Rewrite it from what steps 1 and 2 found, holding, in this order:

- One sentence on what the sprint is for and the one outcome it is measured by.
- The **frontier**: every open ticket with no open blocker, by number and title. These
  can be picked up now.
- What is blocked, each with the ticket it waits on.
- What closed since the last `/ship`, each with the gate that closed it.
- The failable gate total from step 1.

`gh api repos/:owner/:repo/issues/<n> --jq .issue_dependencies_summary.blocked_by`
gives the live blocker count; an open ticket reading `0` is on the frontier. Leave the
parent issue the tickets were cut from as it stands.

Done when the description names every open ticket in the milestone exactly once, and a
reader who saw none of this session can tell what to pick up.

## 4. The next immediate steps

Recommend at most three, drawn from the frontier and ranked. Each names its ticket, why
it is next, and the gate in `python -m tools.gates` that will close it.

Prefer the ticket that unblocks the most others, and the under-an-hour ticket that is
currently blocking the sprint outcome. Name the ticket on the critical path even when
it is not the one to start.

Done when every recommendation carries a ticket number and a gate, and a ticket
labelled `needs-gate` says that defining its check is the first task.
