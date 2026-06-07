# Benchmark Lessons Learned

Debugging narratives, tuning histories, and operational findings from benchmarking local models.
This is the companion doc to [MODEL_LIBRARY.md](MODEL_LIBRARY.md) — scores and operational guidance
live there; investigation details and fix histories live here.

## Think-Tag Issue Deep Dive

### Two distinct mechanisms

Models that emit reasoning traces break standard benchmark harnesses in different ways.

**Type A: Chat template thinking mode** (fix: `--reasoning-budget 0` on llama-server)
- `qwen3:8b` — **fixed with --reasoning-budget 0** (2026-03-16). BBH 0.0→0.6244, DROP 0.0→0.3848 at limit 50
- `qwen3.5:4b` — **fixed with --reasoning-budget 0** (2026-03-15). Pipeline improved: command_safety 91.7%→100%, json_schema 0%→15.4%
- `qwen3.5:9b` — same mechanism, testing with fix in progress
- `qwen3.5:35b-a3b` — **fixed with --reasoning-budget 0** (2026-03-15). Was all-zero pipeline, now: command_safety 100%, long_context 100%, tool_plan 93.3%
- These models use the chat template's native thinking mode. llama-server puts reasoning in a separate `reasoning_content` API field, leaving `content` empty. The fix disables the template thinking feature server-side.

**Type B: Model-trained `<think>` tokens** (partial fix: `--patch-think-tag-strip`)
- `deepseek-r1:7b` — **confirmed: --reasoning-budget 0 does NOT help** (2026-03-15). Model still emits `<think>` tags in content. The thinking is baked into the model's generation vocabulary, not the chat template.
- `deepseek-r1:14b` — **partially fixed with --patch-think-tag-strip** (2026-03-16). BBH 0.0→0.5852 (limit 5). GSM8K 0.0→0.2. DROP still 0.0 (stop sequence `.` truncates inside think chains). The patch removes `\n\n` from API stop sequences, strips `<think>...</think>` from responses, then re-applies stopping client-side. Very slow: BBH limit 5 takes ~2.5 hours on split 1060s because full think chains generate.
- `deepseek-r1:32b` — **tested, confirmed broken**: HumanEval 9% (140/164 empty solutions), Mbpp 26% (226/378 empty), BBH 0.0 all subtasks, DROP em=0 f1=0. Only GSM8K flexible-extract works (0.8). Think tags get stripped by evalplus sanitizer and take actual code with them.
- Any model fine-tuned with reasoning traces (QwQ, R1-distill variants)

**Remaining issues for Type B**: DROP still broken (`.` stop sequence truncates inside think chains — same mechanism as BBH's `\n\n` but harder to fix since `.` is content-meaningful). Code generation still broken (evalplus sanitizer strips think tags + code together). The think-tag strip is a viable approach for tasks with non-content stop sequences (`\n\n`, `Q:`) but needs per-task stop sequence handling for others.

### Gemma 4 thinking mechanism (Type A variant)

Gemma 4 uses `<|channel>thought` prefix and `reasoning_content` API field. The server separates thinking into `reasoning_content`, answer into `content`. Both consume from `max_gen_toks`.

**Root cause of DROP 0.0**: Model outputs `<|channel>thought\n` prefix, and the `\n` stop fires before the answer. With the original `max_gen_toks: 64`, all tokens go to reasoning and content stays empty.

**Fix (2026-04-25)**: Two-part:
1. `--patch-think-tag-strip` removes stops from API calls, strips `<|channel>thought` prefix from content, falls back to `reasoning_content` when content is empty, and re-applies stops client-side
2. DROP `max_gen_toks` increased from 64 to 512 — gives thinking models room to reason + answer; non-thinking models still stop at `\n` quickly

**Progression of scores during fix development (E4B as test model)**:
- No fix: DROP 0.0
- Think-tag-strip only (max_gen_toks 64): DROP 0.0 (all tokens to reasoning)
- Think-tag-strip + max_gen_toks 512: DROP 0.533 (limit 50)
- Think-tag-strip + max_gen_toks 512 + reasoning_content fallback: DROP **0.722** (limit 100)

**BBH was NOT affected** — no regression from the patch on any Gemma 4 model.

### Qwen 3.6 thinking mechanism

Qwen 3.6 requires BOTH fixes:
1. `--reasoning-budget 0` in runtime args (suppresses thinking mode)
2. `--patch-think-tag-strip` in bench-reasoning (strips residual `<think></think>` tags from content)

`--reasoning-budget 0` alone is NOT sufficient: model still emits `<think></think>` wrapper in content, causing `\n\n` stop to truncate after `</think>` tag.

**Smoke test confirmation**: BBH 0.002→**0.911**, DROP 0.0→**0.80** with `--patch-think-tag-strip`.

### `--disable-thinking` does NOT work

lm-eval 0.4.11 doesn't support `extra_body` in model_args — the flag is silently ignored. Do not rely on it.

## Per-Model Tuning Histories

### DeepSeek-R1-14B tuning (2026-03-16)

Multiple tuning passes attempted:
- v1: boolean-only evaluator prompt ("So the answer is True/False") — forced wrong format on math tasks, all-zero GSM8K/DROP
- v2: general worker prompt — no improvement, GSM8K still 0
- Root cause: **structural, not prompt-tunable**. llama-server splits `<think>` into `reasoning_content` API field before any client-side patches see it. Model outputs math answers in LaTeX `\boxed{}` format instead of `#### number`. The `--patch-think-tag-strip` operates on `content` which is already clean (think content already separated by server).
- BBH 0.5852 was achieved only because BBH's `\n\n` stop was the specific stop removed in patch v2. Generalizing the patch to all stops didn't help other tasks.
- Very slow on split 1060s: full think chains generate for every request (~500-1000 tokens), BBH limit 5 took ~2.5 hours

### Phi-4-14B tuning (2026-03-16)

5 prompt iterations attempted:
- baseline (l50): GSM8K 0.70, BBH **0.283**, DROP 0.070 — best BBH score
- v2 (JSON hints + "keep output minimal"): GSM8K 0.80, BBH 0.044, DROP 0.384 — "minimal" killed CoT for BBH
- v3 ("think step by step"): GSM8K 1.0, BBH 0.1185, DROP 0.008 — markdown `\n\n` hits stop sequences
- v4 (stop-strip patch): GSM8K 1.0, BBH 0.0519, DROP 0.008 — stop removal let model ramble past answer
- v5 ("So the answer is" format): GSM8K 1.0, BBH 0.1259, DROP 0.0 — slight BBH gain, DROP destroyed

Root cause: Phi-4 formats CoT with markdown (numbered lists with `\n\n` between steps). BBH's `\n\n` stop truncates reasoning before the answer. Removing stops lets the model finish but it doesn't reliably follow the fewshot "So the answer is X" pattern for complex answer types. DROP's `.` stop has the same issue. Further prompt tuning shows diminishing/negative returns — baseline l50 scores remain the best overall balance.

### Qwen3.5-35B-A3B thinking mode (2026-03-15)

- llama-server detects the Qwen3.5 chat template's `<think>` support and enables `thinking = 1`
- model puts its entire answer into `reasoning_content` API field, leaving `content` empty
- **different from qwen3.5:4b/9b** which embed `<think>` tags directly in content text
- fix: launch with `--reasoning-budget 0` (server-side) or set `chat_template_kwargs.enable_thinking=false` per-request
- with thinking disabled, litmus test passes: clean reasoning (555), clean JSON, correct code (with markdown fences)
- first pipeline run was mostly 0% scores due to thinking mode
- first docker run used 4g memory limit (7B tier) — container was OOM-killed. Brain tier needs 11g/13g.

### E2B alias mismatch (2026-04-25)

`model_tuning_profiles.json` had `gemma-4:e2b-q8` but benchmarks used `gemma-4:e2b`, causing no system prompt resolution. Fixed by adding `gemma-4:e2b` alias entry.

### SmolLM3 alias prompt mismatch (2026-04-28)

The `smollm3:3b` pipeline rerun failed all six stages in 2 seconds with no result files. Root cause was the same alias class as E2B: `model_tuning_profiles.json` had `smollm3:3b` as `_alias_of` only, but `run_local_custom_task.py --require-model-prompt` does not follow aliases. Fixed by adding the explicit SmolLM3 system prompt to the alias entry. Rerun passed all six pipeline stages.

### Phi-4 split startup failure (2026-04-28)

Phase 3 of `l100_upgrade` did not reach benchmarks. The split runtime on GPUs 4+5 failed readiness on port 11438 after 300s. A retained debug launch showed llama.cpp's memory fitter warning that the requested full offload needed 586 MiB less GPU memory, then aborted fitting because `--n-gpu-layers 999` was explicitly set. Removing the forced layer count let llama.cpp auto-fit 41/41 layers and reach `/v1/models` after 282s. Do not force full offload for Phi-4 split reruns on 2x 1060; verify `/v1/models` before launching `bench-reasoning`.

### Gemma-4-12B thinking A/B test (2026-06-06)

Ran BBH l5 simultaneously on two runtimes: `--reasoning-budget 1024` (GPUs 1+3, port 11440) vs `--reasoning-budget 0` (GPUs 4+5, port 11441).

| Setting | BBH l5 | Runtime | Tokens/req |
|---------|--------|---------|------------|
| budget=0 (think off) | **0.822** | 2h25m | ~750 |
| budget=1024 (think on) | **0.244** | 3h57m | ~1800 |

**Root cause**: With thinking enabled, the model generates up to 1024 thinking tokens before the visible answer. BBH uses CoT fewshot with "So the answer is..." extraction. The thinking tokens consume generation budget, and many responses get truncated before the answer extraction point. 13 of 27 BBH subtasks scored 0.0 with thinking on (vs only 0 subtasks scoring 0.0 with thinking off).

**Implication**: For Gemma 4 12B benchmarking, always use `--reasoning-budget 0`. This differs from E4B/E2B where thinking mode is relatively benign (thinking doesn't trigger unless model emits `<|channel>thought`). The 12B model is more aggressive about using the thinking channel.

**GSM8K format issue**: GSM8K scored 0.10 flexible / 0.01 strict at limit 100. The model outputs `$18` instead of `#### 18`. Flexible-extract also fails because `$` prefix confuses the number extractor. This is a format mismatch, not a capability issue — the model's actual math answers are correct.

**2026-06-07 follow-up — 26B-A4B confirms family-wide issue**: Ran BBH l5 on Gemma 4 26B-A4B with `--reasoning-budget 0` + `--patch-think-tag-strip`. Scored **0.867** — vs the previous thinking-on score of **0.265** (l50, April 2026). This is a 3.3x improvement, matching the 12B pattern exactly. The April runs for all Gemma 4 models (E4B=0.316, E2B=0.131, 26B=0.265, 31B=0.339) were all run with thinking enabled and no `--reasoning-budget 0`. **All Gemma 4 BBH scores from April 2026 are invalid** — they need to be re-run with `--reasoning-budget 0`. Added `extra_args: ["--reasoning-budget", "0"]` to all Gemma 4 entries in `model_tuning_profiles.json`.

Also ran DROP l5 on 12B with `--reasoning-budget 0` + `--patch-think-tag-strip`: EM=0.60, F1=0.70. Settings confirmed working for DROP.

### Gemma-4-12B split-load findings (2026-06-06)

Three attempts needed to get the 12B model loaded on 2x 1060 6GB:

1. `--n-gpu-layers 999`: auto-fitter aborts ("n_gpu_layers already set by user to 999")
2. `--tensor-split 1,0,1,0,0,0`: OOM on CUDA0 — **critical finding**: the 6-value tensor-split mask addresses physical GPU indices, but Docker `device=1,3` makes only 2 GPUs visible inside the container (CUDA 0 and 1). Use N values for N visible GPUs.
3. `--tensor-split 1,1 -fit off --n-gpu-layers 48`: success. Model splits: CUDA0=3102 MiB, CUDA1=3786 MiB, CPU=924 MiB.

**Rule**: For Docker GPU passthrough, `--tensor-split` values must match the number of visible GPUs inside the container, not total physical GPUs. Updated `NEW_MODEL_INTEGRATION.md` decision tree.

### 26B-A4B transient crash (2026-04-25)

First l100 DROP run hit a 500 server error at request 51/100: `"Failed to parse input at pos 13: <|channel>thought\n..."`. Transient llama-server parse error on very long thinking chain. Second l100 rerun succeeded cleanly (f1=0.746).

## Knowledge Benchmark Findings

### Prompt impact on knowledge scores (A/B test, 2026-03-14)

Ran all 3 compatible models with `--no-model-prompts` and compared to prompted runs.
Result: **system prompts have no meaningful effect on loglikelihood-based knowledge scores.**

| Model | Task | With Prompt | No Prompt | Delta |
| --- | --- | --- | --- | --- |
| `Mistral-7B` | mmlu | 0.593 | 0.593 | 0.000 |
| `Mistral-7B` | arc_challenge | 0.60 | 0.40 | -0.20 |
| `Mistral-7B` | hellaswag | 0.40 | 0.60 | +0.20 |
| `Mistral-7B` | truthfulqa_mc2 | 0.671 | 0.607 | -0.064 |
| `Mistral-7B` | boolq | 0.80 | 0.80 | 0.000 |
| `Qwen2.5-Coder-7B` | (all 5 tasks) | — | — | 0.000 |
| `DeepSeek-R1-7B` | (all 5 tasks) | — | — | 0.000 |

Qwen2.5-Coder and DeepSeek showed zero difference across all tasks. Mistral's deltas are noise at limit 5 (1 sample = 0.20 swing). Loglikelihood evaluation measures token probabilities, not generated text, so system prompts have minimal influence on the scoring mechanism. The low Qwen2.5-Coder knowledge scores (0.20-0.27) are the model's actual baseline, not prompt interference.

### Qwen2.5-Coder knowledge scores (limit 5)

32B knowledge scores are identical to 7B coder across all 5 tasks. At limit 5, this is almost certainly noise — both models are answering ~1 of 5 samples correctly. These are coder-family models; low knowledge scores are expected and not a concern (see Suite Selection Rationale in MODEL_LIBRARY.md).

## Operational Notes

### Live response sanity pass (2026-03-09)

Custom sequential load succeeded for all five worker targets (`qwen3.5:9b-q3km`,
`deepseek-r1:7b`, `qwen2.5-coder:7b`, `mistral:7b-instruct`, `qwen3.5:4b`) with
one-at-a-time `load_llm` meta tasks.

Prompt/formatting quirks observed from direct `/completion` probes:
- `Qwen2.5-Coder-7B`: strong instruction compliance; returned exact strings and concise output.
- `Qwen3.5-9B`: generally responsive, but can prepend punctuation and sometimes repeats short answers.
- `DeepSeek-R1-7B`: often ignores strict format constraints and expands into long unsolicited text; high-risk for strict-output tasks without strong stop/format guards.
- `Mistral-7B-Instruct`: frequently drifts from exact-format prompts into unrelated continuations; use for open-ended prose, not strict machine-parseable output.
- `Qwen3.5-4B`: tends to emit `<think>` scaffolding even on strict formatting prompts; requires stronger prompt constraints and post-parse checks.

### Reasoning full-suite runtime estimates (no partial scores recorded)

Source runs (canceled before completion):
- `/mnt/shared/logs/benchmarks/parallel_reasoning_suite_20260310_112146`
- `/mnt/shared/logs/benchmarks/parallel_reasoning_suite_20260310_125816`

Estimated time to complete one full reasoning run (`4346` requests/model):

| Model | Estimated full run time |
| --- | --- |
| `Qwen3.5-4B-Q4_K_M.gguf` | est ~2h |
| `Qwen3.5-9B-Q3_K_M.gguf` | est ~3h |
| `DeepSeek-R1-Distill-Qwen-7B-Q4_K_M.gguf` | est ~3 to 4h |
| `Qwen2.5-Coder-7B-Instruct-Q4_K_M.gguf` | est ~5 to 7h |
| `Mistral-7B-Instruct-v0.3-Q4_K_M.gguf` | est ~5 to 7h |

### RPi-tier small-model cohort (2026-03-18)

`Qwen3-1.7B`, `SmolLM3-3B`, `Llama-3.2-3B-Instruct`, `Phi-4-mini`, and `Gemma-3-4B` have completed `bench-pipeline` totals (`6/6` each) and full `bench-code` smoke coverage. Completed `bench-reasoning --limit 100` baselines now exist for `Qwen3-1.7B`, `SmolLM3-3B`, and `Llama-3.2-3B-Instruct`. `Phi-4-mini` has completed `gsm8k` and is still in progress on `bbh`/`drop`. `Gemma-3-4B` is a known reasoning l100 failure case: runtime drops mid-run with `Connection refused` on the 1060 worker path. Treat as benchmark-unstable.

### Qwen3.5 SWA/hybrid memory issue

BBH and DROP fail with exit code 1 on all Qwen3.5 models — caused by SWA (Sliding Window Attention) hybrid memory architecture incompatibility with lm-eval's longer prompt sequences. GSM8K uses shorter prompts and works fine. Also blocks bench-knowledge (503 errors, no KV cache reuse).

### Gemma-3-12B split-load failure (2026-03-16)

Cannot split-load on 1060 GPUs. 262K vocab produces ~3.1GB embedding matrix per GPU — exceeds 6GB VRAM even with reduced layers/ctx. Would need brain GPU (3090) to run reasoning benchmarks.

### Score reconciliation notes

Per-model score paragraphs from the reasoning table:
- **Gemma 4 + Qwen 3.6 reasoning rerun (2026-04-25, limit 50)**: BBH extraction fixed by removing `\n\n` stop sequence and adding `(?i)` case-insensitive regex + `ignore_case`/`ignore_punctuation` on exact_match. Qwen 3.6 also required `--patch-think-tag-strip`. All Gemma 4 DROP scores now final with `--patch-think-tag-strip`.
- **Qwen3-8B reasoning (limit 50, 2026-03-15)**: `--reasoning-budget 0` confirmed as fix. Also requires `--cache-ram 0` to prevent prompt cache OOM on 6GB VRAM.
- **Qwen2.5-Coder-14B reasoning (limit 100, 2026-03-16)**: Scores decreased from limit 5 smoke test as expected — limit 100 values are the reliable baseline.
- **DeepSeek-R1-14B reasoning (2026-03-16)**: BBH 0.5852 with `--patch-think-tag-strip` v2 (removed `\n\n` stop only). GSM8K and DROP remain 0.0. Root cause is structural (see tuning history above).
- **Qwen2.5-Coder-7B reasoning (limit 100)**: BBH improved from 0.6481 (limit 10) to 0.6674 (limit 100). Drop decreased from 0.622 to 0.576.
- **Qwen2.5-Coder-32B reasoning (limit 100, 2026-03-15)**: gsm8k 0.92, bbh 0.4837, drop 0.756 f1 / 0.62 em. Full limit 100 run complete.

### Benchmark result source paths

- bench-pipeline: `/mnt/shared/logs/benchmarks/bench-pipeline/history/parallel_worker_suite_20260310_234145/results`
- bench-pipeline (14B split): `/mnt/shared/logs/benchmarks/bench-pipeline/history/bench-pipeline_*_split_smoke_v1`
- bench-pipeline (14B/32B full): `/mnt/shared/logs/benchmarks/bench-pipeline/history/bench-pipeline_*_full_v2`
- bench-pipeline (R1-14B full): `/mnt/shared/logs/benchmarks/bench-pipeline/history/bench-pipeline_deepseek-r1_14b_pipeline_dsr1_14b_full_v3`
- bench-code: `/mnt/shared/plans/shoulders/benchmarking/docker/bench-code/history/parallel_bench_code_resume_20260311_122032`
- bench-code (14B split): `/mnt/shared/logs/benchmarks/bench-code/history/bench-code_*_split_smoke_v1`
- bench-reasoning: `/mnt/shared/logs/benchmarks/bench-reasoning/history/reasoning_top3_l100_20260312_2105`
- bench-reasoning (14B split): `/mnt/shared/logs/benchmarks/bench-reasoning/history/bench-reasoning_*_split_smoke_v1`
- bench-reasoning (7B limit 100): `/mnt/shared/logs/benchmarks/bench-reasoning/history/bench-reasoning_qwen2.5-coder_7b_reasoning_coder7b_l100_v1`
- bench-reasoning (Qwen3-8B l50): `/mnt/shared/logs/benchmarks/bench-reasoning/history/bench-reasoning_qwen3_8b_reasoning_qwen3_8b_nothink_l50_v1`
- bench-reasoning (Coder-14B l100): `/mnt/shared/logs/benchmarks/bench-reasoning/history/bench-reasoning_qwen2.5-coder_14b_reasoning_coder14b_l100_v1`
- bench-knowledge: `/mnt/shared/logs/benchmarks/bench-knowledge/history/bench-knowledge_*_knowledge_smoke_v1`
- bench-knowledge (32B): `/mnt/shared/logs/benchmarks/bench-knowledge/history/bench-knowledge_qwen2.5-coder-32b_knowledge_brain_smoke_v1`
- brain campaign (32B): `/mnt/shared/logs/benchmarks/campaigns/history/gpu0_brain_qwen25coder32b_smoke/smoke_v1`
- brain campaign (Gemma 4 + Qwen 3.6, 2026-04-22): code in `/mnt/shared/logs/benchmarks/bench-code/history/bench-code_*_{gemma4,qwen36}_*`, reasoning in `/mnt/shared/logs/benchmarks/bench-reasoning/history/bench-reasoning_*_{gemma4,qwen36}_*`
- worker campaign (Gemma 4 E2B/E4B, 2026-04-22): same pattern with `gemma4_e2b` and `gemma4_e4b` run names
