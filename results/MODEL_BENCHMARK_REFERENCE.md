# Model Benchmark Reference

- Generated at: `2026-03-11T15:38:01.673078`
- Records file: `/home/bryan/llm_orchestration/shared/plans/shoulders/benchmarking/results/model_benchmark_records.jsonl`
- Status file: `/home/bryan/llm_orchestration/shared/plans/shoulders/benchmarking/benchmark_status.json`
- Total recorded runs: `32`

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
| Mistral-7B-Instruct-v0.3-Q4_K_M.gguf | bench_code_total_base | 0.481549815498155 | 48.1549815498155 | pass_rate_542_base | 2026-03-11T19:23:09+00:00 | bench-code | code_full_20260310_202111_partial2 |
| Mistral-7B-Instruct-v0.3-Q4_K_M.gguf | bench_code_total_plus | 0.4077490774907749 | 40.774907749077485 | pass_rate_542_plus | 2026-03-11T19:23:09+00:00 | bench-code | code_full_20260310_202111_partial2 |
| Mistral-7B-Instruct-v0.3-Q4_K_M.gguf | custom_worker_suite_total | 0.6835443037974683 | 68.35443037974683 | pass_rate_79 | 2026-03-11T06:47:32+00:00 | bench-pipeline | recovery_ckpt_hot5_20260310_partial3 |
| Qwen2.5-Coder-7B-Instruct-Q4_K_M.gguf | custom_worker_suite_total | 0.7341772151898734 | 73.41772151898735 | pass_rate_79 | 2026-03-11T06:44:32+00:00 | bench-pipeline | recovery_ckpt_hot5_20260310_partial3 |
| Qwen3.5-4B-Q4_K_M.gguf | bench_code_total_base | 0.5719557195571956 | 57.19557195571956 | pass_rate_542_base | 2026-03-11T21:41:09+00:00 | bench-code | code_full_20260310_202111_partial2 |
| Qwen3.5-4B-Q4_K_M.gguf | bench_code_total_plus | 0.5018450184501845 | 50.184501845018445 | pass_rate_542_plus | 2026-03-11T21:41:09+00:00 | bench-code | code_full_20260310_202111_partial2 |
| Qwen3.5-4B-Q4_K_M.gguf | custom_worker_suite_total | 0.6835443037974683 | 68.35443037974683 | pass_rate_79 | 2026-03-11T07:09:52+00:00 | bench-pipeline | recovery_ckpt_hot5_20260310_partial3 |
| Qwen3.5-9B-Q3_K_M.gguf | custom_worker_suite_total | 0.08860759493670886 | 8.860759493670885 | pass_rate_79 | 2026-03-11T01:46:21+00:00 | bench-pipeline | ab_prompt_B_20260310 |
| mistral:7b-instruct | custom_ambiguity_handling | 1.0 | 100.0 | clarification_rate | 2026-03-05T20:20:03.464691 | local_custom | local_custom_probe_v2 |
| qwen2.5-coder:14b | drop | 0.57 | 56.99999999999999 | f1,none | 2026-03-05T15:54:28.421925 | lm_eval | quick_triplet_l1_20260305 |
| qwen2.5-coder:14b | gsm8k | 1.0 | 100.0 | exact_match,flexible-extract | 2026-03-05T15:50:53.042159 | lm_eval | quick_triplet_l1_20260305 |
| qwen2.5-coder:32b | drop | 0.18 | 18.0 | f1,none | 2026-03-05T15:55:15.554964 | lm_eval | quick_triplet_l1_20260305 |
| qwen2.5-coder:32b | gsm8k | 0.0 | 0.0 | exact_match,flexible-extract | 2026-03-05T15:52:07.684619 | lm_eval | quick_triplet_l1_20260305 |
| qwen2.5-coder:7b | custom_json_schema_strict | 0.5 | 50.0 | schema_valid_rate | 2026-03-05T20:20:25.318139 | local_custom | local_custom_probe_v2 |
| qwen2.5-coder:7b | drop | 0.27 | 27.0 | f1,none | 2026-03-05T15:53:05.860807 | lm_eval | quick_triplet_l1_20260305 |
| qwen2.5-coder:7b | gsm8k | 1.0 | 100.0 | exact_match,flexible-extract | 2026-03-05T15:48:24.680621 | lm_eval | quick_triplet_l1_20260305 |
| qwen2.5:7b | bbh | 0.5555555555555556 |  | exact_match,get-answer | 2026-03-05T14:03:11.985279 | lm_eval | initial_matrix_20260305 |
| qwen2.5:7b | custom_command_safety | 1.0 | 100.0 | risk_detection_rate | 2026-03-05T20:20:27.293918 | local_custom | local_custom_probe_v2 |
| qwen2.5:7b | drop | 0.14875 |  | f1,none | 2026-03-05T13:57:56.869958 | lm_eval | initial_matrix_20260305 |
| qwen2.5:7b | gsm8k | 0.75 |  | exact_match,flexible-extract | 2026-03-05T13:57:07.002198 | lm_eval | initial_matrix_20260305 |

## Recent Runs

| Run At | Model | Test ID | Score | Score % | Metric | Harness | Suite | Run ID |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-03-11T21:41:09+00:00 | Qwen3.5-4B-Q4_K_M.gguf | bench_code_total_base | 0.5719557195571956 | 57.19557195571956 | pass_rate_542_base | bench-code | code_full_20260310_202111_partial2 | 4a4e4fc9-7e16-4c98-a27f-3f0bf01d9d21 |
| 2026-03-11T21:41:09+00:00 | Qwen3.5-4B-Q4_K_M.gguf | bench_code_total_plus | 0.5018450184501845 | 50.184501845018445 | pass_rate_542_plus | bench-code | code_full_20260310_202111_partial2 | a4bc0bec-4bd0-4c0a-9246-05e9b2a92eea |
| 2026-03-11T19:23:09+00:00 | Mistral-7B-Instruct-v0.3-Q4_K_M.gguf | bench_code_total_base | 0.481549815498155 | 48.1549815498155 | pass_rate_542_base | bench-code | code_full_20260310_202111_partial2 | 540c9fa2-dd7d-4aec-9ec6-8012a17eb44c |
| 2026-03-11T19:23:09+00:00 | Mistral-7B-Instruct-v0.3-Q4_K_M.gguf | bench_code_total_plus | 0.4077490774907749 | 40.774907749077485 | pass_rate_542_plus | bench-code | code_full_20260310_202111_partial2 | 2c8d79c3-538b-44c1-9e4f-062c1ec39912 |
| 2026-03-11T07:09:52+00:00 | Qwen3.5-4B-Q4_K_M.gguf | custom_worker_suite_total | 0.6835443037974683 | 68.35443037974683 | pass_rate_79 | bench-pipeline | recovery_ckpt_hot5_20260310_partial3 | 880a1560-1266-465e-bee9-a2988440f09c |
| 2026-03-11T06:47:32+00:00 | Mistral-7B-Instruct-v0.3-Q4_K_M.gguf | custom_worker_suite_total | 0.6835443037974683 | 68.35443037974683 | pass_rate_79 | bench-pipeline | recovery_ckpt_hot5_20260310_partial3 | c8c6a35f-cfb8-4231-958c-20e1e0f659a3 |
| 2026-03-11T06:44:32+00:00 | Qwen2.5-Coder-7B-Instruct-Q4_K_M.gguf | custom_worker_suite_total | 0.7341772151898734 | 73.41772151898735 | pass_rate_79 | bench-pipeline | recovery_ckpt_hot5_20260310_partial3 | 6cda6293-6cf6-4003-a0df-1df48930b0b9 |
| 2026-03-11T01:46:21+00:00 | Qwen3.5-9B-Q3_K_M.gguf | custom_worker_suite_total | 0.08860759493670886 | 8.860759493670885 | pass_rate_79 | bench-pipeline | ab_prompt_B_20260310 | 66450d27-c64e-4cac-8139-bdb3130567c0 |
| 2026-03-11T01:43:52+00:00 | Qwen3.5-9B-Q3_K_M.gguf | custom_worker_suite_total | 0.13924050632911392 | 13.924050632911392 | pass_rate_79 | bench-pipeline | ab_prompt_A_20260310 | 5543a79c-ba0b-44c9-8c33-e080e43f852e |
| 2026-03-11T01:29:11+00:00 | Qwen3.5-4B-Q4_K_M.gguf | custom_worker_suite_total | 0.17721518987341772 | 17.72151898734177 | pass_rate_79 | bench-pipeline | ab_prompt_B_20260310 | 920db72b-6dce-403f-ad50-c925d62516ea |
| 2026-03-11T01:16:10+00:00 | Qwen3.5-4B-Q4_K_M.gguf | custom_worker_suite_total | 0.6582278481012658 | 65.82278481012658 | pass_rate_79 | bench-pipeline | ab_prompt_A_20260310 | 28357907-94c3-464f-836e-895cfcd7930b |
| 2026-03-05T20:20:27.293918 | qwen2.5:7b | custom_command_safety | 1.0 | 100.0 | risk_detection_rate | local_custom | local_custom_probe_v2 | 1cb7950f-8eb7-4def-9a65-52f845b5591f |
| 2026-03-05T20:20:25.318139 | qwen2.5-coder:7b | custom_json_schema_strict | 0.5 | 50.0 | schema_valid_rate | local_custom | local_custom_probe_v2 | 73c96bcc-37ff-40dc-b2a5-872c71d74d1c |
| 2026-03-05T20:20:03.464691 | mistral:7b-instruct | custom_ambiguity_handling | 1.0 | 100.0 | clarification_rate | local_custom | local_custom_probe_v2 | 516e8b96-02b0-4ea8-9762-0e421db2667f |
| 2026-03-05T20:19:22.710360 | qwen2.5-coder:7b | custom_json_schema_strict | 1.0 | 100.0 | schema_valid_rate | local_custom | local_custom_probe | 9629b2e8-9ae8-4ef1-b9a7-81baef132300 |
| 2026-03-05T20:19:17.570056 | qwen2.5:7b | custom_command_safety | 0.5 | 50.0 | risk_detection_rate | local_custom | local_custom_probe | f523ca88-e821-4a3b-a878-be8147725afb |
| 2026-03-05T20:19:06.821533 | mistral:7b-instruct | custom_ambiguity_handling | 0.0 | 0.0 | clarification_rate | local_custom | local_custom_probe | b10efe59-e03c-49f4-973c-b1a99c53d214 |
| 2026-03-05T15:55:15.554964 | qwen2.5-coder:32b | drop | 0.18 | 18.0 | f1,none | lm_eval | quick_triplet_l1_20260305 | 145d6b3e-afc6-4f6e-94b7-f9b18b3b0674 |
| 2026-03-05T15:54:28.421925 | qwen2.5-coder:14b | drop | 0.57 | 56.99999999999999 | f1,none | lm_eval | quick_triplet_l1_20260305 | 03c2eeb4-9400-4266-a2b8-845254259673 |
| 2026-03-05T15:53:05.860807 | qwen2.5-coder:7b | drop | 0.27 | 27.0 | f1,none | lm_eval | quick_triplet_l1_20260305 | 68e3dba4-921c-4aa3-ba6e-7ad5a1b469ef |
| 2026-03-05T15:52:07.684619 | qwen2.5-coder:32b | gsm8k | 0.0 | 0.0 | exact_match,flexible-extract | lm_eval | quick_triplet_l1_20260305 | af2d18c9-0263-4357-ac5d-444aaf302ed5 |
| 2026-03-05T15:50:53.042159 | qwen2.5-coder:14b | gsm8k | 1.0 | 100.0 | exact_match,flexible-extract | lm_eval | quick_triplet_l1_20260305 | 87ed19f6-8afd-4eb3-9b7b-0c7a9c991fb6 |
| 2026-03-05T15:48:24.680621 | qwen2.5-coder:7b | gsm8k | 1.0 | 100.0 | exact_match,flexible-extract | lm_eval | quick_triplet_l1_20260305 | d6103acb-4cf7-4f52-b1e2-c1b65fcf8129 |
| 2026-03-05T15:37:21.397028 | qwen2.5-coder:7b | drop | 0.084 | 8.4 | f1,none | lm_eval | baseline_triplet_20260305 | 8920d5fd-db62-4db6-9644-a2d60df69830 |
| 2026-03-05T15:36:15.439452 | qwen2.5-coder:7b | gsm8k | 0.8 | 80.0 | exact_match,flexible-extract | lm_eval | baseline_triplet_20260305 | b5b68292-84c2-4bdc-8d4e-cdf4b86073a8 |
| 2026-03-05T15:20:51.509548 | qwen2.5-coder:7b | gsm8k | 0.8 | 80.0 | exact_match,flexible-extract | lm_eval | smoke_triplet_20260305 | 31eca519-2087-4bb5-b59f-f7e24fad6a7c |
| 2026-03-05T14:06:44.980759 | qwen2.5-coder:14b | drop | 0.09874999999999999 |  | f1,none | lm_eval | initial_matrix_20260305 | 61258339-5f12-432f-ad47-25dc6f6409fd |
| 2026-03-05T14:05:59.822246 | qwen2.5-coder:14b | gsm8k | 0.875 |  | exact_match,flexible-extract | lm_eval | initial_matrix_20260305 | 2e70a728-21a2-4d8f-b403-3abe33a205b8 |
| 2026-03-05T14:03:11.985279 | qwen2.5:7b | bbh | 0.5555555555555556 |  | exact_match,get-answer | lm_eval | initial_matrix_20260305 | 09af4827-1430-4d8a-b700-20e8d607c72b |
| 2026-03-05T13:57:56.869958 | qwen2.5:7b | drop | 0.14875 |  | f1,none | lm_eval | initial_matrix_20260305 | 33259072-ceca-4488-a903-9cefbded7ca0 |
| 2026-03-05T13:57:07.002198 | qwen2.5:7b | gsm8k | 0.75 |  | exact_match,flexible-extract | lm_eval | initial_matrix_20260305 | a26281b8-7cb9-44d3-8f70-d405cdda0e4e |
| 2026-03-05T13:51:40.845290 | qwen2.5:7b | gsm8k | 0.6666666666666666 |  | exact_match,flexible-extract | lm_eval | sanity_runner_patch | c647139c-9beb-49dc-8392-dcc7bc888b61 |
