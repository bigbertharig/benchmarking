# bench-pipeline Run History

Historical results for the worker-facing custom reliability suite.

The main MODEL_LIBRARY.md holds only the latest score per model/test.
This file holds the full history so we can track how prompt and config changes affect scores.

## How to read this table

Each row is one scored run. The system prompt column records the exact prompt used
so you can correlate prompt changes with score changes across runs.

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
