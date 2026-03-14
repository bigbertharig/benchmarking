# Suite Creation

This guide defines how to build new Docker benchmark suites that work with this rig's existing orchestration, logs, and dashboard.

## Goal

A valid suite must:

1. Run as a standalone Docker image.
2. Write resumable run artifacts to shared storage.
3. Expose live progress through status files/logs (so dashboard can show worker state/holding).
4. Fail clearly on real task failures, but skip unavailable tasks cleanly.

## Required Runtime Contract

Each suite container should accept at least:

- `--model <model-id-or-path>`
- `--runtime-base <http://localhost:PORT>` (if using external llama runtime)
- `--tasks <comma,list>`
- `--limit <N>` (optional, but strongly recommended)
- `--run-name <id>` (required for resumable operation)
- `--results-dir <path>` (default `/results`)

Expected launch pattern:

```bash
docker run --rm --network host \
  -v /mnt/shared:/mnt/shared \
  -v /mnt/shared/logs/benchmarks/<suite>/history:/results \
  -v /mnt/shared/plans/shoulders/benchmarking:/benchmark-scripts:ro \
  <suite-image> \
  --model <model> \
  --runtime-base http://localhost:1143X \
  --tasks <task1,task2,...> \
  --limit 100 \
  --run-name <run_id>
```

## Required Output Layout

Write run outputs under:

- `/results/<suite>_<model_safe>_<run_name>/`

Minimum files:

1. `status.json` (live-updated)
2. per-task output dirs (`gsm8k/`, `bbh/`, etc.)
3. suite log at run root (for live progress parsing)

Recommended naming:

- `<worker_label>.log` in the run root for parallel launches
- keep all paths deterministic from `run-name`

## `status.json` Schema (Minimum)

Use this shape so dashboard + tooling can parse without custom adapters:

```json
{
  "run_start": "2026-03-12T21:17:53.098347",
  "model": "Qwen2.5-Coder-7B-Instruct-Q4_K_M.gguf",
  "runtime": "http://localhost:11436",
  "tasks_requested": ["gsm8k", "bbh", "drop"],
  "limit": "100",
  "num_fewshot": "",
  "tasks": {
    "gsm8k": {
      "state": "completed",
      "exit_code": 0,
      "output_dir": "/results/.../gsm8k",
      "started_at": "2026-03-12T21:17:53+00:00",
      "ended_at": "2026-03-12T21:34:36+00:00"
    }
  },
  "updated_at": "2026-03-12T21:34:36.818111"
}
```

Task state values to use:

- terminal success: `completed`
- terminal fail: `failed`
- optional in-progress: `running`

## Task Availability Preflight (Mandatory)

Before execution, filter requested tasks to what the suite runtime actually supports.

Why:

- prevents fake failures like `Tasks not found: math_500`
- keeps `tasks_requested` accurate (dashboard counters reflect real workload)

Pattern:

1. list available tasks (`python -m lm_eval ls tasks` or suite equivalent)
2. compute `kept` and `missing`
3. log `missing` as warning
4. run only `kept`
5. write filtered list into `status.json.tasks_requested`
6. hard fail only if `kept` is empty

## Progress Reporting (Dashboard-Friendly)

Dashboard reads:

- suite from status file location (`bench-reasoning`, `bench-code`, etc.)
- current task + progress from status/log tail

To support good live labels:

1. Emit clear per-task markers in logs:
   - `--- Running task: <task> ---`
2. Emit incremental counters where possible:
   - `Requesting API: ... X/Y`
3. Keep `status.json.updated_at` fresh on each stage transition.

Current display target:

- `State`: suite name (`reasoning`, `code`, `pipeline`, ...)
- `Holding`: `<task> <task_index>/<task_total> - <x/limit-or-x/total>`

## Checkpoint/Resume Rules

For each task in `tasks_requested`:

1. If `status.json.tasks[task].state == completed`, skip.
2. If missing/failed/incomplete, rerun.
3. Re-running with same `--run-name` must be idempotent.

Do not overwrite successful task artifacts when resuming.

## Nickname Mapping for Long Task Names

If task identifiers are too long/noisy, map them using:

- `/home/bryan/Desktop/shared/plans/shoulders/benchmarking/docker/task_nicknames.json`

Use short stable names for UI, keep raw ids in artifacts.

## New Suite Checklist

1. Create `docker/<suite>/Dockerfile`
2. Create `docker/<suite>/run.sh` with CLI contract above
3. Add task preflight filtering
4. Add `status.json` init/update helpers
5. Add checkpoint skip logic
6. Add suite `README.md` (what it validates, tasks, commands)
7. Add suite history doc `BENCH_<SUITE>_HISTORY.md`
8. Add canonical run command to `docker/README.md`
9. Run smoke test (`--limit 3`) then resumable test (`same run-name`)
10. Verify dashboard shows suite + live holding progress

## Minimal `run.sh` Flow

```bash
parse_args
verify_runtime
filter_available_tasks
init_or_refresh_status

for task in tasks_requested:
  if task_completed(task): continue
  mark_running(task)
  run_task_command(task)
  mark_completed_or_failed(task)

print_summary
exit_nonzero_if_failures
```

## Orchestrator Coexistence

Benchmark suites run outside the orchestrator's task queue — they talk directly to
worker HTTP endpoints. This means the orchestrator has no visibility into benchmark
activity.

Current contract:
- benchmark launches must reserve the target GPU before starting work
- reserved GPUs are hidden from normal orchestrator balancing and refuse queued work
- benchmark launchers are responsible for releasing the reservation on exit
- if the suite self-manages reservation inside the container, the container must also
  have the shared root mounted at `/mnt/shared`

Required integration options for a new suite:
- use a host-side launcher that calls `/mnt/shared/scripts/benchmark_gpu_reservation.py`
  before and after the container run
- or document the exact manual reserve/release commands if the suite is intended for
  direct ad hoc `docker run`

Do not assume that talking to `http://localhost:1143X` is enough. Without the explicit
reservation step, plans and benchmarks can still collide on the same worker.

See the main [README](README.md) "Running Benchmarks Alongside Plans" section for the
operator-facing workflow.

## What To Avoid

- Hardcoding task lists without availability checks.
- Counting unavailable tasks as failures.
- Writing only final results (no live status updates).
- Non-deterministic output directories (breaks resume/dashboard).
- Creating a custom status format that bypasses current dashboard parsers.
