# Domain Docs

How the engineering skills should consume this repo's domain documentation when exploring the codebase.

## Before exploring, read these

- **`CONTEXT.md`** at the repo root. It is a glossary and nothing else, by design.
- **`docs/adr/`**: read ADRs that touch the area you're about to work in.

This is a single-context repo. There is no `CONTEXT-MAP.md` and no per-context `CONTEXT.md`.

If any of these files don't exist, **proceed silently**. Don't flag their absence; don't suggest creating them upfront. The `/domain-modeling` skill (reached via `/grill-with-docs` and `/improve-codebase-architecture`) creates them lazily when terms or decisions actually get resolved.

## File structure

```
/
├── CONTEXT.md
├── docs/adr/
│   ├── 0001-track-on-the-field-not-on-the-screen.md
│   └── ... through 0010
└── ur/, tools/, viewer/
```

## Decisions are named `AD-n`, and the name is the stable handle

This repo has called its decisions `AD-1` through `AD-10` since before the code existed, and
the name is cited about 220 times across the documents, the pipeline and the viewer. The
files moved into `docs/adr/` on 2026-09-16; **the names did not change and must not**.
`docs/adr/0007-*.md` is AD-7. Cite a decision as `AD-7`, not as `ADR-0007`.

`docs/09-decision-record.md` is the one-page index of all ten. `docs/02-architecture.md` is
the pipeline diagram and the stage notes, and points here for the reasoning.

## Use the glossary's vocabulary

When your output names a domain concept (in an issue title, a refactor proposal, a hypothesis, a test name), use the term as defined in `CONTEXT.md`. Don't drift to synonyms the glossary explicitly avoids.

Several terms here are narrower than their everyday meaning and getting them wrong changes
what a sentence claims: **slot** is not a person, **declared** is not **measured** is not
**observed**, a **tag** is a fact about the game while a **correction** is a fact about the
tracking, and the correction operation `confirm` is not the evidence state `confirmed`.

If the concept you need isn't in the glossary yet, that's a signal: either you're inventing language the project doesn't use (reconsider) or there's a real gap (note it for `/domain-modeling`).

## Flag ADR conflicts

If your output contradicts an existing ADR, surface it explicitly rather than silently overriding:

> _Contradicts AD-7 (events are tagged by hand), but worth reopening because…_

**One ADR is withdrawn.** AD-10 rests on a false reading of the sport and its supporting
finding is void; see the banner on `docs/adr/0010-*.md` and issue #5. Do not build on it, and
do not treat its withdrawal as licence to rewrite the others by the same argument.
