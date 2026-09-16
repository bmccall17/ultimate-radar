# AD-5 — Evidence states, not confidence scores

Every position sample carries a discrete provenance state (`observed`, `provisional`,
`interpolated`, `predicted`, `unknown`, `confirmed`) plus a positional sigma in yards. See
`docs/05-uncertainty.md` for the full state machine.

> **`provisional` added 2026-09-14.** A sixth state, for a match that re-acquires a slot
> after a long gap. It is an observation of *somebody*; whether it is the same somebody is
> the open question. It renders like an observation and counts for coverage, and it is
> excluded from every metric until a human confirms or swaps it. The reason it needs its own
> state rather than a flag is AD-5's own argument: a small set of named states can be
> rendered distinctly and reasoned about in `if` statements, and "we saw a person here, we
> are not sure it is this person" is a distinct thing to say.

*Why.* A float confidence is uninterpretable to a coach and easy for the code to ignore. A
small set of named states can be rendered distinctly, reasoned about in `if` statements, and
explained in one sentence in the UI. It also lets derived metrics refuse to answer: a
separation number computed from a `predicted` receiver is not a measurement and must not be
displayed as one.
