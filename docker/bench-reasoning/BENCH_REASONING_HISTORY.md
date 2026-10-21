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

## 2026-10-20 Lenient Scoring for Rankings (extract v5)

Rows from this point carry `config_id` `lm-eval-0.4.11-reasoning-extract-v5`. Model rankings use the
flexible rows; strict rows are still recorded beside them, unchanged, so harness-comparable numbers stay
available. The goal of the suite is a rough ranking between models, so a correct answer counts however
it is written, and only answers that cannot be read at all are treated as a separate failure.

- `mmlu_pro_flexible` (new): the option letter read from a bare letter, `(H).`, `Answer: B`, JSON
  (`answer`, `final_answer`, `result`, `option` or `choice` keys, fenced or not), or a closing line that
  names exactly one option. Strict `mmlu_pro_exact_match_custom-extract` only accepts "The answer is (X)".
- JSON answers inside markdown fences are read by every flexible scorer, and the `option`/`choice` keys
  are accepted alongside `answer`.
- Unreadable counts: every flexible row's `extractor_failure_count` is now the number of answers that could
  not be read at all (empty, cut off, a bare JSON opener or fence, no option or number anywhere). Notes say
  `rescued N; unreadable M`, where rescued is the strict misses the flexible reading credited. Before v5
  that field held the rescued count. A high unreadable count flags a model whose output defeats the
  scorer (for example phi-4:14b DROP, 10 of 10 truncated JSON) rather than one that answered wrong.
- `gsm8k_flexible` is lm-eval's own flexible extract, unchanged, but now carries the unreadable count.
- mmlu_pro and gsm8k always run with `--log_samples`, like bbh and drop.
- Past runs were re-scored from their logged samples by `scripts/active/rescore_reasoning_records.py`.
  The new rows keep the original run time, suite and run class, and have `rescored_from_samples` in
  their config. Runs from before MMLU-Pro samples were logged have no `mmlu_pro_flexible` row.
- Why: Phase 4 smokes on 2026-10-20 showed models that answer well but in their own format scored near
  zero: ministral-3:14b bbh 0.022 strict vs 0.370 flexible and MMLU-Pro 0.429 vs 0.657 (JSON answers),
  devstral-small:24b MMLU-Pro 0.186 vs 0.521 (bare letters), gpt-oss:20b DROP 0 vs 0.9
  ("So the answer is ..." with a fuller span). Tuning prompts to the extractor was optimizing for the
  test, not for the work.

## 2026-10-16 BBH Output Budget (extract v4)

Rows from this point carry `config_id` `lm-eval-0.4.11-reasoning-extract-v4`. BBH keeps the template's
`max_gen_toks: 1024` instead of the harness cutting it to 512. A/B on nex-n2.5:mini (limit 10,
`nex_n25_mini_smoke_v1_x3` at 512 vs `nex_n25_mini_p45_bbh1024` at 1024): strict 0.752 -> 0.763,
flexible 0.807 -> 0.837; 3 strict answers gained (dyck_languages, word_sorting), none lost; peak VRAM
21275 -> 21317 MiB, so the old OOM rationale does not hold (llama-server sizes memory by ctx_size).
Long chain-of-thought tasks were being cut before the answer for every model tested.

## 2026-10-16 Scoring Changes (extract v3)

Rows recorded from this date carry `config_id` `lm-eval-0.4.11-reasoning-extract-v3`
(earlier: `-v2`). The comparison group is unchanged.

- Flexible rows beside the strict ones, scored from logged samples by
  `scripts/active/extract_reasoning_results.py`:
  - `bbh_flexible`: correct final answer without the demonstrated "So the answer is" phrase
    (bare option, `Answer: X`, JSON `answer` field, or a final line naming exactly one option).
  - `drop_flexible`: the response contains every span of a gold answer after normalization
    (lead-ins, fuller sentences and spelled-out numbers up to twenty accepted).
  - IFEval stays strict: its prompts instruct the format. Strict `bbh`, `drop_em`, `drop_f1` are unchanged.
  - bbh and drop always run with `--log_samples` so these rows can be scored.
- BBH stop sequence `"Q"` -> `"\nQ:"`. The bare `Q` stop cut any output at a capital Q, so answers like
  `(Q)` in reasoning_about_colored_objects (options run to R) could never be produced, and reasoning with
  words like "Queen" was truncated. This can raise strict BBH slightly versus extract-v2 rows.
- Why: limit-10 smokes of qwen3.8:27b, ornith-1.5:35b-a3b and nex-n2.5:mini showed correct answers
  failing on phrasing (for example DROP "So the answer is 3", BBH `{"answer": "(C)"}`), which pushed
  prompt tuning toward the extractor instead of better answers. See NEW_MODEL_INTEGRATION.md (2026-10-16).

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
