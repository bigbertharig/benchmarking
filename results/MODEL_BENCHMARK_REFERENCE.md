# Model Benchmark Reference

- Generated at: `2026-06-07T21:47:58.209531`
- Records file: `/mnt/shared/plans/shoulders/benchmarking/results/model_benchmark_records.jsonl`
- Status file: `/benchmark-scripts/benchmark_status.json`
- Total recorded runs: `835`

## Operational Status

This section tracks current benchmarkability and backend certification status.

### Runtime Issues

| Subject | State | Last Observed | Notes |
| --- | --- | --- | --- |
| lighteval math dependency pin | warning | 2026-03-05T20:41:00 | Installing math benchmark extras upgraded `latex2sympy2_extended` to 1.11.0, which conflicts with the current `lighteval 0.13.0` pin expecting 1.0.6. lm-eval math tasks now work, but lighteval should be revalidated before use. |
| lm_eval API benchmark environment | resolved | 2026-03-05T20:05:00 | tenacity was installed into ~/ml-env, clearing the earlier lm_eval API dependency blocker. |
| qwen2.5:14b on pair_4_5 | split_blocked | 2026-03-05T00:00:00 | Split warmup failed repeatedly on pair_4_5 and no stable 11441 runtime remained. |
| qwen3.5:4b | blocked | 2026-03-05T00:00:00 | Present in inventory but worker loads and direct runtime probes failed. Not currently benchmarkable on this stack. |
| qwen3.5:9b | blocked | 2026-03-05T00:00:00 | Same failure class as qwen3.5:4b after re-import and direct runtime probes. |

### Backend/Test Certification

| Backend | Test ID | State | Probe Model | Last Observed | Notes |
| --- | --- | --- | --- | --- | --- |
| llama_chat_completions_raw | gsm8k | blocked | qwen2.5-coder:7b | 2026-03-05T20:08:07 | LocalChatCompletion expects messages as list[dict]. Raw chat-completions needs apply_chat_template for these generation tasks. |
| llama_chat_completions_templated | gsm8k | supported | qwen2.5-coder:7b | 2026-03-05T20:23:52 | Probe run completed successfully. |
| llama_chat_completions_templated | drop | supported | qwen2.5-coder:7b | 2026-03-05T20:24:20 | Probe run completed successfully. |
| llama_chat_completions_templated | bbh | supported | qwen2.5-coder:7b | 2026-03-05T20:32:28 | Probe run completed successfully. |
| llama_chat_completions_templated | musr | blocked | mistral:7b-instruct | 2026-03-05T20:36:28 | lm-eval task 'musr' is not available in this environment. Run `python3 -m lm_eval --tasks list` to inspect installed task names. |
| llama_chat_completions_templated | aime_2024 | supported | mistral:7b-instruct | 2026-03-05T20:41:41 | Probe run completed successfully. |
| llama_chat_completions_templated | math_500 | supported | qwen2.5-coder:7b | 2026-03-05T20:43:38 | Probe run completed successfully. |
| llama_chat_completions_templated | gpqa_diamond | env_blocked | qwen2.5:7b | 2026-03-05T20:48:28 | datasets.exceptions.DatasetNotFoundError: Dataset 'Idavidrein/gpqa' is a gated dataset on the Hub. You must be authenticated to access it. |
| llama_completions | boolq | blocked | qwen2.5:7b | 2026-03-05T00:00:00 | Current llama-compatible completions lane still rejects the lm_eval prompt array shape for loglikelihood tasks. Use the gguf/container lane instead. |
| llama_completions | arc_challenge | blocked | qwen2.5:7b | 2026-03-05T20:11:20 | 2026-03-05:20:11:19 WARNING  [models.api_models:479] API request failed with error message: {"error":{"message":"json: cannot unmarshal array into Go struct field CompletionRequest.prompt of type string","type":"invalid_request_error","param":null,"code":null}}. Retrying... |
| llama_completions | piqa | blocked | mistral:7b-instruct | 2026-03-05T20:27:48 | 2026-03-05:20:27:48 WARNING  [models.api_models:479] API request failed with error message: {"error":{"message":"json: cannot unmarshal array into Go struct field CompletionRequest.prompt of type string","type":"invalid_request_error","param":null,"code":null}}. Retrying... |
| llama_completions | winogrande | blocked | qwen2.5-coder:7b | 2026-03-05T20:34:05 | 2026-03-05:20:34:04 WARNING  [models.api_models:479] API request failed with error message: {"error":{"message":"json: cannot unmarshal array into Go struct field CompletionRequest.prompt of type string","type":"invalid_request_error","param":null,"code":null}}. Retrying... |
| llama_completions | hellaswag | blocked | qwen2.5:7b | 2026-03-05T20:34:15 | 2026-03-05:20:34:14 WARNING  [models.api_models:479] API request failed with error message: {"error":{"message":"json: cannot unmarshal array into Go struct field CompletionRequest.prompt of type string","type":"invalid_request_error","param":null,"code":null}}. Retrying... |
| llama_completions | mmlu | blocked | mistral:7b-instruct | 2026-03-05T20:34:42 | 2026-03-05:20:34:41 WARNING  [models.api_models:479] API request failed with error message: {"error":{"message":"json: cannot unmarshal array into Go struct field CompletionRequest.prompt of type string","type":"invalid_request_error","param":null,"code":null}}. Retrying... |
| llama_completions | truthfulqa_mc2 | blocked | mistral:7b-instruct | 2026-03-05T20:35:17 | 2026-03-05:20:35:16 WARNING  [models.api_models:479] API request failed with error message: {"error":{"message":"json: cannot unmarshal array into Go struct field CompletionRequest.prompt of type string","type":"invalid_request_error","param":null,"code":null}}. Retrying... |
| llama_cpp_gguf | boolq | blocked | qwen2.5-coder:32b | 2026-03-06T14:38:03 | Historical gguf certification attempt captured a limit-warning path instead of a clean support verdict. Re-run certification on the current llama.cpp container lane. |

### Task Runtime Notes

| Test ID | Runtime Class | Last Observed | Notes |
| --- | --- | --- | --- |
| aime_2024 | quick_probe | 2026-03-05T20:41:41 | Runs cleanly as a short templated-chat generation probe once the harness alias is mapped to `aime24`. |
| bbh | slow_probe | 2026-03-05T20:32:28 | Can run successfully on templated chat, but long enough to wedge broad audit batches if mixed with many other probes. Keep it in a smaller chunk. |
| gpqa_diamond | gated_dataset | 2026-03-05T20:43:00 | Task name resolves after aliasing, but the upstream dataset is gated on Hugging Face. Treat this as blocked by access, not by model runtime. |
| math_500 | extra_packages_required | 2026-03-05T20:43:38 | Requires math extras (`math_verify`, `sympy`, `antlr4-python3-runtime==4.11`) before the probe can run. After install, the task is supported. |
| mmlu | slow_setup | 2026-03-05T20:34:42 | Group task expands across many subjects before first request. Use as a deliberate longer audit, not a quick smoke probe. |
| mmmlu | very_slow_group | 2026-03-05T20:45:00 | Full MMMLU group expansion is too slow for quick certification runs. Expect roughly 20 to 30 minutes before the first real results or first failures. Use a representative subject for backend certification and reserve the full grouped task for dedicated benchmark runs. |

## Latest Score Per Model/Test

| Model | Test ID | Score | Score % | Metric | Last Tested | Harness | Suite |
| --- | --- | --- | --- | --- | --- | --- | --- |
| DeepSeek-R1-Distill-Qwen-14B-Q4_K_M.gguf | drop_em | 0.0 | 0.0 | em,none | 2026-03-17T01:08:31+00:00 | bench-reasoning | bench-reasoning_DeepSeek-R1-Distill-Qwen-14B-Q4_K_M.gguf_reasoning_deepseek14b_v6_workerprompt |
| DeepSeek-R1-Distill-Qwen-14B-Q4_K_M.gguf | drop_f1 | 0.082 | 8.200000000000001 | f1,none | 2026-03-17T01:08:31+00:00 | bench-reasoning | bench-reasoning_DeepSeek-R1-Distill-Qwen-14B-Q4_K_M.gguf_reasoning_deepseek14b_v6_workerprompt |
| DeepSeek-R1-Distill-Qwen-14B-Q4_K_M.gguf | gsm8k_flexible | 0.0 | 0.0 | exact_match,flexible-extract | 2026-03-17T01:06:22+00:00 | bench-reasoning | bench-reasoning_DeepSeek-R1-Distill-Qwen-14B-Q4_K_M.gguf_reasoning_deepseek14b_v6_workerprompt |
| DeepSeek-R1-Distill-Qwen-14B-Q4_K_M.gguf | gsm8k_strict | 0.0 | 0.0 | exact_match,strict-match | 2026-03-17T01:06:22+00:00 | bench-reasoning | bench-reasoning_DeepSeek-R1-Distill-Qwen-14B-Q4_K_M.gguf_reasoning_deepseek14b_v6_workerprompt |
| DeepSeek-R1-Distill-Qwen-7B-Q4_K_M.gguf | bbh | 0.0 | 0.0 | exact_match,get-answer | 2026-03-12T12:04:41+00:00 | bench-reasoning | bench-reasoning_DeepSeek-R1-Distill-Qwen-7B-Q4_K_M.gguf_rr_l100_ctx8k_parallel_reasoning_l100_ctx8k_20260312_021803_p11439 |
| DeepSeek-R1-Distill-Qwen-7B-Q4_K_M.gguf | drop_em | 0.0 | 0.0 | em,none | 2026-03-12T12:08:11+00:00 | bench-reasoning | bench-reasoning_DeepSeek-R1-Distill-Qwen-7B-Q4_K_M.gguf_rr_l100_ctx8k_parallel_reasoning_l100_ctx8k_20260312_021803_p11439 |
| DeepSeek-R1-Distill-Qwen-7B-Q4_K_M.gguf | drop_f1 | 0.0 | 0.0 | f1,none | 2026-03-12T12:08:11+00:00 | bench-reasoning | bench-reasoning_DeepSeek-R1-Distill-Qwen-7B-Q4_K_M.gguf_rr_l100_ctx8k_parallel_reasoning_l100_ctx8k_20260312_021803_p11439 |
| DeepSeek-R1-Distill-Qwen-7B-Q4_K_M.gguf | gsm8k_flexible | 0.38 | 38.0 | exact_match,flexible-extract | 2026-03-12T09:44:14+00:00 | bench-reasoning | bench-reasoning_DeepSeek-R1-Distill-Qwen-7B-Q4_K_M.gguf_rr_l100_ctx8k_parallel_reasoning_l100_ctx8k_20260312_021803_p11439 |
| DeepSeek-R1-Distill-Qwen-7B-Q4_K_M.gguf | gsm8k_strict | 0.3 | 30.0 | exact_match,strict-match | 2026-03-12T09:44:14+00:00 | bench-reasoning | bench-reasoning_DeepSeek-R1-Distill-Qwen-7B-Q4_K_M.gguf_rr_l100_ctx8k_parallel_reasoning_l100_ctx8k_20260312_021803_p11439 |
| Llama-3.2-3B-Instruct-Q4_K_M.gguf | bbh | 0.5888888888888889 | 58.88888888888889 | exact_match,get-answer | 2026-03-17T06:00:00+00:00 | bench-reasoning | bench-reasoning_Llama-3.2-3B-Instruct-Q4_K_M.gguf_reasoning_llama32_3b_l10_promptv2 |
| Llama-3.2-3B-Instruct-Q4_K_M.gguf | drop_em | 0.2 | 20.0 | em,none | 2026-03-17T06:00:31+00:00 | bench-reasoning | bench-reasoning_Llama-3.2-3B-Instruct-Q4_K_M.gguf_reasoning_llama32_3b_l10_promptv2 |
| Llama-3.2-3B-Instruct-Q4_K_M.gguf | drop_f1 | 0.5269999999999999 | 52.69999999999999 | f1,none | 2026-03-17T06:00:31+00:00 | bench-reasoning | bench-reasoning_Llama-3.2-3B-Instruct-Q4_K_M.gguf_reasoning_llama32_3b_l10_promptv2 |
| Llama-3.2-3B-Instruct-Q4_K_M.gguf | gsm8k_flexible | 0.7 | 70.0 | exact_match,flexible-extract | 2026-03-17T05:34:29+00:00 | bench-reasoning | bench-reasoning_Llama-3.2-3B-Instruct-Q4_K_M.gguf_reasoning_llama32_3b_l10_promptv2 |
| Llama-3.2-3B-Instruct-Q4_K_M.gguf | gsm8k_strict | 0.7 | 70.0 | exact_match,strict-match | 2026-03-17T05:34:29+00:00 | bench-reasoning | bench-reasoning_Llama-3.2-3B-Instruct-Q4_K_M.gguf_reasoning_llama32_3b_l10_promptv2 |
| Mistral-7B-Instruct-v0.3-Q4_K_M.gguf | bench_code_total_base | 0.481549815498155 | 48.1549815498155 | pass_rate_542_base | 2026-03-11T19:23:09+00:00 | bench-code | code_full_20260310_202111_partial2 |
| Mistral-7B-Instruct-v0.3-Q4_K_M.gguf | bench_code_total_plus | 0.4077490774907749 | 40.774907749077485 | pass_rate_542_plus | 2026-03-11T19:23:09+00:00 | bench-code | code_full_20260310_202111_partial2 |
| Mistral-7B-Instruct-v0.3-Q4_K_M.gguf | custom_worker_suite_total | 0.6835443037974683 | 68.35443037974683 | pass_rate_79 | 2026-03-11T06:47:32+00:00 | bench-pipeline | recovery_ckpt_hot5_20260310_partial3 |
| Mistral-7B-Instruct-v0.3-Q4_K_M.gguf | gsm8k_flexible | 0.48 | 48.0 | exact_match,flexible-extract | 2026-03-12T09:38:26+00:00 | bench-reasoning | bench-reasoning_Mistral-7B-Instruct-v0.3-Q4_K_M.gguf_rr_l100_ctx8k_parallel_reasoning_l100_ctx8k_20260312_021803_p11437 |
| Mistral-7B-Instruct-v0.3-Q4_K_M.gguf | gsm8k_strict | 0.48 | 48.0 | exact_match,strict-match | 2026-03-12T09:38:26+00:00 | bench-reasoning | bench-reasoning_Mistral-7B-Instruct-v0.3-Q4_K_M.gguf_rr_l100_ctx8k_parallel_reasoning_l100_ctx8k_20260312_021803_p11437 |
| Phi-4-mini-instruct-Q4_K_M.gguf | bbh | 0.5777777777777777 | 57.77777777777777 | exact_match,get-answer | 2026-03-17T06:05:07+00:00 | bench-reasoning | bench-reasoning_Phi-4-mini-instruct-Q4_K_M.gguf_reasoning_phi4mini_3p8b_l10_promptv2 |
| Phi-4-mini-instruct-Q4_K_M.gguf | drop_em | 0.1 | 10.0 | em,none | 2026-03-17T06:05:39+00:00 | bench-reasoning | bench-reasoning_Phi-4-mini-instruct-Q4_K_M.gguf_reasoning_phi4mini_3p8b_l10_promptv2 |
| Phi-4-mini-instruct-Q4_K_M.gguf | drop_f1 | 0.275 | 27.500000000000004 | f1,none | 2026-03-17T06:05:39+00:00 | bench-reasoning | bench-reasoning_Phi-4-mini-instruct-Q4_K_M.gguf_reasoning_phi4mini_3p8b_l10_promptv2 |
| Phi-4-mini-instruct-Q4_K_M.gguf | gsm8k_flexible | 0.7 | 70.0 | exact_match,flexible-extract | 2026-03-17T05:34:50+00:00 | bench-reasoning | bench-reasoning_Phi-4-mini-instruct-Q4_K_M.gguf_reasoning_phi4mini_3p8b_l10_promptv2 |
| Phi-4-mini-instruct-Q4_K_M.gguf | gsm8k_strict | 0.7 | 70.0 | exact_match,strict-match | 2026-03-17T05:34:50+00:00 | bench-reasoning | bench-reasoning_Phi-4-mini-instruct-Q4_K_M.gguf_reasoning_phi4mini_3p8b_l10_promptv2 |
| Qwen2.5-Coder-7B-Instruct-Q4_K_M.gguf | custom_worker_suite_total | 0.7341772151898734 | 73.41772151898735 | pass_rate_79 | 2026-03-11T06:44:32+00:00 | bench-pipeline | recovery_ckpt_hot5_20260310_partial3 |
| Qwen2.5-Coder-7B-Instruct-Q4_K_M.gguf | gsm8k_flexible | 0.78 | 78.0 | exact_match,flexible-extract | 2026-03-12T09:32:56+00:00 | bench-reasoning | bench-reasoning_Qwen2.5-Coder-7B-Instruct-Q4_K_M.gguf_rr_l100_ctx8k_parallel_reasoning_l100_ctx8k_20260312_021803_p11438 |
| Qwen2.5-Coder-7B-Instruct-Q4_K_M.gguf | gsm8k_strict | 0.75 | 75.0 | exact_match,strict-match | 2026-03-12T09:32:56+00:00 | bench-reasoning | bench-reasoning_Qwen2.5-Coder-7B-Instruct-Q4_K_M.gguf_rr_l100_ctx8k_parallel_reasoning_l100_ctx8k_20260312_021803_p11438 |
| Qwen3-1.7B-Q4_K_M.gguf | bbh | 0.0 | 0.0 | exact_match,get-answer | 2026-03-17T05:38:22+00:00 | bench-reasoning | bench-reasoning_Qwen3-1.7B-Q4_K_M.gguf_reasoning_qwen3_1p7b_l10_promptv2 |
| Qwen3-1.7B-Q4_K_M.gguf | drop_em | 0.0 | 0.0 | em,none | 2026-03-17T05:39:01+00:00 | bench-reasoning | bench-reasoning_Qwen3-1.7B-Q4_K_M.gguf_reasoning_qwen3_1p7b_l10_promptv2 |
| Qwen3-1.7B-Q4_K_M.gguf | drop_f1 | 0.36100000000000004 | 36.1 | f1,none | 2026-03-17T05:39:01+00:00 | bench-reasoning | bench-reasoning_Qwen3-1.7B-Q4_K_M.gguf_reasoning_qwen3_1p7b_l10_promptv2 |
| Qwen3-1.7B-Q4_K_M.gguf | gsm8k_flexible | 0.5 | 50.0 | exact_match,flexible-extract | 2026-03-17T05:26:06+00:00 | bench-reasoning | bench-reasoning_Qwen3-1.7B-Q4_K_M.gguf_reasoning_qwen3_1p7b_l10_promptv2 |
| Qwen3-1.7B-Q4_K_M.gguf | gsm8k_strict | 0.5 | 50.0 | exact_match,strict-match | 2026-03-17T05:26:06+00:00 | bench-reasoning | bench-reasoning_Qwen3-1.7B-Q4_K_M.gguf_reasoning_qwen3_1p7b_l10_promptv2 |
| Qwen3.5-4B-Q4_K_M.gguf | bench_code_total_base | 0.5719557195571956 | 57.19557195571956 | pass_rate_542_base | 2026-03-11T21:41:09+00:00 | bench-code | code_full_20260310_202111_partial2 |
| Qwen3.5-4B-Q4_K_M.gguf | bench_code_total_plus | 0.5018450184501845 | 50.184501845018445 | pass_rate_542_plus | 2026-03-11T21:41:09+00:00 | bench-code | code_full_20260310_202111_partial2 |
| Qwen3.5-4B-Q4_K_M.gguf | custom_worker_suite_total | 0.6835443037974683 | 68.35443037974683 | pass_rate_79 | 2026-03-11T07:09:52+00:00 | bench-pipeline | recovery_ckpt_hot5_20260310_partial3 |
| Qwen3.5-9B-Q3_K_M.gguf | bbh | 0.0 | 0.0 | exact_match,get-answer | 2026-03-12T12:10:58+00:00 | bench-reasoning | bench-reasoning_Qwen3.5-9B-Q3_K_M.gguf_rr_l100_ctx8k_parallel_reasoning_l100_ctx8k_20260312_021803_p11435 |
| Qwen3.5-9B-Q3_K_M.gguf | custom_worker_suite_total | 0.08860759493670886 | 8.860759493670885 | pass_rate_79 | 2026-03-11T01:46:21+00:00 | bench-pipeline | ab_prompt_B_20260310 |
| Qwen3.5-9B-Q3_K_M.gguf | drop_em | 0.0 | 0.0 | em,none | 2026-03-12T12:13:46+00:00 | bench-reasoning | bench-reasoning_Qwen3.5-9B-Q3_K_M.gguf_rr_l100_ctx8k_parallel_reasoning_l100_ctx8k_20260312_021803_p11435 |
| Qwen3.5-9B-Q3_K_M.gguf | drop_f1 | 0.0 | 0.0 | f1,none | 2026-03-12T12:13:46+00:00 | bench-reasoning | bench-reasoning_Qwen3.5-9B-Q3_K_M.gguf_rr_l100_ctx8k_parallel_reasoning_l100_ctx8k_20260312_021803_p11435 |
| Qwen3.5-9B-Q3_K_M.gguf | gsm8k_flexible | 0.0 | 0.0 | exact_match,flexible-extract | 2026-03-12T09:56:46+00:00 | bench-reasoning | bench-reasoning_Qwen3.5-9B-Q3_K_M.gguf_rr_l100_ctx8k_parallel_reasoning_l100_ctx8k_20260312_021803_p11435 |
| Qwen3.5-9B-Q3_K_M.gguf | gsm8k_strict | 0.0 | 0.0 | exact_match,strict-match | 2026-03-12T09:56:46+00:00 | bench-reasoning | bench-reasoning_Qwen3.5-9B-Q3_K_M.gguf_rr_l100_ctx8k_parallel_reasoning_l100_ctx8k_20260312_021803_p11435 |
| SmolLM3-3B-Q4_K_M.gguf | bbh | 0.6222222222222222 | 62.22222222222222 | exact_match,get-answer | 2026-03-17T06:00:32+00:00 | bench-reasoning | bench-reasoning_SmolLM3-3B-Q4_K_M.gguf_reasoning_smollm3_3b_l10_promptv2 |
| SmolLM3-3B-Q4_K_M.gguf | drop_em | 0.0 | 0.0 | em,none | 2026-03-17T06:01:03+00:00 | bench-reasoning | bench-reasoning_SmolLM3-3B-Q4_K_M.gguf_reasoning_smollm3_3b_l10_promptv2 |
| SmolLM3-3B-Q4_K_M.gguf | drop_f1 | 0.23500000000000001 | 23.5 | f1,none | 2026-03-17T06:01:03+00:00 | bench-reasoning | bench-reasoning_SmolLM3-3B-Q4_K_M.gguf_reasoning_smollm3_3b_l10_promptv2 |
| SmolLM3-3B-Q4_K_M.gguf | gsm8k_flexible | 0.6 | 60.0 | exact_match,flexible-extract | 2026-03-17T05:34:31+00:00 | bench-reasoning | bench-reasoning_SmolLM3-3B-Q4_K_M.gguf_reasoning_smollm3_3b_l10_promptv2 |
| SmolLM3-3B-Q4_K_M.gguf | gsm8k_strict | 0.6 | 60.0 | exact_match,strict-match | 2026-03-17T05:34:31+00:00 | bench-reasoning | bench-reasoning_SmolLM3-3B-Q4_K_M.gguf_reasoning_smollm3_3b_l10_promptv2 |
| deepseek-r1:14b | bbh | 0.5851851851851851 | 58.51851851851851 | exact_match,get-answer | 2026-03-16T21:59:53+00:00 | bench-reasoning | bench-reasoning_deepseek-r1_14b_reasoning_dsr1_14b_thinkstrip_smoke_v2 |
| deepseek-r1:14b | drop_em | 0.0 | 0.0 | em,none | 2026-03-16T22:00:28+00:00 | bench-reasoning | bench-reasoning_deepseek-r1_14b_reasoning_dsr1_14b_thinkstrip_smoke_v2 |
| deepseek-r1:14b | drop_f1 | 0.0 | 0.0 | f1,none | 2026-03-16T22:00:28+00:00 | bench-reasoning | bench-reasoning_deepseek-r1_14b_reasoning_dsr1_14b_thinkstrip_smoke_v2 |
| deepseek-r1:14b | gsm8k_flexible | 0.2 | 20.0 | exact_match,flexible-extract | 2026-03-16T20:14:15+00:00 | bench-reasoning | bench-reasoning_deepseek-r1_14b_reasoning_dsr1_14b_thinkstrip_smoke_v2 |
| deepseek-r1:14b | gsm8k_strict | 0.0 | 0.0 | exact_match,strict-match | 2026-03-16T20:14:15+00:00 | bench-reasoning | bench-reasoning_deepseek-r1_14b_reasoning_dsr1_14b_thinkstrip_smoke_v2 |
| deepseek-r1:32b | bbh | 0.0 | 0.0 | exact_match,get-answer | 2026-03-15T02:11:49+00:00 | bench-reasoning | bench-reasoning_deepseek-r1_32b_reasoning_r1_32b_smoke_v1 |
| deepseek-r1:32b | drop_em | 0.0 | 0.0 | em,none | 2026-03-15T02:12:49+00:00 | bench-reasoning | bench-reasoning_deepseek-r1_32b_reasoning_r1_32b_smoke_v1 |
| deepseek-r1:32b | drop_f1 | 0.0 | 0.0 | f1,none | 2026-03-15T02:12:49+00:00 | bench-reasoning | bench-reasoning_deepseek-r1_32b_reasoning_r1_32b_smoke_v1 |
| deepseek-r1:32b | gsm8k_flexible | 0.8 | 80.0 | exact_match,flexible-extract | 2026-03-15T02:07:01+00:00 | bench-reasoning | bench-reasoning_deepseek-r1_32b_reasoning_r1_32b_smoke_v1 |
| deepseek-r1:32b | gsm8k_strict | 0.2 | 20.0 | exact_match,strict-match | 2026-03-15T02:07:01+00:00 | bench-reasoning | bench-reasoning_deepseek-r1_32b_reasoning_r1_32b_smoke_v1 |
| deepseek-r1:7b | daedalmap_catalog_discipline_json_valid_rate | 0.4666666666666667 | 46.666666666666664 | json_valid_rate | 2026-03-21T03:43:40+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_deepseek-r1_7b |
| deepseek-r1:7b | daedalmap_catalog_discipline_no_halluc_rate | 0.6666666666666666 | 66.66666666666666 | no_halluc_rate | 2026-03-21T03:43:40+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_deepseek-r1_7b |
| deepseek-r1:7b | daedalmap_catalog_discipline_pass_rate | 0.13333333333333333 | 13.333333333333334 | pass_rate | 2026-03-21T03:43:40+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_deepseek-r1_7b |
| deepseek-r1:7b | daedalmap_catalog_discipline_type_correct_rate | 0.4 | 40.0 | type_correct_rate | 2026-03-21T03:43:40+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_deepseek-r1_7b |
| deepseek-r1:7b | daedalmap_geographic_precision_json_valid_rate | 0.4 | 40.0 | json_valid_rate | 2026-03-21T03:47:48+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_deepseek-r1_7b |
| deepseek-r1:7b | daedalmap_geographic_precision_no_halluc_rate | 1.0 | 100.0 | no_halluc_rate | 2026-03-21T03:47:49+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_deepseek-r1_7b |
| deepseek-r1:7b | daedalmap_geographic_precision_pass_rate | 0.26666666666666666 | 26.666666666666668 | pass_rate | 2026-03-21T03:47:48+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_deepseek-r1_7b |
| deepseek-r1:7b | daedalmap_geographic_precision_source_hit_rate | 0.8 | 80.0 | source_hit_rate | 2026-03-21T03:47:49+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_deepseek-r1_7b |
| deepseek-r1:7b | daedalmap_geographic_precision_source_valid_rate | 0.8 | 80.0 | source_valid_rate | 2026-03-21T03:47:49+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_deepseek-r1_7b |
| deepseek-r1:7b | daedalmap_geographic_precision_type_correct_rate | 0.3333333333333333 | 33.33333333333333 | type_correct_rate | 2026-03-21T03:47:49+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_deepseek-r1_7b |
| deepseek-r1:7b | daedalmap_json_discipline_json_valid_rate | 0.4666666666666667 | 46.666666666666664 | json_valid_rate | 2026-03-21T03:51:47+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_deepseek-r1_7b |
| deepseek-r1:7b | daedalmap_json_discipline_no_halluc_rate | 1.0 | 100.0 | no_halluc_rate | 2026-03-21T03:51:48+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_deepseek-r1_7b |
| deepseek-r1:7b | daedalmap_json_discipline_pass_rate | 0.3333333333333333 | 33.33333333333333 | pass_rate | 2026-03-21T03:51:47+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_deepseek-r1_7b |
| deepseek-r1:7b | daedalmap_json_discipline_source_hit_rate | 0.6666666666666666 | 66.66666666666666 | source_hit_rate | 2026-03-21T03:51:48+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_deepseek-r1_7b |
| deepseek-r1:7b | daedalmap_json_discipline_source_valid_rate | 0.6666666666666666 | 66.66666666666666 | source_valid_rate | 2026-03-21T03:51:48+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_deepseek-r1_7b |
| deepseek-r1:7b | daedalmap_json_discipline_type_correct_rate | 0.4 | 40.0 | type_correct_rate | 2026-03-21T03:51:48+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_deepseek-r1_7b |
| deepseek-r1:7b | daedalmap_multi_source_json_valid_rate | 0.2 | 20.0 | json_valid_rate | 2026-03-21T03:56:02+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_deepseek-r1_7b |
| deepseek-r1:7b | daedalmap_multi_source_no_halluc_rate | 1.0 | 100.0 | no_halluc_rate | 2026-03-21T03:56:02+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_deepseek-r1_7b |
| deepseek-r1:7b | daedalmap_multi_source_pass_rate | 0.13333333333333333 | 13.333333333333334 | pass_rate | 2026-03-21T03:56:02+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_deepseek-r1_7b |
| deepseek-r1:7b | daedalmap_multi_source_source_hit_rate | 0.6666666666666666 | 66.66666666666666 | source_hit_rate | 2026-03-21T03:56:03+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_deepseek-r1_7b |
| deepseek-r1:7b | daedalmap_multi_source_source_valid_rate | 0.6666666666666666 | 66.66666666666666 | source_valid_rate | 2026-03-21T03:56:03+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_deepseek-r1_7b |
| deepseek-r1:7b | daedalmap_multi_source_type_correct_rate | 0.2 | 20.0 | type_correct_rate | 2026-03-21T03:56:02+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_deepseek-r1_7b |
| deepseek-r1:7b | daedalmap_source_grounding_json_valid_rate | 0.35 | 35.0 | json_valid_rate | 2026-03-21T04:01:51+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_deepseek-r1_7b |
| deepseek-r1:7b | daedalmap_source_grounding_no_halluc_rate | 1.0 | 100.0 | no_halluc_rate | 2026-03-21T04:01:51+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_deepseek-r1_7b |
| deepseek-r1:7b | daedalmap_source_grounding_pass_rate | 0.3 | 30.0 | pass_rate | 2026-03-21T04:01:51+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_deepseek-r1_7b |
| deepseek-r1:7b | daedalmap_source_grounding_source_hit_rate | 1.0 | 100.0 | source_hit_rate | 2026-03-21T04:01:51+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_deepseek-r1_7b |
| deepseek-r1:7b | daedalmap_source_grounding_source_valid_rate | 1.0 | 100.0 | source_valid_rate | 2026-03-21T04:01:51+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_deepseek-r1_7b |
| deepseek-r1:7b | daedalmap_source_grounding_type_correct_rate | 0.3 | 30.0 | type_correct_rate | 2026-03-21T04:01:51+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_deepseek-r1_7b |
| deepseek-r1:7b | daedalmap_type_routing_json_valid_rate | 0.5 | 50.0 | json_valid_rate | 2026-03-21T04:07:02+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_deepseek-r1_7b |
| deepseek-r1:7b | daedalmap_type_routing_no_halluc_rate | 0.95 | 95.0 | no_halluc_rate | 2026-03-21T04:07:02+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_deepseek-r1_7b |
| deepseek-r1:7b | daedalmap_type_routing_pass_rate | 0.35 | 35.0 | pass_rate | 2026-03-21T04:07:02+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_deepseek-r1_7b |
| deepseek-r1:7b | daedalmap_type_routing_source_hit_rate | 1.0 | 100.0 | source_hit_rate | 2026-03-21T04:07:02+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_deepseek-r1_7b |
| deepseek-r1:7b | daedalmap_type_routing_source_valid_rate | 1.0 | 100.0 | source_valid_rate | 2026-03-21T04:07:02+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_deepseek-r1_7b |
| deepseek-r1:7b | daedalmap_type_routing_type_correct_rate | 0.35 | 35.0 | type_correct_rate | 2026-03-21T04:07:02+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_deepseek-r1_7b |
| deepseek-r1:7b | gsm8k_flexible | 0.09 | 9.0 | exact_match,flexible-extract | 2026-03-12T05:42:46+00:00 | bench-reasoning | bench-reasoning_deepseek-r1_7b_rr_l100_c05_20260311_221559_p11437 |
| deepseek-r1:7b | gsm8k_strict | 0.0 | 0.0 | exact_match,strict-match | 2026-03-12T05:42:46+00:00 | bench-reasoning | bench-reasoning_deepseek-r1_7b_rr_l100_c05_20260311_221559_p11437 |
| gemma-3-4b-it-Q4_K_M.gguf | bbh | 0.5481481481481482 | 54.81481481481482 | exact_match,get-answer | 2026-03-17T02:37:46+00:00 | bench-reasoning | bench-reasoning_gemma-3-4b-it-Q4_K_M.gguf_reasoning_gemma3-4b_smoke_v1 |
| gemma-3-4b-it-Q4_K_M.gguf | drop_em | 0.2 | 20.0 | em,none | 2026-03-17T02:38:19+00:00 | bench-reasoning | bench-reasoning_gemma-3-4b-it-Q4_K_M.gguf_reasoning_gemma3-4b_smoke_v1 |
| gemma-3-4b-it-Q4_K_M.gguf | drop_f1 | 0.266 | 26.6 | f1,none | 2026-03-17T02:38:19+00:00 | bench-reasoning | bench-reasoning_gemma-3-4b-it-Q4_K_M.gguf_reasoning_gemma3-4b_smoke_v1 |
| gemma-3-4b-it-Q4_K_M.gguf | gsm8k_flexible | 0.7 | 70.0 | exact_match,flexible-extract | 2026-03-17T05:34:54+00:00 | bench-reasoning | bench-reasoning_gemma-3-4b-it-Q4_K_M.gguf_reasoning_gemma3_4b_l10_promptv2 |
| gemma-3-4b-it-Q4_K_M.gguf | gsm8k_strict | 0.7 | 70.0 | exact_match,strict-match | 2026-03-17T05:34:54+00:00 | bench-reasoning | bench-reasoning_gemma-3-4b-it-Q4_K_M.gguf_reasoning_gemma3_4b_l10_promptv2 |
| gemma-3:12b | gsm8k_flexible | 0.6 | 60.0 | exact_match,flexible-extract | 2026-03-14T23:43:27+00:00 | bench-reasoning | bench-reasoning_gemma-3_12b_reasoning_gemma3_smoke_v1 |
| gemma-3:12b | gsm8k_strict | 0.6 | 60.0 | exact_match,strict-match | 2026-03-14T23:43:27+00:00 | bench-reasoning | bench-reasoning_gemma-3_12b_reasoning_gemma3_smoke_v1 |
| gemma-3:4b | daedalmap_catalog_discipline_json_valid_rate | 1.0 | 100.0 | json_valid_rate | 2026-03-21T02:57:33+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_gemma-3_4b |
| gemma-3:4b | daedalmap_catalog_discipline_no_halluc_rate | 0.5333333333333333 | 53.333333333333336 | no_halluc_rate | 2026-03-21T02:57:33+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_gemma-3_4b |
| gemma-3:4b | daedalmap_catalog_discipline_pass_rate | 0.0 | 0.0 | pass_rate | 2026-03-21T02:57:33+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_gemma-3_4b |
| gemma-3:4b | daedalmap_catalog_discipline_source_valid_rate | 0.75 | 75.0 | source_valid_rate | 2026-03-21T02:57:34+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_gemma-3_4b |
| gemma-3:4b | daedalmap_catalog_discipline_type_correct_rate | 0.0 | 0.0 | type_correct_rate | 2026-03-21T02:57:33+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_gemma-3_4b |
| gemma-3:4b | daedalmap_geographic_precision_json_valid_rate | 0.9333333333333333 | 93.33333333333333 | json_valid_rate | 2026-03-21T02:58:16+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_gemma-3_4b |
| gemma-3:4b | daedalmap_geographic_precision_no_halluc_rate | 1.0 | 100.0 | no_halluc_rate | 2026-03-21T02:58:16+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_gemma-3_4b |
| gemma-3:4b | daedalmap_geographic_precision_pass_rate | 0.8666666666666667 | 86.66666666666667 | pass_rate | 2026-03-21T02:58:16+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_gemma-3_4b |
| gemma-3:4b | daedalmap_geographic_precision_source_hit_rate | 0.9285714285714286 | 92.85714285714286 | source_hit_rate | 2026-03-21T02:58:16+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_gemma-3_4b |
| gemma-3:4b | daedalmap_geographic_precision_source_valid_rate | 0.9285714285714286 | 92.85714285714286 | source_valid_rate | 2026-03-21T02:58:16+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_gemma-3_4b |
| gemma-3:4b | daedalmap_geographic_precision_type_correct_rate | 0.9333333333333333 | 93.33333333333333 | type_correct_rate | 2026-03-21T02:58:16+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_gemma-3_4b |
| gemma-3:4b | daedalmap_json_discipline_json_valid_rate | 1.0 | 100.0 | json_valid_rate | 2026-03-21T02:58:48+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_gemma-3_4b |
| gemma-3:4b | daedalmap_json_discipline_no_halluc_rate | 1.0 | 100.0 | no_halluc_rate | 2026-03-21T02:58:48+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_gemma-3_4b |
| gemma-3:4b | daedalmap_json_discipline_pass_rate | 0.9333333333333333 | 93.33333333333333 | pass_rate | 2026-03-21T02:58:48+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_gemma-3_4b |
| gemma-3:4b | daedalmap_json_discipline_source_hit_rate | 1.0 | 100.0 | source_hit_rate | 2026-03-21T02:58:48+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_gemma-3_4b |
| gemma-3:4b | daedalmap_json_discipline_source_valid_rate | 1.0 | 100.0 | source_valid_rate | 2026-03-21T02:58:48+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_gemma-3_4b |
| gemma-3:4b | daedalmap_json_discipline_type_correct_rate | 0.9333333333333333 | 93.33333333333333 | type_correct_rate | 2026-03-21T02:58:48+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_gemma-3_4b |
| gemma-3:4b | daedalmap_multi_source_json_valid_rate | 0.8 | 80.0 | json_valid_rate | 2026-03-21T02:59:54+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_gemma-3_4b |
| gemma-3:4b | daedalmap_multi_source_no_halluc_rate | 1.0 | 100.0 | no_halluc_rate | 2026-03-21T02:59:55+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_gemma-3_4b |
| gemma-3:4b | daedalmap_multi_source_pass_rate | 0.7333333333333333 | 73.33333333333333 | pass_rate | 2026-03-21T02:59:54+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_gemma-3_4b |
| gemma-3:4b | daedalmap_multi_source_source_hit_rate | 1.0 | 100.0 | source_hit_rate | 2026-03-21T02:59:55+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_gemma-3_4b |
| gemma-3:4b | daedalmap_multi_source_source_valid_rate | 0.9166666666666666 | 91.66666666666666 | source_valid_rate | 2026-03-21T02:59:55+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_gemma-3_4b |
| gemma-3:4b | daedalmap_multi_source_type_correct_rate | 0.8 | 80.0 | type_correct_rate | 2026-03-21T02:59:55+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_gemma-3_4b |
| gemma-3:4b | daedalmap_source_grounding_json_valid_rate | 1.0 | 100.0 | json_valid_rate | 2026-03-21T03:00:42+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_gemma-3_4b |
| gemma-3:4b | daedalmap_source_grounding_no_halluc_rate | 0.95 | 95.0 | no_halluc_rate | 2026-03-21T03:00:42+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_gemma-3_4b |
| gemma-3:4b | daedalmap_source_grounding_pass_rate | 0.9 | 90.0 | pass_rate | 2026-03-21T03:00:42+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_gemma-3_4b |
| gemma-3:4b | daedalmap_source_grounding_source_hit_rate | 0.9 | 90.0 | source_hit_rate | 2026-03-21T03:00:42+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_gemma-3_4b |
| gemma-3:4b | daedalmap_source_grounding_source_valid_rate | 0.95 | 95.0 | source_valid_rate | 2026-03-21T03:00:42+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_gemma-3_4b |
| gemma-3:4b | daedalmap_source_grounding_type_correct_rate | 1.0 | 100.0 | type_correct_rate | 2026-03-21T03:00:42+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_gemma-3_4b |
| gemma-3:4b | daedalmap_type_routing_json_valid_rate | 0.9 | 90.0 | json_valid_rate | 2026-03-21T03:01:40+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_gemma-3_4b |
| gemma-3:4b | daedalmap_type_routing_no_halluc_rate | 0.95 | 95.0 | no_halluc_rate | 2026-03-21T03:01:40+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_gemma-3_4b |
| gemma-3:4b | daedalmap_type_routing_pass_rate | 0.55 | 55.00000000000001 | pass_rate | 2026-03-21T03:01:39+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_gemma-3_4b |
| gemma-3:4b | daedalmap_type_routing_source_hit_rate | 1.0 | 100.0 | source_hit_rate | 2026-03-21T03:01:40+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_gemma-3_4b |
| gemma-3:4b | daedalmap_type_routing_source_valid_rate | 0.8571428571428571 | 85.71428571428571 | source_valid_rate | 2026-03-21T03:01:40+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_gemma-3_4b |
| gemma-3:4b | daedalmap_type_routing_type_correct_rate | 0.6 | 60.0 | type_correct_rate | 2026-03-21T03:01:40+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_gemma-3_4b |
| gemma-4:12b | bbh | 0.24444444444444444 | 24.444444444444443 | exact_match,get-answer | 2026-06-06T23:52:14+00:00 | bench-reasoning | gemma4_12b_think1024_bbh_l5 |
| gemma-4:12b | drop_em | 0.6 | 60.0 | em,none | 2026-06-07T08:40:29+00:00 | bench-reasoning | gemma4_12b_drop_l5_budget0 |
| gemma-4:12b | drop_f1 | 0.7 | 70.0 | f1,none | 2026-06-07T08:40:29+00:00 | bench-reasoning | gemma4_12b_drop_l5_budget0 |
| gemma-4:12b | gsm8k_flexible | 0.2 | 20.0 | exact_match,flexible-extract | 2026-06-06T20:11:17+00:00 | bench-reasoning | gemma4_12b_smoke_l5 |
| gemma-4:12b | gsm8k_strict | 0.0 | 0.0 | exact_match,strict-match | 2026-06-06T20:11:17+00:00 | bench-reasoning | gemma4_12b_smoke_l5 |
| gemma-4:26b-a4b | bbh | 0.8703703703703703 | 87.03703703703704 | exact_match,get-answer | 2026-06-07T20:16:42+00:00 | bench-reasoning | campaign_26b_reasoning |
| gemma-4:26b-a4b | drop_em | 0.6 | 60.0 | em,none | 2026-06-07T20:17:12+00:00 | bench-reasoning | campaign_26b_reasoning |
| gemma-4:26b-a4b | drop_f1 | 0.727 | 72.7 | f1,none | 2026-06-07T20:17:12+00:00 | bench-reasoning | campaign_26b_reasoning |
| gemma-4:26b-a4b | gsm8k_flexible | 0.9 | 90.0 | exact_match,flexible-extract | 2026-06-07T20:07:38+00:00 | bench-reasoning | campaign_26b_reasoning |
| gemma-4:26b-a4b | gsm8k_strict | 0.9 | 90.0 | exact_match,strict-match | 2026-06-07T20:07:37+00:00 | bench-reasoning | campaign_26b_reasoning |
| gemma-4:31b | bbh | 0.8703703703703703 | 87.03703703703704 | exact_match,get-answer | 2026-06-07T20:27:04+00:00 | bench-reasoning | campaign_31b_reasoning |
| gemma-4:31b | drop_em | 0.6 | 60.0 | em,none | 2026-06-07T20:27:34+00:00 | bench-reasoning | campaign_31b_reasoning |
| gemma-4:31b | drop_f1 | 0.727 | 72.7 | f1,none | 2026-06-07T20:27:34+00:00 | bench-reasoning | campaign_31b_reasoning |
| gemma-4:31b | gsm8k_flexible | 0.9 | 90.0 | exact_match,flexible-extract | 2026-06-07T20:17:59+00:00 | bench-reasoning | campaign_31b_reasoning |
| gemma-4:31b | gsm8k_strict | 0.9 | 90.0 | exact_match,strict-match | 2026-06-07T20:17:59+00:00 | bench-reasoning | campaign_31b_reasoning |
| gemma-4:e2b | bbh | 0.12222222222222222 | 12.222222222222221 | exact_match,get-answer | 2026-06-07T21:00:37+00:00 | bench-reasoning | campaign_e2b_reasoning |
| gemma-4:e2b | drop_em | 0.0 | 0.0 | em,none | 2026-06-07T21:02:58+00:00 | bench-reasoning | campaign_e2b_reasoning |
| gemma-4:e2b | drop_f1 | 0.0 | 0.0 | f1,none | 2026-06-07T21:02:58+00:00 | bench-reasoning | campaign_e2b_reasoning |
| gemma-4:e2b | gsm8k_flexible | 0.6 | 60.0 | exact_match,flexible-extract | 2026-06-07T20:08:35+00:00 | bench-reasoning | campaign_e2b_reasoning |
| gemma-4:e2b | gsm8k_strict | 0.5 | 50.0 | exact_match,strict-match | 2026-06-07T20:08:35+00:00 | bench-reasoning | campaign_e2b_reasoning |
| gemma-4:e4b | bbh | 0.08148148148148149 | 8.148148148148149 | exact_match,get-answer | 2026-06-07T21:46:05+00:00 | bench-reasoning | campaign_e4b_reasoning |
| gemma-4:e4b | drop_em | 0.3 | 30.0 | em,none | 2026-06-07T21:47:58+00:00 | bench-reasoning | campaign_e4b_reasoning |
| gemma-4:e4b | drop_f1 | 0.307 | 30.7 | f1,none | 2026-06-07T21:47:58+00:00 | bench-reasoning | campaign_e4b_reasoning |
| gemma-4:e4b | gsm8k_flexible | 0.6 | 60.0 | exact_match,flexible-extract | 2026-06-07T20:08:59+00:00 | bench-reasoning | campaign_e4b_reasoning |
| gemma-4:e4b | gsm8k_strict | 0.2 | 20.0 | exact_match,strict-match | 2026-06-07T20:08:59+00:00 | bench-reasoning | campaign_e4b_reasoning |
| llama3.2:3b | bbh | 0.5896296296296296 | 58.96296296296296 | exact_match,get-answer | 2026-03-18T10:01:42+00:00 | bench-reasoning | bench-reasoning_llama3.2_3b_small_llama32_3b_reasoning_l100_v1 |
| llama3.2:3b | daedalmap_catalog_discipline_json_valid_rate | 1.0 | 100.0 | json_valid_rate | 2026-03-21T02:57:59+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_llama3.2_3b |
| llama3.2:3b | daedalmap_catalog_discipline_no_halluc_rate | 0.5333333333333333 | 53.333333333333336 | no_halluc_rate | 2026-03-21T02:57:59+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_llama3.2_3b |
| llama3.2:3b | daedalmap_catalog_discipline_pass_rate | 0.0 | 0.0 | pass_rate | 2026-03-21T02:57:59+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_llama3.2_3b |
| llama3.2:3b | daedalmap_catalog_discipline_source_valid_rate | 0.6666666666666666 | 66.66666666666666 | source_valid_rate | 2026-03-21T02:57:59+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_llama3.2_3b |
| llama3.2:3b | daedalmap_catalog_discipline_type_correct_rate | 0.0 | 0.0 | type_correct_rate | 2026-03-21T02:57:59+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_llama3.2_3b |
| llama3.2:3b | daedalmap_geographic_precision_json_valid_rate | 1.0 | 100.0 | json_valid_rate | 2026-03-21T02:58:22+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_llama3.2_3b |
| llama3.2:3b | daedalmap_geographic_precision_no_halluc_rate | 1.0 | 100.0 | no_halluc_rate | 2026-03-21T02:58:22+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_llama3.2_3b |
| llama3.2:3b | daedalmap_geographic_precision_pass_rate | 0.9333333333333333 | 93.33333333333333 | pass_rate | 2026-03-21T02:58:22+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_llama3.2_3b |
| llama3.2:3b | daedalmap_geographic_precision_source_hit_rate | 0.9333333333333333 | 93.33333333333333 | source_hit_rate | 2026-03-21T02:58:22+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_llama3.2_3b |
| llama3.2:3b | daedalmap_geographic_precision_source_valid_rate | 0.9333333333333333 | 93.33333333333333 | source_valid_rate | 2026-03-21T02:58:22+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_llama3.2_3b |
| llama3.2:3b | daedalmap_geographic_precision_type_correct_rate | 1.0 | 100.0 | type_correct_rate | 2026-03-21T02:58:22+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_llama3.2_3b |
| llama3.2:3b | daedalmap_json_discipline_json_valid_rate | 1.0 | 100.0 | json_valid_rate | 2026-03-21T02:58:40+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_llama3.2_3b |
| llama3.2:3b | daedalmap_json_discipline_no_halluc_rate | 1.0 | 100.0 | no_halluc_rate | 2026-03-21T02:58:40+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_llama3.2_3b |
| llama3.2:3b | daedalmap_json_discipline_pass_rate | 0.8 | 80.0 | pass_rate | 2026-03-21T02:58:40+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_llama3.2_3b |
| llama3.2:3b | daedalmap_json_discipline_source_hit_rate | 1.0 | 100.0 | source_hit_rate | 2026-03-21T02:58:40+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_llama3.2_3b |
| llama3.2:3b | daedalmap_json_discipline_source_valid_rate | 1.0 | 100.0 | source_valid_rate | 2026-03-21T02:58:40+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_llama3.2_3b |
| llama3.2:3b | daedalmap_json_discipline_type_correct_rate | 0.8 | 80.0 | type_correct_rate | 2026-03-21T02:58:40+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_llama3.2_3b |
| llama3.2:3b | daedalmap_multi_source_json_valid_rate | 0.8 | 80.0 | json_valid_rate | 2026-03-21T02:59:16+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_llama3.2_3b |
| llama3.2:3b | daedalmap_multi_source_no_halluc_rate | 1.0 | 100.0 | no_halluc_rate | 2026-03-21T02:59:16+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_llama3.2_3b |
| llama3.2:3b | daedalmap_multi_source_pass_rate | 0.8 | 80.0 | pass_rate | 2026-03-21T02:59:16+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_llama3.2_3b |
| llama3.2:3b | daedalmap_multi_source_source_hit_rate | 1.0 | 100.0 | source_hit_rate | 2026-03-21T02:59:16+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_llama3.2_3b |
| llama3.2:3b | daedalmap_multi_source_source_valid_rate | 1.0 | 100.0 | source_valid_rate | 2026-03-21T02:59:17+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_llama3.2_3b |
| llama3.2:3b | daedalmap_multi_source_type_correct_rate | 0.8 | 80.0 | type_correct_rate | 2026-03-21T02:59:16+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_llama3.2_3b |
| llama3.2:3b | daedalmap_source_grounding_json_valid_rate | 0.95 | 95.0 | json_valid_rate | 2026-03-21T02:59:44+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_llama3.2_3b |
| llama3.2:3b | daedalmap_source_grounding_no_halluc_rate | 1.0 | 100.0 | no_halluc_rate | 2026-03-21T02:59:44+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_llama3.2_3b |
| llama3.2:3b | daedalmap_source_grounding_pass_rate | 0.85 | 85.0 | pass_rate | 2026-03-21T02:59:44+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_llama3.2_3b |
| llama3.2:3b | daedalmap_source_grounding_source_hit_rate | 0.8947368421052632 | 89.47368421052632 | source_hit_rate | 2026-03-21T02:59:44+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_llama3.2_3b |
| llama3.2:3b | daedalmap_source_grounding_source_valid_rate | 0.9473684210526315 | 94.73684210526315 | source_valid_rate | 2026-03-21T02:59:45+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_llama3.2_3b |
| llama3.2:3b | daedalmap_source_grounding_type_correct_rate | 0.95 | 95.0 | type_correct_rate | 2026-03-21T02:59:44+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_llama3.2_3b |
| llama3.2:3b | daedalmap_type_routing_json_valid_rate | 0.9 | 90.0 | json_valid_rate | 2026-03-21T03:00:16+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_llama3.2_3b |
| llama3.2:3b | daedalmap_type_routing_no_halluc_rate | 0.95 | 95.0 | no_halluc_rate | 2026-03-21T03:00:16+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_llama3.2_3b |
| llama3.2:3b | daedalmap_type_routing_pass_rate | 0.55 | 55.00000000000001 | pass_rate | 2026-03-21T03:00:16+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_llama3.2_3b |
| llama3.2:3b | daedalmap_type_routing_source_hit_rate | 0.75 | 75.0 | source_hit_rate | 2026-03-21T03:00:16+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_llama3.2_3b |
| llama3.2:3b | daedalmap_type_routing_source_valid_rate | 0.875 | 87.5 | source_valid_rate | 2026-03-21T03:00:16+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_llama3.2_3b |
| llama3.2:3b | daedalmap_type_routing_type_correct_rate | 0.65 | 65.0 | type_correct_rate | 2026-03-21T03:00:16+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_llama3.2_3b |
| llama3.2:3b | drop_em | 0.28 | 28.000000000000004 | em,none | 2026-03-18T10:02:29+00:00 | bench-reasoning | bench-reasoning_llama3.2_3b_small_llama32_3b_reasoning_l100_v1 |
| llama3.2:3b | drop_f1 | 0.43260000000000004 | 43.260000000000005 | f1,none | 2026-03-18T10:02:29+00:00 | bench-reasoning | bench-reasoning_llama3.2_3b_small_llama32_3b_reasoning_l100_v1 |
| llama3.2:3b | gsm8k_flexible | 0.72 | 72.0 | exact_match,flexible-extract | 2026-03-18T05:59:05+00:00 | bench-reasoning | bench-reasoning_llama3.2_3b_small_llama32_3b_reasoning_l100_v1 |
| llama3.2:3b | gsm8k_strict | 0.7 | 70.0 | exact_match,strict-match | 2026-03-18T05:59:05+00:00 | bench-reasoning | bench-reasoning_llama3.2_3b_small_llama32_3b_reasoning_l100_v1 |
| mistral:7b-instruct | custom_ambiguity_handling | 1.0 | 100.0 | clarification_rate | 2026-03-05T20:20:03.464691 | local_custom | local_custom_probe_v2 |
| mistral:7b-instruct | daedalmap_catalog_discipline_json_valid_rate | 0.8666666666666667 | 86.66666666666667 | json_valid_rate | 2026-03-21T03:41:34+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_mistral_7b-instruct |
| mistral:7b-instruct | daedalmap_catalog_discipline_no_halluc_rate | 0.5333333333333333 | 53.333333333333336 | no_halluc_rate | 2026-03-21T03:41:35+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_mistral_7b-instruct |
| mistral:7b-instruct | daedalmap_catalog_discipline_pass_rate | 0.0 | 0.0 | pass_rate | 2026-03-21T03:41:34+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_mistral_7b-instruct |
| mistral:7b-instruct | daedalmap_catalog_discipline_source_valid_rate | 0.7142857142857143 | 71.42857142857143 | source_valid_rate | 2026-03-21T03:41:35+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_mistral_7b-instruct |
| mistral:7b-instruct | daedalmap_catalog_discipline_type_correct_rate | 0.0 | 0.0 | type_correct_rate | 2026-03-21T03:41:35+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_mistral_7b-instruct |
| mistral:7b-instruct | daedalmap_geographic_precision_json_valid_rate | 1.0 | 100.0 | json_valid_rate | 2026-03-21T03:42:26+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_mistral_7b-instruct |
| mistral:7b-instruct | daedalmap_geographic_precision_no_halluc_rate | 1.0 | 100.0 | no_halluc_rate | 2026-03-21T03:42:26+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_mistral_7b-instruct |
| mistral:7b-instruct | daedalmap_geographic_precision_pass_rate | 0.8666666666666667 | 86.66666666666667 | pass_rate | 2026-03-21T03:42:26+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_mistral_7b-instruct |
| mistral:7b-instruct | daedalmap_geographic_precision_source_hit_rate | 0.8666666666666667 | 86.66666666666667 | source_hit_rate | 2026-03-21T03:42:26+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_mistral_7b-instruct |
| mistral:7b-instruct | daedalmap_geographic_precision_source_valid_rate | 0.8666666666666667 | 86.66666666666667 | source_valid_rate | 2026-03-21T03:42:26+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_mistral_7b-instruct |
| mistral:7b-instruct | daedalmap_geographic_precision_type_correct_rate | 1.0 | 100.0 | type_correct_rate | 2026-03-21T03:42:26+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_mistral_7b-instruct |
| mistral:7b-instruct | daedalmap_json_discipline_json_valid_rate | 1.0 | 100.0 | json_valid_rate | 2026-03-21T03:43:02+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_mistral_7b-instruct |
| mistral:7b-instruct | daedalmap_json_discipline_no_halluc_rate | 1.0 | 100.0 | no_halluc_rate | 2026-03-21T03:43:02+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_mistral_7b-instruct |
| mistral:7b-instruct | daedalmap_json_discipline_pass_rate | 0.6666666666666666 | 66.66666666666666 | pass_rate | 2026-03-21T03:43:02+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_mistral_7b-instruct |
| mistral:7b-instruct | daedalmap_json_discipline_source_hit_rate | 1.0 | 100.0 | source_hit_rate | 2026-03-21T03:43:02+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_mistral_7b-instruct |
| mistral:7b-instruct | daedalmap_json_discipline_source_valid_rate | 0.875 | 87.5 | source_valid_rate | 2026-03-21T03:43:02+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_mistral_7b-instruct |
| mistral:7b-instruct | daedalmap_json_discipline_type_correct_rate | 0.7333333333333333 | 73.33333333333333 | type_correct_rate | 2026-03-21T03:43:02+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_mistral_7b-instruct |
| mistral:7b-instruct | daedalmap_multi_source_json_valid_rate | 1.0 | 100.0 | json_valid_rate | 2026-03-21T03:44:07+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_mistral_7b-instruct |
| mistral:7b-instruct | daedalmap_multi_source_no_halluc_rate | 1.0 | 100.0 | no_halluc_rate | 2026-03-21T03:44:07+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_mistral_7b-instruct |
| mistral:7b-instruct | daedalmap_multi_source_pass_rate | 0.8 | 80.0 | pass_rate | 2026-03-21T03:44:07+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_mistral_7b-instruct |
| mistral:7b-instruct | daedalmap_multi_source_source_hit_rate | 0.9285714285714286 | 92.85714285714286 | source_hit_rate | 2026-03-21T03:44:07+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_mistral_7b-instruct |
| mistral:7b-instruct | daedalmap_multi_source_source_valid_rate | 0.8571428571428571 | 85.71428571428571 | source_valid_rate | 2026-03-21T03:44:07+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_mistral_7b-instruct |
| mistral:7b-instruct | daedalmap_multi_source_type_correct_rate | 0.9333333333333333 | 93.33333333333333 | type_correct_rate | 2026-03-21T03:44:07+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_mistral_7b-instruct |
| mistral:7b-instruct | daedalmap_source_grounding_json_valid_rate | 1.0 | 100.0 | json_valid_rate | 2026-03-21T03:44:59+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_mistral_7b-instruct |
| mistral:7b-instruct | daedalmap_source_grounding_no_halluc_rate | 1.0 | 100.0 | no_halluc_rate | 2026-03-21T03:44:59+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_mistral_7b-instruct |
| mistral:7b-instruct | daedalmap_source_grounding_pass_rate | 0.95 | 95.0 | pass_rate | 2026-03-21T03:44:59+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_mistral_7b-instruct |
| mistral:7b-instruct | daedalmap_source_grounding_source_hit_rate | 0.95 | 95.0 | source_hit_rate | 2026-03-21T03:44:59+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_mistral_7b-instruct |
| mistral:7b-instruct | daedalmap_source_grounding_source_valid_rate | 0.95 | 95.0 | source_valid_rate | 2026-03-21T03:44:59+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_mistral_7b-instruct |
| mistral:7b-instruct | daedalmap_source_grounding_type_correct_rate | 1.0 | 100.0 | type_correct_rate | 2026-03-21T03:44:59+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_mistral_7b-instruct |
| mistral:7b-instruct | daedalmap_type_routing_json_valid_rate | 0.95 | 95.0 | json_valid_rate | 2026-03-21T03:46:07+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_mistral_7b-instruct |
| mistral:7b-instruct | daedalmap_type_routing_no_halluc_rate | 0.95 | 95.0 | no_halluc_rate | 2026-03-21T03:46:07+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_mistral_7b-instruct |
| mistral:7b-instruct | daedalmap_type_routing_pass_rate | 0.55 | 55.00000000000001 | pass_rate | 2026-03-21T03:46:07+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_mistral_7b-instruct |
| mistral:7b-instruct | daedalmap_type_routing_source_hit_rate | 0.5 | 50.0 | source_hit_rate | 2026-03-21T03:46:07+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_mistral_7b-instruct |
| mistral:7b-instruct | daedalmap_type_routing_source_valid_rate | 0.8333333333333334 | 83.33333333333334 | source_valid_rate | 2026-03-21T03:46:07+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_mistral_7b-instruct |
| mistral:7b-instruct | daedalmap_type_routing_type_correct_rate | 0.7 | 70.0 | type_correct_rate | 2026-03-21T03:46:07+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_mistral_7b-instruct |
| mistral:7b-instruct | gsm8k_flexible | 0.48 | 48.0 | exact_match,flexible-extract | 2026-03-12T05:36:44+00:00 | bench-reasoning | bench-reasoning_mistral_7b-instruct_rr_l100_c05_20260311_221559_p11435 |
| mistral:7b-instruct | gsm8k_strict | 0.48 | 48.0 | exact_match,strict-match | 2026-03-12T05:36:44+00:00 | bench-reasoning | bench-reasoning_mistral_7b-instruct_rr_l100_c05_20260311_221559_p11435 |
| phi-4-Q4_K_M.gguf | bbh | 0.1259259259259259 | 12.592592592592592 | exact_match,get-answer | 2026-03-17T01:43:41+00:00 | bench-reasoning | bench-reasoning_phi-4-Q4_K_M.gguf_reasoning_phi4_v5_answerfmt |
| phi-4-Q4_K_M.gguf | drop_em | 0.0 | 0.0 | em,none | 2026-03-17T01:45:09+00:00 | bench-reasoning | bench-reasoning_phi-4-Q4_K_M.gguf_reasoning_phi4_v5_answerfmt |
| phi-4-Q4_K_M.gguf | drop_f1 | 0.0 | 0.0 | f1,none | 2026-03-17T01:45:09+00:00 | bench-reasoning | bench-reasoning_phi-4-Q4_K_M.gguf_reasoning_phi4_v5_answerfmt |
| phi-4-Q4_K_M.gguf | gsm8k_flexible | 1.0 | 100.0 | exact_match,flexible-extract | 2026-03-17T01:05:18+00:00 | bench-reasoning | bench-reasoning_phi-4-Q4_K_M.gguf_reasoning_phi4_v5_answerfmt |
| phi-4-Q4_K_M.gguf | gsm8k_strict | 0.0 | 0.0 | exact_match,strict-match | 2026-03-17T01:05:18+00:00 | bench-reasoning | bench-reasoning_phi-4-Q4_K_M.gguf_reasoning_phi4_v5_answerfmt |
| phi-4-mini:3.8b | bbh | 0.5722222222222222 | 57.22222222222222 | exact_match,get-answer | 2026-03-18T22:55:05+00:00 | bench-reasoning | bench-reasoning_phi-4-mini_3.8b_small_phi4mini_reasoning_l100_v1 |
| phi-4-mini:3.8b | daedalmap_json_discipline_json_valid_rate | 0.6 | 60.0 | json_valid_rate | 2026-03-21T02:48:43+00:00 | bench-daedalmap | daedalmap_small_models_smoke_v7_phi-4-mini_3.8b |
| phi-4-mini:3.8b | daedalmap_json_discipline_no_halluc_rate | 1.0 | 100.0 | no_halluc_rate | 2026-03-21T02:48:43+00:00 | bench-daedalmap | daedalmap_small_models_smoke_v7_phi-4-mini_3.8b |
| phi-4-mini:3.8b | daedalmap_json_discipline_pass_rate | 0.4 | 40.0 | pass_rate | 2026-03-21T02:48:42+00:00 | bench-daedalmap | daedalmap_small_models_smoke_v7_phi-4-mini_3.8b |
| phi-4-mini:3.8b | daedalmap_json_discipline_type_correct_rate | 0.4 | 40.0 | type_correct_rate | 2026-03-21T02:48:43+00:00 | bench-daedalmap | daedalmap_small_models_smoke_v7_phi-4-mini_3.8b |
| phi-4-mini:3.8b | daedalmap_source_grounding_json_valid_rate | 0.8 | 80.0 | json_valid_rate | 2026-03-21T02:48:53+00:00 | bench-daedalmap | daedalmap_small_models_smoke_v7_phi-4-mini_3.8b |
| phi-4-mini:3.8b | daedalmap_source_grounding_no_halluc_rate | 1.0 | 100.0 | no_halluc_rate | 2026-03-21T02:48:53+00:00 | bench-daedalmap | daedalmap_small_models_smoke_v7_phi-4-mini_3.8b |
| phi-4-mini:3.8b | daedalmap_source_grounding_pass_rate | 0.6 | 60.0 | pass_rate | 2026-03-21T02:48:53+00:00 | bench-daedalmap | daedalmap_small_models_smoke_v7_phi-4-mini_3.8b |
| phi-4-mini:3.8b | daedalmap_source_grounding_source_hit_rate | 0.75 | 75.0 | source_hit_rate | 2026-03-21T02:48:53+00:00 | bench-daedalmap | daedalmap_small_models_smoke_v7_phi-4-mini_3.8b |
| phi-4-mini:3.8b | daedalmap_source_grounding_source_valid_rate | 0.75 | 75.0 | source_valid_rate | 2026-03-21T02:48:53+00:00 | bench-daedalmap | daedalmap_small_models_smoke_v7_phi-4-mini_3.8b |
| phi-4-mini:3.8b | daedalmap_source_grounding_type_correct_rate | 0.8 | 80.0 | type_correct_rate | 2026-03-21T02:48:53+00:00 | bench-daedalmap | daedalmap_small_models_smoke_v7_phi-4-mini_3.8b |
| phi-4-mini:3.8b | drop_em | 0.11 | 11.0 | em,none | 2026-03-18T22:56:14+00:00 | bench-reasoning | bench-reasoning_phi-4-mini_3.8b_small_phi4mini_reasoning_l100_v1 |
| phi-4-mini:3.8b | drop_f1 | 0.28470000000000006 | 28.470000000000006 | f1,none | 2026-03-18T22:56:14+00:00 | bench-reasoning | bench-reasoning_phi-4-mini_3.8b_small_phi4mini_reasoning_l100_v1 |
| phi-4-mini:3.8b | gsm8k_flexible | 0.69 | 69.0 | exact_match,flexible-extract | 2026-03-18T06:02:21+00:00 | bench-reasoning | bench-reasoning_phi-4-mini_3.8b_small_phi4mini_reasoning_l100_v1 |
| phi-4-mini:3.8b | gsm8k_strict | 0.7 | 70.0 | exact_match,strict-match | 2026-03-18T06:02:21+00:00 | bench-reasoning | bench-reasoning_phi-4-mini_3.8b_small_phi4mini_reasoning_l100_v1 |
| phi-4:14b | bbh | 0.577037037037037 | 57.7037037037037 | exact_match,get-answer | 2026-04-29T04:46:26+00:00 | bench-reasoning | phi4_l100_rerun_20260428 |
| phi-4:14b | drop_em | 0.02 | 2.0 | em,none | 2026-04-29T04:48:28+00:00 | bench-reasoning | phi4_l100_rerun_20260428 |
| phi-4:14b | drop_f1 | 0.0925 | 9.25 | f1,none | 2026-04-29T04:48:28+00:00 | bench-reasoning | phi4_l100_rerun_20260428 |
| phi-4:14b | gsm8k_flexible | 0.78 | 78.0 | exact_match,flexible-extract | 2026-04-28T18:39:09+00:00 | bench-reasoning | phi4_l100_rerun_20260428 |
| phi-4:14b | gsm8k_strict | 0.56 | 56.00000000000001 | exact_match,strict-match | 2026-04-28T18:39:09+00:00 | bench-reasoning | phi4_l100_rerun_20260428 |
| qwen2.5-coder:14b | bbh | 0.5937037037037037 | 59.370370370370374 | exact_match,get-answer | 2026-03-16T16:23:17+00:00 | bench-reasoning | bench-reasoning_qwen2.5-coder_14b_reasoning_coder14b_l100_v1 |
| qwen2.5-coder:14b | drop | 0.57 | 56.99999999999999 | f1,none | 2026-03-05T15:54:28.421925 | lm_eval | quick_triplet_l1_20260305 |
| qwen2.5-coder:14b | drop_em | 0.28 | 28.000000000000004 | em,none | 2026-03-16T16:25:26+00:00 | bench-reasoning | bench-reasoning_qwen2.5-coder_14b_reasoning_coder14b_l100_v1 |
| qwen2.5-coder:14b | drop_f1 | 0.4802000000000002 | 48.02000000000002 | f1,none | 2026-03-16T16:25:26+00:00 | bench-reasoning | bench-reasoning_qwen2.5-coder_14b_reasoning_coder14b_l100_v1 |
| qwen2.5-coder:14b | gsm8k | 1.0 | 100.0 | exact_match,flexible-extract | 2026-03-05T15:50:53.042159 | lm_eval | quick_triplet_l1_20260305 |
| qwen2.5-coder:14b | gsm8k_flexible | 0.89 | 89.0 | exact_match,flexible-extract | 2026-03-16T07:21:32+00:00 | bench-reasoning | bench-reasoning_qwen2.5-coder_14b_reasoning_coder14b_l100_v1 |
| qwen2.5-coder:14b | gsm8k_strict | 0.88 | 88.0 | exact_match,strict-match | 2026-03-16T07:21:32+00:00 | bench-reasoning | bench-reasoning_qwen2.5-coder_14b_reasoning_coder14b_l100_v1 |
| qwen2.5-coder:32b | bbh | 0.4837037037037037 | 48.37037037037037 | exact_match,get-answer | 2026-03-15T22:45:25+00:00 | bench-reasoning | bench-reasoning_qwen2.5-coder_32b_reasoning_coder32b_l100_v1 |
| qwen2.5-coder:32b | drop | 0.18 | 18.0 | f1,none | 2026-03-05T15:55:15.554964 | lm_eval | quick_triplet_l1_20260305 |
| qwen2.5-coder:32b | drop_em | 0.62 | 62.0 | em,none | 2026-03-15T22:46:12+00:00 | bench-reasoning | bench-reasoning_qwen2.5-coder_32b_reasoning_coder32b_l100_v1 |
| qwen2.5-coder:32b | drop_f1 | 0.7561000000000003 | 75.61000000000003 | f1,none | 2026-03-15T22:46:12+00:00 | bench-reasoning | bench-reasoning_qwen2.5-coder_32b_reasoning_coder32b_l100_v1 |
| qwen2.5-coder:32b | gsm8k | 0.0 | 0.0 | exact_match,flexible-extract | 2026-03-05T15:52:07.684619 | lm_eval | quick_triplet_l1_20260305 |
| qwen2.5-coder:32b | gsm8k_flexible | 0.92 | 92.0 | exact_match,flexible-extract | 2026-03-15T07:52:40+00:00 | bench-reasoning | bench-reasoning_qwen2.5-coder_32b_reasoning_coder32b_l100_v1 |
| qwen2.5-coder:32b | gsm8k_strict | 0.92 | 92.0 | exact_match,strict-match | 2026-03-15T07:52:40+00:00 | bench-reasoning | bench-reasoning_qwen2.5-coder_32b_reasoning_coder32b_l100_v1 |
| qwen2.5-coder:7b | bbh | 0.6444444444444445 | 64.44444444444444 | exact_match,get-answer | 2026-04-24T18:41:43+00:00 | bench-reasoning | smoke_coder7b_nonn_bbh_l5 |
| qwen2.5-coder:7b | custom_json_schema_strict | 0.5 | 50.0 | schema_valid_rate | 2026-03-05T20:20:25.318139 | local_custom | local_custom_probe_v2 |
| qwen2.5-coder:7b | daedalmap_catalog_discipline_json_valid_rate | 1.0 | 100.0 | json_valid_rate | 2026-03-21T03:39:06+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_qwen2.5-coder_7b |
| qwen2.5-coder:7b | daedalmap_catalog_discipline_no_halluc_rate | 0.5333333333333333 | 53.333333333333336 | no_halluc_rate | 2026-03-21T03:39:06+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_qwen2.5-coder_7b |
| qwen2.5-coder:7b | daedalmap_catalog_discipline_pass_rate | 0.4 | 40.0 | pass_rate | 2026-03-21T03:39:05+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_qwen2.5-coder_7b |
| qwen2.5-coder:7b | daedalmap_catalog_discipline_source_valid_rate | 0.0 | 0.0 | source_valid_rate | 2026-03-21T03:39:06+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_qwen2.5-coder_7b |
| qwen2.5-coder:7b | daedalmap_catalog_discipline_type_correct_rate | 0.7333333333333333 | 73.33333333333333 | type_correct_rate | 2026-03-21T03:39:06+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_qwen2.5-coder_7b |
| qwen2.5-coder:7b | daedalmap_geographic_precision_json_valid_rate | 1.0 | 100.0 | json_valid_rate | 2026-03-21T03:39:47+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_qwen2.5-coder_7b |
| qwen2.5-coder:7b | daedalmap_geographic_precision_no_halluc_rate | 1.0 | 100.0 | no_halluc_rate | 2026-03-21T03:39:47+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_qwen2.5-coder_7b |
| qwen2.5-coder:7b | daedalmap_geographic_precision_pass_rate | 0.8 | 80.0 | pass_rate | 2026-03-21T03:39:46+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_qwen2.5-coder_7b |
| qwen2.5-coder:7b | daedalmap_geographic_precision_source_hit_rate | 0.8571428571428571 | 85.71428571428571 | source_hit_rate | 2026-03-21T03:39:47+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_qwen2.5-coder_7b |
| qwen2.5-coder:7b | daedalmap_geographic_precision_source_valid_rate | 0.9285714285714286 | 92.85714285714286 | source_valid_rate | 2026-03-21T03:39:47+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_qwen2.5-coder_7b |
| qwen2.5-coder:7b | daedalmap_geographic_precision_type_correct_rate | 0.9333333333333333 | 93.33333333333333 | type_correct_rate | 2026-03-21T03:39:47+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_qwen2.5-coder_7b |
| qwen2.5-coder:7b | daedalmap_json_discipline_json_valid_rate | 1.0 | 100.0 | json_valid_rate | 2026-03-21T03:40:19+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_qwen2.5-coder_7b |
| qwen2.5-coder:7b | daedalmap_json_discipline_no_halluc_rate | 1.0 | 100.0 | no_halluc_rate | 2026-03-21T03:40:19+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_qwen2.5-coder_7b |
| qwen2.5-coder:7b | daedalmap_json_discipline_pass_rate | 0.6666666666666666 | 66.66666666666666 | pass_rate | 2026-03-21T03:40:19+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_qwen2.5-coder_7b |
| qwen2.5-coder:7b | daedalmap_json_discipline_source_hit_rate | 0.8 | 80.0 | source_hit_rate | 2026-03-21T03:40:19+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_qwen2.5-coder_7b |
| qwen2.5-coder:7b | daedalmap_json_discipline_source_valid_rate | 0.8 | 80.0 | source_valid_rate | 2026-03-21T03:40:19+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_qwen2.5-coder_7b |
| qwen2.5-coder:7b | daedalmap_json_discipline_type_correct_rate | 0.7333333333333333 | 73.33333333333333 | type_correct_rate | 2026-03-21T03:40:19+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_qwen2.5-coder_7b |
| qwen2.5-coder:7b | daedalmap_multi_source_json_valid_rate | 1.0 | 100.0 | json_valid_rate | 2026-03-21T03:41:40+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_qwen2.5-coder_7b |
| qwen2.5-coder:7b | daedalmap_multi_source_no_halluc_rate | 1.0 | 100.0 | no_halluc_rate | 2026-03-21T03:41:40+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_qwen2.5-coder_7b |
| qwen2.5-coder:7b | daedalmap_multi_source_pass_rate | 0.9333333333333333 | 93.33333333333333 | pass_rate | 2026-03-21T03:41:39+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_qwen2.5-coder_7b |
| qwen2.5-coder:7b | daedalmap_multi_source_source_hit_rate | 1.0 | 100.0 | source_hit_rate | 2026-03-21T03:41:40+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_qwen2.5-coder_7b |
| qwen2.5-coder:7b | daedalmap_multi_source_source_valid_rate | 0.9333333333333333 | 93.33333333333333 | source_valid_rate | 2026-03-21T03:41:40+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_qwen2.5-coder_7b |
| qwen2.5-coder:7b | daedalmap_multi_source_type_correct_rate | 1.0 | 100.0 | type_correct_rate | 2026-03-21T03:41:40+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_qwen2.5-coder_7b |
| qwen2.5-coder:7b | daedalmap_source_grounding_json_valid_rate | 1.0 | 100.0 | json_valid_rate | 2026-03-21T03:42:27+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_qwen2.5-coder_7b |
| qwen2.5-coder:7b | daedalmap_source_grounding_no_halluc_rate | 0.95 | 95.0 | no_halluc_rate | 2026-03-21T03:42:27+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_qwen2.5-coder_7b |
| qwen2.5-coder:7b | daedalmap_source_grounding_pass_rate | 0.75 | 75.0 | pass_rate | 2026-03-21T03:42:27+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_qwen2.5-coder_7b |
| qwen2.5-coder:7b | daedalmap_source_grounding_source_hit_rate | 0.8823529411764706 | 88.23529411764706 | source_hit_rate | 2026-03-21T03:42:28+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_qwen2.5-coder_7b |
| qwen2.5-coder:7b | daedalmap_source_grounding_source_valid_rate | 0.9411764705882353 | 94.11764705882352 | source_valid_rate | 2026-03-21T03:42:28+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_qwen2.5-coder_7b |
| qwen2.5-coder:7b | daedalmap_source_grounding_type_correct_rate | 0.85 | 85.0 | type_correct_rate | 2026-03-21T03:42:27+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_qwen2.5-coder_7b |
| qwen2.5-coder:7b | daedalmap_type_routing_json_valid_rate | 1.0 | 100.0 | json_valid_rate | 2026-03-21T03:43:14+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_qwen2.5-coder_7b |
| qwen2.5-coder:7b | daedalmap_type_routing_no_halluc_rate | 0.95 | 95.0 | no_halluc_rate | 2026-03-21T03:43:14+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_qwen2.5-coder_7b |
| qwen2.5-coder:7b | daedalmap_type_routing_pass_rate | 0.6 | 60.0 | pass_rate | 2026-03-21T03:43:14+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_qwen2.5-coder_7b |
| qwen2.5-coder:7b | daedalmap_type_routing_source_hit_rate | 0.6666666666666666 | 66.66666666666666 | source_hit_rate | 2026-03-21T03:43:14+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_qwen2.5-coder_7b |
| qwen2.5-coder:7b | daedalmap_type_routing_source_valid_rate | 1.0 | 100.0 | source_valid_rate | 2026-03-21T03:43:14+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_qwen2.5-coder_7b |
| qwen2.5-coder:7b | daedalmap_type_routing_type_correct_rate | 0.7 | 70.0 | type_correct_rate | 2026-03-21T03:43:14+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_qwen2.5-coder_7b |
| qwen2.5-coder:7b | drop | 0.27 | 27.0 | f1,none | 2026-03-05T15:53:05.860807 | lm_eval | quick_triplet_l1_20260305 |
| qwen2.5-coder:7b | drop_em | 0.4 | 40.0 | em,none | 2026-04-24T02:54:13+00:00 | bench-reasoning | patch_validation_coder7b_l5 |
| qwen2.5-coder:7b | drop_f1 | 0.6 | 60.0 | f1,none | 2026-04-24T02:54:13+00:00 | bench-reasoning | patch_validation_coder7b_l5 |
| qwen2.5-coder:7b | gsm8k | 1.0 | 100.0 | exact_match,flexible-extract | 2026-03-05T15:48:24.680621 | lm_eval | quick_triplet_l1_20260305 |
| qwen2.5-coder:7b | gsm8k_flexible | 0.78 | 78.0 | exact_match,flexible-extract | 2026-03-12T05:31:29+00:00 | bench-reasoning | bench-reasoning_qwen2.5-coder_7b_rr_l100_c05_20260311_221559_p11439 |
| qwen2.5-coder:7b | gsm8k_strict | 0.75 | 75.0 | exact_match,strict-match | 2026-03-12T05:31:29+00:00 | bench-reasoning | bench-reasoning_qwen2.5-coder_7b_rr_l100_c05_20260311_221559_p11439 |
| qwen2.5:7b | bbh | 0.5555555555555556 |  | exact_match,get-answer | 2026-03-05T14:03:11.985279 | lm_eval | initial_matrix_20260305 |
| qwen2.5:7b | custom_command_safety | 1.0 | 100.0 | risk_detection_rate | 2026-03-05T20:20:27.293918 | local_custom | local_custom_probe_v2 |
| qwen2.5:7b | drop | 0.14875 |  | f1,none | 2026-03-05T13:57:56.869958 | lm_eval | initial_matrix_20260305 |
| qwen2.5:7b | gsm8k | 0.75 |  | exact_match,flexible-extract | 2026-03-05T13:57:07.002198 | lm_eval | initial_matrix_20260305 |
| qwen3.5:4b | custom_command_safety | 1.0 | 100.0 | risk_detection_rate | 2026-04-03T14:30:20.198505 | local_custom | individual_custom |
| qwen3.5:4b | daedalmap_catalog_discipline_json_valid_rate | 0.6666666666666666 | 66.66666666666666 | json_valid_rate | 2026-03-21T02:59:19+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_qwen3.5_4b |
| qwen3.5:4b | daedalmap_catalog_discipline_no_halluc_rate | 0.7333333333333333 | 73.33333333333333 | no_halluc_rate | 2026-03-21T02:59:19+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_qwen3.5_4b |
| qwen3.5:4b | daedalmap_catalog_discipline_pass_rate | 0.4666666666666667 | 46.666666666666664 | pass_rate | 2026-03-21T02:59:19+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_qwen3.5_4b |
| qwen3.5:4b | daedalmap_catalog_discipline_type_correct_rate | 0.6666666666666666 | 66.66666666666666 | type_correct_rate | 2026-03-21T02:59:19+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_qwen3.5_4b |
| qwen3.5:4b | daedalmap_geographic_precision_json_valid_rate | 0.13333333333333333 | 13.333333333333334 | json_valid_rate | 2026-03-21T03:03:26+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_qwen3.5_4b |
| qwen3.5:4b | daedalmap_geographic_precision_no_halluc_rate | 1.0 | 100.0 | no_halluc_rate | 2026-03-21T03:03:26+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_qwen3.5_4b |
| qwen3.5:4b | daedalmap_geographic_precision_pass_rate | 0.06666666666666667 | 6.666666666666667 | pass_rate | 2026-03-21T03:03:25+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_qwen3.5_4b |
| qwen3.5:4b | daedalmap_geographic_precision_source_hit_rate | 1.0 | 100.0 | source_hit_rate | 2026-03-21T03:03:26+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_qwen3.5_4b |
| qwen3.5:4b | daedalmap_geographic_precision_source_valid_rate | 1.0 | 100.0 | source_valid_rate | 2026-03-21T03:03:26+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_qwen3.5_4b |
| qwen3.5:4b | daedalmap_geographic_precision_type_correct_rate | 0.06666666666666667 | 6.666666666666667 | type_correct_rate | 2026-03-21T03:03:26+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_qwen3.5_4b |
| qwen3.5:4b | daedalmap_json_discipline_json_valid_rate | 0.6 | 60.0 | json_valid_rate | 2026-03-21T03:06:30+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_qwen3.5_4b |
| qwen3.5:4b | daedalmap_json_discipline_no_halluc_rate | 1.0 | 100.0 | no_halluc_rate | 2026-03-21T03:06:30+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_qwen3.5_4b |
| qwen3.5:4b | daedalmap_json_discipline_pass_rate | 0.6 | 60.0 | pass_rate | 2026-03-21T03:06:30+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_qwen3.5_4b |
| qwen3.5:4b | daedalmap_json_discipline_source_hit_rate | 1.0 | 100.0 | source_hit_rate | 2026-03-21T03:06:30+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_qwen3.5_4b |
| qwen3.5:4b | daedalmap_json_discipline_source_valid_rate | 1.0 | 100.0 | source_valid_rate | 2026-03-21T03:06:30+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_qwen3.5_4b |
| qwen3.5:4b | daedalmap_json_discipline_type_correct_rate | 0.6 | 60.0 | type_correct_rate | 2026-03-21T03:06:30+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_qwen3.5_4b |
| qwen3.5:4b | daedalmap_multi_source_json_valid_rate | 0.2 | 20.0 | json_valid_rate | 2026-03-21T03:10:30+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_qwen3.5_4b |
| qwen3.5:4b | daedalmap_multi_source_no_halluc_rate | 1.0 | 100.0 | no_halluc_rate | 2026-03-21T03:10:30+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_qwen3.5_4b |
| qwen3.5:4b | daedalmap_multi_source_pass_rate | 0.2 | 20.0 | pass_rate | 2026-03-21T03:10:30+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_qwen3.5_4b |
| qwen3.5:4b | daedalmap_multi_source_source_hit_rate | 1.0 | 100.0 | source_hit_rate | 2026-03-21T03:10:30+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_qwen3.5_4b |
| qwen3.5:4b | daedalmap_multi_source_source_valid_rate | 1.0 | 100.0 | source_valid_rate | 2026-03-21T03:10:30+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_qwen3.5_4b |
| qwen3.5:4b | daedalmap_multi_source_type_correct_rate | 0.2 | 20.0 | type_correct_rate | 2026-03-21T03:10:30+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_qwen3.5_4b |
| qwen3.5:4b | daedalmap_source_grounding_json_valid_rate | 0.25 | 25.0 | json_valid_rate | 2026-03-21T03:15:37+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_qwen3.5_4b |
| qwen3.5:4b | daedalmap_source_grounding_no_halluc_rate | 1.0 | 100.0 | no_halluc_rate | 2026-03-21T03:15:37+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_qwen3.5_4b |
| qwen3.5:4b | daedalmap_source_grounding_pass_rate | 0.25 | 25.0 | pass_rate | 2026-03-21T03:15:37+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_qwen3.5_4b |
| qwen3.5:4b | daedalmap_source_grounding_source_hit_rate | 1.0 | 100.0 | source_hit_rate | 2026-03-21T03:15:37+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_qwen3.5_4b |
| qwen3.5:4b | daedalmap_source_grounding_source_valid_rate | 1.0 | 100.0 | source_valid_rate | 2026-03-21T03:15:38+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_qwen3.5_4b |
| qwen3.5:4b | daedalmap_source_grounding_type_correct_rate | 0.25 | 25.0 | type_correct_rate | 2026-03-21T03:15:37+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_qwen3.5_4b |
| qwen3.5:4b | daedalmap_type_routing_json_valid_rate | 0.45 | 45.0 | json_valid_rate | 2026-03-21T03:19:57+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_qwen3.5_4b |
| qwen3.5:4b | daedalmap_type_routing_no_halluc_rate | 0.95 | 95.0 | no_halluc_rate | 2026-03-21T03:19:57+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_qwen3.5_4b |
| qwen3.5:4b | daedalmap_type_routing_pass_rate | 0.35 | 35.0 | pass_rate | 2026-03-21T03:19:57+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_qwen3.5_4b |
| qwen3.5:4b | daedalmap_type_routing_source_valid_rate | 1.0 | 100.0 | source_valid_rate | 2026-03-21T03:19:58+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_qwen3.5_4b |
| qwen3.5:4b | daedalmap_type_routing_type_correct_rate | 0.4 | 40.0 | type_correct_rate | 2026-03-21T03:19:57+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_qwen3.5_4b |
| qwen3.5:4b | gsm8k_flexible | 0.8 | 80.0 | exact_match,flexible-extract | 2026-03-15T06:39:01+00:00 | bench-reasoning | bench-reasoning_qwen3.5_4b_reasoning_q35_4b_nothink_v1 |
| qwen3.5:4b | gsm8k_strict | 0.8 | 80.0 | exact_match,strict-match | 2026-03-15T06:39:01+00:00 | bench-reasoning | bench-reasoning_qwen3.5_4b_reasoning_q35_4b_nothink_v1 |
| qwen3.5:9b | gsm8k_flexible | 0.8 | 80.0 | exact_match,flexible-extract | 2026-03-15T06:46:17+00:00 | bench-reasoning | bench-reasoning_qwen3.5_9b_reasoning_q35_9b_nothink_v1 |
| qwen3.5:9b | gsm8k_strict | 0.8 | 80.0 | exact_match,strict-match | 2026-03-15T06:46:17+00:00 | bench-reasoning | bench-reasoning_qwen3.5_9b_reasoning_q35_9b_nothink_v1 |
| qwen3.5:9b-q3km | daedalmap_catalog_discipline_json_valid_rate | 0.8 | 80.0 | json_valid_rate | 2026-03-21T03:47:02+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_qwen3.5_9b-q3km |
| qwen3.5:9b-q3km | daedalmap_catalog_discipline_no_halluc_rate | 0.5333333333333333 | 53.333333333333336 | no_halluc_rate | 2026-03-21T03:47:02+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_qwen3.5_9b-q3km |
| qwen3.5:9b-q3km | daedalmap_catalog_discipline_pass_rate | 0.3333333333333333 | 33.33333333333333 | pass_rate | 2026-03-21T03:47:02+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_qwen3.5_9b-q3km |
| qwen3.5:9b-q3km | daedalmap_catalog_discipline_type_correct_rate | 0.8 | 80.0 | type_correct_rate | 2026-03-21T03:47:02+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_qwen3.5_9b-q3km |
| qwen3.5:9b-q3km | daedalmap_geographic_precision_json_valid_rate | 0.06666666666666667 | 6.666666666666667 | json_valid_rate | 2026-03-21T03:53:55+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_qwen3.5_9b-q3km |
| qwen3.5:9b-q3km | daedalmap_geographic_precision_no_halluc_rate | 1.0 | 100.0 | no_halluc_rate | 2026-03-21T03:53:55+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_qwen3.5_9b-q3km |
| qwen3.5:9b-q3km | daedalmap_geographic_precision_pass_rate | 0.06666666666666667 | 6.666666666666667 | pass_rate | 2026-03-21T03:53:55+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_qwen3.5_9b-q3km |
| qwen3.5:9b-q3km | daedalmap_geographic_precision_source_hit_rate | 1.0 | 100.0 | source_hit_rate | 2026-03-21T03:53:55+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_qwen3.5_9b-q3km |
| qwen3.5:9b-q3km | daedalmap_geographic_precision_source_valid_rate | 1.0 | 100.0 | source_valid_rate | 2026-03-21T03:53:55+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_qwen3.5_9b-q3km |
| qwen3.5:9b-q3km | daedalmap_geographic_precision_type_correct_rate | 0.06666666666666667 | 6.666666666666667 | type_correct_rate | 2026-03-21T03:53:55+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_qwen3.5_9b-q3km |
| qwen3.5:9b-q3km | daedalmap_json_discipline_json_valid_rate | 0.6 | 60.0 | json_valid_rate | 2026-03-21T03:59:14+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_qwen3.5_9b-q3km |
| qwen3.5:9b-q3km | daedalmap_json_discipline_no_halluc_rate | 1.0 | 100.0 | no_halluc_rate | 2026-03-21T03:59:14+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_qwen3.5_9b-q3km |
| qwen3.5:9b-q3km | daedalmap_json_discipline_pass_rate | 0.6 | 60.0 | pass_rate | 2026-03-21T03:59:14+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_qwen3.5_9b-q3km |
| qwen3.5:9b-q3km | daedalmap_json_discipline_source_hit_rate | 1.0 | 100.0 | source_hit_rate | 2026-03-21T03:59:14+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_qwen3.5_9b-q3km |
| qwen3.5:9b-q3km | daedalmap_json_discipline_source_valid_rate | 1.0 | 100.0 | source_valid_rate | 2026-03-21T03:59:14+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_qwen3.5_9b-q3km |
| qwen3.5:9b-q3km | daedalmap_json_discipline_type_correct_rate | 0.6 | 60.0 | type_correct_rate | 2026-03-21T03:59:14+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_qwen3.5_9b-q3km |
| qwen3.5:9b-q3km | daedalmap_multi_source_json_valid_rate | 0.06666666666666667 | 6.666666666666667 | json_valid_rate | 2026-03-21T04:06:05+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_qwen3.5_9b-q3km |
| qwen3.5:9b-q3km | daedalmap_multi_source_no_halluc_rate | 1.0 | 100.0 | no_halluc_rate | 2026-03-21T04:06:05+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_qwen3.5_9b-q3km |
| qwen3.5:9b-q3km | daedalmap_multi_source_pass_rate | 0.06666666666666667 | 6.666666666666667 | pass_rate | 2026-03-21T04:06:05+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_qwen3.5_9b-q3km |
| qwen3.5:9b-q3km | daedalmap_multi_source_type_correct_rate | 0.06666666666666667 | 6.666666666666667 | type_correct_rate | 2026-03-21T04:06:05+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_qwen3.5_9b-q3km |
| qwen3.5:9b-q3km | daedalmap_source_grounding_json_valid_rate | 0.3 | 30.0 | json_valid_rate | 2026-03-21T04:14:48+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_qwen3.5_9b-q3km |
| qwen3.5:9b-q3km | daedalmap_source_grounding_no_halluc_rate | 1.0 | 100.0 | no_halluc_rate | 2026-03-21T04:14:48+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_qwen3.5_9b-q3km |
| qwen3.5:9b-q3km | daedalmap_source_grounding_pass_rate | 0.3 | 30.0 | pass_rate | 2026-03-21T04:14:48+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_qwen3.5_9b-q3km |
| qwen3.5:9b-q3km | daedalmap_source_grounding_source_hit_rate | 1.0 | 100.0 | source_hit_rate | 2026-03-21T04:14:48+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_qwen3.5_9b-q3km |
| qwen3.5:9b-q3km | daedalmap_source_grounding_source_valid_rate | 1.0 | 100.0 | source_valid_rate | 2026-03-21T04:14:48+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_qwen3.5_9b-q3km |
| qwen3.5:9b-q3km | daedalmap_source_grounding_type_correct_rate | 0.3 | 30.0 | type_correct_rate | 2026-03-21T04:14:48+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_qwen3.5_9b-q3km |
| qwen3.5:9b-q3km | daedalmap_type_routing_json_valid_rate | 0.6 | 60.0 | json_valid_rate | 2026-03-21T04:22:00+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_qwen3.5_9b-q3km |
| qwen3.5:9b-q3km | daedalmap_type_routing_no_halluc_rate | 0.95 | 95.0 | no_halluc_rate | 2026-03-21T04:22:00+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_qwen3.5_9b-q3km |
| qwen3.5:9b-q3km | daedalmap_type_routing_pass_rate | 0.55 | 55.00000000000001 | pass_rate | 2026-03-21T04:22:00+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_qwen3.5_9b-q3km |
| qwen3.5:9b-q3km | daedalmap_type_routing_source_hit_rate | 1.0 | 100.0 | source_hit_rate | 2026-03-21T04:22:00+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_qwen3.5_9b-q3km |
| qwen3.5:9b-q3km | daedalmap_type_routing_source_valid_rate | 1.0 | 100.0 | source_valid_rate | 2026-03-21T04:22:00+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_qwen3.5_9b-q3km |
| qwen3.5:9b-q3km | daedalmap_type_routing_type_correct_rate | 0.6 | 60.0 | type_correct_rate | 2026-03-21T04:22:00+00:00 | bench-daedalmap | daedalmap_single_gpu_large_full_v1_qwen3.5_9b-q3km |
| qwen3.5:9b-q3km | gsm8k_flexible | 0.0 | 0.0 | exact_match,flexible-extract | 2026-03-12T05:54:36+00:00 | bench-reasoning | bench-reasoning_qwen3.5_9b-q3km_rr_l100_c05_20260311_221559_p11438 |
| qwen3.5:9b-q3km | gsm8k_strict | 0.0 | 0.0 | exact_match,strict-match | 2026-03-12T05:54:36+00:00 | bench-reasoning | bench-reasoning_qwen3.5_9b-q3km_rr_l100_c05_20260311_221559_p11438 |
| qwen3.6:27b | bbh | 0.8925925925925926 | 89.25925925925927 | exact_match,get-answer | 2026-04-25T05:54:41+00:00 | bench-reasoning | qwen36_27b_l50_bbhdrop_v2 |
| qwen3.6:27b | drop_em | 0.84 | 84.0 | em,none | 2026-04-25T05:55:36+00:00 | bench-reasoning | qwen36_27b_l50_bbhdrop_v2 |
| qwen3.6:27b | drop_f1 | 0.8834000000000001 | 88.34 | f1,none | 2026-04-25T05:55:36+00:00 | bench-reasoning | qwen36_27b_l50_bbhdrop_v2 |
| qwen3.6:35b-a3b | bbh | 0.8762962962962964 | 87.62962962962963 | exact_match,get-answer | 2026-04-25T06:40:19+00:00 | bench-reasoning | qwen36_35b_l50_bbhdrop_v2 |
| qwen3.6:35b-a3b | drop_em | 0.78 | 78.0 | em,none | 2026-04-25T06:40:58+00:00 | bench-reasoning | qwen36_35b_l50_bbhdrop_v2 |
| qwen3.6:35b-a3b | drop_f1 | 0.8302 | 83.02000000000001 | f1,none | 2026-04-25T06:40:58+00:00 | bench-reasoning | qwen36_35b_l50_bbhdrop_v2 |
| qwen3:1.7b | bbh | 0.0 | 0.0 | exact_match,get-answer | 2026-03-18T18:30:08+00:00 | bench-reasoning | bench-reasoning_qwen3_1.7b_small_qwen3_1p7b_reasoning_l100_v1 |
| qwen3:1.7b | daedalmap_catalog_discipline_json_valid_rate | 0.5333333333333333 | 53.333333333333336 | json_valid_rate | 2026-03-21T02:57:34+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_qwen3_1.7b |
| qwen3:1.7b | daedalmap_catalog_discipline_no_halluc_rate | 0.6666666666666666 | 66.66666666666666 | no_halluc_rate | 2026-03-21T02:57:34+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_qwen3_1.7b |
| qwen3:1.7b | daedalmap_catalog_discipline_pass_rate | 0.26666666666666666 | 26.666666666666668 | pass_rate | 2026-03-21T02:57:34+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_qwen3_1.7b |
| qwen3:1.7b | daedalmap_catalog_discipline_source_valid_rate | 0.5 | 50.0 | source_valid_rate | 2026-03-21T02:57:35+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_qwen3_1.7b |
| qwen3:1.7b | daedalmap_catalog_discipline_type_correct_rate | 0.4 | 40.0 | type_correct_rate | 2026-03-21T02:57:34+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_qwen3_1.7b |
| qwen3:1.7b | daedalmap_geographic_precision_json_valid_rate | 0.6 | 60.0 | json_valid_rate | 2026-03-21T02:59:14+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_qwen3_1.7b |
| qwen3:1.7b | daedalmap_geographic_precision_no_halluc_rate | 1.0 | 100.0 | no_halluc_rate | 2026-03-21T02:59:14+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_qwen3_1.7b |
| qwen3:1.7b | daedalmap_geographic_precision_pass_rate | 0.5333333333333333 | 53.333333333333336 | pass_rate | 2026-03-21T02:59:14+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_qwen3_1.7b |
| qwen3:1.7b | daedalmap_geographic_precision_source_hit_rate | 0.8888888888888888 | 88.88888888888889 | source_hit_rate | 2026-03-21T02:59:14+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_qwen3_1.7b |
| qwen3:1.7b | daedalmap_geographic_precision_source_valid_rate | 1.0 | 100.0 | source_valid_rate | 2026-03-21T02:59:15+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_qwen3_1.7b |
| qwen3:1.7b | daedalmap_geographic_precision_type_correct_rate | 0.6 | 60.0 | type_correct_rate | 2026-03-21T02:59:14+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_qwen3_1.7b |
| qwen3:1.7b | daedalmap_json_discipline_json_valid_rate | 0.7333333333333333 | 73.33333333333333 | json_valid_rate | 2026-03-21T03:00:31+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_qwen3_1.7b |
| qwen3:1.7b | daedalmap_json_discipline_no_halluc_rate | 1.0 | 100.0 | no_halluc_rate | 2026-03-21T03:00:31+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_qwen3_1.7b |
| qwen3:1.7b | daedalmap_json_discipline_pass_rate | 0.6666666666666666 | 66.66666666666666 | pass_rate | 2026-03-21T03:00:31+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_qwen3_1.7b |
| qwen3:1.7b | daedalmap_json_discipline_source_hit_rate | 1.0 | 100.0 | source_hit_rate | 2026-03-21T03:00:32+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_qwen3_1.7b |
| qwen3:1.7b | daedalmap_json_discipline_source_valid_rate | 1.0 | 100.0 | source_valid_rate | 2026-03-21T03:00:32+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_qwen3_1.7b |
| qwen3:1.7b | daedalmap_json_discipline_type_correct_rate | 0.6666666666666666 | 66.66666666666666 | type_correct_rate | 2026-03-21T03:00:31+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_qwen3_1.7b |
| qwen3:1.7b | daedalmap_multi_source_json_valid_rate | 0.06666666666666667 | 6.666666666666667 | json_valid_rate | 2026-03-21T03:02:23+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_qwen3_1.7b |
| qwen3:1.7b | daedalmap_multi_source_no_halluc_rate | 1.0 | 100.0 | no_halluc_rate | 2026-03-21T03:02:23+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_qwen3_1.7b |
| qwen3:1.7b | daedalmap_multi_source_pass_rate | 0.06666666666666667 | 6.666666666666667 | pass_rate | 2026-03-21T03:02:23+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_qwen3_1.7b |
| qwen3:1.7b | daedalmap_multi_source_source_hit_rate | 1.0 | 100.0 | source_hit_rate | 2026-03-21T03:02:23+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_qwen3_1.7b |
| qwen3:1.7b | daedalmap_multi_source_source_valid_rate | 1.0 | 100.0 | source_valid_rate | 2026-03-21T03:02:23+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_qwen3_1.7b |
| qwen3:1.7b | daedalmap_multi_source_type_correct_rate | 0.06666666666666667 | 6.666666666666667 | type_correct_rate | 2026-03-21T03:02:23+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_qwen3_1.7b |
| qwen3:1.7b | daedalmap_source_grounding_json_valid_rate | 0.65 | 65.0 | json_valid_rate | 2026-03-21T03:04:32+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_qwen3_1.7b |
| qwen3:1.7b | daedalmap_source_grounding_no_halluc_rate | 1.0 | 100.0 | no_halluc_rate | 2026-03-21T03:04:32+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_qwen3_1.7b |
| qwen3:1.7b | daedalmap_source_grounding_pass_rate | 0.65 | 65.0 | pass_rate | 2026-03-21T03:04:32+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_qwen3_1.7b |
| qwen3:1.7b | daedalmap_source_grounding_source_hit_rate | 1.0 | 100.0 | source_hit_rate | 2026-03-21T03:04:32+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_qwen3_1.7b |
| qwen3:1.7b | daedalmap_source_grounding_source_valid_rate | 1.0 | 100.0 | source_valid_rate | 2026-03-21T03:04:32+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_qwen3_1.7b |
| qwen3:1.7b | daedalmap_source_grounding_type_correct_rate | 0.65 | 65.0 | type_correct_rate | 2026-03-21T03:04:32+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_qwen3_1.7b |
| qwen3:1.7b | daedalmap_type_routing_json_valid_rate | 0.6 | 60.0 | json_valid_rate | 2026-03-21T03:06:20+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_qwen3_1.7b |
| qwen3:1.7b | daedalmap_type_routing_no_halluc_rate | 0.95 | 95.0 | no_halluc_rate | 2026-03-21T03:06:20+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_qwen3_1.7b |
| qwen3:1.7b | daedalmap_type_routing_pass_rate | 0.45 | 45.0 | pass_rate | 2026-03-21T03:06:20+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_qwen3_1.7b |
| qwen3:1.7b | daedalmap_type_routing_source_hit_rate | 1.0 | 100.0 | source_hit_rate | 2026-03-21T03:06:20+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_qwen3_1.7b |
| qwen3:1.7b | daedalmap_type_routing_source_valid_rate | 1.0 | 100.0 | source_valid_rate | 2026-03-21T03:06:21+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_qwen3_1.7b |
| qwen3:1.7b | daedalmap_type_routing_type_correct_rate | 0.5 | 50.0 | type_correct_rate | 2026-03-21T03:06:20+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_qwen3_1.7b |
| qwen3:1.7b | drop_em | 0.02 | 2.0 | em,none | 2026-03-18T18:31:24+00:00 | bench-reasoning | bench-reasoning_qwen3_1.7b_small_qwen3_1p7b_reasoning_l100_v1 |
| qwen3:1.7b | drop_f1 | 0.1661 | 16.61 | f1,none | 2026-03-18T18:31:24+00:00 | bench-reasoning | bench-reasoning_qwen3_1.7b_small_qwen3_1p7b_reasoning_l100_v1 |
| qwen3:1.7b | gsm8k_flexible | 0.46 | 46.0 | exact_match,flexible-extract | 2026-03-18T17:55:04+00:00 | bench-reasoning | bench-reasoning_qwen3_1.7b_small_qwen3_1p7b_reasoning_l100_v1 |
| qwen3:1.7b | gsm8k_strict | 0.44 | 44.0 | exact_match,strict-match | 2026-03-18T17:55:04+00:00 | bench-reasoning | bench-reasoning_qwen3_1.7b_small_qwen3_1p7b_reasoning_l100_v1 |
| qwen3:8b | bbh | 0.6244444444444445 | 62.44444444444445 | exact_match,get-answer | 2026-03-16T08:44:34+00:00 | bench-reasoning | bench-reasoning_qwen3_8b_reasoning_qwen3_8b_nothink_l50_v1 |
| qwen3:8b | drop_em | 0.18 | 18.0 | em,none | 2026-03-16T08:45:40+00:00 | bench-reasoning | bench-reasoning_qwen3_8b_reasoning_qwen3_8b_nothink_l50_v1 |
| qwen3:8b | drop_f1 | 0.3848000000000001 | 38.48000000000001 | f1,none | 2026-03-16T08:45:40+00:00 | bench-reasoning | bench-reasoning_qwen3_8b_reasoning_qwen3_8b_nothink_l50_v1 |
| qwen3:8b | gsm8k_flexible | 0.9 | 90.0 | exact_match,flexible-extract | 2026-03-15T22:40:05+00:00 | bench-reasoning | bench-reasoning_qwen3_8b_reasoning_qwen3_8b_nothink_l50_v1 |
| qwen3:8b | gsm8k_strict | 0.9 | 90.0 | exact_match,strict-match | 2026-03-15T22:40:05+00:00 | bench-reasoning | bench-reasoning_qwen3_8b_reasoning_qwen3_8b_nothink_l50_v1 |
| smollm3:3b | bbh | 0.6677777777777778 | 66.77777777777779 | exact_match,get-answer | 2026-03-18T10:07:52+00:00 | bench-reasoning | bench-reasoning_smollm3_3b_small_smollm3_reasoning_l100_v1 |
| smollm3:3b | custom_ambiguity_handling | 0.0 | 0.0 | score | 2026-04-28T18:06:52+00:00 | bench-pipeline | smollm3_3b_pipeline_v2_rerun |
| smollm3:3b | custom_command_safety | 1.0 | 100.0 | score | 2026-04-28T18:06:35+00:00 | bench-pipeline | smollm3_3b_pipeline_v2_rerun |
| smollm3:3b | custom_json_schema_strict | 0.15384615384615385 | 15.384615384615385 | score | 2026-04-28T18:06:29+00:00 | bench-pipeline | smollm3_3b_pipeline_v2_rerun |
| smollm3:3b | custom_long_context_extract | 0.9285714285714286 | 92.85714285714286 | score | 2026-04-28T18:07:09+00:00 | bench-pipeline | smollm3_3b_pipeline_v2_rerun |
| smollm3:3b | custom_orchestration_tradeoff | 0.5833333333333334 | 58.333333333333336 | score | 2026-04-28T18:07:02+00:00 | bench-pipeline | smollm3_3b_pipeline_v2_rerun |
| smollm3:3b | custom_tool_plan_sequence | 0.8 | 80.0 | score | 2026-04-28T18:06:58+00:00 | bench-pipeline | smollm3_3b_pipeline_v2_rerun |
| smollm3:3b | daedalmap_catalog_discipline_json_valid_rate | 1.0 | 100.0 | json_valid_rate | 2026-03-21T02:56:41+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_smollm3_3b |
| smollm3:3b | daedalmap_catalog_discipline_no_halluc_rate | 0.3333333333333333 | 33.33333333333333 | no_halluc_rate | 2026-03-21T02:56:41+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_smollm3_3b |
| smollm3:3b | daedalmap_catalog_discipline_pass_rate | 0.0 | 0.0 | pass_rate | 2026-03-21T02:56:40+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_smollm3_3b |
| smollm3:3b | daedalmap_catalog_discipline_source_valid_rate | 0.5454545454545454 | 54.54545454545454 | source_valid_rate | 2026-03-21T02:56:41+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_smollm3_3b |
| smollm3:3b | daedalmap_catalog_discipline_type_correct_rate | 0.0 | 0.0 | type_correct_rate | 2026-03-21T02:56:41+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_smollm3_3b |
| smollm3:3b | daedalmap_geographic_precision_json_valid_rate | 0.9333333333333333 | 93.33333333333333 | json_valid_rate | 2026-03-21T02:57:22+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_smollm3_3b |
| smollm3:3b | daedalmap_geographic_precision_no_halluc_rate | 1.0 | 100.0 | no_halluc_rate | 2026-03-21T02:57:22+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_smollm3_3b |
| smollm3:3b | daedalmap_geographic_precision_pass_rate | 0.7333333333333333 | 73.33333333333333 | pass_rate | 2026-03-21T02:57:22+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_smollm3_3b |
| smollm3:3b | daedalmap_geographic_precision_source_hit_rate | 0.7857142857142857 | 78.57142857142857 | source_hit_rate | 2026-03-21T02:57:22+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_smollm3_3b |
| smollm3:3b | daedalmap_geographic_precision_source_valid_rate | 0.7857142857142857 | 78.57142857142857 | source_valid_rate | 2026-03-21T02:57:22+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_smollm3_3b |
| smollm3:3b | daedalmap_geographic_precision_type_correct_rate | 0.9333333333333333 | 93.33333333333333 | type_correct_rate | 2026-03-21T02:57:22+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_smollm3_3b |
| smollm3:3b | daedalmap_json_discipline_json_valid_rate | 1.0 | 100.0 | json_valid_rate | 2026-03-21T02:57:43+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_smollm3_3b |
| smollm3:3b | daedalmap_json_discipline_no_halluc_rate | 1.0 | 100.0 | no_halluc_rate | 2026-03-21T02:57:43+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_smollm3_3b |
| smollm3:3b | daedalmap_json_discipline_pass_rate | 0.7333333333333333 | 73.33333333333333 | pass_rate | 2026-03-21T02:57:43+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_smollm3_3b |
| smollm3:3b | daedalmap_json_discipline_source_hit_rate | 0.8571428571428571 | 85.71428571428571 | source_hit_rate | 2026-03-21T02:57:43+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_smollm3_3b |
| smollm3:3b | daedalmap_json_discipline_source_valid_rate | 0.8888888888888888 | 88.88888888888889 | source_valid_rate | 2026-03-21T02:57:43+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_smollm3_3b |
| smollm3:3b | daedalmap_json_discipline_type_correct_rate | 0.8 | 80.0 | type_correct_rate | 2026-03-21T02:57:43+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_smollm3_3b |
| smollm3:3b | daedalmap_multi_source_json_valid_rate | 0.9333333333333333 | 93.33333333333333 | json_valid_rate | 2026-03-21T02:58:29+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_smollm3_3b |
| smollm3:3b | daedalmap_multi_source_no_halluc_rate | 1.0 | 100.0 | no_halluc_rate | 2026-03-21T02:58:29+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_smollm3_3b |
| smollm3:3b | daedalmap_multi_source_pass_rate | 0.7333333333333333 | 73.33333333333333 | pass_rate | 2026-03-21T02:58:29+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_smollm3_3b |
| smollm3:3b | daedalmap_multi_source_source_hit_rate | 0.8571428571428571 | 85.71428571428571 | source_hit_rate | 2026-03-21T02:58:29+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_smollm3_3b |
| smollm3:3b | daedalmap_multi_source_source_valid_rate | 0.7857142857142857 | 78.57142857142857 | source_valid_rate | 2026-03-21T02:58:29+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_smollm3_3b |
| smollm3:3b | daedalmap_multi_source_type_correct_rate | 0.9333333333333333 | 93.33333333333333 | type_correct_rate | 2026-03-21T02:58:29+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_smollm3_3b |
| smollm3:3b | daedalmap_source_grounding_json_valid_rate | 0.95 | 95.0 | json_valid_rate | 2026-03-21T02:59:03+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_smollm3_3b |
| smollm3:3b | daedalmap_source_grounding_no_halluc_rate | 0.95 | 95.0 | no_halluc_rate | 2026-03-21T02:59:03+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_smollm3_3b |
| smollm3:3b | daedalmap_source_grounding_pass_rate | 0.75 | 75.0 | pass_rate | 2026-03-21T02:59:03+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_smollm3_3b |
| smollm3:3b | daedalmap_source_grounding_source_hit_rate | 0.7894736842105263 | 78.94736842105263 | source_hit_rate | 2026-03-21T02:59:03+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_smollm3_3b |
| smollm3:3b | daedalmap_source_grounding_source_valid_rate | 0.8421052631578947 | 84.21052631578947 | source_valid_rate | 2026-03-21T02:59:03+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_smollm3_3b |
| smollm3:3b | daedalmap_source_grounding_type_correct_rate | 0.95 | 95.0 | type_correct_rate | 2026-03-21T02:59:03+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_smollm3_3b |
| smollm3:3b | daedalmap_type_routing_json_valid_rate | 1.0 | 100.0 | json_valid_rate | 2026-03-21T02:59:45+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_smollm3_3b |
| smollm3:3b | daedalmap_type_routing_no_halluc_rate | 0.95 | 95.0 | no_halluc_rate | 2026-03-21T02:59:45+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_smollm3_3b |
| smollm3:3b | daedalmap_type_routing_pass_rate | 0.45 | 45.0 | pass_rate | 2026-03-21T02:59:45+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_smollm3_3b |
| smollm3:3b | daedalmap_type_routing_source_hit_rate | 0.5 | 50.0 | source_hit_rate | 2026-03-21T02:59:45+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_smollm3_3b |
| smollm3:3b | daedalmap_type_routing_source_valid_rate | 0.75 | 75.0 | source_valid_rate | 2026-03-21T02:59:45+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_smollm3_3b |
| smollm3:3b | daedalmap_type_routing_type_correct_rate | 0.55 | 55.00000000000001 | type_correct_rate | 2026-03-21T02:59:45+00:00 | bench-daedalmap | daedalmap_small_models_full_v1_smollm3_3b |
| smollm3:3b | drop_em | 0.19 | 19.0 | em,none | 2026-03-18T10:08:48+00:00 | bench-reasoning | bench-reasoning_smollm3_3b_small_smollm3_reasoning_l100_v1 |
| smollm3:3b | drop_f1 | 0.3302000000000001 | 33.02000000000001 | f1,none | 2026-03-18T10:08:48+00:00 | bench-reasoning | bench-reasoning_smollm3_3b_small_smollm3_reasoning_l100_v1 |
| smollm3:3b | gsm8k_flexible | 0.79 | 79.0 | exact_match,flexible-extract | 2026-03-18T05:59:56+00:00 | bench-reasoning | bench-reasoning_smollm3_3b_small_smollm3_reasoning_l100_v1 |
| smollm3:3b | gsm8k_strict | 0.79 | 79.0 | exact_match,strict-match | 2026-03-18T05:59:56+00:00 | bench-reasoning | bench-reasoning_smollm3_3b_small_smollm3_reasoning_l100_v1 |

## Recent Runs

| Run At | Model | Test ID | Score | Score % | Metric | Harness | Suite | Run ID |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-06-07T21:47:58+00:00 | gemma-4:e4b | drop_em | 0.3 | 30.0 | em,none | bench-reasoning | campaign_e4b_reasoning | 8ced1cd8-8a8a-40ce-a589-ebbb9daf9703 |
| 2026-06-07T21:47:58+00:00 | gemma-4:e4b | drop_f1 | 0.307 | 30.7 | f1,none | bench-reasoning | campaign_e4b_reasoning | 20640bd3-6350-4ab9-aa34-2be4b8a90fed |
| 2026-06-07T21:46:05+00:00 | gemma-4:e4b | bbh | 0.08148148148148149 | 8.148148148148149 | exact_match,get-answer | bench-reasoning | campaign_e4b_reasoning | 3b74c0d9-22d0-44af-8bb0-6eb766122dc7 |
| 2026-06-07T21:02:58+00:00 | gemma-4:e2b | drop_em | 0.0 | 0.0 | em,none | bench-reasoning | campaign_e2b_reasoning | 6a32de28-55eb-4d43-9249-7b328a1ea66c |
| 2026-06-07T21:02:58+00:00 | gemma-4:e2b | drop_f1 | 0.0 | 0.0 | f1,none | bench-reasoning | campaign_e2b_reasoning | 22d14948-2b7a-4296-aac2-b5fc3fc4a60f |
| 2026-06-07T21:00:37+00:00 | gemma-4:e2b | bbh | 0.12222222222222222 | 12.222222222222221 | exact_match,get-answer | bench-reasoning | campaign_e2b_reasoning | 5254fc7a-265d-4fb8-a4c2-036b97c71fa7 |
| 2026-06-07T20:27:34+00:00 | gemma-4:31b | drop_em | 0.6 | 60.0 | em,none | bench-reasoning | campaign_31b_reasoning | b3c4cf1a-4357-4743-be5a-e3468b5e6f75 |
| 2026-06-07T20:27:34+00:00 | gemma-4:31b | drop_f1 | 0.727 | 72.7 | f1,none | bench-reasoning | campaign_31b_reasoning | 53bea4d0-e6f2-46f3-8eb4-2526f7e0a0a6 |
| 2026-06-07T20:27:04+00:00 | gemma-4:31b | bbh | 0.8703703703703703 | 87.03703703703704 | exact_match,get-answer | bench-reasoning | campaign_31b_reasoning | 052e0485-0067-427f-a7dd-d59b599509bc |
| 2026-06-07T20:17:59+00:00 | gemma-4:31b | gsm8k_strict | 0.9 | 90.0 | exact_match,strict-match | bench-reasoning | campaign_31b_reasoning | 87563261-9bb3-4950-8e45-eb730fcf040d |
| 2026-06-07T20:17:59+00:00 | gemma-4:31b | gsm8k_flexible | 0.9 | 90.0 | exact_match,flexible-extract | bench-reasoning | campaign_31b_reasoning | 810c746f-b484-4e25-ac85-d377f347f262 |
| 2026-06-07T20:17:12+00:00 | gemma-4:26b-a4b | drop_em | 0.6 | 60.0 | em,none | bench-reasoning | campaign_26b_reasoning | 1f312a9d-8c06-4f45-866e-0a4492351f52 |
| 2026-06-07T20:17:12+00:00 | gemma-4:26b-a4b | drop_f1 | 0.727 | 72.7 | f1,none | bench-reasoning | campaign_26b_reasoning | 69841f2e-4c13-4992-bc25-dfdb634fe479 |
| 2026-06-07T20:16:42+00:00 | gemma-4:26b-a4b | bbh | 0.8703703703703703 | 87.03703703703704 | exact_match,get-answer | bench-reasoning | campaign_26b_reasoning | dd811a20-723e-4ce2-90ce-3dbf5c1d4354 |
| 2026-06-07T20:08:59+00:00 | gemma-4:e4b | gsm8k_strict | 0.2 | 20.0 | exact_match,strict-match | bench-reasoning | campaign_e4b_reasoning | a5996343-9083-4a3e-9b76-50768ab768f2 |
| 2026-06-07T20:08:59+00:00 | gemma-4:e4b | gsm8k_flexible | 0.6 | 60.0 | exact_match,flexible-extract | bench-reasoning | campaign_e4b_reasoning | 70905887-2c13-4262-9cae-44d1d40ec69e |
| 2026-06-07T20:08:35+00:00 | gemma-4:e2b | gsm8k_strict | 0.5 | 50.0 | exact_match,strict-match | bench-reasoning | campaign_e2b_reasoning | 97592235-d717-4916-9261-c25d8dfb06e2 |
| 2026-06-07T20:08:35+00:00 | gemma-4:e2b | gsm8k_flexible | 0.6 | 60.0 | exact_match,flexible-extract | bench-reasoning | campaign_e2b_reasoning | d29a6d8b-e33f-4265-b7da-5cba0f815d11 |
| 2026-06-07T20:07:38+00:00 | gemma-4:26b-a4b | gsm8k_flexible | 0.9 | 90.0 | exact_match,flexible-extract | bench-reasoning | campaign_26b_reasoning | 61b02d20-a04c-4b06-a465-6c2c2c640ff1 |
| 2026-06-07T20:07:37+00:00 | gemma-4:26b-a4b | gsm8k_strict | 0.9 | 90.0 | exact_match,strict-match | bench-reasoning | campaign_26b_reasoning | 715c3696-bb29-4695-89de-64c18752677b |
| 2026-06-07T08:44:45+00:00 | gemma-4:26b-a4b | bbh | 0.8666666666666667 | 86.66666666666667 | exact_match,get-answer | bench-reasoning | gemma4_26b_bbh_l5_budget0 | b4fe333e-5204-41a8-8d68-f5bfa19a6a15 |
| 2026-06-07T08:40:29+00:00 | gemma-4:12b | drop_em | 0.6 | 60.0 | em,none | bench-reasoning | gemma4_12b_drop_l5_budget0 | 797d12e2-2a5e-484d-9978-efec3292c51e |
| 2026-06-07T08:40:29+00:00 | gemma-4:12b | drop_f1 | 0.7 | 70.0 | f1,none | bench-reasoning | gemma4_12b_drop_l5_budget0 | 2e8bd4e2-e075-48c9-8670-2915c1d8ddbd |
| 2026-06-06T23:52:14+00:00 | gemma-4:12b | bbh | 0.24444444444444444 | 24.444444444444443 | exact_match,get-answer | bench-reasoning | gemma4_12b_think1024_bbh_l5 | 2ce58381-0600-474a-9ae1-9ddd3539b085 |
| 2026-06-06T22:52:06+00:00 | gemma-4:12b | bbh | 0.8222222222222222 | 82.22222222222221 | exact_match,get-answer | bench-reasoning | gemma4_12b_nobudget_bbh_l5 | a8773fc6-f3f2-49f7-89a8-f0cae360d13f |
| 2026-06-06T20:11:17+00:00 | gemma-4:12b | gsm8k_strict | 0.0 | 0.0 | exact_match,strict-match | bench-reasoning | gemma4_12b_smoke_l5 | c91f1f04-f822-4478-aeb0-742f5fb67b10 |
| 2026-06-06T20:11:17+00:00 | gemma-4:12b | gsm8k_flexible | 0.2 | 20.0 | exact_match,flexible-extract | bench-reasoning | gemma4_12b_smoke_l5 | 4c5a0750-aa8c-4eab-9e68-367c5d772d12 |
| 2026-06-06T17:35:02+00:00 | gemma-4:12b | gsm8k_strict | 0.01 | 1.0 | exact_match,strict-match | bench-reasoning | gemma4_12b_l100_v2 | 7f25db20-4bb1-4e54-bdc6-901f79198c0c |
| 2026-06-06T17:35:02+00:00 | gemma-4:12b | gsm8k_flexible | 0.1 | 10.0 | exact_match,flexible-extract | bench-reasoning | gemma4_12b_l100_v2 | d7d42314-e003-420e-9516-939e73bb6bb8 |
| 2026-06-06T16:25:31+00:00 | gemma-4:12b | gsm8k_strict | 0.01 | 1.0 | exact_match,strict-match | bench-reasoning | gemma4_12b_l100_v1 | 3d2dfe13-025a-48a6-b5f4-1028ceca1e05 |
| 2026-06-06T16:25:31+00:00 | gemma-4:12b | gsm8k_flexible | 0.07 | 7.000000000000001 | exact_match,flexible-extract | bench-reasoning | gemma4_12b_l100_v1 | e2745187-21b9-48a6-9a34-71ef13d456b1 |
| 2026-04-29T04:48:28+00:00 | phi-4:14b | drop_em | 0.02 | 2.0 | em,none | bench-reasoning | phi4_l100_rerun_20260428 | 82007ddf-5e3b-4623-8d1d-7c766d052f4a |
| 2026-04-29T04:48:28+00:00 | phi-4:14b | drop_f1 | 0.0925 | 9.25 | f1,none | bench-reasoning | phi4_l100_rerun_20260428 | aab9a0c1-f84f-4ae2-90be-40e00422c613 |
| 2026-04-29T04:46:26+00:00 | phi-4:14b | bbh | 0.577037037037037 | 57.7037037037037 | exact_match,get-answer | bench-reasoning | phi4_l100_rerun_20260428 | 85c005f8-310a-487e-85b3-005fd43f44d8 |
| 2026-04-28T18:39:09+00:00 | phi-4:14b | gsm8k_strict | 0.56 | 56.00000000000001 | exact_match,strict-match | bench-reasoning | phi4_l100_rerun_20260428 | 4d9cef92-e207-4e56-83b5-6d7118be35d3 |
| 2026-04-28T18:39:09+00:00 | phi-4:14b | gsm8k_flexible | 0.78 | 78.0 | exact_match,flexible-extract | bench-reasoning | phi4_l100_rerun_20260428 | af30fb55-8b4f-47a8-b87e-3b75e2a27f15 |
| 2026-04-28T18:07:09+00:00 | smollm3:3b | custom_long_context_extract | 0.9285714285714286 | 92.85714285714286 | score | bench-pipeline | smollm3_3b_pipeline_v2_rerun | 131a4271-faf3-4543-8b73-537af6a886d3 |
| 2026-04-28T18:07:02+00:00 | smollm3:3b | custom_orchestration_tradeoff | 0.5833333333333334 | 58.333333333333336 | score | bench-pipeline | smollm3_3b_pipeline_v2_rerun | 224b1ab7-2071-4dbf-9181-df2ad571f84d |
| 2026-04-28T18:06:58+00:00 | smollm3:3b | custom_tool_plan_sequence | 0.8 | 80.0 | score | bench-pipeline | smollm3_3b_pipeline_v2_rerun | a0465c51-266e-4fd3-ba21-d42b36080b6e |
| 2026-04-28T18:06:52+00:00 | smollm3:3b | custom_ambiguity_handling | 0.0 | 0.0 | score | bench-pipeline | smollm3_3b_pipeline_v2_rerun | b9279a50-b806-4974-8c83-c2cc3a0396a3 |
