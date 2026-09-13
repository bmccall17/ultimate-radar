# Rules of engagement

You are building `ultimate-radar`. Read `docs/01-brief.md` and `docs/04-milestones.md`
before writing code. Work milestone by milestone; each has an acceptance test that must
pass before you move on.

## Hard rules

1. **Licence gate.** Before adding any dependency or model weight, find its licence and
   add a row to `docs/07-licenses.md`. If it is AGPL-3.0, GPL, CC-BY-NC, or a custom
   non-OSI licence, do not add it — pick the permissive alternative already listed there.
   If you cannot confirm a licence, do not use it and say so.
2. **Never mutate tracking output.** `tracks.json` is append-only truth about what the
   pipeline saw. Human edits go in `corrections.json`. `ur/resolve.py` combines them.
   If you find yourself editing `tracks.json` in place, you have taken a wrong turn.
3. **Every position carries provenance.** No function may return a bare `(x, y)`. It
   returns a sample with an evidence state and a sigma. See `docs/05-uncertainty.md`.
   A metric computed from weak evidence must be labelled as such, not silently reported.
4. **No invented players.** Exactly 7 per team per point. The tracker maintains 14 slots.
   It may not create a 15th, and it may not delete one.
5. **Field coordinates are the common language.** Yards, origin at the corner of the
   defending endzone, X along the field (0–120), Y across (0–53.333). Image coordinates
   never leave the detection and calibration stages.
6. **Determinism.** Seed everything. Same input, same output — the eval numbers are
   meaningless otherwise.

## Working style

- Prefer a stage you can run alone, on one possession, in under a minute, over an
  end-to-end script. Every stage reads and writes files described in
  `docs/03-data-contracts.md`.
- Write the acceptance test for a milestone before the milestone.
- When a model underperforms, first try more tiling, more labelled frames, or a better
  motion prior. Swapping architectures is the last move, not the first.
- When something cannot be done automatically at acceptable quality, make it a two-click
  human task and move on. Human-in-the-loop is the design, not a failure.
- Keep the viewer dependency-free: plain HTML, CSS and JS reading a JSON file. It must
  open from `file://` or a static host with no build step.

## What to do when you are stuck

Write the question into `docs/08-risks.md` under "Open questions", make the most
conservative choice that keeps the pipeline honest (usually: mark it unknown and let a
human fix it), and keep going. Do not fake data to make a stage look like it works.
