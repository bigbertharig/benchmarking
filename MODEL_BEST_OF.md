# Model Best Of

Use this page for model decisions. Detailed scores, runtime notes, and test
history remain in the linked evidence documents.

Last decision review: `2026-08-14`

## Best By Job

| Job | Preferred model | Runner-up | Placement | Evidence | Decision note |
| --- | --- | --- | --- | --- | --- |
| Country-import coordinator | `qwen3.5:27b` | `devstral-small:24b` | 3090 | Import prep 86.7% combined; pipeline 75.7% | Best complete import-oriented result in the August smoke campaign. |
| Data preparation | `ministral-3:14b` | `qwen3.5:27b` | 2x 1060 split | 80.0% vs 78.0% | Provisional: only a two-point smoke-test lead. |
| Geometry preparation | `qwen3.5:27b` | `devstral-small:24b` | 3090 | 95.4% vs 91.0% | Strongest classification, prep-plan, and handoff aggregate. |
| Brain code generation | `qwen3.5:27b` | `qwen3-coder:30b-a3b` | 3090 | HumanEval+ base 95.1% vs 91.5% | Qwen Coder leads MBPP+ base, 87.8% vs 85.7%; choose by workload when code-only. |
| Split-worker code generation | `ministral-3:14b` | `ministral-3:8b` | 2x 1060 split | HumanEval+ base 87.2% vs 84.1% | Full code suites completed; 14B is stronger but slower. |
| Fast split-worker import prep | `ministral-3:8b` | `ministral-3:14b` | 2x 1060 split | Data 76.0%; geometry 83.4% | Use when throughput matters more than best available planning quality. |
| Agent/tool orchestration | `qwen3.5:27b` (provisional) | `qwen3-coder:30b-a3b` | 3090 | Pipeline 75.7%; routing 88.6% | Agent suite is still too small for a final decision. |
| Deep reasoning | Hold | Hold | Any | August evidence has five examples per leaf; l50 validation was thermally interrupted | Do not rank models until a hardware-cleared validation run completes. |
| Single-1060 worker | Hold | Hold | 1x 1060 | Ministral 3B full code run was thermally interrupted | Rerun code/runtime qualification after hardware clearance. |
| CPU worker | Hold | Hold | CPU stack | No comparable modern campaign | Select only after bounded CPU runtime tests. |

## Best By Rig Lane

| Lane | Default | Use it for | Avoid or escalate when |
| --- | --- | --- | --- |
| 3090 brain | `qwen3.5:27b` | Country imports, geometry prep, broad orchestration, general code | Use `qwen3-coder:30b-a3b` for code-heavy MBPP-style work. |
| 2x 1060 quality | `ministral-3:14b` | Data prep and split-worker code | Geometry planning currently trails the brain models. |
| 2x 1060 speed | `ministral-3:8b` | Parallel import-prep lanes and cheaper code work | Escalate difficult prep plans and final handoffs. |
| 1x 1060 | No default yet | Reserved pending rerun | Do not route production prep to Ministral 3B yet. |
| CPU stack | No default yet | Deterministic bounded preprocessing | Do not assign open-ended model inference yet. |

## Evidence State

- Import, geometry, pipeline, agent, and routing comparisons are smoke evidence
  from campaign `20260813_limit5_all` with per-task limit 5 where supported.
- HumanEval+ and MBPP+ code results are full-suite results from the same campaign.
- Runtime failures are not model-quality scores. Failed or interrupted groups
  stay out of final decisions until rerun.
- Validation attempt `20260820_modern_validation_l50` ended in a rig thermal
  shutdown at 100C. Partial rows from that run are not decision evidence.
- A close score is not treated as a permanent winner. Prefer the cheaper lane
  when the difference is small and the task does not require the stronger model.

## Update Rule

Update this page only after a campaign review. Change a decision when the new
evidence is comparable, the relevant run completed, and the operational tradeoff
is understood. Keep provisional and hold states explicit.

Evidence:

- [Generated benchmark reference](results/MODEL_BENCHMARK_REFERENCE.md)
- [Machine-readable scoreboard](results/model_library_scoreboard.json)
- [Runtime guide](MODEL_RUNTIME_GUIDE.md)
- [Benchmark lessons](BENCHMARK_LESSONS_LEARNED.md)
