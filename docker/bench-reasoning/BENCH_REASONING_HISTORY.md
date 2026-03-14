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

## In-Progress Runs

- `reasoning_top3_l100_20260312_2105` (started 2026-03-12 UTC)
  - models:
    - `Qwen2.5-Coder-7B-Instruct-Q4_K_M.gguf` (`11436`)
    - `Mistral-7B-Instruct-v0.3-Q4_K_M.gguf` (`11437`)
    - `DeepSeek-R1-Distill-Qwen-7B-Q4_K_M.gguf` (`11439`)
  - tasks: `gsm8k,bbh,drop,math_500,aime_2024`
  - limit: `100`
  - output root: `/mnt/shared/logs/benchmarks/bench-reasoning/history/reasoning_top3_l100_20260312_2105`
  - run logs:
    - `/mnt/shared/logs/benchmarks/bench-reasoning/history/reasoning_top3_l100_20260312_2105/qwen25_coder7b.log`
    - `/mnt/shared/logs/benchmarks/bench-reasoning/history/reasoning_top3_l100_20260312_2105/mistral7b.log`
    - `/mnt/shared/logs/benchmarks/bench-reasoning/history/reasoning_top3_l100_20260312_2105/deepseek_r1_7b.log`

## 2026-03-12 Debug Sweep (BBH Boolean, Small Limits)

Goal:
- diagnose why some models were scoring `0.0` on `bbh_cot_fewshot_boolean_expressions`
- keep tweaks model/runtime-side (prompts, request behavior, parser handling), without changing benchmark task files

Runner/test changes used in this sweep:
- `run.sh` gained optional patch flags:
  - `--patch-reasoning-content-fallback`
  - `--patch-boolean-answer-canonicalization`
- no task YAML or benchmark question set was edited

### Experiment Results

| Run Date (UTC) | Model | Task | Limit | Variant | Score | Run Path |
| --- | --- | --- | --- | --- | --- | --- |
| 2026-03-12 | qwen3.5:9b-q3km | bbh_cot_fewshot_boolean_expressions | 10 | prompt_tweak_v1 + `until=["</s>"]` + reasoning fallback | 0.0 | `/mnt/shared/logs/benchmarks/bench-reasoning/debug_zero_scores/probe_l10_prompt_tweak_v1/qwen35_9b` |
| 2026-03-12 | qwen3.5:4b | bbh_cot_fewshot_boolean_expressions | 10 | prompt_tweak_v1 + `until=["</s>"]` + reasoning fallback | 0.0 | `/mnt/shared/logs/benchmarks/bench-reasoning/debug_zero_scores/probe_l10_prompt_tweak_v1/qwen35_4b` |
| 2026-03-12 | deepseek-r1:7b | bbh_cot_fewshot_boolean_expressions | 10 | prompt_tweak_v1 + `until=["</s>"]` + reasoning fallback | 1.0 | `/mnt/shared/logs/benchmarks/bench-reasoning/debug_zero_scores/probe_l10_prompt_tweak_v1/deepseek_r1_7b` |
| 2026-03-12 | qwen3.5:9b-q3km | bbh_cot_fewshot_boolean_expressions | 10 | baseline prompt + default BBH stops + reasoning fallback | 0.0 | `/mnt/shared/logs/benchmarks/bench-reasoning/debug_zero_scores/probe_qwen9b_no_gen_override_l10` |
| 2026-03-12 | qwen3.5:4b | bbh_cot_fewshot_boolean_expressions | 10 | baseline prompt + default BBH stops + reasoning fallback | 0.0 | `/mnt/shared/logs/benchmarks/bench-reasoning/debug_zero_scores/probe_qwen4b_no_gen_override_l10` |
| 2026-03-12 | qwen3.5:9b-q3km | bbh_cot_fewshot_boolean_expressions | 10 | baseline prompt + default BBH stops + reasoning fallback + boolean canonicalization | 0.0 | `/mnt/shared/logs/benchmarks/bench-reasoning/debug_zero_scores/probe_qwen_boolean_canon_l10/qwen35_9b` |
| 2026-03-12 | qwen3.5:4b | bbh_cot_fewshot_boolean_expressions | 10 | baseline prompt + default BBH stops + reasoning fallback + boolean canonicalization | 0.0 | `/mnt/shared/logs/benchmarks/bench-reasoning/debug_zero_scores/probe_qwen_boolean_canon_l10/qwen35_4b` |
| 2026-03-12 | qwen3.5:9b-q3km | bbh_cot_fewshot_boolean_expressions | 10 | baseline prompt + `until=["</s>"]` + reasoning fallback + boolean canonicalization | 0.0 | `/mnt/shared/logs/benchmarks/bench-reasoning/debug_zero_scores/probe_qwen9b_canon_until_eos_l10` |
| 2026-03-12 | qwen3.5:9b-q3km | bbh_cot_fewshot_boolean_expressions | 10 | disable-thinking request override + baseline prompt | 0.0 | `/mnt/shared/logs/benchmarks/bench-reasoning/debug_zero_scores/probe_qwen_disable_thinking_l10_v2/qwen35_9b` |
| 2026-03-12 | qwen3.5:4b | bbh_cot_fewshot_boolean_expressions | 10 | disable-thinking request override + baseline prompt | 0.0 | `/mnt/shared/logs/benchmarks/bench-reasoning/debug_zero_scores/probe_qwen_disable_thinking_l10_v2/qwen35_4b` |
| 2026-03-12 | qwen3.5:9b-q3km | bbh_cot_fewshot_boolean_expressions | 10 | disable-thinking request override + strict phrase prompt (`So the answer is ...`) | 0.0 | `/mnt/shared/logs/benchmarks/bench-reasoning/debug_zero_scores/probe_qwen_disablethinking_strictphrase_l10/qwen35_9b` |
| 2026-03-12 | qwen3.5:4b | bbh_cot_fewshot_boolean_expressions | 10 | disable-thinking request override + strict phrase prompt (`So the answer is ...`) | 0.0 | `/mnt/shared/logs/benchmarks/bench-reasoning/debug_zero_scores/probe_qwen_disablethinking_strictphrase_l10/qwen35_4b` |

### Additional Failed Probe (Not Scored)

| Run Date (UTC) | Model | Variant | Outcome | Run Path |
| --- | --- | --- | --- | --- |
| 2026-03-12 | qwen3.5:9b-q3km | `local-completions` API mode (with and without `tokenized_requests=True`) | failed: tokenizer/model-id resolution attempted against HF (`401 RepositoryNotFound`) | `/mnt/shared/logs/benchmarks/bench-reasoning/debug_zero_scores/probe_qwen9b_local_completions_l10` and `/mnt/shared/logs/benchmarks/bench-reasoning/debug_zero_scores/probe_qwen9b_local_completions_tokenized_l10` |

### Conclusions From This Sweep

- DeepSeek benefited from stricter output prompting in reasoning runs.
- Qwen3.5 9B and 4B remained `0.0` across prompt and parser-side extraction attempts in these BBH boolean probes.
- Default BBH stop settings (`</s>`, `Q`, `\\n\\n`) greatly improved runtime speed on Qwen compared with `until=["</s>"]`, but did not improve score.
- Qwen accepted request override `chat_template_kwargs.enable_thinking=false` (model-side), but score remained `0.0` in limit-10 probes; direct spot-checks showed formatted output can still be incorrect on boolean reasoning.
- No benchmark task definition files were changed during this sweep.
