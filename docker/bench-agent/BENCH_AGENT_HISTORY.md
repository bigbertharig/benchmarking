# bench-agent Run History

## Runs

(No real-model runs yet.)

## Harness Validation

- 2026-08-09: methodology 1.1.0 made the per-response token budget explicit
  after an unbounded server default drove a smoke run to the rig's thermal
  warning boundary. No real-model 1.0.0 results existed to migrate.
- 2026-08-09: localhost mock-runtime tests passed for executable selection,
  transient-error recovery, no-tool behavior, schema rejection, semantic
  argument scoring, and sandbox path confinement. This is harness validation,
  not a model benchmark run.
