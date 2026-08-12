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
