# bench-pipeline Run History

Historical results for the worker-facing custom reliability suite.

The main MODEL_LIBRARY.md holds only the latest score per model/test.
This file holds the full history so we can track how prompt and config changes affect scores.

## How to read this table

Each row is one scored run. The system prompt column records the exact prompt used
so you can correlate prompt changes with score changes across runs.

## 2026-10-23 JSON Schema Grading v2 (methodology 2.1.0)

Rows from this point carry methodology `bench-pipeline/local-custom` version 2.1.0, comparison group
`pipeline-local-custom-v2`. Only `custom_json_schema_strict` grading changed; the other five tests grade as
before, but share the suite's methodology version.

- The `priority` value is no longer graded, only its type (an integer). The prompts give the schema as
  `"priority": integer` and never say what priority means, while every case expected the GPU number from
  the input (or 1 when none was named). Models that read it as urgency failed nearly every case: on the
  latest runs gemma-4:31b scored 0.154, qwen3.6:27b 0.231 and qwen3-coder-next 0.308, almost all
  "priority mismatch". The test is meant to measure strict JSON with the required keys and types.
- `action_contains` matches across spaces, hyphens and underscores ("fall back" counts for "fallback").
- The `priority` values were removed from the cases' `expected` blocks in `custom_tasks/cases.json`.
- Past runs were re-graded from the responses saved in each `result.json` by
  `scripts/active/rescore_pipeline_json_records.py` (56 runs, every model in the ledger). The new rows keep
  the original run time, suite and run class, have `rescored_from_responses` in their config, and replace the
  rows they re-grade in the scoreboard (`benchmark_records.selection_key` prefers the newer methodology on a
  tie). Examples, old -> new: nemotron-3.5-bolt 0.154 -> 0.923, gemma-4:31b 0.154 -> 0.769,
  qwen3-coder-next 0.308 -> 0.923, qwen3.8:27b 0.385 -> 1.000.
- Still graded and still failing, open questions: the `safe` flag (expected `true` in all 13 cases and not
  defined in the prompt either; 147 case failures across the saved runs, for example llama3.3:70b answers
  `false` for "restart gpu") and a few arbitrary action keywords ("request" for "stop run and request
  corrected path", "index" for "verify DC batch status then build _index.json"). Fenced or non-JSON answers
  remain failures by design.

## Results

### Repeat consistency baseline (2026-03-10, no prompt tuning)

Run path: `/mnt/shared/logs/benchmarks/parallel_worker_suite_20260310_002158/results`

| Run Date (UTC) | Model | Score | Passes | Total | System Prompt Used |
| --- | --- | --- | --- | --- | --- |
| 2026-03-10T07:25:00 | Qwen2.5-Coder-7B-Instruct-Q4_K_M.gguf | 50/79 | 50 | 79 | (no prompt profiles) |
| 2026-03-10T07:25:57 | Mistral-7B-Instruct-v0.3-Q4_K_M.gguf | 54/79 | 54 | 79 | (no prompt profiles) |
| 2026-03-10T07:48:14 | DeepSeek-R1-Distill-Qwen-7B-Q4_K_M.gguf | 29/79 | 29 | 79 | (no prompt profiles) |
| 2026-03-10T07:47:23 | Qwen3.5-4B-Q4_K_M.gguf | 13/79 | 13 | 79 | (no prompt profiles) |
| 2026-03-10T08:02:27 | Qwen3.5-9B-Q3_K_M.gguf | 16/79 | 16 | 79 | (no prompt profiles) |

### Prompt-tuned pass (2026-03-10, with --use-model-prompts)

Run path: `/mnt/shared/logs/benchmarks/parallel_worker_suite_20260310_094238/results`

| Run Date (UTC) | Model | Score | Passes | Total | System Prompt Used |
| --- | --- | --- | --- | --- | --- |
| 2026-03-10T16:44:10 | Qwen2.5-Coder-7B-Instruct-Q4_K_M.gguf | 59/79 | 59 | 79 | (see per-test results) |
| 2026-03-10T16:45:39 | Mistral-7B-Instruct-v0.3-Q4_K_M.gguf | 53/79 | 53 | 79 | (see per-test results) |
| 2026-03-10T17:04:12 | DeepSeek-R1-Distill-Qwen-7B-Q4_K_M.gguf | 40/79 | 40 | 79 | (see per-test results) |
| 2026-03-10T17:07:52 | Qwen3.5-4B-Q4_K_M.gguf | 18/79 | 18 | 79 | (see per-test results) |
| 2026-03-10T17:23:26 | Qwen3.5-9B-Q3_K_M.gguf | 15/79 | 15 | 79 | (see per-test results) |

### Prompt impact comparison

| Model | Baseline | Prompt-tuned | Delta | Baseline time (s) | Tuned time (s) |
| --- | --- | --- | --- | --- | --- |
| Qwen2.5-Coder-7B-Instruct-Q4_K_M.gguf | 50/79 | 59/79 | +9 | 182 | 91 |
| Mistral-7B-Instruct-v0.3-Q4_K_M.gguf | 54/79 | 53/79 | -1 | 239 | 180 |
| DeepSeek-R1-Distill-Qwen-7B-Q4_K_M.gguf | 29/79 | 40/79 | +11 | 1576 | 1293 |
| Qwen3.5-4B-Q4_K_M.gguf | 13/79 | 18/79 | +5 | 1525 | 1513 |
| Qwen3.5-9B-Q3_K_M.gguf | 16/79 | 15/79 | -1 | 2429 | 2447 |

## Notes

- The repeat consistency baseline had no prompt profiles enabled.
- The prompt-tuned pass used `--use-model-prompts` with profiles from `custom_tasks/model_prompt_profiles.json`.
- Per-test detail and exact prompt text are in each run's `result.json` under `prompts_snapshot` and `system_prompt_used`.
