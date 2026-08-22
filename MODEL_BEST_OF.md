# Model Best Of

Use this page for model decisions. Detailed scores, runtime notes, and test
history remain in the linked evidence documents.

Last decision review: `2026-08-22`

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
| Split-worker deep reasoning | `ministral-3:14b` | `ministral-3:8b` | 2x 1060 split | Valid l50 GSM8K, DROP, and IFEval plus runtime coverage | Prefer 14B for quality; 8B remains the faster lane. Brain l50 evidence is still pending. |
| Single-1060 worker | `qwen2.5-coder:7b` | `ministral-3:3b` | 1x 1060 | Ministral 3B completed full EvalPlus and runtime qualification | Keep the established 7B default; Ministral 3B is a smaller tested alternative. |
| CPU worker | Hold | Hold | CPU stack | No comparable modern campaign | Select only after bounded CPU runtime tests. |

## Best By Rig Lane

| Lane | Default | Use it for | Avoid or escalate when |
| --- | --- | --- | --- |
| 3090 brain | `qwen3.5:27b` | Country imports, geometry prep, broad orchestration, general code | Use `qwen3-coder:30b-a3b` for code-heavy MBPP-style work. |
| 2x 1060 quality | `ministral-3:14b` | Data prep and split-worker code | Geometry planning currently trails the brain models. |
| 2x 1060 speed | `ministral-3:8b` | Parallel import-prep lanes and cheaper code work | Escalate difficult prep plans and final handoffs. |
| 1x 1060 | `qwen2.5-coder:7b` | Structured extraction, code, and document preparation | `ministral-3:3b` is tested but weaker and remains an explicit alternative. |
| CPU stack | No default yet | Deterministic bounded preprocessing | Do not assign open-ended model inference yet. |

## Evidence State

- Import, geometry, pipeline, agent, and routing comparisons are smoke evidence
  from campaign `20260813_limit5_all` with per-task limit 5 where supported.
- HumanEval+ and MBPP+ code results are full-suite results from the same campaign.
- Runtime failures are not model-quality scores. Failed or interrupted groups
  stay out of final decisions until rerun.
- Validation attempt `20260820_modern_validation_l50` ended in a rig thermal
  shutdown at 100C. Partial rows from that run are not decision evidence.
- Sequential retry `20260820_modern_validation_l50_retry3` completed without a
  thermal abort. CPU package temperature peaked at 94C. Ministral 14B/8B l50
  reasoning and runtime evidence, plus Ministral 3B full code/runtime evidence,
  is valid.
- The retry's three brain lanes are invalid: port 11434 continued serving
  `qwen3.6:27b` while the controller attributed responses to Qwen3.5, Qwen
  Coder, and Devstral. Those rows were removed from the canonical ledger and
  cannot be used until a brain-only rerun verifies runtime model identity.
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
