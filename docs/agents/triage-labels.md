# Triage Labels

The skills speak in terms of five canonical triage roles. This file maps those roles to the
actual label strings used in this repo's issue tracker.

**Our labels name the next thing to type.** A label that says `ready-for-agent` makes a
reader work out what happens next; a label that says `ready-for-implement` tells them to run
`/implement`. Where no skill call is the answer, the label says what is actually true instead
of inventing one.

| Label in mattpocock/skills | Label in our tracker | Meaning | Next call |
| -------------------------- | -------------------- | ------- | --------- |
| `needs-triage`             | `ready-for-triage`      | Nobody has evaluated this yet | `/triage` |
| `needs-info`               | `ready-for-questionnaire` | The answer is in somebody else's head and has not been asked for | `/to-questionnaire` |
| `ready-for-agent`          | `ready-for-implement`   | Fully specified, ready for an AFK agent | `/implement` |
| `ready-for-human`          | `ready-for-human`       | Needs a person, not an agent: watching footage, making a judgement, clicking through somebody else's dashboard | none, or `/wizard` when it is infrastructure or credentials |
| `wontfix`                  | `wontfix`               | Will not be actioned | none |

When a skill mentions a role (e.g. "apply the AFK-ready triage label"), use the corresponding
label string from the second column.

Two of the five keep a name that is not a call, and deliberately. `ready-for-human` is done by
a person at a keyboard or in front of the footage, and naming a skill there would be a lie
about who does the work. `wontfix` is the absence of a next step.

`ready-for-questionnaire` carries one nuance: it means the question has not been put yet. An
issue where somebody has already been asked and has not replied is waiting, not ready, and
should say so in a comment rather than sit under a label that invites a second questionnaire.

## Labels this repo already uses, which are not triage roles

Do not confuse these with the five above. They describe what a ticket is about, not what
state it is in.

| Label | Meaning here |
|---|---|
| `needs-gate` | The ticket has no named check in `python -m tools.gates` yet, so it has no definition of done. Defining the check is the first task. |
| `needs-human` | Blocked on tagging, or on a judgement only somebody watching the footage can make. **This is about the footage.** `ready-for-human` above is a triage state about who does the work. |
| `research` | Parked. An experiment, not a release blocker. Nothing here can stop a publish. |
| `index` | The game-wide possession index and what derives from it. |
| `repair` | Human-in-the-loop correction tooling. |
| `calibration`, `goal-2`, `publishing` | Which thread of the project the ticket serves. |
