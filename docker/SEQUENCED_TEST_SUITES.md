# Sequenced Test Suites

This document describes the corrected operator path for running several
benchmark suites back to back on the same loaded runtime.

The working method is manual suite sequencing against a verified live port.
Do not use a campaign wrapper as the primary operator path for worker
benchmarks.

## Correct Sequencing Model

The sequence is:

1. load the target model runtime
2. verify the runtime answers `/v1/models` with the expected model
3. run one suite directly with `docker run --rm ... bench-*`
4. when it finishes, run the next suite against the same port
5. if the runtime disappears, stop and repair the runtime before launching the next suite

This keeps each suite independent and matches the successful 12B/14B runs from
2026-03-14 through 2026-03-16.

## Why This Is The Canonical Path

This is the pattern that already worked in live runs:

- 14B split pipeline smoke runs on ports `11437` and `11438`
- 14B split code smoke runs on those same ports
- 14B split reasoning smoke runs on those same ports
- 12B single-worker pipeline/reasoning/code smoke runs on `11435`

The historical artifacts for those runs are in:

- `/media/bryan/shared/logs/benchmarks/bench-pipeline/history`
- `/media/bryan/shared/logs/benchmarks/bench-code/history`
- `/media/bryan/shared/logs/benchmarks/bench-reasoning/history`

Examples that completed cleanly:

- `bench-pipeline_qwen2.5-coder_14b_pipeline_coder14b_split_smoke_v1`
- `bench-code_qwen2.5-coder_14b_code_coder14b_split_smoke_v1`
- `bench-reasoning_qwen2.5-coder_14b_reasoning_coder14b_split_smoke_v1`
- `bench-pipeline_gemma-3_12b_pipeline_gemma3_smoke_v1`
- `bench-code_phi-4_14b_code_phi4_smoke_v1`

## Operator Rules

- Load models one at a time.
- Verify `/v1/models` before every suite launch.
- Treat each suite as its own Docker job.
- Reuse the same `--run-name` only when intentionally resuming that same suite.
- Do not assume the runtime stayed healthy between suites; check it directly.
- If `bench-code` loses the runtime and starts reconnecting forever, stop the container and repair the runtime before retrying.

## Standard Sequence

Default order:

1. `bench-pipeline`
2. `bench-code`
3. `bench-reasoning`

Reason:

- `bench-pipeline` is the fastest way to catch broken formatting, JSON, and instruction-following failures
- `bench-code` is expensive and should only run after the runtime has already passed basic reliability checks
- `bench-reasoning` is long-running and should be launched only after the runtime path is proven stable

`bench-knowledge` is separate and should not be part of the default worker sequence.

`bench-daedalmap` is also separate from the default worker sequence. It is a custom
chat-routing suite, not a replacement for `bench-pipeline` / `bench-code` / `bench-reasoning`.
Use it when you want to evaluate DaedalMap-specific instruction following and bucket-backed
source availability on the same loaded runtime.

## Runtime Verification

Before each suite:

```bash
curl -s http://localhost:11437/v1/models
```

Confirm:

- the port responds
- the expected model is listed

If the response is wrong or empty, fix the runtime first. Do not launch the next suite.

## 7B Single-Worker Sequence

Example: GPU 2, port `11436`

Pipeline:

```bash
docker run --rm --network host \
  -e BENCHMARK_DISABLE_AUTO_RESERVE=1 \
  -v /mnt/shared:/mnt/shared \
  -v /mnt/shared/logs/benchmarks/bench-pipeline/history:/results \
  -v /mnt/shared/plans/shoulders/benchmarking:/benchmark-scripts:ro \
  bench-pipeline \
  --model qwen2.5-coder:7b \
  --runtime-base http://localhost:11436 \
  --run-name pipeline_coder7b_v1
```

Code:

```bash
docker run --rm --network host \
  -v /mnt/shared:/mnt/shared \
  -v /mnt/shared/logs/benchmarks/bench-code/history:/results \
  bench-code \
  --model qwen2.5-coder:7b \
  --runtime-base http://localhost:11436 \
  --tasks humaneval,mbpp \
  --run-name code_coder7b_v1
```

Reasoning:

```bash
docker run --rm --network host \
  -v /mnt/shared:/mnt/shared \
  -v /mnt/shared/logs/benchmarks/bench-reasoning/history:/results \
  -v /mnt/shared/plans/shoulders/benchmarking:/benchmark-scripts:ro \
  bench-reasoning \
  --model qwen2.5-coder:7b \
  --runtime-base http://localhost:11436 \
  --tasks gsm8k,bbh,drop \
  --limit 50 \
  --run-name reasoning_coder7b_l50_v1
```

DaedalMap smoke:

```bash
docker run --rm --network host \
  --env-file /mnt/shared/plans/shoulders/benchmarking/docker/bench-daedalmap/.env \
  -e BENCHMARK_DISABLE_AUTO_RESERVE=1 \
  -v /mnt/shared:/mnt/shared \
  -v /mnt/shared/logs/benchmarks/bench-daedalmap/history:/results \
  -v /mnt/shared/plans/shoulders/benchmarking:/benchmark-scripts:ro \
  bench-daedalmap \
  --model qwen2.5-coder:7b \
  --runtime-base http://localhost:11436 \
  --tasks json_discipline,source_grounding \
  --limit 5 \
  --run-name daedalmap_smoke_coder7b_v1
```

DaedalMap bucket-backed smoke:

```bash
docker run --rm --network host \
  --env-file /mnt/shared/plans/shoulders/benchmarking/docker/bench-daedalmap/.env \
  -e BENCHMARK_DISABLE_AUTO_RESERVE=1 \
  -v /mnt/shared:/mnt/shared \
  -v /mnt/shared/logs/benchmarks/bench-daedalmap/history:/results \
  -v /mnt/shared/plans/shoulders/benchmarking:/benchmark-scripts:ro \
  bench-daedalmap \
  --model qwen2.5-coder:7b \
  --runtime-base http://localhost:11436 \
  --tasks geographic_precision,multi_source \
  --limit 1 \
  --execute \
  --run-name daedalmap_bucket_smoke_coder7b_v1
```

## 14B Split-Worker Sequence

For 14B models on 2x 1060, first launch the split runtime, then run suites
directly against the split port.

Example runtime launch for GPUs `1+3`, port `11437`:

```bash
docker run -d --name llama-split-13 \
  --runtime=nvidia -e NVIDIA_VISIBLE_DEVICES=1,3 \
  -p 11437:8000 \
  -v /mnt/shared/models:/models:ro \
  llama-runtime:sm61-sm86 \
  --model /models/qwen2.5-coder-14b/Qwen2.5-Coder-14B-Instruct-Q4_K_M.gguf \
  --n-gpu-layers 999 --split-mode layer --tensor-split 1,1 \
  --ctx-size 8192 --host 0.0.0.0 --port 8000
```

Key flags:

- `--runtime=nvidia -e NVIDIA_VISIBLE_DEVICES=1,3`
- `--split-mode layer`
- `--tensor-split 1,1`

Then verify:

```bash
curl -s http://localhost:11437/v1/models
```

Then run suites one at a time.

Pipeline:

```bash
docker run --rm --network host \
  -e BENCHMARK_DISABLE_AUTO_RESERVE=1 \
  -v /mnt/shared:/mnt/shared \
  -v /mnt/shared/logs/benchmarks/bench-pipeline/history:/results \
  -v /mnt/shared/plans/shoulders/benchmarking:/benchmark-scripts:ro \
  bench-pipeline \
  --model qwen2.5-coder:14b \
  --runtime-base http://localhost:11437 \
  --run-name pipeline_coder14b_split_smoke_v1
```

Code:

```bash
docker run --rm --network host \
  -v /mnt/shared:/mnt/shared \
  -v /mnt/shared/logs/benchmarks/bench-code/history:/results \
  bench-code \
  --model qwen2.5-coder:14b \
  --runtime-base http://localhost:11437 \
  --tasks humaneval,mbpp \
  --run-name code_coder14b_split_smoke_v1
```

Reasoning:

```bash
docker run --rm --network host \
  -v /mnt/shared:/mnt/shared \
  -v /mnt/shared/logs/benchmarks/bench-reasoning/history:/results \
  -v /mnt/shared/plans/shoulders/benchmarking:/benchmark-scripts:ro \
  bench-reasoning \
  --model qwen2.5-coder:14b \
  --runtime-base http://localhost:11437 \
  --tasks gsm8k,bbh,drop \
  --limit 5 \
  --run-name reasoning_coder14b_split_smoke_v1
```

Use the same pattern for the `4+5` split pair on port `11438`.

## 12B Single-Worker Sequence

The 12B Gemma smoke runs that completed successfully used the same direct
per-suite method on a single worker port.

Example port:

- `gemma-3:12b` on `http://localhost:11435`

Run the three suite commands above with the correct model id and port.

## Failure Handling

If a suite fails:

1. stop that suite container
2. verify the runtime still answers `/v1/models`
3. if the runtime is gone, reload it
4. rerun only that suite with the same `--run-name` if resume is desired
5. do not launch later suites until the current suite is either completed or explicitly abandoned

## What To Avoid (Manual Path)

Do not treat worker benchmark sequencing as a separate campaign/orchestration layer
when running ad-hoc debugging or single-model investigations.

The stable manual path is:

- manual runtime preparation
- direct suite execution
- direct runtime verification between suites

Use that path for debugging, single-model work, and reproducing failures.

---

## Automated Multi-Model Campaign Script

For running the same suite sequence across many models unattended, use the
standalone campaign shell script pattern. This was first proven in the
Gemma 4 + Qwen 3.6 campaign (2026-04-22).

### When to Use

- Testing a batch of new models (e.g. new model family release)
- Running code + reasoning at a specific limit across all models
- Overnight unattended runs where you want load → bench → unload → next

### Script Location

```
/mnt/shared/scripts/benchmarks/run_new_models_campaign.sh
```

Use this as a template. Copy and edit for new campaigns — do not modify the
original for one-off runs.

### How It Works

The script bypasses the orchestrator meta-task system entirely. It directly:

1. Launches `run_runtime.sh` to load a model
2. Polls `curl /v1/models` until HTTP 200 (with timeout)
3. Runs `docker run --rm ... bench-*` containers directly
4. Stops the runtime container
5. Moves to the next model

This avoids orchestrator dependency and works with any model, even ones not
in `models.catalog.json`.

### Script Structure

```bash
#!/usr/bin/env bash
set -euo pipefail

RUNTIME_IMAGE="llama-runtime:b8884-candidate"
SHARED="/mnt/shared"

# Helper functions: log, wait_for_model, stop_runtime, start_runtime,
# run_pipeline, run_code, run_reasoning, run_full_suite

# Phase 1: Worker models (parallel on separate GPUs)
start_runtime "name-a" "$model_a" $port_a $gpu_a
start_runtime "name-b" "$model_b" $port_b $gpu_b
wait_for_model $port_a
wait_for_model $port_b
( run_full_suite "model-b:id" $port_b "tag_b" 50 ) &
run_full_suite "model-a:id" $port_a "tag_a" 50
wait  # wait for background
stop_runtime "name-a"
stop_runtime "name-b"

# Phase 2: Brain models (sequential on GPU 0)
for each brain model:
    start_runtime "llama-brain" "$model" 11434 0
    wait_for_model 11434
    run_full_suite "model:id" 11434 "tag" 50
    stop_runtime "llama-brain"
```

### Key Design Decisions

| Decision | Rationale |
|---|---|
| Direct `run_runtime.sh` | No orchestrator dependency; works for ad-hoc testing |
| `--rm` on all bench containers | Auto-cleanup; no orphaned containers |
| `BENCHMARK_DISABLE_AUTO_RESERVE=1` | Required for ad-hoc runs outside orchestrator |
| Parallel workers, sequential brains | Workers use separate GPUs; brains share GPU 0 |
| Qwen 3.6 gets `--reasoning-budget 0` | Suppresses thinking mode (same as Qwen 3.5 family) |
| `set -euo pipefail` | Fail fast on errors; don't silently continue |
| Reuse container name `llama-brain` | Ensures old runtime is gone before loading next |

### GPU/Port Mapping

| GPU | Port | Type | Campaign Role |
|---|---|---|---|
| 0 | 11434 | 3090 brain | Sequential brain models |
| 1 | 11435 | 1060 worker | Parallel worker A |
| 3 | 11437 | 1060 worker | Parallel worker B |

GPU 2 (port 11436) is typically reserved for the orchestrator's default
worker. Don't use it in campaign scripts unless you've stopped the
orchestrator first.

### Model Tuning Profiles

All models in the campaign **must** have entries in
`model_tuning_profiles.json` before running. The bench-pipeline suite
requires model-specific prompts by default (`--require-model-prompt`).

Add entries with:
- GGUF filename key (e.g. `gemma-4-e4b-it-Q4_K_M.gguf`)
- Short-form alias key (e.g. `gemma-4:e4b` with `_alias_of` reference)

### Monitoring a Running Campaign

```bash
# Live log tail
ssh 10.0.0.3 'tail -30 /mnt/shared/logs/benchmarks/campaigns/new_models_campaign_live.log'

# Running containers
ssh 10.0.0.3 'docker ps --format "table {{.Names}}\t{{.Status}}"'

# Per-container progress (bench-code shows task numbers)
ssh 10.0.0.3 'docker logs <container_name> 2>&1 | tail -5'

# GPU status
ssh 10.0.0.3 'nvidia-smi --query-gpu=index,memory.used,utilization.gpu --format=csv,noheader'
```

### First Successful Campaign

Run: 2026-04-22, Gemma 4 + Qwen 3.6 upgrade batch

- **Phase 1**: Gemma 4 E4B + E2B parallel on GPUs 1+3 (code + reasoning, limit 50)
- **Phase 2**: Sequential on GPU 0: Gemma 4 26B-A4B → 31B → Qwen 3.6 27B → 35B-A3B
- Script: `/mnt/shared/scripts/benchmarks/run_new_models_campaign.sh`
- Log: `/mnt/shared/logs/benchmarks/campaigns/new_models_campaign_live.log`

### Creating a New Campaign

1. Copy the template script:
   ```bash
   cp /mnt/shared/scripts/benchmarks/run_new_models_campaign.sh \
      /mnt/shared/scripts/benchmarks/run_<campaign_name>.sh
   ```
2. Edit the model list, GPU assignments, and limit values
3. Ensure all models have tuning profiles in `model_tuning_profiles.json` (check both GGUF filename key AND short-form alias match the model ID you pass to `--model`)
4. Ensure all model GGUFs exist in `/mnt/shared/models/`
5. Ensure benchmark Docker images are built (`bench-pipeline`, `bench-code`, `bench-reasoning`)
6. **Check thinking-model flags** (see table below) — wrong flags = zero scores
7. Launch:
   ```bash
   ssh 10.0.0.3 'nohup bash /mnt/shared/scripts/benchmarks/run_<campaign_name>.sh \
     > /mnt/shared/logs/benchmarks/campaigns/<campaign_name>_live.log 2>&1 &'
   ```

### Thinking Model Benchmark Flags (bench-reasoning)

Models with built-in thinking/reasoning modes need special flags or they score near-zero on BBH and DROP. Check `MODEL_LIBRARY.md` family sections for per-model details.

| Model Family | Runtime Flag | bench-reasoning Flag | Why |
|---|---|---|---|
| **Gemma 4** (all variants) | none | `--patch-think-tag-strip` | Model emits `<\|channel>thought` prefix; `\n` stop truncates before answer. Patch removes stops from API, strips prefix, reapplies client-side. |
| **Qwen 3.6** (all variants) | `--reasoning-budget 0` | `--patch-think-tag-strip` | Model wraps content in `<think>...</think>` even with budget 0. Patch strips tags and reapplies stops. |
| **DeepSeek-R1** variants | none | `--patch-think-tag-strip` | Server splits thinking into `reasoning_content` field. Patch handles content fallback. |
| Non-thinking models | none | none | Standard extraction works. |

**Key gotchas:**
- `--disable-thinking` does NOT work in lm-eval 0.4.11 — never use it
- `--reasoning-budget 0` alone is insufficient for Qwen 3.6 benchmarks
- The always-on DROP patch uses `max_gen_toks: 512` (not 64) to give thinking models room
- Always do a limit 2-5 smoke test before launching a full campaign on thinking models
- If DROP scores 0.0, the most likely cause is a missing `--patch-think-tag-strip` flag

### Per-Model Flags in Campaign Scripts

The template (`run_new_models_campaign.sh`) supports per-model flags via arrays at the top of the script. This is how thinking-model settings are passed through to `run_reasoning()` and `run_full_suite()`:

```bash
# Define per-family reasoning flags at the top of your campaign script
GEMMA4_REASONING_FLAGS=(--patch-think-tag-strip)
QWEN36_REASONING_FLAGS=(--patch-think-tag-strip)
CODER7B_REASONING_FLAGS=()  # non-thinking: no extra flags

# Pass them through to run_full_suite or run_reasoning:
run_full_suite "gemma-4:e4b" 11435 "gemma4_e4b_l50" 50 "${GEMMA4_REASONING_FLAGS[@]}"
run_full_suite "qwen3.6:27b" 11434 "qwen36_27b_l50" 50 "${QWEN36_REASONING_FLAGS[@]}"
run_reasoning  "gemma-4:31b" 11434 "gemma4_31b_drop" 100 "${GEMMA4_REASONING_FLAGS[@]}"
```

Runtime-level flags (like `--reasoning-budget 0` for Qwen 3.6) are handled inside `start_runtime()` based on model path detection. Bench-level flags are passed through the campaign call sites.

When adding a new model family, check `MODEL_LIBRARY.md` for its family section — the "Best practices" block documents which flags are needed.

### Differences from Campaign Runner (`run_benchmark_campaign.py`)

| Feature | Shell script | Campaign runner |
|---|---|---|
| Model loading | Direct `run_runtime.sh` | Orchestrator meta-tasks |
| Multi-model | Yes (sequential loop) | No (single model per config) |
| Multi-suite | Yes (inline calls) | Yes (suite array in JSON) |
| Orchestrator required | No | Yes |
| GPU reservation | No (manual) | Yes (automatic) |
| Checkpointing | No (log-based) | Yes (status.json) |
| Resume | No | Yes (`--run-id`) |
| Best for | Batch testing new models | Production benchmarking |
