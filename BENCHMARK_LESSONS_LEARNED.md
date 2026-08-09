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

### Qwen3.6-27B brain split-load: 3090 + 1060s for extended context (2026-08-03)

Tested splitting the brain model (Qwen3.6-27B) across the 3090 and 1060s to increase context window beyond the 3090-only 8192 baseline. Despite documented tensor split bug #22058, Qwen3.6 splits correctly across mixed GPU architectures (sm86 + sm61).

**GPU error workaround**: GPUs 1-3 were in "Unknown Error" state. `--gpus "device=0,4"` fails because `nvidia-container-cli` can't enumerate when some GPUs are errored. Fix: use `--runtime=nvidia` with `-e NVIDIA_VISIBLE_DEVICES=<UUID1>,<UUID2>`.

```bash
# Failed (nvidia-container-cli detection error with errored GPUs):
docker run --gpus "device=0,4,5" ...

# Working (UUID passthrough):
docker run --runtime=nvidia \
  -e NVIDIA_VISIBLE_DEVICES=GPU-409c0fe8-...,GPU-fd82a1a6-...,GPU-d24dca6a-... \
  ...
```

**Context scaling results** (all with `--flash-attn on -ctk q8_0 -ctv q8_0 -fit off`):

| ctx_size | GPUs | tensor-split | GPU 0 (3090) | GPU 4 (1060) | GPU 5 (1060) | Total VRAM | KV cache |
|----------|------|-------------|-------------|-------------|-------------|------------|----------|
| 8,192 | 1 (baseline) | — | 16,273 MiB | — | — | 16,273 MiB | ~442 MiB |
| 32,768 | 2 | 4,1 | 12,953 MiB | 4,214 MiB | — | 17,167 MiB | 1,088 MiB |
| 65,536 | 2 | 4,1 | 13,873 MiB | 4,434 MiB | — | 18,307 MiB | 2,176 MiB |
| 131,072 | 3 | 4,1,1 | 13,413 MiB | 3,154 MiB | 4,196 MiB | 20,763 MiB | 4,352 MiB |
| 262,144 | 3 | 4,1,1 | 16,549 MiB | 3,762 MiB | 5,076 MiB | 25,387 MiB | 8,704 MiB |

**Key observations**:
- Model weights are constant (~16 GB total, ~682 MiB CPU mapped). Only KV cache, recurrent state, and compute buffers scale with context.
- Extra VRAM for 262k vs 8k baseline: ~9.1 GB (almost entirely KV cache).
- 2-GPU (3090+1060) comfortably handles 65k context; 128k is tight on the 1060 (1.3 GB free).
- 3-GPU (3090+2×1060) handles full 262k training context with 8 GB free on 3090, ~1 GB free on 1060s.
- All 65/65 layers stay on GPU at every context size tested.
- Inference verified correct at all context sizes (15×37=555).

**Qwen3.6 tensor split bug #22058**: Despite documentation warning to "avoid split-GPU configs", tensor split works correctly for Qwen3.6-27B across 3090+1060 in practice. The bug may be specific to certain split configurations, older llama.cpp versions, or different Qwen3.6 variants. Tested with `llama-runtime:b8884-candidate`.

**Practical recommendation**: For geometry brain work needing large context (long system prompts + config schemas), use 3090+1060 with ctx_size 65536. This is 8x the current baseline with comfortable headroom. Full 262k is available if needed but leaves the 1060s near capacity.

### `--no-mmap` causes Docker OOM kills (2026-06-10)

E4B reasoning benchmark kept OOM-killing during BBH (long few-shot CoT prompts). Root cause: `--no-mmap` in `run_runtime.sh` converted the GGUF file-backed pages into `malloc`'d anonymous memory, which Docker's cgroup counts as non-reclaimable.

**Measured comparison** (E4B, 5.0GB GGUF, all 43/43 layers on GPU):

| | `--no-mmap` | mmap (default) |
|--|-------------|----------------|
| CPU buffer label | `CPU model buffer` | `CPU_Mapped model buffer` |
| Anonymous memory | 2900 MB | 278–827 MB |
| Peak cgroup total | 6000 MB | 1580 MB |
| Needed Docker limit | 6g/8g | 2g/3g |

With `--no-mmap`, 2730 MB stays in anonymous RAM even with full GPU offload (embedding table + output head). With mmap, those tensors are file-backed and the kernel reclaims pages not actively needed. Full bench-reasoning l5 (GSM8K + BBH + DROP) completed at 2g Docker limit with mmap.

**Brain tier caveat**: Anonymous memory also scales with `ctx_size` due to KV cache scratch buffers. Brain-tier models (ctx 16384) need ~8-9 GB anon regardless of mmap mode. Tested: 31B OOM'd at 4g, 6g, 8g; passed at 10g/12g. The mmap fix saves ~1g for brain (CPU buffer moves from anon to file) but the ctx-driven buffers dominate.

**Fix**: Removed `--no-mmap` from `run_runtime.sh`. Updated campaign runner memory limits: single 2g/3g (was 6g/8g), brain 10g/12g (was 11g/13g), split 10g/12g (was 10g/12g).

**Note**: `docker stats` will show higher memory with mmap (includes reclaimable file cache in the headline number). This is cosmetic — the kernel reclaims those pages under pressure. The original `--no-mmap` was likely added based on misleading `docker stats` output.

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
- gpt-oss 20B (2026-06-12): `/mnt/shared/logs/benchmarks/bench-{pipeline,code,reasoning}/history/*gptoss*`
- Phi-4-mini-reasoning (2026-06-12): `/mnt/shared/logs/benchmarks/bench-{pipeline,reasoning}/history/*phi4mr*`

## gpt-oss 20B: Channel-Based Thinking and BBH Extraction (2026-06-12)

**Problem**: gpt-oss 20B scored BBH 6.7% on first run despite being a capable model.

**Root cause chain**:
1. OpenAI-family models use channel tokens (`<|channel|>analysis`, `<|channel|>final`) to route reasoning to the `reasoning_content` API field. This is architectural — `--reasoning-budget 0` sets `thinking=0` in the runtime but the model still generates channel tokens.
2. With reasoning in `reasoning_content`, the `content` field receives only the terse final answer (e.g., bare letter "A").
3. The "strict worker" system prompt ("keep output minimal") reinforced bare-letter answers.
4. When the model did output "So the answer is", it used markdown bold `**(A)**`, breaking the BBH `get-answer` regex `[Ss]o the answer is \(([A-Za-z])\)`.

**Fix**: Changed system prompt to explicitly request the extraction format: "reason briefly then conclude with exactly: So the answer is (X). Use plain text only, no markdown formatting." Added `--reasoning-budget 0` to `extra_args`.

**Result**: BBH improved from 6.7% → 64.1% (l10 smoke). The model is genuinely capable — the original score was entirely an extraction failure.

**Lesson**: Channel-based thinking models (OpenAI family) need prompt engineering for BBH extraction because the reasoning that would naturally contain "So the answer is (X)" goes to `reasoning_content` instead of `content`. The content field must be explicitly instructed to include the extractable pattern.

## Phi-4-mini-reasoning 3.8B: Structural Think Tokens (2026-06-12)

**Problem**: All litmus tests FAIL due to `<think>` tags. bench-code incompatible. bench-pipeline json_schema 0%.

**Root cause**: Like DeepSeek-R1, this model has think tokens baked into the vocabulary from reasoning fine-tuning. Runtime shows `thinking=0` — it doesn't recognize them as special. `--reasoning-budget 0` has no effect. The model simply generates `<think>...</think>` blocks as regular text output before every answer.

**Impact by suite**:
- bench-reasoning: Fixable with `--patch-think-tag-strip`. GSM8K strict 0% (format issue — stripped output doesn't have `#### N`), flexible 10%. BBH/DROP pending.
- bench-code: **Incompatible**. evalplus sanitizer strips think tags + code together, resulting in empty solutions. Long think chains also cause OOM/timeout on 1060 (2g Docker limit exceeded; needs 3g/4g).
- bench-pipeline: json_schema 0% (think tags in JSON). Other stages score well (cmd_safety 83%, tool_plan 100%).

**bench-reasoning update**: BBH and DROP both failed — runtime OOM killed on 1060 after ~52 minutes of BBH generation. BBH few-shot prompts are ~1000+ tokens; combined with think chain generation, this exhausts the 3g Docker memory limit. GSM8K completed because its prompts are shorter. bench-reasoning is only partially viable for this model on 1060 hardware (GSM8K works, BBH/DROP do not).

**Lesson**: Structural think-token models (DeepSeek-R1, Phi-4-mini-reasoning) have fundamental incompatibilities with multiple suites. bench-code fails (evalplus strips think+code). bench-reasoning BBH/DROP fail on 1060 (memory pressure from think chains + long prompts). These cannot be fixed via model settings — they would require suite changes or different hardware. Document the limitations and skip affected suites.

## Runtime Image Mismatch: Gemma 4 Requires b8884-candidate

**Date**: 2026-06-12/13

**Symptom**: Overnight campaign Block 2 (Gemma-4-12B on brain) failed — runtime loaded but never responded to health checks. Wait loop timed out after 5 minutes.

**Root cause**: `run_runtime.sh` defaults to `llama-runtime:sm61-sm86` (March 2026 build) which does not support the Gemma 4 `gemma4` architecture (`unknown model architecture: 'gemma4'`). All Gemma 4 models require `llama-runtime:b8884-candidate` (April 2026 build). The overnight script omitted `--image` so it used the default.

**Fix**: Always specify `--image llama-runtime:b8884-candidate` when loading any Gemma 4 model with `run_runtime.sh`.

**Lesson**: When scripting multi-model campaigns, explicitly specify the runtime image per block. Different model families may require different runtime builds. The default image is not guaranteed to support all architectures. This is documented in model_tuning_profiles.json notes and MODEL_RUNTIME_GUIDE.md but easy to miss in ad-hoc scripts.

## Split-Load Reference

Consolidated reference for running models across multiple GPUs via tensor splitting. All findings from individual experiments above are gathered here.

### Hardware layout

| Config | Host GPUs | Docker visible | Port | Status (2026-08-03) |
|--------|-----------|----------------|------|---------------------|
| brain_extended | GPU 0 + GPU 4 | CUDA0, CUDA1 | 11434 | **Working** — 3090+1060, up to 128k ctx |
| brain_max | GPU 0 + GPU 4 + GPU 5 | CUDA0, CUDA1, CUDA2 | 11434 | **Working** — 3090+2×1060, up to 262k ctx |
| pair_1_3 | GPU 1 + GPU 3 | CUDA0, CUDA1 | 11435 | **Down** — GPUs 1-3 in "Unknown Error" state |
| pair_4_5 | GPU 4 + GPU 5 | CUDA0, CUDA1 | 11438 | **Working** — requires UUID passthrough |

### Working docker run commands

```bash
# Brain + 1 1060 (65k ctx, comfortable headroom):
docker run --rm --detach \
  --name llama-brain-split \
  --runtime=nvidia \
  -e NVIDIA_VISIBLE_DEVICES=GPU-409c0fe8-38ef-14ad-dbc6-a0437261e9cb,GPU-fd82a1a6-06aa-3ec2-1786-ae7b4474105c \
  --oom-score-adj 500 --memory 20g --memory-swap 24g \
  --network host \
  -v /mnt/shared/models/qwen3.6-27b:/mnt/shared/models/qwen3.6-27b:ro \
  llama-runtime:b8884-candidate \
  llama-server \
  --model /mnt/shared/models/qwen3.6-27b/Qwen3.6-27B-Q4_K_M.gguf \
  --host 127.0.0.1 --port 11434 \
  --ctx-size 65536 --n-gpu-layers 999 \
  --batch-size 64 --threads 8 --parallel 1 \
  --flash-attn on -ctk q8_0 -ctv q8_0 \
  --tensor-split 4,1 --reasoning-budget 0 -fit off

# Brain + 2 1060s (262k max ctx):
docker run --rm --detach \
  --name llama-brain-split \
  --runtime=nvidia \
  -e NVIDIA_VISIBLE_DEVICES=GPU-409c0fe8-38ef-14ad-dbc6-a0437261e9cb,GPU-fd82a1a6-06aa-3ec2-1786-ae7b4474105c,GPU-d24dca6a-b19f-2018-57b7-15a79466efdf \
  --oom-score-adj 500 --memory 20g --memory-swap 24g \
  --network host \
  -v /mnt/shared/models/qwen3.6-27b:/mnt/shared/models/qwen3.6-27b:ro \
  llama-runtime:b8884-candidate \
  llama-server \
  --model /mnt/shared/models/qwen3.6-27b/Qwen3.6-27B-Q4_K_M.gguf \
  --host 127.0.0.1 --port 11434 \
  --ctx-size 262144 --n-gpu-layers 999 \
  --batch-size 64 --threads 8 --parallel 1 \
  --flash-attn on -ctk q8_0 -ctv q8_0 \
  --tensor-split 4,1,1 --reasoning-budget 0 -fit off

# Worker split (1060 pair, standard via run_runtime.sh when GPUs healthy):
bash /mnt/shared/scripts/llama_runtime/run_runtime.sh \
  --name llama-split-pair45 \
  --model /mnt/shared/models/<model-dir>/<model>.gguf \
  --port 11438 \
  --gpus "device=4,5" \
  --tensor-split 1,1 \
  --ctx-size 16384 \
  --memory-limit 10g --memory-swap 12g \
  --extra-arg "-fit" --extra-arg "off"
```

### GPU UUIDs (for when `--gpus device=N,M` fails)

```
GPU 0: GPU-409c0fe8-38ef-14ad-dbc6-a0437261e9cb  (3090 Ti)
GPU 4: GPU-fd82a1a6-06aa-3ec2-1786-ae7b4474105c  (1060 6GB)
GPU 5: GPU-d24dca6a-b19f-2018-57b7-15a79466efdf  (1060 6GB)
```

Obtain fresh UUIDs with: `nvidia-smi -L 2>/dev/null | grep UUID`

### Tested split configurations

**Brain model (Qwen3.6-27B) across mixed architectures:**

| ctx_size | GPUs | tensor-split | GPU 0 (3090) | GPU 4 (1060) | GPU 5 (1060) | KV cache | Status |
|----------|------|-------------|-------------|-------------|-------------|----------|--------|
| 8,192 | 1 (baseline) | — | 16,273 MiB | — | — | ~442 MiB | Working |
| 32,768 | 2 | 4,1 | 12,953 MiB | 4,214 MiB | — | 1,088 MiB | Working |
| 65,536 | 2 | 4,1 | 13,873 MiB | 4,434 MiB | — | 2,176 MiB | Working (recommended) |
| 131,072 | 2 | 4,1 | — | — (tight) | — | 4,352 MiB | Working (1060 near limit) |
| 131,072 | 3 | 4,1,1 | 13,413 MiB | 3,154 MiB | 4,196 MiB | 4,352 MiB | Working |
| 262,144 | 3 | 4,1,1 | 16,549 MiB | 3,762 MiB | 5,076 MiB | 8,704 MiB | Working (max) |

**Worker models across 1060 pairs:**

| Model | CUDA0 MiB | CUDA1 MiB | CPU MiB | Layers | ctx_size | Status |
|-------|-----------|-----------|---------|--------|----------|--------|
| Gemma-4-12B Q4_K_M | 3,102 | 3,786 | 924 | 48/48 | 4,096 | Working (pair_1_3) |
| Qwen2.5-Coder-14B Q4_K_M | 3,917 | 4,231 | 418 | 49/49 | 16,384 | Working (pair_4_5) |
| Phi-4-14B Q4_K_M | — | — | — | 41/41 auto | 16,384 | Working (no forced layers) |

### Known failures and restrictions

| Model | Issue | Bug/Workaround |
|-------|-------|----------------|
| Qwen3.6-27B | Tensor split bug #22058 | **Actually works** on 3090+1060 with b8884-candidate. Bug may be version/config specific. |
| Gemma-3-12B | 262K vocab embedding too large | ~3.1GB embedding per GPU exceeds 6GB VRAM |
| Phi-4-14B | `--n-gpu-layers 999` aborts | Remove forced layer count, let auto-fitter work |
| Any model | `--gpus device=N,M` with errored GPUs | Use UUID passthrough via `--runtime=nvidia` + `-e NVIDIA_VISIBLE_DEVICES` |

### Critical rules

1. **tensor-split values = visible GPU count** — `--tensor-split 4,1` for 2 GPUs, `4,1,1` for 3. NOT physical index masks.
2. **`-fit off` required** when using `--n-gpu-layers 999` — prevents auto-fitter from aborting
3. **Gemma 4 / Qwen 3.6 need `llama-runtime:b8884-candidate`** — default image doesn't support these architectures
4. **Docker memory limits**: 20g/24g for brain split (KV cache at high ctx dominates); 10g/12g for worker splits
5. **mmap ON** (default) — do NOT add `--no-mmap` (causes Docker OOM, see `--no-mmap` section above)
6. **Port convention**: brain → 11434, pair_1_3 → 11435, pair_4_5 → 11438
7. **Weight the tensor-split toward the 3090** — `4,1` or `4,1,1` keeps most weights on the faster GPU
