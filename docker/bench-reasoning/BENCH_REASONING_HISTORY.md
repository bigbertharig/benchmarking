# bench-reasoning Run History

Historical results for the lm-eval reasoning-focused suite.

The main MODEL_LIBRARY.md holds only the latest score per model/test.
This file holds the full history so we can track how prompt and config changes affect scores.

## How to read this table

Each row is one scored run. For lm-eval runs, the prompt is determined by the chat
template and any system prompt injected via the template configuration.

## Results

| Run Date (UTC) | Model | Tasks | Scores | Config Notes | Run Path |
| --- | --- | --- | --- | --- | --- |

No completed reasoning suite runs recorded yet. Partial/canceled runs:
- `parallel_reasoning_suite_20260310_112146` (canceled)
- `parallel_reasoning_suite_20260310_125816` (canceled)

Earlier individual task runs (from lm-eval, not full suite):

| Run Date (UTC) | Model | Task | Score | Metric | Suite | Run Path |
| --- | --- | --- | --- | --- | --- | --- |
| 2026-03-05 | qwen2.5:7b | gsm8k | 0.75 | exact_match | initial_matrix_20260305 | (ledger) |
| 2026-03-05 | qwen2.5:7b | bbh | 0.5556 | exact_match | initial_matrix_20260305 | (ledger) |
| 2026-03-05 | qwen2.5:7b | drop | 0.1488 | f1 | initial_matrix_20260305 | (ledger) |
| 2026-03-05 | qwen2.5-coder:7b | gsm8k | 1.0 | exact_match | quick_triplet_l1_20260305 | (ledger) |
| 2026-03-05 | qwen2.5-coder:7b | drop | 0.27 | f1 | quick_triplet_l1_20260305 | (ledger) |
| 2026-03-05 | qwen2.5-coder:14b | gsm8k | 1.0 | exact_match | quick_triplet_l1_20260305 | (ledger) |
| 2026-03-05 | qwen2.5-coder:14b | drop | 0.57 | f1 | quick_triplet_l1_20260305 | (ledger) |
| 2026-03-05 | qwen2.5-coder:32b | gsm8k | 0.0 | exact_match | quick_triplet_l1_20260305 | (ledger) |
| 2026-03-05 | qwen2.5-coder:32b | drop | 0.18 | f1 | quick_triplet_l1_20260305 | (ledger) |

## Notes

- Individual task runs above were recorded through the benchmark ledger, not through full docker suite runs.
- Full docker reasoning suite runs have been attempted but canceled before scoring.
