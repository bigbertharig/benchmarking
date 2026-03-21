# Docker Benchmark Suites

This is the operator guide for running the benchmark Docker suites against the
live worker runtimes.

For building new suites that integrate cleanly with dashboard/orchestration:
- [SUITE_CREATION.md](SUITE_CREATION.md)
- [SEQUENCED_TEST_SUITES.md](SEQUENCED_TEST_SUITES.md)
- [MULTI_MODEL_SINGLE_SUITE.md](MULTI_MODEL_SINGLE_SUITE.md)
- [SINGLE_GPU_COHORT_SUITES.md](SINGLE_GPU_COHORT_SUITES.md)

For operator use, the canonical sequencing path is still manual:
- load and verify the runtime first
- run each suite directly with its own `docker run`
- verify the runtime again before starting the next suite

The sequenced guide documents that manual path. It is not a separate campaign
control layer for worker benchmarking.

The multi-model single-suite guide is a separate control path for a different
operator goal:
- sequenced tests: one model, many suites
- multi-model single-suite: one suite, many models

This matters operationally:
- "sequenced" means calling the same proven manual suite commands one at a time
- it does not mean inventing a new wrapper, campaign layer, or alternate launch path
- if you want to run multiple suites on one loaded model, reuse the direct suite commands and insert runtime checks between them

## Current Rig Layout

| GPU | Port | Type | Models | Notes |
| --- | --- | --- | --- | --- |
| 0 | 11434 | Brain (3090 24GB) | qwen2.5-coder:32b, deepseek-r1:32b | Single GPU, large models only |
| 1 | 11435 | Worker (1060 6GB) | 7B models or split pair with GPU 3 | Split pair uses port 11435 |
| 2 | 11436 | Worker (1060 6GB) | 7B models (standalone only) | |
| 3 | — | Worker (1060 6GB) | Split partner for GPU 1 | No own port when split |
| 4 | 11438 | Worker (1060 6GB) | 7B models or split pair with GPU 5 | Split pair uses port 11438 |
| 5 | — | Worker (1060 6GB) | Split partner for GPU 4 | No own port when split |

Split pairs: GPUs 1+3 and GPUs 4+5 can each load one 14B model (qwen2.5-coder:14b, deepseek-r1:14b, phi-4:14b).

**Quick status check** (run this first in any session):
```bash
ssh 10.0.0.3 'bash /mnt/shared/scripts/benchmarks/bench_status.sh'
```
Shows: GPU VRAM/util/temp, running containers + progress, chain logs, memory, earlyoom, recent OOM kills.

**Deep status check** (use this when a run is active or looks suspicious):
```bash
ssh 10.0.0.3 'bash /mnt/shared/scripts/benchmarks/bench_status.sh --deep'
```
Adds:
- direct runtime port probes for `11434..11439`
- per-benchmark progress lines
- rough progress / ETA estimates
- reconnect / runtime-unreachable / OOM signal summaries when present

Operator rule:
- run `bench_status.sh` once for the fast overview
- run `bench_status.sh --deep` when you need to confirm a benchmark is actually advancing and not just alive

**Results status check** (use this when runs may have finished or partially completed):
```bash
ssh 10.0.0.3 'bash /mnt/shared/scripts/benchmarks/bench_status.sh --results'
```
Adds:
- recent benchmark result summaries grouped by run
- `completed` vs `incomplete` labeling
- task-level status for recent `bench-code`, `bench-reasoning`, and `bench-pipeline` outputs

Recommended operator flow:
1. run `bench_status.sh`
2. if a run is active but suspicious, run `bench_status.sh --deep`
3. if runs may have finished or partially completed, run `bench_status.sh --results`

**How to run a test**: pick a suite README below, find the Quick Start for your model tier, paste the command on the rig.

**Before running any test**, check the "Before Running" section below.

| Suite | What | Quick start |
| --- | --- | --- |
| [bench-pipeline](bench-pipeline/README.md) | Worker reliability (JSON, safety, sequencing) | ~5 min |
| [bench-code](bench-code/README.md) | Code generation (humaneval, mbpp) | ~30 min - 2h |
| [bench-reasoning](bench-reasoning/README.md) | Reasoning (gsm8k, bbh, drop) | ~1h (limit 5) to ~9h (limit 100) |
| [bench-daedalmap](bench-daedalmap/README.md) | DaedalMap chat routing + bucket-backed data validation | ~5 min smoke, ~45 min full 100-case run |
| [bench-knowledge](bench-knowledge/README.md) | Knowledge (mmlu, arc, hellaswag) | ~1.5h - 8h at limit 5 |

## Before Running

**Status checks are part of the standard workflow.** Use:
```bash
ssh 10.0.0.3 'bash /mnt/shared/scripts/benchmarks/bench_status.sh'
ssh 10.0.0.3 'bash /mnt/shared/scripts/benchmarks/bench_status.sh --deep'
ssh 10.0.0.3 'bash /mnt/shared/scripts/benchmarks/bench_status.sh --results'
```
Do the fast check before launches. Use `--deep` during long-running `bench-code`,
`bench-reasoning`, or any time a run feels stalled. Use `--results` when you need
to know what actually finished and what is still incomplete.

**Canonical sequence for multiple suites on one model:**
1. load the model runtime
2. verify `/v1/models` on the target port
3. run `bench-pipeline`
4. verify `/v1/models` again
5. run `bench-code`
6. verify `/v1/models` again
7. run `bench-reasoning`

Operator rule:
- if a suite fails or the runtime disappears, stop there
- repair or reload the runtime
- rerun that suite directly
- do not continue to later suites on a suspect runtime

**0. Load models one at a time.** Never load multiple models simultaneously.
Parallel loading clogs the shared USB/PCIe bus, causing 3-5x longer load times
and potential timeouts. Load one model, wait until `/v1/models` responds with the
model ID, then load the next. The orchestrator enforces this via sequential
`load_llm` meta tasks — follow the same discipline for manual benchmark runs.

**0b. Check system RAM pressure.** Each llama-server can consume 6-7 GB of system RAM
on top of VRAM due to mmap file mapping and KV cache overflow. With 30 GiB system RAM,
running 3+ models simultaneously risks OOM. Check with:
```bash
docker stats --no-stream --format "{{.Name}}: {{.MemUsage}}"
```
Known causes of high system RAM:
- **mmap**: llama-server maps the full GGUF into virtual address space (shows as RSS)
- **KV cache overflow**: large ctx_size on small VRAM cards spills KV cache to system RAM
- **CPU-mapped layers**: when model doesn't fully fit, some layers stay on CPU
Fixes (apply to `run_runtime.sh` or docker run):
- `--no-mmap`: disable mmap, loads model directly instead of mapping file to virtual memory. Slower load but eliminates RSS inflation from mapped file pages.
- `--no-kv-offload` or `-nkvo`: keeps KV cache on GPU only, prevents CPU RAM spillover. Will fail if VRAM is too tight — reduce `--ctx-size` instead.
- `-ctk q8_0 -ctv q8_0`: quantize KV cache from f16 to q8_0, halves KV cache memory. Small quality impact.
- `-ctk q4_0 -ctv q4_0`: aggressive KV quantization, quarters KV cache. Bigger quality tradeoff.
- Reduce `--ctx-size`: most benchmarks use short prompts, ctx_size=4096 is often enough for smoke tests and dramatically reduces KV cache size.
See MODEL_LIBRARY.md "RAM vs VRAM" for per-model analysis.

**0b. Run the litmus test first.** Before committing to the full suite on a new model,
run the 3 quick curl checks in MODEL_LIBRARY.md → "Pre-Flight Litmus Test". This catches
`<think>` wrappers, broken JSON, and other output format issues that produce all-zero scores
and waste hours. Takes 30 seconds, saves potentially hours of wasted benchmarking.

**1. Rebuild if images are stale.** The Docker images bake `run.sh` at build time.
If you've changed any suite's `run.sh`, CLI flags, or defaults, rebuild first:

```bash
ssh 10.0.0.3 'cd /mnt/shared/plans/shoulders/benchmarking/docker && \
  docker build -t bench-pipeline bench-pipeline && \
  docker build -t bench-code bench-code && \
  docker build -t bench-reasoning bench-reasoning && \
  docker build -t bench-knowledge bench-knowledge'
```

To check if an image is stale:
```bash
docker run --rm --entrypoint cat bench-pipeline /opt/bench/run.sh | head -15
```

**2. Add `-e BENCHMARK_DISABLE_AUTO_RESERVE=1`** to all `docker run` commands.
The reservation system requires `filelock` which isn't installed in the container.
Without this env var, bench-pipeline containers will crash immediately on startup.

```bash
docker run --rm --network host \
  -e BENCHMARK_DISABLE_AUTO_RESERVE=1 \
  ...
```

**3. Model ID matching.** The `--model` value must fuzzy-match a key in
`model_tuning_profiles.json` for prompts to resolve. Most Ollama-style short IDs
work (e.g. `qwen2.5-coder:14b` matches `Qwen2.5-Coder-14B-Instruct-Q4_K_M.gguf`).

DeepSeek models need explicit aliases because `deepseek-r1:14b` does NOT substring-match
`DeepSeek-R1-Distill-Qwen-14B-Q4_K_M.gguf` (the "Distill-Qwen" part breaks it).
Short-form aliases (`deepseek-r1:7b`, `deepseek-r1:14b`, `deepseek-r1:32b`) are already
added in `model_tuning_profiles.json`.

## Architecture

Each docker suite is self-contained:
- its own README explaining what it tests, how prompts work, and how to run it
- its own HISTORY file tracking every run with timestamps, prompts used, and scores
- its own result archives in per-run directories under `/media/bryan/shared/logs/benchmarks/`

The main `MODEL_LIBRARY.md` holds only the latest scores per model/test as a simple
summary table. For full history and prompt traceability, check each suite's history file.

Machine-readable score state:
- canonical machine-readable ledger: `/media/bryan/shared/plans/shoulders/benchmarking/results/model_benchmark_records.jsonl`
- latest parsed scoreboard view: `/media/bryan/shared/plans/shoulders/benchmarking/results/model_library_scoreboard.json`
- markdown operator doc: `/media/bryan/shared/plans/shoulders/benchmarking/MODEL_LIBRARY.md`

Current policy:
- suites auto-append completed results into `model_benchmark_records.jsonl` as tests/tasks finish
- `MODEL_LIBRARY.md` is still maintained separately for operator notes and curated summary rows
- `build_model_library_scoreboard.py` currently syncs **from** `MODEL_LIBRARY.md` **to** `model_library_scoreboard.json`
- this means the JSONL ledger and markdown doc are intentionally separate for now; the auto-recorded JSONL is the live raw machine-readable feed, while markdown remains the curated human view

Storage policy (do not mix suite outputs in one folder):
- `bench-pipeline`: `/mnt/shared/logs/benchmarks/bench-pipeline/history`
- `bench-code`: `/mnt/shared/logs/benchmarks/bench-code/history`
- `bench-reasoning`: `/mnt/shared/logs/benchmarks/bench-reasoning/history`
- `bench-daedalmap`: `/mnt/shared/logs/benchmarks/bench-daedalmap/history`
- `bench-knowledge`: `/mnt/shared/logs/benchmarks/bench-knowledge/history`

## Prompt Methodology (applies to all suites)

Each model has a universal system prompt in `model_tuning_profiles.json` that deploys
with it for real work.

Suite support differs:
- `bench-pipeline`: per-model prompts enabled, strict model-specific prompt required by default.
- `bench-reasoning`: per-model prompts enabled, strict model-specific prompt required by default.
- `bench-knowledge`: per-model prompts enabled, strict model-specific prompt required by default.
- `bench-code`: still uses EvalPlus built-in prompting (no profile-based per-model prompt injection yet).

Every run archives the exact prompt used in its result files, so historical runs are
self-contained. You can always reconstruct "we ran test X with prompt Y and got score Z"
from any past run without needing the current profiles.

Workflow:
1. Run a suite with the current prompts
2. As each task/test completes, the suite auto-appends machine-readable rows to `results/model_benchmark_records.jsonl`
3. Record the run narrative in the suite's HISTORY file
4. Compare across runs to learn what prompt changes helped
5. Fold improvements back into the universal prompt in `model_tuning_profiles.json`
6. Update `MODEL_LIBRARY.md` with the curated latest scores / operator notes, then refresh `model_library_scoreboard.json` from markdown if needed

## Result Recording

Automatic machine-readable recording is now built into the suite runners.

What gets recorded automatically:
- `bench-pipeline`: each passed custom test row
- `bench-reasoning`: completed task metrics as separate rows
  - `gsm8k_strict`
  - `gsm8k_flexible`
  - `bbh`
  - `drop_em`
  - `drop_f1`
- `bench-code`: completed dataset metrics as separate rows
  - `humaneval_base`
  - `humaneval_plus`
  - `mbpp_base`
  - `mbpp_plus`
- `bench-daedalmap`: completed category summaries as separate rows
  - `<category>_pass_rate`
  - `<category>_json_valid_rate`
  - `<category>_type_correct_rate`
  - `<category>_no_halluc_rate`
  - `<category>_source_hit_rate` when applicable
  - `<category>_source_valid_rate` when applicable
- `bench-knowledge`: each numeric lm-eval metric emitted for the completed task

How it works:
- suites call `scripts/active/record_benchmark_result.py` at successful task/test completion
- each appended JSONL row includes model, test id, score, metric, harness, suite/run name, timestamp, and notes
- failed tasks are **not** auto-recorded as numeric scores
- rerun skipping still comes from the suite checkpoint/status files, not from the JSONL ledger

Operator note:
- the JSONL ledger is the easiest source for CSV export or future dashboard model-comparison views
- the markdown doc remains the operator-facing summary until we flip the full source-of-truth direction

## Suites

| Suite | What It Tests | Prompt Source | History |
| --- | --- | --- | --- |
| `bench-pipeline` | Worker-facing custom reliability (JSON, safety, ambiguity, sequencing, tradeoffs, extraction) | Model-specific prompt profiles + per-test overrides + tuning profile fallback | [HISTORY](bench-pipeline/BENCH_PIPELINE_HISTORY.md) |
| `bench-reasoning` | lm-eval reasoning tasks (gsm8k, bbh, drop, math_500, aime_2024) | Model-specific prompt profiles injected via `--system_instruction` | [HISTORY](bench-reasoning/BENCH_REASONING_HISTORY.md) |
| `bench-knowledge` | lm-eval MC/loglikelihood tasks (mmlu, arc_challenge, hellaswag, etc.) | Model-specific prompt profiles injected via `--system_instruction` | [HISTORY](bench-knowledge/BENCH_KNOWLEDGE_HISTORY.md) |
| `bench-code` | EvalPlus code generation (humaneval, mbpp) | EvalPlus built-in prompts (no profile injection yet) | [HISTORY](bench-code/BENCH_CODE_HISTORY.md) |
| `bench-daedalmap` | DaedalMap chat-layer routing, source grounding, and direct bucket validation for `data_s3` cases | Self-contained benchmark prompt from `benchmark_prompt.py` + direct bucket validation from `staging/catalog.json` | [HISTORY](bench-daedalmap/BENCH_DAEDALMAP_HISTORY.md) |

## Test Volume Quick Reference

- `bench-code`:
  - humaneval: 164
  - mbpp: 378
  - total full run: **542**
  - scoring behavior: **all-or-nothing per dataset**
- `bench-reasoning`:
  - core long-run set (`gsm8k + bbh + drop`) expands to **29 suites** (`27` BBH subtasks + `gsm8k` + `drop`)
  - approximate full set sizes:
    - `bbh` total: ~6.5k
    - `gsm8k`: ~1.3k
    - `drop`: ~9.5k
    - combined: ~17k
  - with `--limit L`: about `29 * L` prompts (example `L=150` => around `~4.3k`)
  - effective max `L` is dataset size per suite (higher values behave as full dataset)
  - scoring behavior: **limit-based partial runs are valid**
- `bench-knowledge`:
  - default set has **5 task groups**:
    - `mmlu` ~14k
    - `arc_challenge` ~1.1k
    - `hellaswag` ~10k
    - `truthfulqa_mc2` ~800
    - `boolq` ~3.3k
  - combined full set: ~29k
  - with `--limit L`: up to `5 * L` prompts (example `L=150` => up to `750`)
  - effective max `L` is dataset size per task (higher values behave as full dataset)
  - scoring behavior: **limit-based partial runs are valid**

Per-image docs:
- `bench-pipeline`: [README](bench-pipeline/README.md) / [HISTORY](bench-pipeline/BENCH_PIPELINE_HISTORY.md)
- `bench-reasoning`: [README](bench-reasoning/README.md) / [HISTORY](bench-reasoning/BENCH_REASONING_HISTORY.md)
- `bench-knowledge`: [README](bench-knowledge/README.md) / [HISTORY](bench-knowledge/BENCH_KNOWLEDGE_HISTORY.md)
- `bench-code`: [README](bench-code/README.md) / [HISTORY](bench-code/BENCH_CODE_HISTORY.md)

## First-Run Checklist

1. Confirm target worker endpoints are loaded:
   - `http://localhost:11435` .. `http://localhost:11439`
2. Run the overview status check:
   - `ssh 10.0.0.3 'bash /mnt/shared/scripts/benchmarks/bench_status.sh'`
3. If anything looks off or a long suite is already running, run the deep check:
   - `ssh 10.0.0.3 'bash /mnt/shared/scripts/benchmarks/bench_status.sh --deep'`
4. If runs may have completed or partially completed, run the results check:
   - `ssh 10.0.0.3 'bash /mnt/shared/scripts/benchmarks/bench_status.sh --results'`
5. For strict-output custom tests, prefer the worker currently running
   `qwen2.5-coder:7b` (recently `11437`).
6. Ensure benchmark workers stay loaded long enough for suite runs:
   - `max_hot_workers` should not force immediate unload.
7. When running multiple suites on one model, follow the manual sequence exactly:
   - load -> verify -> pipeline -> verify -> code -> verify -> reasoning
   - use the same direct suite commands from the suite READMEs
   - do not substitute a new wrapper or alternate launch path unless it has already been proven on the rig

## Canonical Run Patterns

When you want to run several suites on the same model, these are still the same
commands to use. Sequencing means running them one after another with runtime
verification between them, not switching to a different launch system.

Reasoning:

```bash
docker run --rm --network host \
  -v /mnt/shared:/mnt/shared \
  -v /mnt/shared/logs/benchmarks/bench-reasoning/history:/results \
  -v /mnt/shared/plans/shoulders/benchmarking:/benchmark-scripts:ro \
  bench-reasoning --model qwen2.5-coder:7b --runtime-base http://localhost:11437 --run-name reasoning_full_v1
```

Code:

```bash
docker run --rm --network host \
  -v /mnt/shared:/mnt/shared \
  -v /mnt/shared/logs/benchmarks/bench-code/history:/results \
  bench-code --model qwen2.5-coder:7b --runtime-base http://localhost:11437
```

Code preflight-only (timeout + reachability sanity):

```bash
docker run --rm --network host \
  -v /mnt/shared:/mnt/shared \
  bench-code --model qwen2.5-coder:7b --runtime-base http://localhost:11437 --preflight-only --request-timeout 30
```

Code resumable run:

```bash
docker run --rm --network host \
  -v /mnt/shared:/mnt/shared \
  -v /mnt/shared/logs/benchmarks/bench-code/history:/results \
  bench-code --model qwen2.5-coder:7b --runtime-base http://localhost:11437 --run-name coding_full_v1
```

Pipeline (custom worker-facing tests):

```bash
docker run --rm --network host \
  -e BENCHMARK_DISABLE_AUTO_RESERVE=1 \
  -v /mnt/shared:/mnt/shared \
  -v /mnt/shared/logs/benchmarks/bench-pipeline/history:/results \
  -v /mnt/shared/plans/shoulders/benchmarking:/benchmark-scripts:ro \
  bench-pipeline --model qwen2.5-coder:7b --runtime-base http://localhost:11437 --run-name pipeline_worker_v1
```

Pipeline stage-progress artifacts (new):
- each run now writes:
  - `<results>/<model_safe>_<timestamp>_stage_updates.jsonl`
  - `<results>/<model_safe>_<timestamp>_status.json`
- each completed test group appends one JSONL line with:
  - `test_id`, `status`, `score`, `passes`, `total`, `result_path`
  - `stage_start`, `stage_end`, `duration_seconds`, `elapsed_total_seconds`
- this allows partial result capture during long multi-stage runs.

Knowledge (GGUF + llama.cpp server inside container):

```bash
docker run --rm --gpus '"device=1"' \
  -v /mnt/shared:/mnt/shared \
  -v /mnt/shared/models:/models:ro \
  -v /mnt/shared/logs/benchmarks/bench-knowledge/history:/results \
  -v /mnt/shared/plans/shoulders/benchmarking:/benchmark-scripts:ro \
  bench-knowledge /models/<model-folder>/<model-file>.gguf --reserve-gpu gpu-2 --run-name knowledge_full_v1
```

## Checkpoint/Resume Support

All benchmark suites now support resumable runs with a stable run id:

- `bench-code`: `--run-name` (existing)
- `bench-reasoning`: `--run-name` (task-level checkpoint in `status.json`)
- `bench-knowledge`: `--run-name` (task-level checkpoint in `status.json`)
- `bench-pipeline`: `--run-name` (test-level checkpoint in `*_checkpoint.json`)

Resume behavior:

- completed stages are skipped
- failed or incomplete stages are rerun
- rerun with the same command and same `--run-name`

## Trimmed 50-Question Suites

Frozen suite definitions:
- `/media/bryan/shared/plans/shoulders/benchmarking/suites/reasoning_lite_v1.json`
- `/media/bryan/shared/plans/shoulders/benchmarking/suites/knowledge_lite_v1.json`
- `/media/bryan/shared/plans/shoulders/benchmarking/suites/coding_lite_v1.json`

Reasoning lite (`5 tasks x limit 10 = 50`):

```bash
docker run --rm --network host \
  -v /mnt/shared:/mnt/shared \
  -v /mnt/shared/logs/benchmarks/bench-reasoning/history:/results \
  bench-reasoning \
  --model Qwen2.5-Coder-7B-Instruct-Q4_K_M.gguf \
  --runtime-base http://localhost:11437 \
  --tasks gsm8k,bbh,drop,math_500,aime_2024 \
  --limit 10
```

Knowledge lite (`5 tasks x limit 10 = 50`):

```bash
docker run --rm --gpus '"device=1"' \
  -v /mnt/shared:/mnt/shared \
  -v /mnt/shared/models:/models:ro \
  -v /mnt/shared/logs/benchmarks/bench-knowledge/history:/results \
  bench-knowledge \
  /models/<model-folder>/<model-file>.gguf --reserve-gpu gpu-2 \
  --tasks mmlu,arc_challenge,hellaswag,truthfulqa_mc2,boolq \
  --limit 10
```

Coding lite status:
- currently blocked in active `bench-code` flow because EvalPlus evaluate requires
  full problem coverage for each dataset.
- see `suites/coding_lite_v1.json` for target shape and blocker note.

## Mixing Suites Across Workers

The CPU-based suites (`bench-pipeline`, `bench-reasoning`, `bench-code`) are independent
network clients — each container connects to one worker port and nothing else. You can
split workers across different suites in the same session.

Example: reasoning on workers 1 & 3, code on workers 2, 4, 5:

```bash
# reasoning on ports 11435 and 11437
docker run --rm --network host \
  -v /mnt/shared/logs/benchmarks/bench-reasoning/history:/results \
  -v /mnt/shared/plans/shoulders/benchmarking:/benchmark-scripts:ro \
  bench-reasoning --model qwen2.5-coder:7b --runtime-base http://localhost:11435 --run-name reasoning_split_v1 &

docker run --rm --network host \
  -v /mnt/shared/logs/benchmarks/bench-reasoning/history:/results \
  -v /mnt/shared/plans/shoulders/benchmarking:/benchmark-scripts:ro \
  bench-reasoning --model qwen2.5-coder:7b --runtime-base http://localhost:11437 --run-name reasoning_split_v1b &

# code on ports 11436, 11438, 11439
docker run --rm --network host \
  -v /mnt/shared/logs/benchmarks/bench-code/history:/results \
  bench-code --model qwen2.5-coder:7b --runtime-base http://localhost:11436 --run-name coding_split_v1 &

docker run --rm --network host \
  -v /mnt/shared/logs/benchmarks/bench-code/history:/results \
  bench-code --model qwen2.5-coder:7b --runtime-base http://localhost:11438 --run-name coding_split_v1b &

docker run --rm --network host \
  -v /mnt/shared/logs/benchmarks/bench-code/history:/results \
  bench-code --model qwen2.5-coder:7b --runtime-base http://localhost:11439 --run-name coding_split_v1c &
```

Rules:
- **One container per port** — never double-book the same worker port.
- **Each container gets its own `--run-name`** — results and checkpoints stay isolated.
- `bench-knowledge` runs on a dedicated GPU (`--gpus "device=X"`) and doesn't touch worker
  ports, so it can run in parallel with any CPU-based suite split with zero contention.
- The parallel runner (`start_parallel_worker_suite.sh`) runs one suite on all ports. For
  mixed splits, launch containers individually as shown above.

## Running Benchmarks Alongside Plans

Benchmarks can now coexist with plans, but only when the target worker GPUs are
explicitly reserved first.

What exists now:
- worker GPUs publish a benchmark reservation in heartbeat
- reserved workers refuse all queued orchestrator tasks
- the brain excludes reserved GPUs from normal load/unload balancing
- `scripts/active/start_parallel_worker_suite.sh` now reserves each worker port before
  launch and releases it on exit

What is still unsafe:
- raw ad hoc `docker run ... --runtime-base http://localhost:1143X` commands are still
  **not** safe by themselves
- if you bypass the reservation helper, the orchestrator will still treat that GPU as
  available

Worker-backed suites (`bench-reasoning`, `bench-code`, `bench-pipeline`) now reserve
their target runtime automatically when `/mnt/shared` is mounted into the container.
`bench-knowledge` can also auto-reserve, but it needs an explicit `--reserve-gpu gpu-X`
because it does not target a worker port.

Manual reservation path for custom direct launches:

```bash
python3 /mnt/shared/scripts/benchmark_gpu_reservation.py \
  --shared-path /mnt/shared \
  --port 11437 \
  --owner bench-reasoning \
  --run-id reasoning_manual_01 \
  reserve
```

Then run the benchmark container, and release afterward:

```bash
python3 /mnt/shared/scripts/benchmark_gpu_reservation.py \
  --shared-path /mnt/shared \
  --port 11437 \
  --owner bench-reasoning \
  release
```

What would be needed:

1. A `reserved` flag in the GPU heartbeat (`/mnt/shared/gpus/gpu_*/heartbeat.json`).
2. A guard in `gpu_tasks.py:claim_tasks()` that skips non-meta tasks when reserved.
3. A meta-task pair (`reserve_gpu` / `release_gpu`) so benchmark scripts can set/clear
   the flag through the normal task queue.
4. `start_custom_mode.py` sets reservation after benchmark mode starts, before model loads.
5. `start_parallel_worker_suite.sh` clears reservation after all containers finish.

Until this exists: **do not submit plans while benchmarks are running.** The workers
will interleave benchmark and plan work on the same GPU, corrupting both.

## Memory Protection (OOM Prevention)

Added 2026-03-14 after an OOM crash killed NFS and froze all operator SSH sessions.

**Root cause:** Multiple llama-server containers with no Docker memory limits exhausted
30 GB system RAM + 8 GB swap. Kernel OOM killer cascaded to NFS server and journald.

**Four layers of protection are now in place:**

| Layer | What | Config Location | How to Tune |
| --- | --- | --- | --- |
| Docker `--memory` | Per-container RAM cap | `config.benchmark.json` → `llama_single_defaults.memory_limit`, per-model profiles | Change `memory_limit` / `memory_swap` values |
| earlyoom | Userspace OOM killer at 5% free | `/etc/default/earlyoom` on rig | Adjust `-m` and `-s` percentages |
| `oom_score_adj` | NFS/SSH immune to kernel OOM | `oom-protect-critical.service` on rig | Systemd unit, runs at boot |
| zram | 15 GB compressed swap in RAM | `/etc/default/zramswap` on rig | Adjust `PERCENT` value |

**Current Docker memory limits** (in `config.benchmark.json`):

| Model tier | `memory_limit` | `memory_swap` | Observed RSS |
| --- | --- | --- | --- |
| 7B single (default) | `4g` | `5g` | ~2.8 GB |
| 14B split (default) | `8g` | `10g` | ~6.1 GB |
| 32B brain (per-profile) | `11g` | `13g` | ~8.0 GB |

These limits are passed via `run_runtime.sh --memory-limit` and `--memory-swap` flags.
When a container hits its limit, Docker kills *only that container* — no system-wide cascade.

**To check protections on the rig:**
```bash
# earlyoom status
journalctl -u earlyoom --no-pager -n 5

# OOM protection active
cat /proc/$(pgrep -x nfsd | head -1)/oom_score_adj  # should be -1000

# zram active
swapon --show

# Container memory limits
docker stats --no-stream --format 'table {{.Name}}\t{{.MemUsage}}'
```

**If a container gets OOM-killed by Docker (exit code 137):**
- The container dies cleanly; other services are unaffected
- Increase `memory_limit` in the model's profile in `config.benchmark.json`
- For benchmark docker runs (not orchestrator-managed), add `--memory` directly:
  `docker run --memory=12g --memory-swap=14g ...`

## Common Failure Modes

- **Container exits immediately with no output**:
  - missing `-e BENCHMARK_DISABLE_AUTO_RESERVE=1` (reservation helper needs `filelock`)
  - check with `docker run --rm ... bench-pipeline --model X --runtime-base Y` (without `-d`) to see error
- **`Use model prompts: 0` in logs (prompts not applied)**:
  - stale Docker image; rebuild with `docker build -t bench-pipeline bench-pipeline`
- **`Cannot reach llama-compatible runtime`**:
  - missing `--network host`
  - wrong `--runtime-base` port
  - worker unloaded between prep and run
- **`Unknown arg: --runtime-base`**:
  - stale image build; rebuild the image from current docker sources
- **`No model-specific system prompt found for ...`**:
  - model ID doesn't match any key in `model_tuning_profiles.json`
  - for DeepSeek models, ensure short-form aliases exist (see "Before Running" above)
  - or run with `--allow-generic-prompt-fallback`
- **`Custom test runner not found`** in `bench-pipeline`:
  - missing scripts mount:
    `-v /mnt/shared/plans/shoulders/benchmarking:/benchmark-scripts:ro`
- **All pipeline tests score empty/fail in 0 seconds**:
  - `--require-model-prompt` is failing silently for each test because prompt can't resolve
  - check model ID fuzzy matching (see "Before Running" above)
- **All pipeline scores 0% but model responds correctly in litmus test**:
  - model has native thinking mode (`thinking = 1` in docker logs) that puts answers in
    `reasoning_content` API field instead of `content`
  - affected: Qwen3.5 family (35b-a3b confirmed, likely 4b/9b too)
  - fix: add `--reasoning-budget 0` to llama-server launch:
    `--extra-arg "--reasoning-budget" --extra-arg "0"` in `run_runtime.sh`
  - verify: `docker logs <container> 2>&1 | grep "thinking ="` — should show `thinking = 0` after fix
  - per-request alternative: set `chat_template_kwargs: {"enable_thinking": false}` in API call

## Parallel Worker Run Pattern

Run one `bench-pipeline` container per loaded worker endpoint (`11435..11439`),
with one log file per port and a shared run directory.

Canonical rig-side launcher:

```bash
/mnt/shared/plans/shoulders/benchmarking/start_parallel_worker_suite.sh --background
```

Prompt-profile tuned run:

```bash
/mnt/shared/plans/shoulders/benchmarking/start_parallel_worker_suite.sh \
  --background \
  --run-name worker_custom_v1 \
  --use-model-prompts
```

This prints:
- `RUN_ROOT=<run_dir>`
- `LAUNCH_PID=<pid>`

Operational notes from first parallel launch:
- model speed differs significantly; some ports may complete multiple stages while
  others remain in stage 1.
- inspect per-port logs instead of relying only on top-level process output.
- write an explicit manifest (`port -> model -> log`) for clean post-run scoring.
- rerun with the same `--run-root` and `--run-name` to reuse per-port checkpoints.

Live monitor commands:

```bash
# container/process presence
ssh 10.0.0.3 'ps -ef | grep -E "docker run|run_local_custom_task" | grep -v grep'

# per-port stage transitions
ssh 10.0.0.3 'for f in /mnt/shared/logs/benchmarks/bench-pipeline/history/<run_dir>/port_*.log; do echo "### $f"; grep -E "^--- Running|^--- .* done ---|^=== bench-pipeline COMPLETE ===|^Passed:|^Failed:" "$f"; done'
```

## Timed Snapshot Scheduler

Use one reusable scheduler for any suite run root (`bench-pipeline`, `bench-code`,
`bench-reasoning`, `bench-knowledge`) to write timed progress snapshots.

Script path:

```bash
/mnt/shared/plans/shoulders/benchmarking/docker/snapshot_scheduler.sh
```

Default schedule (from launch time):
- `10m`, `30m`, `1h`, `2h`, `3h`, `4h`, `5h`, `6h`

Launch in background:

```bash
ssh 10.0.0.3 '/mnt/shared/plans/shoulders/benchmarking/docker/snapshot_scheduler.sh \
  --run-root /mnt/shared/logs/benchmarks/bench-pipeline/history/<run_dir> \
  --background'
```

This writes:
- snapshots: `/mnt/shared/logs/benchmarks/bench-pipeline/history/<run_dir>/snapshots/snapshot_<label>.json`
- monitor log: `/mnt/shared/logs/benchmarks/bench-pipeline/history/<run_dir>/snapshot_monitor.out`

Custom schedule example:

```bash
ssh 10.0.0.3 '/mnt/shared/plans/shoulders/benchmarking/docker/snapshot_scheduler.sh \
  --run-root /mnt/shared/logs/benchmarks/bench-pipeline/history/<run_dir> \
  --specs "300:5m 900:15m 1800:30m" \
  --name progress \
  --background'
```

## Memory Protection (OOM Prevention)

Last updated: 2026-03-14

Four layers protect the rig from OOM cascades that kill NFS/SSH:

### Layer 1: Docker memory limits (primary defense)

Each llama-server container runs with `--memory` and `--memory-swap` limits.
These are set in `config.benchmark.json` model profiles and passed through `run_runtime.sh`.

Current limits:

| Tier | `--memory` | `--memory-swap` | Notes |
|---|---|---|---|
| Single (7B, 1x 1060) | 4g | 5g | Fits comfortably |
| Split (14B, 2x 1060) | 10g | 12g | Bumped from 8g/10g after gemma-3 OOM (2026-03-14) |
| Brain (32B/35B, 3090) | 11g | 13g | Model weights mostly in VRAM, CPU buffer ~500MB. Applies to qwen2.5-coder:32b, deepseek-r1:32b, qwen3.5:35b-a3b |

Config locations:
- `config.benchmark.json` → `llama_split_defaults.memory_limit` / `memory_swap`
- `config.benchmark.json` → per-model overrides in `llama_single_profiles` / `llama_split_profiles`
- `run_runtime.sh` → `--memory-limit` / `--memory-swap` flags

**Tuning rule:** Set Docker memory limit ~2GB above observed RSS peak. Docker's OOM handler
is cleaner than the kernel OOM killer — it stops the container gracefully. If the kernel
OOM killer fires instead of Docker's, the limit is too high (Docker didn't catch it first).

### Layer 2: earlyoom (userspace OOM killer)

Kills memory hogs before kernel OOM cascades to critical services.

Config: `/etc/default/earlyoom`
```
# -m 10: trigger at 10% free RAM (~3GB on 30GB rig)
# -s 50: trigger at 50% free swap (earlyoom uses AND logic — both conditions
#   must be true. With 23GB swap, -s 8 meant earlyoom never fired because
#   swap stayed above 8% while RAM hit 0%.)
# -r 10: report every 10s to syslog
# --avoid: protect critical services
# --prefer: kill llama-server/bench containers first (restartable)
EARLYOOM_ARGS="-m 10 -s 50 -r 10 --avoid '(sshd|nfsd|systemd|brain\.py|gpu_core)' --prefer '(llama-server|bench-)' -n"
```

Tuning history:
- 2026-03-14 initial: `-m 5 -s 5 -r 60` — kernel OOM killer beat earlyoom on gemma-3 crash
- 2026-03-14 tuned: `-m 8 -s 8 -r 10` — higher threshold + faster polling to catch spikes
- 2026-03-15 tuned: `-m 10 -s 50` — fixed AND-logic deadlock: earlyoom never fired because `-s 8` with 23GB swap pool meant swap never dropped below threshold while RAM hit 0%

Check status: `journalctl -u earlyoom -f`

### Layer 3: oom_score_adj (kernel OOM immunity)

Systemd service sets `oom_score_adj=-1000` on nfsd and sshd at boot.
This makes the kernel OOM killer skip these processes entirely.

Config: `/etc/systemd/system/oom-protect-critical.service`

### Layer 4: zram (compressed swap)

Provides 15GB compressed swap (zstd) in addition to 8GB disk swap.
Gives containers breathing room before OOM triggers.

Config: `/etc/default/zramswap` (`ALGO=zstd`, `PERCENT=50`, `PRIORITY=100`)

### Diagnostic commands

```bash
# Check earlyoom status
journalctl -u earlyoom --since "1 hour ago" --no-pager | tail -20

# Check for kernel OOM kills
sudo dmesg | grep -i "oom\|killed process"

# Check Docker container memory limits
docker inspect <container> --format "memory={{.HostConfig.Memory}} swap={{.HostConfig.MemorySwap}}"

# Check current memory pressure
free -h; swapon --show

# Check zram usage
zramctl
```

## Version Drift Check

If behavior looks outdated, inspect the script baked in the image:

```bash
docker run --rm --entrypoint /bin/sh bench-pipeline -c 'sed -n "1,220p" /opt/bench/run.sh'
```

Rebuild when image script differs from repo script.

Also rebuild after any change to suite `run.sh` or CLI flags. A stale image can
look like a runtime bug (for example: `Unknown arg: --tuning-profiles`).

## Rebuild

From `/mnt/shared/plans/shoulders/benchmarking/docker`:

```bash
docker build -t bench-code bench-code
docker build -t bench-knowledge bench-knowledge
docker build -t bench-pipeline bench-pipeline
docker build -t bench-reasoning bench-reasoning
```
