JSON Schema files for the contracts in `docs/03-data-contracts.md`.

Write these in M1 as the contracts stabilise, one file per contract, and validate every
stage's output against its schema in the stage's own test. A stage that emits a file failing
its schema is a failing stage — this is the cheapest guard against the pipeline drifting
apart across milestones.

Expected files: `clip.schema.json`, `calibration.schema.json`, `detections.schema.json`,
`tracks.schema.json`, `identities.schema.json`, `events.schema.json`,
`corrections.schema.json`, `possession.schema.json`.
