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
| 4 | Smoke Runs | 30 min - 2h | All suites produce non-zero scores |
| 5 | Full Run | 2-12h | Limit 50/100 scores recorded |
| 6 | Finalize | 10 min | All companion docs updated |

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
  --gguf /mnt/shared/models/<model-dir>/<filename>.gguf \
  --port <port> \
  --gpu <gpu-id> \
  --ctx-size <from profile> \
  --batch-size <from profile>

# Split GPU (14B tier)
/mnt/shared/scripts/llama_runtime/run_runtime.sh \
  --gguf /mnt/shared/models/<model-dir>/<filename>.gguf \
  --port <port> \
  --gpu <gpu1>,<gpu2> \
  --ctx-size <from profile> \
  --batch-size <from profile>
```

**Extra args** (add as needed):
- Qwen 3.x/3.5/3.6: `--extra-arg "--reasoning-budget" --extra-arg "0"`
- Gemma 4 (all sizes): `--extra-arg "--reasoning-budget" --extra-arg "0"` (REQUIRED — thinking mode destroys BBH/DROP extraction)
- Split models that fail with `--n-gpu-layers 999`: remove forced layer count, let llama.cpp auto-fit

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
  -v /mnt/shared:/mnt/shared \
  -v /mnt/shared/logs/benchmarks/bench-code/history:/results \
  bench-code --model <model-id> --runtime-base http://localhost:<port> --run-name <model>_smoke_v1
```

**Reasoning** (from rig):
```bash
docker run --rm --network host \
  -v /mnt/shared:/mnt/shared \
  -v /mnt/shared/logs/benchmarks/bench-reasoning/history:/results \
  -v /mnt/shared/plans/shoulders/benchmarking:/benchmark-scripts:ro \
  bench-reasoning --model <model-id> --runtime-base http://localhost:<port> --run-name <model>_smoke_v1 --limit 10
```

**Add flags as needed**:
- Gemma 4: `--patch-think-tag-strip` for bench-reasoning (runtime MUST have `--reasoning-budget 0`)
- Qwen 3.x/3.6: `--patch-think-tag-strip` for bench-reasoning (runtime MUST have `--reasoning-budget 0`)

**Verify between suites**:
```bash
curl -s http://localhost:<port>/v1/models
```
If runtime died, reload before continuing.

**Gate**: All suites produce non-zero scores. Record exact scores.

## Phase 5: Full Run

Run the standard suite at limit 50 or 100 for publishable scores.

Use the same commands as Phase 4, with:
- Reasoning: `--limit 50` or `--limit 100`
- Code: no limit flag (full 542 problems)
- Pipeline: no limit flag (full custom test set)

**Recommended sequence**: pipeline → code → reasoning (reasoning is longest, do it last).

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
└── DeepSeek-R1 (any size)
    → Structural: <think> tokens baked into vocabulary
    → --reasoning-budget 0 does NOT help
    → --patch-think-tag-strip partially helps (BBH yes, DROP no, code no)
    → Record limitation, proceed with known constraints
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

### Phase 6: Finalize
- [x] BENCHMARK_SCORES.md updated — family summary, pipeline, code, reasoning tables + notes
- [x] MODEL_LIBRARY.md inventory updated — added to Active Model Inventory as 12B split
- [x] MODEL_RUNTIME_GUIDE.md notes added — updated gemma-4 family section, thinking reference, context sizes
- [x] BENCHMARK_LESSONS_LEARNED.md updated — thinking A/B test results and split-load findings
- Notes: DROP not yet run. GSM8K format issue (0.10) is known. BBH 0.822 is strong (best in Gemma 4 family by wide margin when thinking is off).
