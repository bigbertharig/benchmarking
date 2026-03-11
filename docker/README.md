# Docker Benchmark Suites

This is the operator guide for running the benchmark Docker suites against the
live worker runtimes.

## Architecture

Each docker suite is self-contained:
- its own README explaining what it tests, how prompts work, and how to run it
- its own HISTORY file tracking every run with timestamps, prompts used, and scores
- its own result archives in per-run directories under `/media/bryan/shared/logs/benchmarks/`

The main `MODEL_LIBRARY.md` holds only the latest scores per model/test as a simple
summary table. For full history and prompt traceability, check each suite's history file.

Storage policy (do not mix suite outputs in one folder):
- `bench-pipeline`: `/mnt/shared/logs/benchmarks/bench-pipeline/history`
- `bench-code`: `/mnt/shared/logs/benchmarks/bench-code/history`
- `bench-reasoning`: `/mnt/shared/logs/benchmarks/bench-reasoning/history`
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
2. Record results in the suite's HISTORY file
3. Compare across runs to learn what prompt changes helped
4. Fold improvements back into the universal prompt in `model_tuning_profiles.json`
5. The main MODEL_LIBRARY.md gets updated with only the latest scores

## Suites

| Suite | What It Tests | Prompt Source | History |
| --- | --- | --- | --- |
| `bench-pipeline` | Worker-facing custom reliability (JSON, safety, ambiguity, sequencing, tradeoffs, extraction) | Model-specific prompt profiles + per-test overrides + tuning profile fallback | [HISTORY](bench-pipeline/BENCH_PIPELINE_HISTORY.md) |
| `bench-reasoning` | lm-eval reasoning tasks (gsm8k, bbh, drop, math_500, aime_2024) | Model-specific prompt profiles injected via `--system_instruction` | [HISTORY](bench-reasoning/BENCH_REASONING_HISTORY.md) |
| `bench-knowledge` | lm-eval MC/loglikelihood tasks (mmlu, arc_challenge, hellaswag, etc.) | Model-specific prompt profiles injected via `--system_instruction` | [HISTORY](bench-knowledge/BENCH_KNOWLEDGE_HISTORY.md) |
| `bench-code` | EvalPlus code generation (humaneval, mbpp) | EvalPlus built-in prompts (no profile injection yet) | [HISTORY](bench-code/BENCH_CODE_HISTORY.md) |

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
2. For strict-output custom tests, prefer the worker currently running
   `qwen2.5-coder:7b` (recently `11437`).
3. Ensure benchmark workers stay loaded long enough for suite runs:
   - `max_hot_workers` should not force immediate unload.

## Canonical Run Patterns

Reasoning:

```bash
docker run --rm --network host \
  -v /mnt/shared/logs/benchmarks/bench-reasoning/history:/results \
  -v /mnt/shared/plans/shoulders/benchmarking:/benchmark-scripts:ro \
  bench-reasoning --model qwen2.5-coder:7b --runtime-base http://localhost:11437 --run-name reasoning_full_v1
```

Code:

```bash
docker run --rm --network host \
  -v /mnt/shared/logs/benchmarks/bench-code/history:/results \
  bench-code --model qwen2.5-coder:7b --runtime-base http://localhost:11437
```

Code preflight-only (timeout + reachability sanity):

```bash
docker run --rm --network host \
  bench-code --model qwen2.5-coder:7b --runtime-base http://localhost:11437 --preflight-only --request-timeout 30
```

Code resumable run:

```bash
docker run --rm --network host \
  -v /mnt/shared/logs/benchmarks/bench-code/history:/results \
  bench-code --model qwen2.5-coder:7b --runtime-base http://localhost:11437 --run-name coding_full_v1
```

Pipeline (custom worker-facing tests):

```bash
docker run --rm --network host \
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
  -v /mnt/shared/models:/models:ro \
  -v /mnt/shared/logs/benchmarks/bench-knowledge/history:/results \
  -v /mnt/shared/plans/shoulders/benchmarking:/benchmark-scripts:ro \
  bench-knowledge /models/<model-folder>/<model-file>.gguf --run-name knowledge_full_v1
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
  -v /mnt/shared/models:/models:ro \
  -v /mnt/shared/logs/benchmarks/bench-knowledge/history:/results \
  bench-knowledge \
  /models/<model-folder>/<model-file>.gguf \
  --tasks mmlu,arc_challenge,hellaswag,truthfulqa_mc2,boolq \
  --limit 10
```

Coding lite status:
- currently blocked in active `bench-code` flow because EvalPlus evaluate requires
  full problem coverage for each dataset.
- see `suites/coding_lite_v1.json` for target shape and blocker note.

## Common Failure Modes

- `Cannot reach llama-compatible runtime`:
  - missing `--network host`
  - wrong `--runtime-base` port
  - worker unloaded between prep and run
- `Unknown arg: --runtime-base`:
  - stale image build; rebuild the image from current docker sources
- `No model-specific system prompt found for ...`:
  - add `system_prompt` for that model in `custom_tasks/model_prompt_profiles.json` or `model_tuning_profiles.json`
  - or run with `--allow-generic-prompt-fallback`
- `Custom test runner not found` in `bench-pipeline`:
  - missing scripts mount:
    `-v /mnt/shared/plans/shoulders/benchmarking:/benchmark-scripts:ro`

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
