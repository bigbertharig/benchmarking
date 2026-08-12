# bench-dataimport Run History

## Runs

- 2026-08-12: Shared-drive smoke comparison
  `20260812_qwen25coder_small_import_comparison_r1` ran one
  `schema_understanding` and one `reference` case per model.
  `qwen2.5-coder:14b` and `qwen2.5-coder:7b` each scored 0.7619, below the
  earlier `qwen3.6:27b` smoke score of 1.0000. Both smaller models omitted the
  requested `geographic_level`; their reference outputs also exceeded the
  allowed keyword-gap budget. The 14B and 7B outputs had five and seven keyword
  gaps respectively, although both land in the same current rubric band.

## Harness Validation

- 2026-08-09: localhost mock-runtime smoke passed for one
  `schema_understanding` case through the real schema-v2 recorder and derived
  report generators. This is harness validation, not a model benchmark run.
