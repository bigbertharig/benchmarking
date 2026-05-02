# Model Runtime Guide

Per-model runtime requirements, best practices, memory limits, and compatibility info.

Companion docs:
- [MODEL_LIBRARY.md](MODEL_LIBRARY.md) — model selection hub, best choices, inventory
- [BENCHMARK_SCORES.md](BENCHMARK_SCORES.md) — pure score tables
- [BENCHMARK_LESSONS_LEARNED.md](BENCHMARK_LESSONS_LEARNED.md) — debugging narratives and tuning histories
- Model tuning profiles: `/media/bryan/shared/plans/shoulders/benchmarking/model_tuning_profiles.json`

## Pre-Flight Litmus Test

Before committing a model to the full benchmark suite, run a quick litmus to catch
output format issues (`<think>` wrappers, broken JSON, refusal loops) that would
waste hours and produce all-zero scores.

```bash
# 1. Reasoning check
curl -s http://localhost:PORT/v1/chat/completions -d '{
  "model": "MODEL_ID",
  "messages": [{"role":"user","content":"What is 15 * 37? Reply with ONLY the number."}],
  "temperature": 0
}' | python3 -c "import json,sys; r=json.load(sys.stdin); c=r['choices'][0]['message']['content']; print(c); ok='555' in c and '<think>' not in c; print('PASS' if ok else 'FAIL: check for think tags or wrong answer')"

# 2. JSON check
curl -s http://localhost:PORT/v1/chat/completions -d '{
  "model": "MODEL_ID",
  "messages": [{"role":"user","content":"Return a JSON object with keys \"name\" and \"age\" for a 30-year-old named Alice. Output ONLY valid JSON, no explanation."}],
  "temperature": 0
}' | python3 -c "import json,sys; r=json.load(sys.stdin); c=r['choices'][0]['message']['content']; print(c); json.loads(c); print('PASS')"

# 3. Code generation check
curl -s http://localhost:PORT/v1/chat/completions -d '{
  "model": "MODEL_ID",
  "messages": [{"role":"user","content":"Write a Python function is_palindrome(s) that returns True if s is a palindrome. Output ONLY the function, no explanation."}],
  "temperature": 0
}' | python3 -c "import json,sys; c=json.load(sys.stdin)['choices'][0]['message']['content']; print(c); ok='def is_palindrome' in c and '<think>' not in c; print('PASS' if ok else 'FAIL')"
```

If any check FAILs, see [BENCHMARK_LESSONS_LEARNED.md](BENCHMARK_LESSONS_LEARNED.md) for think-tag troubleshooting.

## Thinking Model Quick Reference

| Family | Runtime flag | Benchmark flag | Issue without fix |
|--------|-------------|----------------|-------------------|
| Qwen 3.6 (all sizes) | `--reasoning-budget 0` | `--patch-think-tag-strip` | BBH/DROP 0.0 |
| Gemma 4 (all sizes) | none | `--patch-think-tag-strip` (DROP only) | DROP 0.0 |

## Active Model Runtime Notes

### qwen2.5-coder:7b

- GGUF: `Qwen2.5-Coder-7B-Instruct-Q4_K_M.gguf`
- Tier: 7B single worker (GPU 1-5)
- Context: 16384 (benchmark-safe on 6GB)
- Best for: structured extraction, general QA, coding
- Strong instruction compliance, concise output

### llama-3.2:3b

- GGUF: `Llama-3.2-3B-Instruct-Q4_K_M.gguf`
- Tier: 3B single worker (GPU 1-5)
- Only non-Qwen/Gemma/Phi family in fleet (diversity)
- Newest Llama that fits on 1060s (Llama 4 Scout needs ~60GB VRAM)

### smollm3:3b

- GGUF: `SmolLM3-3B-Q4_K_M.gguf`
- Tier: 3B single worker (GPU 1-5)
- Best RPi-tier model for reasoning (BBH 0.6678 — best in small tier)
- Pipeline runner requires an explicit `system_prompt` on the `smollm3:3b` alias in `model_tuning_profiles.json`; `_alias_of` alone is not followed by `--require-model-prompt`.

### qwen2.5-coder:14b

- GGUF: `Qwen2.5-Coder-14B-Instruct-Q4_K_M.gguf`
- Tier: 14B split worker (GPU 1+3 or 4+5)
- Split baseline on pair_4_5 is still unstable (warmup failures)
- Best for: split-worker coding/reasoning, nearly matches 32B on code

### phi-4:14b

- GGUF: `phi-4-Q4_K_M.gguf`
- Tier: 14B split worker (GPU 1+3 or 4+5)
- Best for: instruction-following (100% cmd_safety, tool_plan, long_context)
- Weak on JSON (0%) and DROP (0.070)
- Do NOT use stop-strip patch (hurts more than helps)
- 2026-04-28 startup note: the Phase 3 l100 rerun failed before benchmarks because the split runtime on GPUs 4+5 did not become ready on port 11438 within 300s. Forcing `--n-gpu-layers 999` triggers llama.cpp's memory fitter warning (`need to use 586 MiB less`) and prevents automatic fit. Removing the forced layer count let llama.cpp auto-fit and reach `/v1/models` after 282s.

### qwen2.5-coder:32b

- GGUF: `Qwen2.5-Coder-32B-Instruct-Q4_K_M.gguf`
- Tier: brain (GPU 0, 3090)
- Best for: code generation (91.5% HumanEval, 89.7% MBPP)
- Pipeline underperformance is likely system prompt mismatch (tuned for 7B style)

### gemma-4 family (E4B, E2B, 26B-A4B, 31B)

- GGUFs: `gemma-4-e4b-it-Q4_K_M.gguf`, `gemma-4-e2b-it-Q8_0.gguf`, `gemma-4-26B-A4B-it-Q4_K_M.gguf`, `gemma-4-31B-it-Q4_K_M.gguf`
- Tiers: E4B/E2B single worker, 26B-A4B/31B brain
- Requires `llama-runtime:b8884-candidate` (llama.cpp >= b8884)
- Apache 2.0 license
- **Benchmark: `--patch-think-tag-strip` REQUIRED for DROP** (harmless for other suites)
- `--disable-thinking` does NOT work in lm-eval 0.4.11
- Memory: E4B ~5GB, E2B ~3-4GB (1060), 26B-A4B 16GB + 577MB CPU, 31B ~18GB (3090)
- E2B model ID: use `gemma-4:e2b` (alias added to model_tuning_profiles.json)
- Do NOT use for code generation — Qwen family is dramatically better

### qwen3.6 family (27B, 35B-A3B)

- GGUFs: `Qwen3.6-27B-Q4_K_M.gguf`, `Qwen3.6-35B-A3B-UD-Q4_K_M.gguf`
- Tier: brain (GPU 0, 3090)
- Gated Delta Networks architecture (hybrid linear attention)
- Requires `llama-runtime:b8884-candidate` (llama.cpp >= b8884)
- **Runtime: `--reasoning-budget 0` REQUIRED**
- **Benchmark: `--patch-think-tag-strip` REQUIRED** (BBH + DROP)
- `--reasoning-budget 0` alone is NOT sufficient for benchmarks
- Memory: 27B ~16GB, 35B-A3B 21.3GB (tight on 3090 — do NOT increase ctx beyond 16384)
- 35B-A3B has recurrent state (`llama_memory_recurrent`)
- Tensor split has known bug (#22058) — avoid split-GPU configs

## Startup Context Policy

Last validated: 2026-03-10

Config locations:
- `/home/bryan/llm_orchestration/shared/agents/config.json` (normal/default)
- `/home/bryan/llm_orchestration/shared/agents/config.benchmark.json` (benchmark runtime)
- `/home/bryan/llm_orchestration/shared/plans/shoulders/benchmarking/config.benchmark.json` (benchmark repo copy)

Active worker context sizes:
- `qwen2.5-coder:7b`: `ctx_size=16384`
- Gemma-4 E4B/E2B: `ctx_size=4096` (worker tier)
- Brain models (Gemma-4 26B/31B, Qwen3.6): `ctx_size=16384`

Startup commands:
```bash
# default mode
python3 ~/llm_orchestration/scripts/benchmarks/start_default_mode.py
# empty mode
python3 ~/llm_orchestration/scripts/benchmarks/start_empty_mode.py
```

## CPU Inference (Pi 5)

llama.cpp built from source on Pi 5 (aarch64, CPU-only, no CUDA).

Binary: `/home/bryan/llama.cpp/build/bin/llama-server`

Start a CPU inference server:
```bash
/home/bryan/llama.cpp/build/bin/llama-server \
  --model /media/bryan/shared/models/<model-dir>/<model>.gguf \
  --host 0.0.0.0 --port 8080 \
  --ctx-size 4096 \
  --threads 4
```

Run benchmarks against it from the rig:
```bash
docker run --rm --network host ... bench-pipeline \
  --model <model-id> \
  --runtime-base http://10.0.0.2:8080 \
  --run-name <run_name>
```

Measured speed (Pi 5, 4× Cortex-A76, 8GB):
- 3B model: ~3.3 tok/s generation, ~18-21 tok/s prompt
- Expect ~12× slower than 1060 GPU for 3B, ratio worsens with model size

Notes:
- Models load over NFS from shared drive — first load takes 30-60s
- `--reasoning-budget 0` does NOT suppress thinking for all models (SmolLM3 ignores it)
- Scores are identical to GPU — only speed differs
- See [MODEL_LIBRARY.md](MODEL_LIBRARY.md) "CPU Inference and Swarm Deployment" for use cases and upgrade scenarios

## Compatibility Limits

Host llama chat runtime:
- works for generation tasks with `--apply_chat_template`: gsm8k, drop, bbh, math_500, aime_2024
- works for custom pipeline tests via `local_custom` harness
- MC/loglikelihood tasks should use `bench-knowledge` (llama.cpp gguf), not host chat runtime

General rules:
- **load models one at a time** — parallel loading clogs shared USB/PCIe bus (3-5x longer load times)
- do not load 7B or smaller on GPU 0, do not load 30B+ on 1060 workers

## Prompt Methodology

Two-layer prompt system:

1. **Universal system prompt** (per model): `model_tuning_profiles.json` → `models.<gguf_id>.system_prompt`. Deploys with the model for real work.

2. **Test-specific overrides** (per suite/test): `custom_tasks/model_prompt_profiles.json` → `models[].test_overrides.<test_id>`. Used instead of universal prompt when present.

Prompt history is captured in every run result (`result.json`):
- `prompts_snapshot.resolved_system_prompt`: exact prompt used
- `prompts_snapshot.resolved_source`: universal vs override
- per-case `system_prompt_used`: exact prompt per test case

Archives: `/media/bryan/shared/logs/benchmarks/<suite_run_timestamp>/results/<test_id>_<timestamp>/result.json`

Tuning workflow: start with universal prompt → run suite → add test_overrides for weak tests → when override consistently improves, fold back into universal → remove override.
