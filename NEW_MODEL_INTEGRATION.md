# New Model Integration Playbook

Repeatable process for onboarding a new model: download, register, load, test, benchmark, finalize.

Companion docs:
- [MODEL_LIBRARY.md](MODEL_LIBRARY.md) — model selection hub, best choices, inventory
- [BENCHMARK_SCORES.md](BENCHMARK_SCORES.md) — pure score tables
- [MODEL_RUNTIME_GUIDE.md](MODEL_RUNTIME_GUIDE.md) — per-model runtime requirements and best practices
- [BENCHMARK_LESSONS_LEARNED.md](BENCHMARK_LESSONS_LEARNED.md) — debugging narratives and tuning histories
- [docker/README.md](docker/README.md) — Docker suite operator guide
- Model tuning profiles: `model_tuning_profiles.json`
- Model catalog: `/media/bryan/shared/agents/models.catalog.json`

---

# Part 1: Process Reference

## Overview

Each new model goes through 7 phases:

| Phase | What | Time | Gate |
|-------|------|------|------|
| 0 | Download | varies | GGUF on disk, size verified |
| 1 | Register | 5 min | Entries in tuning profiles + catalog |
| 2 | First Load | 2-10 min | `/v1/models` responds, no errors |
| 3 | Litmus Test | 1 min | 3 curl checks pass |
| 3.5 | Runtime Characterization | 5-30 min | Load time, sustained decode rate, and power envelope recorded |
| 4 | Smoke Runs | 30 min - 2h | All suites produce non-zero scores |
| 5 | Full Run | 2-12h | Limit 50/100 scores recorded |
| 6 | Finalize | 10 min | All companion docs updated |

### Philosophy: Model Settings, Not Suite Changes

The goal of integration is to see how a model works with our **existing benchmark suites** using
only model-level settings (system prompt, runtime args, tuning profile). If a model has quirks
with a specific suite (e.g., structural think tokens breaking code extraction), **document the
limitation** in the integration log and tuning profile notes, then move on.

Do not:
- Modify suite code to accommodate a specific model
- Add model-specific extraction logic to benchmarks
- Create custom test harnesses

Do:
- Tune the system prompt (prompt families above)
- Set runtime args (`--reasoning-budget`, `--jinja`, etc.)
- Use existing suite flags (`--patch-think-tag-strip`, `--limit`, etc.)
- Record incompatibilities as known limitations with root cause

If a limitation is severe enough to matter (e.g., a model can't be evaluated at all on a suite),
add it to the "Known Suite Incompatibilities" section in the integration log and revisit later.

## Phase 0: Download

Get the GGUF file onto the rig.

**Directory convention**: `/mnt/shared/models/<model-dir>/`

```bash
# Create model directory on rig
ssh 10.0.0.3 'mkdir -p /mnt/shared/models/<model-dir>'

# Download (huggingface example)
ssh 10.0.0.3 'cd /mnt/shared/models/<model-dir> && \
  wget -q "https://huggingface.co/<org>/<repo>/resolve/main/<filename>.gguf"'

# Verify file size
ssh 10.0.0.3 'ls -lh /mnt/shared/models/<model-dir>/<filename>.gguf'
```

**Naming convention**: directory is lowercase-hyphenated model name (e.g. `gemma-4-12b`). Keep the upstream GGUF filename as-is.

**Gate**: File exists, size matches expected from source.

## Phase 1: Register

Add the model to the two config files that the benchmark system reads.

### 1a. model_tuning_profiles.json

Add two entries: the GGUF key (full filename) and a short alias.

```json
{
  "<GGUF-filename>.gguf": {
    "status": "untuned",
    "last_tuned_at": null,
    "benchmark_suite": "agent_reliability",
    "system_prompt": "<pick from prompt families below>",
    "inference": {
      "temperature": 0.0,
      "top_p": 1.0,
      "max_tokens": 512
    },
    "runtime": {
      "ctx_size": <4096 for worker, 16384 for brain>,
      "batch_size": <64 for worker, 128 for brain>,
      "parallel": 1,
      "n_gpu_layers": 999
    },
    "notes": "<tier and placement info>"
  },
  "<short-alias>": {
    "_alias_of": "<GGUF-filename>.gguf",
    "system_prompt": "<same as above>"
  }
}
```

**Prompt families** (choose based on model behavior):

| Family | When to use | Prompt |
|--------|-------------|--------|
| Worker (strict) | Default for most models | `"You are a strict worker assistant. Follow instructions exactly and keep output minimal. When JSON is requested, return raw JSON only. Never wrap JSON in ```json code blocks or markdown formatting. Start JSON with { and end with }."` |
| Thinking suppression | Qwen 3.x/3.5/3.6 family | `"You are a worker assistant. Never output <think> tags, chain-of-thought, or internal reasoning. Respond with only the final answer in the exact format requested. When JSON is requested, return raw JSON with no markdown or extra text. When a short answer is requested, give only that answer."` |
| Benchmark assistant | Small models (3B and under) | `"You are a strict benchmark assistant. Think silently and output only the final answer. Never include reasoning, analysis, or extra text. For GSM8K-style math, end with exactly: #### <answer>. For BBH-style reasoning, end with exactly: So the answer is <answer>. For short reading-comprehension questions, output only the shortest final answer phrase."` |

### 1b. models.catalog.json

Add an entry to the `models` array:

```json
{
  "id": "<short-id>",
  "tier": <1 for single, 2 for split, 3 for brain>,
  "placement": "<single_gpu|split_gpu>",
  "gguf_path": "/mnt/shared/models/<model-dir>/<filename>.gguf",
  "tags": ["<relevant>", "<tags>"]
}
```

For split models, add `split_groups`:
```json
{
  "split_groups": [
    {"id": "pair_1_3", "members": ["gpu-1", "gpu-3"], "port": 11440},
    {"id": "pair_4_5", "members": ["gpu-4", "gpu-5"], "port": 11441}
  ]
}
```

**Gate**: Both files have valid JSON. Short alias resolves in tuning profiles.

## Phase 2: First Load

Start the runtime and verify the model loads cleanly.

**Debug-only direct path** (use this for first-time load testing):

```bash
ssh 10.0.0.3

# Single GPU (worker tier)
/mnt/shared/scripts/llama_runtime/run_runtime.sh \
  --name llama-<model>-test \
  --model /mnt/shared/models/<model-dir>/<filename>.gguf \
  --port <port> \
  --gpus device=<gpu-id> \
  --ctx-size <from profile> \
  --batch-size <from profile> \
  --memory-limit 2g --memory-swap 3g

# Brain GPU (3090)
/mnt/shared/scripts/llama_runtime/run_runtime.sh \
  --name llama-<model>-test \
  --model /mnt/shared/models/<model-dir>/<filename>.gguf \
  --port 11434 \
  --gpus device=0 \
  --ctx-size 16384 \
  --batch-size 128 \
  --memory-limit 10g --memory-swap 12g

# Split GPU (14B tier)
/mnt/shared/scripts/llama_runtime/run_runtime.sh \
  --name llama-<model>-test \
  --model /mnt/shared/models/<model-dir>/<filename>.gguf \
  --port <port> \
  --gpus device=<gpu1>,<gpu2> \
  --ctx-size <from profile> \
  --batch-size <from profile> \
  --tensor-split 1,1 \
  --memory-limit 10g --memory-swap 12g
```

**Extra args** (add as needed):
- Qwen 3.x/3.5/3.6: `--extra-arg "--reasoning-budget" --extra-arg "0"`
- Gemma 4 (all sizes): `--extra-arg "--reasoning-budget" --extra-arg "0"` (REQUIRED — thinking mode destroys BBH/DROP extraction)
- OpenAI models (gpt-oss): `--extra-arg "--jinja"` (required for chat template)
- Split models that fail with `--n-gpu-layers 999`: remove forced layer count, let llama.cpp auto-fit
- MXFP4/native quant models: no special flags needed — llama.cpp handles MXFP4 natively (supported since ~b6962)

**Verification**:

```bash
# Check model responds
curl -s http://localhost:<port>/v1/models | python3 -c "import json,sys; print(json.dumps(json.load(sys.stdin),indent=2))"

# Check container logs
docker logs $(docker ps -q --filter "ancestor=llama-runtime*" | head -1) 2>&1 | tail -30

# Check VRAM
nvidia-smi --query-gpu=index,memory.used,memory.total --format=csv,noheader
```

**Gate**: `/v1/models` returns correct model ID, no warnings in logs, VRAM within expected range.

## Phase 3: Litmus Test

Three quick curl checks to catch output format issues before committing to benchmarks.

```bash
PORT=<port>
MODEL_ID=<model-id>

# 1. Reasoning check (expect: 555, no think tags)
curl -s http://localhost:$PORT/v1/chat/completions -d '{
  "model": "'$MODEL_ID'",
  "messages": [{"role":"user","content":"What is 15 * 37? Reply with ONLY the number."}],
  "temperature": 0
}' | python3 -c "import json,sys; r=json.load(sys.stdin); c=r['choices'][0]['message']['content']; print(c); ok='555' in c and '<think>' not in c; print('PASS' if ok else 'FAIL: check for think tags or wrong answer')"

# 2. JSON check (expect: valid JSON with name/age)
curl -s http://localhost:$PORT/v1/chat/completions -d '{
  "model": "'$MODEL_ID'",
  "messages": [{"role":"user","content":"Return a JSON object with keys \"name\" and \"age\" for a 30-year-old named Alice. Output ONLY valid JSON, no explanation."}],
  "temperature": 0
}' | python3 -c "import json,sys; r=json.load(sys.stdin); c=r['choices'][0]['message']['content']; print(c); json.loads(c); print('PASS')"

# 3. Code generation check (expect: function def, no think tags)
curl -s http://localhost:$PORT/v1/chat/completions -d '{
  "model": "'$MODEL_ID'",
  "messages": [{"role":"user","content":"Write a Python function is_palindrome(s) that returns True if s is a palindrome. Output ONLY the function, no explanation."}],
  "temperature": 0
}' | python3 -c "import json,sys; c=json.load(sys.stdin)['choices'][0]['message']['content']; print(c); ok='def is_palindrome' in c and '<think>' not in c; print('PASS' if ok else 'FAIL')"
```

**If any check fails**, see the Decision Trees below before proceeding.

**Gate**: All 3 checks PASS (with or without applied fixes documented in notes).

## Phase 3.5: Runtime Characterization

Run this mandatory measurement for every newly certified model before suite smoke runs. It
captures the operational cost that quality scores do not represent and must use the same
runtime image, placement, tensor split, context size, and batch size intended for testing.

Record:

- First-load duration: container start to the first successful `/v1/models` response, including whether the GGUF came from shared storage or a rig-local hot set.
- Sustained decode: at least 256 generated tokens (512 preferred) from a deterministic prompt; record completion-token count, generation tok/s, prompt tok/s, and wall time from the server response timings.
- GPU envelope: sample `nvidia-smi` once per second during that same decode; record average and peak power, temperature, and utilization for every participating GPU, plus combined average GPU power and decode energy in Wh.

Store the result in `results/runtime_experiments/` with `quality_ledger: false`. Runtime
results complement quality history; they never replace or invalidate previous model scores.

**Gate**: A reproducible runtime record exists. A format limitation discovered during litmus
must be documented in the tuning profile before the smoke campaign starts.

## Phase 4: Smoke Runs (limit 10)

Run each suite with `--limit 10` to confirm non-zero scores and catch format issues early.

**Why limit 10, not limit 5**: Limit 5 is too few samples to distinguish real model problems
from noise. Limit 10 gives enough signal to catch format extraction failures (e.g. GSM8K
strict-match 0.0 because model outputs `$18` instead of `#### 18`), while still completing
in minutes instead of hours. Always review smoke scores and a few raw outputs before
committing to the full limit 100 run.

**Check raw outputs after smoke**: After the smoke run, inspect 2-3 raw model responses to
verify the model is producing answers in the expected format. A non-zero flexible-extract
score with zero strict-match usually means a format issue that may or may not improve at
scale — decide whether to fix before the full run.

**Pre-flight**:
```bash
# Verify runtime is still up
curl -s http://localhost:<port>/v1/models

# Verify Docker images are current
docker run --rm --entrypoint cat bench-pipeline /opt/bench/run.sh | head -5
# If stale, rebuild:
# cd /mnt/shared/plans/shoulders/benchmarking/docker && docker build -t bench-pipeline bench-pipeline && docker build -t bench-code bench-code && docker build -t bench-reasoning bench-reasoning
```

**Pipeline** (from rig):
```bash
docker run --rm --network host \
  -e BENCHMARK_DISABLE_AUTO_RESERVE=1 \
  -v /mnt/shared:/mnt/shared \
  -v /mnt/shared/logs/benchmarks/bench-pipeline/history:/results \
  -v /mnt/shared/plans/shoulders/benchmarking:/benchmark-scripts:ro \
  bench-pipeline --model <model-id> --runtime-base http://localhost:<port> --run-name <model>_smoke_v1
```

**Code** (from rig):
```bash
docker run --rm --network host \
  -e BENCHMARK_DISABLE_AUTO_RESERVE=1 \
  -v /mnt/shared:/mnt/shared \
  -v /mnt/shared/logs/benchmarks/bench-code/history:/results \
  bench-code --model <model-id> --runtime-base http://localhost:<port> --run-name <model>_smoke_v1
```

**Reasoning** (from rig):
```bash
docker run --rm --network host \
  -e BENCHMARK_DISABLE_AUTO_RESERVE=1 \
  -v /mnt/shared:/mnt/shared \
  -v /mnt/shared/logs/benchmarks/bench-reasoning/history:/results \
  -v /mnt/shared/plans/shoulders/benchmarking:/benchmark-scripts:ro \
  bench-reasoning --model <model-id> --runtime-base http://localhost:<port> --run-name <model>_smoke_v1 --limit 10
```

**Add flags as needed**:
- Gemma 4: `--patch-think-tag-strip` for bench-reasoning (runtime MUST have `--reasoning-budget 0`)
- Qwen 3.x/3.6: `--patch-think-tag-strip` for bench-reasoning (runtime MUST have `--reasoning-budget 0`)
- Phi-4-mini-reasoning / DeepSeek-R1: `--patch-think-tag-strip` for bench-reasoning (structural think tokens, `--reasoning-budget 0` has no effect)

**Verify between suites**:
```bash
curl -s http://localhost:<port>/v1/models
```
If runtime died, reload before continuing.

**Gate**: All suites produce non-zero scores. Record exact scores.

## Phase 5: Full Run

Run the standard suite at limit 50 or 100 for publishable scores.

**Option A: Manual docker runs** (same as Phase 4, with higher limits):
- Reasoning: `--limit 50` or `--limit 100`
- Code: no limit flag (full 542 problems)
- Pipeline: no limit flag (full custom test set)

**Option B: Campaign runner** (preferred for multi-model or multi-suite runs):

Create a campaign manifest and use `run_campaign.py` for automated GPU scheduling,
checkpoint/resume, and parallel execution. See [CAMPAIGN_RUNNER.md](docker/CAMPAIGN_RUNNER.md).

```bash
# Create manifest, then:
python3 /mnt/shared/scripts/benchmarks/run_campaign.py \
  /mnt/shared/plans/shoulders/benchmarking/campaigns/<manifest>.json \
  --dry-run   # verify schedule first
```

**Recommended sequence** (for manual runs): pipeline → code → reasoning (reasoning is longest, do it last).

**Monitor progress**:
```bash
ssh 10.0.0.3 'bash /mnt/shared/scripts/benchmarks/bench_status.sh --deep'
```

**Gate**: All suites complete with stable scores. Record run names and exact scores.

## Phase 6: Finalize

Update all companion docs with the new model's data.

| Doc | What to update |
|-----|---------------|
| [BENCHMARK_SCORES.md](BENCHMARK_SCORES.md) | Add score rows to each suite table |
| [MODEL_LIBRARY.md](MODEL_LIBRARY.md) | Add to Active Model Inventory; update Best Choices if applicable |
| [MODEL_RUNTIME_GUIDE.md](MODEL_RUNTIME_GUIDE.md) | Add runtime notes section for the model |
| [BENCHMARK_LESSONS_LEARNED.md](BENCHMARK_LESSONS_LEARNED.md) | Add entry if non-trivial issues were encountered |

**Gate**: All docs updated, scores published, model is discoverable.

---

## Decision Trees

### Litmus Fails: Think Tags in Output

```
Litmus shows <think> tags or empty content
├── Check model family
│
├── OpenAI gpt-oss (channel-based thinking)
│   → thinking=1 but content field is CLEAN
│   → Reasoning goes to reasoning_content field via channel system
│   → No --reasoning-budget 0 needed, no --patch-think-tag-strip needed
│   → This is the ideal behavior — litmus should pass all 3 checks
│   → If litmus passes: proceed normally, no special bench flags
│
├── Qwen 3.x / 3.5 / 3.6
│   → Add --reasoning-budget 0 to runtime args
│   → Reload runtime
│   → Retest litmus
│   → If still shows empty <think></think> wrappers:
│     add --patch-think-tag-strip at bench time
│
├── Gemma 4 (any size)
│   → Expected: model uses <|channel>thought prefix
│   → Content field should still have the answer
│   → If content empty: reasoning consumed max_gen_toks
│   → Fix: --reasoning-budget 0 on runtime (REQUIRED for ALL sizes)
│   → A/B tested on 12B: budget=0 scored BBH 0.82, budget=1024 scored 0.24
│   → Confirmed on 26B-A4B: budget=0 scored BBH 0.87, previous thinking-on was 0.27
│   → Thinking tokens consume generation budget → answer truncated
│   → Also apply --patch-think-tag-strip at bench time (BBH + DROP)
│   → Mark litmus PASS with note
│
├── DeepSeek-R1 (any size)
│   → Structural: <think> tokens baked into vocabulary
│   → --reasoning-budget 0 does NOT help
│   → --patch-think-tag-strip partially helps (BBH yes, DROP no, code no)
│   → Record limitation, proceed with known constraints
│
└── Phi-4-mini-reasoning (and similar reasoning-finetuned models)
    → Structural: <think> tokens from reasoning finetune
    → --reasoning-budget 0 does NOT help (runtime shows thinking=0 anyway)
    → --patch-think-tag-strip needed for BBH/DROP
    → Code suite will have degraded results (think tokens stripped with code)
    → Same behavior pattern as DeepSeek-R1
```

### Smoke Suite Scores All Zero

```
All scores 0 in a suite
├── Check container logs for "Use model prompts: 1"
│   └── Shows 0 → Stale Docker image
│       → Rebuild: docker build -t bench-<suite> bench-<suite>
│
├── Check container logs for "thinking = 1"
│   └── Shows 1 → Thinking mode active
│       → Add --reasoning-budget 0 to runtime, reload
│       → Verify: docker logs <ctr> 2>&1 | grep "thinking ="
│
├── Check if model ID fuzzy-matches tuning profiles
│   └── No match → Model prompts not resolving
│       → Add explicit alias to model_tuning_profiles.json
│       → Or run with --allow-generic-prompt-fallback
│
└── Check for stop sequence truncation
    ├── BBH: \n\n stop truncates after think tags
    │   → Apply --patch-think-tag-strip
    └── DROP: . stop truncates inside think chains
        → Apply --patch-think-tag-strip + max_gen_toks 512
```

### Runtime Won't Load (OOM / Timeout)

```
Runtime fails to start or gets OOM-killed
├── Exit code 137 (Docker OOM)
│   → Container hit memory limit
│   → Increase memory_limit in config.benchmark.json
│   → Or add --memory=Xg --memory-swap=Yg to docker run
│
├── Split model fails with "need to use X MiB less"
│   → Remove --n-gpu-layers 999, let llama.cpp auto-fit
│   → The auto-fitter will place layers across GPUs correctly
│
├── Timeout (no /v1/models response after 300s)
│   → Reduce ctx_size (try 4096 for smoke, increase later)
│   → Check if model is too large for target GPUs
│   → For split: ensure both GPUs are free
│
├── "unknown model architecture" error
│   → Runtime image too old for this model family
│   → Check required image tag in MODEL_RUNTIME_GUIDE.md
│   → Rebuild/pull updated runtime image
│
└── System RAM pressure
    → Check: free -h; docker stats --no-stream
    → See docker/README.md "Memory Protection" section
    → Reduce number of concurrent models
```

### Code Suite All-Zero but Pipeline/Reasoning Work

```
bench-code produces 0% but other suites score
├── Think tags consumed code output
│   → evalplus sanitizer strips <think> + code together
│   → No clean fix for thinking models
│   → Record as known limitation
│
└── Model emits markdown fences around code
    → evalplus expects raw code
    → Check if code output starts with ```python
    → May need prompt tuning to suppress fences
```

### Special Model Types

**MoE (Mixture of Experts)** — e.g., Gemma 4 26B-A4B, Qwen3.5 35B-A3B, gpt-oss 20B:
- GGUF file size reflects total params but active params per-token are much smaller
- Inference speed closer to the active param count (3-4B active runs like a 3-4B dense model)
- VRAM usage depends on total params (all experts must be loaded), not active params
- Brain tier for models >12GB GGUF, single tier if GGUF fits in 6GB

**MXFP4/Native Quantization** — e.g., gpt-oss 20B:
- Some models ship as MXFP4 (Microscaling FP4) GGUFs instead of post-training quantized Q4/Q8
- llama.cpp handles MXFP4 natively (supported since ~b6962, our runtime is b8884+)
- No special flags needed — treat like any other GGUF
- File size may differ from Q4_K_M expectations for same param count

**OpenAI-family models** — e.g., gpt-oss:
- Require `--jinja` flag for chat template processing
- Add `--extra-arg "--jinja"` to run_runtime.sh invocation
- Add `"--jinja"` to `extra_args` in tuning profiles

---

## Phase Checklist Template

Copy this section for each new model integration. Replace placeholders with actual values.

```markdown
## Integration: <model-name> (<date>)

Tier: <single/split/brain> | GPU target: <gpu list> | Port: <port>
GGUF: <filename> | Size: <size> | Source: <url>

### Phase 0: Download
- [ ] GGUF downloaded to `/mnt/shared/models/<dir>/`
- [ ] File size verified: <expected> vs <actual>
- Notes:

### Phase 1: Register
- [ ] `model_tuning_profiles.json` — GGUF key added
- [ ] `model_tuning_profiles.json` — short alias added
- [ ] `models.catalog.json` — entry added
- [ ] System prompt: <which prompt family>
- [ ] Runtime config: ctx_size=<>, batch_size=<>, n_gpu_layers=<>
- Notes:

### Phase 2: First Load
- [ ] Runtime started with `run_runtime.sh`
- [ ] `/v1/models` responds with correct model ID
- [ ] Docker logs checked — no warnings
- [ ] VRAM usage: <amount>
- [ ] Load time: <seconds>
- [ ] Runtime image: <image tag>
- [ ] Extra args needed: <list or none>
- Notes:

### Phase 3: Litmus Test
- [ ] Reasoning check (555): PASS/FAIL
- [ ] JSON check: PASS/FAIL
- [ ] Code generation check: PASS/FAIL
- Fixes applied: <none or description>
- Notes:

### Phase 4: Smoke Runs (limit 10)
- [ ] bench-pipeline: <scores or link>
- [ ] bench-code: <scores or link>
- [ ] bench-reasoning --limit 10: <scores or link>
- [ ] Raw outputs inspected — format issues identified and documented
- [ ] All suites produce non-zero scores
- Flags needed: <list>
- Fixes applied: <none or description>
- Notes:

### Phase 5: Full Run (limit 50/100)
- [ ] bench-pipeline: <scores>
- [ ] bench-code: <scores>
- [ ] bench-reasoning --limit <N>: <scores>
- Run names: <list>
- Notes:

### Phase 6: Finalize
- [ ] BENCHMARK_SCORES.md updated
- [ ] MODEL_LIBRARY.md inventory updated
- [ ] MODEL_RUNTIME_GUIDE.md notes added
- [ ] BENCHMARK_LESSONS_LEARNED.md updated (if applicable)
```

---

# Part 2: Integration Log

## Integration: Gemma 4 12B (2026-06-05)

Tier: split (2x 1060 6GB) | GPU target: GPU 1+3 or 4+5 | Port: 11440 or 11441
GGUF: `gemma-4-12B-it-Q4_K_M.gguf` | Size: 7.4 GB (Q4_K_M) | Source: HuggingFace (google/gemma-4-12b-it-GGUF)

### Phase 0: Download
- [x] GGUF downloaded to `/mnt/shared/models/gemma-4-12b/`
- [x] File size verified: ~7.4 GB expected vs 7381382048 bytes (6.9 GiB) actual
- Notes: File already present on shared drive.

### Phase 1: Register
- [x] `model_tuning_profiles.json` — GGUF key added (`gemma-4-12B-it-Q4_K_M.gguf`)
- [x] `model_tuning_profiles.json` — short alias added (`gemma-4:12b`)
- [x] `models.catalog.json` — entry added (tier 2, split_gpu, pair_1_3/pair_4_5)
- [x] System prompt: Worker (strict) — same family as other Gemma 4 models
- [x] Runtime config: ctx_size=8192, batch_size=64, n_gpu_layers=999
- Notes: Used same prompt and config pattern as gemma-4-e4b/e2b. Split placement matches qwen2.5-coder:14b and phi-4:14b split groups.

### Phase 2: First Load
- [x] Runtime started with `run_runtime.sh`
- [x] `/v1/models` responds with correct model ID (`gemma-4-12B-it-Q4_K_M.gguf`)
- [x] Docker logs checked — no warnings (thinking=1 as expected for Gemma 4)
- [x] VRAM usage: GPU 1: 3372 MiB, GPU 3: 4060 MiB, CPU mapped: 924 MiB
- [x] Load time: ~40s
- [x] Runtime image: `llama-runtime:b8884-candidate` (b8884-750579ff1)
- [x] Extra args needed: `--tensor-split 1,1` (NOT `1,0,1,0,0,0` — use 2-value mask matching visible GPUs), `-fit off` (auto-fitter fails with forced `--n-gpu-layers 999`), no forced n-gpu-layers
- Notes:
  - First attempt with `--n-gpu-layers 999`: auto-fitter aborted ("n_gpu_layers already set by user to 999, abort")
  - Second attempt without forced layers but `--tensor-split 1,0,1,0,0,0`: OOM on CUDA0 — the 6-value split mask doesn't match 2 visible GPUs, full 7024 MiB allocated to device 0
  - Third attempt with `--tensor-split 1,1 -fit off --n-gpu-layers 48`: success, model split across both GPUs
  - Model buffer: CUDA0=3102 MiB, CUDA1=3786 MiB, CPU=924 MiB
  - KV cache: 34 MiB (non-SWA, 8 layers) + 212.5 MiB (SWA, 40 layers)

### Phase 3: Litmus Test
- [x] Reasoning check (555): **PASS** — clean "555" response, no think tags
- [!] JSON check: **FAIL** — wraps JSON in ```json markdown fences (known Gemma 4 behavior, consistent with E4B/E2B)
- [x] Code generation check: **PASS** — clean function output (wraps in ```python but function present)
- Fixes applied: none — JSON fencing is a known Gemma 4 trait handled by system prompt at bench time
- Notes: thinking=1 active in runtime but content field receives the answer correctly. `--patch-think-tag-strip` will be needed for DROP (same as all Gemma 4 models).

### Phase 4: Smoke Runs → merged with Phase 5
- Skipped standalone smoke (limit 5) — went directly to full runs since pipeline is fast and code has no limit option.

### Phase 5: Full Run
- [x] bench-pipeline (full): json_schema 23.1%, cmd_safety 75.0%, ambiguity 46.2%, tool_plan 93.3%, orch_tradeoff 83.3%, long_context 92.9%
- [x] bench-code (full 542): HumanEval base 11.0%, plus 11.0%; MBPP base 36.8%, plus 34.7%
- [x] bench-reasoning: COMPLETED (A/B test: thinking-on vs thinking-off)
- Run names: `gemma4_12b_smoke_v1` (pipeline, code), `gemma4_12b_l100_v2` (reasoning GSM8K), `gemma4_12b_think1024_bbh_l5` (BBH think-on), `gemma4_12b_nobudget_bbh_l5` (BBH think-off)
- Flags needed: `-e BENCHMARK_DISABLE_AUTO_RESERVE=1` for all suites, `--patch-think-tag-strip` for reasoning
- Notes:
  - Pipeline took ~45 min on split 1060s. Non-zero on all 6 tests.
  - Code took ~12 hours on split 1060s (542 problems at ~0.75/min). Low HumanEval consistent with other Gemma 4 models — markdown code fences stripped by evalplus sanitizer.
  - First reasoning attempt (v1) failed: rig root disk 100% full, HuggingFace dataset download failed. Fixed by `docker container prune && docker image prune` (freed 22 GB). Retried as v2.
  - Reasoning v2 (l100): GSM8K completed: strict 0.01, flexible 0.10. Low strict score is format mismatch: model outputs `$18` instead of `#### 18`. Flexible extract also low because `$` prefix confuses number extractor. Known Gemma 4 output format issue, not a capability issue.
  - L100 BBH/DROP never completed — l100 BBH on split 1060s estimated 50+ hours. Run was stopped in favor of A/B testing approach.
  - **A/B Test: Thinking On vs Off (BBH l5)**:
    - Two runtimes loaded: `gemma4-12b-budget1024` (GPUs 1+3, port 11440, `--reasoning-budget 1024`) and `gemma4-12b-nobudget` (GPUs 4+5, port 11441, `--reasoning-budget 0`)
    - Both running BBH l5 (135 requests each) simultaneously
    - Budget=1024 generates ~1800 tokens/request (thinking + answer), budget=0 generates ~750 tokens/request
    - **Think-off result: BBH = 0.8222** (completed in 2h25m, avg 64s/req)
    - **Think-on result: BBH = 0.2444** (completed in 3h57m, avg 106s/req)
    - **Verdict**: `--reasoning-budget 0` is vastly better for BBH benchmarks. Thinking tokens consume generation budget, truncating the CoT answer before the "So the answer is..." extraction point. 13 of 27 subtasks scored 0.0 with thinking on.
    - **Recommendation for Gemma 4 12B benchmarks**: Use `--reasoning-budget 0` for all reasoning suites. The model reasons well in the visible output without needing the hidden thinking channel.
  - **Brain re-run (2026-06-13)**: BBH l50 and DROP l50 on brain (3090) with `--reasoning-budget 0` and `--patch-think-tag-strip`:
    - BBH l50: 0.8067 (confirmed l5 A/B test score of 0.822)
    - DROP l50: EM 0.7400, F1 0.7892 — first DROP score, very strong
    - Runtime: brain (GPU 0, 3090), `llama-runtime:b8884-candidate`, ~75 min total
    - Run name: `gemma4_12b_brain_l50_v1`
    - Note: Previous overnight attempt failed due to using default `sm61-sm86` image (Gemma 4 arch unsupported). Fixed by specifying `--image llama-runtime:b8884-candidate`.

### Phase 6: Finalize
- [x] BENCHMARK_SCORES.md updated — family summary, pipeline, code, reasoning tables + notes (updated with brain l50 BBH/DROP)
- [x] MODEL_LIBRARY.md inventory updated — added to Active Model Inventory as 12B split
- [x] MODEL_RUNTIME_GUIDE.md notes added — updated gemma-4 family section, thinking reference, context sizes
- [x] BENCHMARK_LESSONS_LEARNED.md updated — thinking A/B test results, split-load findings, runtime image mismatch lesson
- Notes: BBH 0.807 at l50 confirms l5 A/B test. DROP F1 0.789 is competitive with 26B-A4B (0.785) and 31B (0.793). GSM8K format issue (0.10) remains — known Gemma 4 output format, not capability.

## Integration: gpt-oss 20B (2026-06-12)

Tier: brain (3090 24GB) | GPU target: GPU 0 | Port: 11434
GGUF: `gpt-oss-20b-mxfp4.gguf` | Size: 12.1 GB (MXFP4 native) | Source: HuggingFace (ggml-org/gpt-oss-20b-GGUF)

Architecture: MoE, 21B total params, 3.6B active. OpenAI's first open-weight model. Apache 2.0.

### Phase 0: Download
- [x] GGUF downloaded to `/mnt/shared/models/gpt-oss-20b/`
- [x] File size verified: ~12.1 GB expected vs 12,109,566,560 bytes (11.3 GiB) actual
- Notes: Downloaded via wget from HuggingFace. MXFP4 is a native quantization format (not post-training quant like Q4_K_M).

### Phase 1: Register
- [x] `model_tuning_profiles.json` — GGUF key added (`gpt-oss-20b-mxfp4.gguf`)
- [x] `model_tuning_profiles.json` — short alias added (`gpt-oss:20b`)
- [x] `models.catalog.json` — entry added (tier 3, single_gpu/brain)
- [x] System prompt: Worker (strict)
- [x] Runtime config: ctx_size=16384, batch_size=128, n_gpu_layers=999
- [x] Extra args: `--jinja` (required for OpenAI chat template)
- Notes: First MXFP4 model in our catalog. MoE with 3.6B active — should be fast despite 20B total.

### Phase 2: First Load
- [x] Runtime started with `run_runtime.sh`
- [x] `/v1/models` responds with correct model ID (`gpt-oss-20b-mxfp4.gguf`)
- [x] Docker logs checked — clean load, `thinking = 1` (runtime auto-detects thinking via OpenAI channels)
- [x] VRAM usage: 11,587 MiB on GPU 0 (13GB headroom on 3090)
- [x] Load time: ~5s
- [x] Runtime image: llama-runtime:sm61-sm86
- [x] Extra args needed: `--jinja` (confirmed required for chat template)
- Notes: Chat template uses OpenAI channel system (`<|start|>`, `<|channel|>`, `<|message|>`, `<|end|>`). Channels: analysis, commentary, final. "Reasoning: medium" preset. Compute buffer: 99.6 MiB. KV cache at ctx 16384.

### Phase 3: Litmus Test
- [x] Reasoning check (555): **PASS** — clean "555" in content, reasoning goes to `reasoning_content` field (properly separated)
- [x] JSON check: **PASS** — clean valid JSON `{"name":"Alice","age":30}`, no markdown fences
- [x] Code generation check: **PASS** — clean `def is_palindrome(s): return s == s[::-1]`
- Fixes applied: none needed
- Notes: Cleanest litmus results of any model tested. thinking=1 but reasoning goes to separate `reasoning_content` field via OpenAI channel system, not inline `<think>` tags. Content field is always clean. No `--reasoning-budget 0` needed, no `--patch-think-tag-strip` needed. This is how thinking SHOULD work.

### Phase 4: Smoke Runs (limit 10)
- [x] bench-pipeline: json_schema 23.1%, cmd_safety 75.0%, ambiguity 15.4%, tool_plan 93.3%, orch_tradeoff 75.0%, long_context 92.9%
- [x] bench-code (full 542): HumanEval base 62.2% / plus 58.5%, MBPP base 73.8% / plus 63.5%
- [x] bench-reasoning --limit 10 (v1, OLD prompt): GSM8K strict 20% / flexible 80%, BBH 6.7%, DROP EM 50% / F1 60%
- [x] bench-reasoning --limit 10 (v2, FIXED prompt): GSM8K strict 20% / flexible 60%, **BBH 64.1%**, DROP EM 20% / F1 44.8%
- [x] Raw outputs inspected — BBH extraction failure diagnosed (see notes)
- [x] All suites produce non-zero scores (except BBH v1 — fixed in v2)
- Flags needed: None for pipeline/code. `--reasoning-budget 0` added to runtime for reasoning v2 (prompt fix, not thinking suppression).
- Fixes applied:
  - **BBH 6.7% root cause**: Channel-based thinking puts reasoning in `reasoning_content`, content gets only terse bare letter ("A"). System prompt "keep output minimal" reinforced this. Additionally, when model does output "So the answer is", it wraps answer in markdown bold `**(A)**` which breaks the `get-answer` regex `[Ss]o the answer is \(([A-Za-z])\)`.
  - **Fix**: Changed system prompt to: "reason briefly then conclude with exactly: So the answer is (X). Use plain text only, no markdown formatting." Added `--reasoning-budget 0` to `extra_args` (prevents channel reasoning from consuming output budget).
  - **Verified**: Manual curl test with updated prompt produces extractable "So the answer is (B)." — regex matches.
- Notes:
  - Pipeline: ~65s total on 3090. All 6 stages non-zero.
  - Code: ~32 min on 3090. Best HumanEval base (62.2%) and MBPP base (73.8%) in catalog.
  - Reasoning v1: GSM8K and DROP decent, BBH is extraction-broken (not capability).
  - Run names: `gptoss_smoke_v1` (pipeline), `gptoss_code_v1` (code), `gptoss_smoke_v1` (reasoning v1), `gptoss_smoke_v2` (reasoning v2)

### Phase 5: Full Run (limit 50/100)
- [x] bench-reasoning --limit 100 (GSM8K, BBH, DROP): COMPLETE
  - Run name: `gptoss_l100_v1`
  - GSM8K: strict 0.15, flexible 0.80 (strict low due to format: model outputs number without `#### N` prefix)
  - BBH: 0.645 (confirmed l10 smoke score of 0.641 — prompt fix is stable at scale)
  - DROP: EM 0.18, F1 0.351
  - Runtime: brain (GPU 0, 3090), ~82 min total, `--reasoning-budget 0`, `--jinja`
- [n/a] bench-pipeline: no limit parameter (fixed test set), smoke run is the full run
- [n/a] bench-code: no limit parameter (fixed test set), smoke run is the full run
- Notes: GSM8K flexible improved from 0.60 (l10) to 0.80 (l100) — small sample noise at l10. BBH and DROP stable. This model's main strength is code generation (HumanEval 62.2%, MBPP 73.8%).

### Phase 6: Finalize
- [x] BENCHMARK_SCORES.md updated (l100 reasoning scores, family summary)
- [x] MODEL_LIBRARY.md inventory updated
- [x] MODEL_RUNTIME_GUIDE.md notes added
- [x] BENCHMARK_LESSONS_LEARNED.md updated (channel-based thinking narrative)

## Integration: Phi-4-mini-reasoning 3.8B (2026-06-12)

Tier: single (1060 6GB) | GPU target: GPUs 1-5 | Port: 11435-11439
GGUF: `Phi-4-mini-reasoning-Q4_K_M.gguf` | Size: 2.49 GB (Q4_K_M) | Source: HuggingFace (unsloth/Phi-4-mini-reasoning-GGUF)

Architecture: Dense 3.8B. Microsoft reasoning-focused variant of Phi-4-mini. MIT license.
Has `<think>`/`</think>` reasoning tokens — similar to DeepSeek-R1 family.

### Phase 0: Download
- [x] GGUF downloaded to `/mnt/shared/models/phi-4-mini-reasoning/`
- [x] File size verified: ~2.49 GB expected vs 2.4 GB actual
- Notes: Downloaded via wget from HuggingFace (unsloth GGUF conversion).

### Phase 1: Register
- [x] `model_tuning_profiles.json` — GGUF key added (`Phi-4-mini-reasoning-Q4_K_M.gguf`)
- [x] `model_tuning_profiles.json` — short alias added (`phi-4-mini-reasoning:3.8b`)
- [x] `models.catalog.json` — entry added (tier 1, single_gpu)
- [x] System prompt: Worker (strict)
- [x] Runtime config: ctx_size=4096, batch_size=64, n_gpu_layers=999
- Notes: Same size as phi-4-mini-instruct but different model — trained specifically for reasoning with think tokens.

### Phase 2: First Load
- [x] Runtime started with `run_runtime.sh`
- [x] `/v1/models` responds with correct model ID (`Phi-4-mini-reasoning-Q4_K_M.gguf`)
- [x] Docker logs checked — no warnings, `thinking = 0` (runtime doesn't auto-detect thinking mode)
- [x] VRAM usage: 2772 MiB on GPU 1
- [x] Load time: ~3s
- [x] Runtime image: llama-runtime:sm61-sm86
- [x] Extra args needed: `--reasoning-budget 0` tested but has NO EFFECT — think tokens are structural (same as DeepSeek-R1)
- Notes: Chat template detected as Phi-style (`<|system|>`, `<|user|>`, `<|assistant|>`). KV cache 272 MiB (q8_0). Model metadata includes `general.finetune = reasoning`.

### Phase 3: Litmus Test
- [!] Reasoning check (555): **FAIL** — correct answer (555) but wrapped in verbose `<think>` chain-of-thought
- [!] JSON check: **FAIL** — think tags + wraps JSON in ```json markdown fences
- [!] Code generation check: **FAIL** — think tags present, function is correct inside
- Fixes applied: None effective — `--reasoning-budget 0` does not suppress think tokens. They are structural (baked into model vocabulary/training), not an API feature.
- Notes: Identical behavior to DeepSeek-R1 family. The model always generates `<think>...</think>` blocks before the answer. Answers themselves are correct. Will use `--patch-think-tag-strip` at bench time for BBH/DROP. Code suite will have degraded results (evalplus sanitizer strips think + code together). This is a known limitation for think-token models.

### Phase 4: Smoke Runs (limit 10)
- [x] bench-pipeline: json_schema 0%, cmd_safety 83.3%, ambiguity 76.9%, tool_plan 100%, orch_tradeoff 83.3%, long_context FAILED (runtime OOM killed)
- [!] bench-code: **INCOMPATIBLE** — structural think tokens break evalplus code extraction
  - v1: OOM killed at 2g Docker memory limit (anon-rss: 2073576kB)
  - v2: Restarted with 3g/4g limits, got 64/164 HumanEval before runtime timeout
  - Root cause: Think chains produce very long output (thousands of tokens) per problem, causing either memory pressure or timeouts on 1060
  - Parsed solutions show `<think>` as entire content — evalplus sanitizer strips think + code together
  - **Known limitation**: bench-code is not viable for structural-think-token models on 1060 hardware
- [!] bench-reasoning --limit 10: GSM8K strict 0% / flex 10%. **BBH FAILED** (runtime OOM killed after ~52 min). **DROP FAILED** (runtime already dead).
  - Root cause: BBH few-shot prompts are long (~1000+ tokens), combined with think chains exhausts memory at 3g Docker limit on 1060
  - GSM8K completed because prompts are shorter and 10 requests finished before memory pressure built
- [x] Raw outputs inspected — think tokens in all outputs confirmed
- [!] Not all suites produce non-zero scores (json_schema 0%, bench-code incompatible)
- Flags needed: `--patch-think-tag-strip` for bench-reasoning. Memory limit 3g/4g for runtime.
- Notes:
  - Pipeline: 5/6 stages passed, 1 failed (long_context — runtime died under memory pressure from long context + think chains)
  - Code: Known limitation, documented. Not a model settings fix — structural think tokens can't be disabled.
  - Reasoning: Not yet attempted. Expected to work with `--patch-think-tag-strip`.
  - Run names: `phi4mr_smoke_v1` (pipeline), `phi4mr_smoke_v1`/`phi4mr_smoke_v2` (code — both failed)
  - **Known Suite Incompatibilities**:
    - bench-code: Structural think tokens break evalplus extraction. No model settings fix available.
    - bench-pipeline json_schema: Think tokens in JSON responses. Would need `--patch-think-tag-strip` equivalent for pipeline suite.

### Phase 5: Full Run (limit 50/100)
- [ ] bench-pipeline: <pending>
- [ ] bench-code: **SKIPPED** — known incompatibility (structural think tokens)
- [ ] bench-reasoning --limit 50: <pending>
- Run names:
- Notes: bench-code skipped due to documented incompatibility.

### Phase 6: Finalize
- [ ] BENCHMARK_SCORES.md updated
- [ ] MODEL_LIBRARY.md inventory updated
- [ ] MODEL_RUNTIME_GUIDE.md notes added
- [ ] BENCHMARK_LESSONS_LEARNED.md updated (if applicable)
