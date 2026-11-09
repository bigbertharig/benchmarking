# Qwen3.6 27B versus Qwen3.8 27B: saved-run audit

Reviewed 2026-11-08 from saved ledger, lm-eval results and logged samples. No GPU jobs were run. These are Q4_K_M and UD-Q4_K_M GGUF runs on the rig, not official-weight reproductions. The runs differ in reasoning mode and generation budget, so the comparison is a workload observation rather than an isolated model-version experiment.

## Main finding

| Test | Qwen3.6 27B | Qwen3.8 27B | Reading |
| --- | ---: | ---: | --- |
| BBH strict, 1,350 | 91.56% | 41.63% | Strict extractor requires demonstrated answer phrase. |
| BBH flexible, 1,350 | 91.56% | 91.04% | Difference is 7 answers of 1,350 (0.52 points). |
| GSM8K flexible, 50 | 92% | 94% | Two percentage points is one question. |
| MMLU-Pro flexible, 280 | 79.29% | 81.07% | Small local advantage for 3.8. |
| IFEval strict prompt, 50 | 88% | 92% | Two questions; format matters here. |
| HumanEval+, 164 | 90.24% | 90.24% | Tie on short function generation. |
| MBPP+, 378 | 77.51% | 77.51% | Tie on short function generation. |
| Custom ambiguity handling, 13 | 6/13 | 12/13 | Promising 3.8 advantage; small hand-authored suite. |
| Custom JSON schema strict, 13 | 3/13 | 5/13 | Both poor in this run; inspect response failure modes. |
| Geoimport Brazil planning, one scored case | 81.82% | 96.97% | Promising application signal; one case cannot establish generality. |

BBH source campaigns: `campaign_qwen3_6_27b_reasoning_l50_20261022_024509` and `campaign_qwen38_reasoning_l50_20261017_011528`. Both use 27 BBH subtasks with 50 examples each and the same recorded system instruction SHA (`6498a50122a666e9b7f5ce13d56100b2523f65604658cd515d451de23ad18288`). Qwen3.6 used `--reasoning off`, no generation override and a 512-token registry default. Qwen3.8 used `--reasoning on`, `max_gen_toks=8192,until=</s>` and an 8192-token registry default. Its BBH run took 21,507 seconds versus 7,167 seconds for 3.6. The ~3x runtime difference cannot be attributed to model version alone.

In logged `boolean_expressions` samples, 45/50 Qwen3.8 answers were bare `True` or `False` and only 5 included the phrase expected by strict `get-answer`. One raw correct `False` was recorded as `filtered_resps: ["[invalid]"]`. Qwen3.6 supplied the phrase in all 50 cases. The saved Qwen3.8 thinking-off smoke scored 82.96% strict / 87.78% flexible (10 examples per subtask); thinking-on smoke scored 37.41% strict / 89.63% flexible. Qwen3.6 thinking-on smoke also had a strict/flexible split (56.67% / 81.11%). This supports a reasoning-mode and extractor interaction, not a demonstrated 3.8 reasoning collapse.

## Benchmark and Docker issues to address

1. `docker/bench-reasoning/run.sh` still labels current extraction-v5 runs with `COMPARISON_GROUP=lm-eval-0.4.11-reasoning-extract-v2` and methodology `2.0.0`. Config IDs distinguish versions, but the broad comparison group can lead consumers to mix different extraction semantics. Version comparison groups deliberately and preserve the old rows.
2. The Qwen3.8 BBH validated run was extracted with v4, while the Qwen3.6 run used v5. Qwen3.8's later v5 flexible rescore from logged samples still reads 91.04%; compare flexible rows with recorded config and source campaign, not the strict headline alone. In older rows `extractor_failure_count=667` means answers rescued by flexible scoring; in v5 its meaning is unreadable outputs (53 for this 3.8 run, 15 for 3.6). This field changed meaning without a schema change, so historical dashboards should not aggregate it across versions.
3. `docker/bench-reasoning/Dockerfile` pins `lm_eval[api]==0.4.11` and `transformers==5.3.0`, but `run.sh` patches installed lm-eval files at runtime. Those switches are part of the effective benchmark configuration and should be captured per run with patch hashes or immutable image digest; a Dockerfile tag alone does not define the protocol.
4. Flexible BBH counts a correct bare final answer, which is appropriate for a capability comparison, but strict format compliance should remain visible separately for workflows that require an exact output contract. The reported `unreadable` count is an extractor diagnostic, not a verified count of model reasoning failures.
5. Current short-code and 50-question public subsets cannot explain public agentic claims. Use the existing harness and application tasks as the next comparison tier, with multiple cases and fixed tool/runtime settings. The 13-case custom and one-case geoimport differences are leads, not replacement evidence.

## Next comparison after GPUs are free

Run a matched 3.6/3.8 matrix on the same harness image, prompt, context, token budget, quantization class and reasoning mode; keep both strict and flexible results and log samples. Start with a few representative application tasks and multi-step tool use, then expand only if the signal persists. Record latency and tokens alongside answer quality. Do not rerun the current 1,350-question BBH simply to reconcile the known extraction artifact.
