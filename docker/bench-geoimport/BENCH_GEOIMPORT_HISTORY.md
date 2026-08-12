# bench-geoimport Run History

## Harness Validation

- 2026-08-12: Initial v1 suite created for geometry/admin-spine classification,
  job planning, and QA-claim discipline.
- 2026-08-12: Replaced v1 with prep-only methodology v2 after clarifying the
  three assurance levels. V2 evaluates local assignment classification,
  executable preparation plans, and reviewable handoff readiness. Cloud
  candidate QA and trusted-machine final QA are explicitly out of scope.
- 2026-08-12: Added model-agnostic enum guidance and text normalization, then
  connected the suite to shared `model_tuning_profiles.json`. Model profiles
  may tune inference/output discipline but cannot alter cases or scoring.
- 2026-08-12: `qwen3.6:27b` passed all five v2 prep cases at 0.9652 average
  (`20260812_qwen36_27b_geoimport_prep_v2_r2`). Per-case scores were 0.9474,
  1.0000, 0.8788, 1.0000, and 1.0000. The local SSD model load was 10 seconds.
  The remaining plan deductions were substantive omissions around explicit
  existing-script selection, identity outputs, and lightweight count/schema
  language, not response-format quirks.
- 2026-08-12: Shared-drive smoke comparison
  `20260812_qwen25coder_small_import_comparison_r1` confirmed that the fixed
  suite separates smaller models without format-specific scoring changes.
  `qwen2.5-coder:14b` passed at 0.9192 (1.0000 classification, 0.7576 plan,
  1.0000 failed-check handoff). `qwen2.5-coder:7b` scored 0.8740 (0.9474,
  0.7273, 0.9474) and correctly failed the 0.9000 aggregate threshold. The
  matching three-case `qwen3.6:27b` subset scored 0.9421. Deductions reflected
  omitted provenance, existing-script, identity, count, and schema-check
  details rather than JSON or prompt-family incompatibility.
- 2026-08-12: First uncached shared-drive loads took 56 seconds for the 14B
  model and 35 seconds for the 7B model. Immediate reloads took 7 and 4 seconds
  with filesystem cache. All runtime and benchmark containers were reaped.
