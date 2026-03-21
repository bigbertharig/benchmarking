# Single-GPU Cohort Suites

This is a thin wrapper path for:

1. choose a predefined single-GPU cohort
2. keep worker slots busy
3. load models one at a time through the canonical runtime prep script
4. start the benchmark suite as each runtime becomes ready
5. unload finished workers so the next queued model can reuse the slot

This is not a new loader.

Canonical load/verify path remains:

- [`/media/bryan/shared/scripts/prepare_llm_runtimes.py`](/media/bryan/shared/scripts/prepare_llm_runtimes.py)

## Current Cohorts

- `small_models`: single-GPU models with size `< 5B`
- `single_gpu_large`: single-GPU models with size `>= 5B` and `<= 9B`

Model membership is derived from:

- [`/media/bryan/shared/plans/shoulders/benchmarking/models.catalog.json`](/media/bryan/shared/plans/shoulders/benchmarking/models.catalog.json)

## Runner

- [`/media/bryan/shared/plans/shoulders/benchmarking/scripts/active/run_single_gpu_cohort_suite.py`](/media/bryan/shared/plans/shoulders/benchmarking/scripts/active/run_single_gpu_cohort_suite.py)

## Flow

1. clear currently loaded worker runtimes
2. scan single-GPU workers from `config.benchmark.json`
3. start one model load through `prepare_llm_runtimes.py`
4. when a worker verifies ready, launch the suite on that worker
5. while suites are running, continue loading the next queued model onto another free worker
6. when a suite finishes, unload that worker and recycle the slot

At most one model load is active at a time.
Multiple benchmark jobs may run in parallel on already-loaded workers.

## Dry Run

```bash
python3 /media/bryan/shared/plans/shoulders/benchmarking/scripts/active/run_single_gpu_cohort_suite.py \
  bench-daedalmap small_models \
  --shared-root /media/bryan/shared \
  --suite-arg=--execute \
  --env-file /media/bryan/shared/plans/shoulders/benchmarking/docker/bench-daedalmap/.env \
  --dry-run
```

Existing-score policy:

- default is `--existing-policy skip`
- use `--existing-policy rerun` to force fresh runs even when the ledger already has rows for that suite/model

## Real Run

```bash
python3 /media/bryan/shared/plans/shoulders/benchmarking/scripts/active/run_single_gpu_cohort_suite.py \
  bench-daedalmap small_models \
  --shared-root /media/bryan/shared \
  --suite-arg=--execute \
  --env-file /media/bryan/shared/plans/shoulders/benchmarking/docker/bench-daedalmap/.env
```

## Status

Campaign status is written under:

- `/media/bryan/shared/logs/benchmarks/cohort_suite_runs/history/<run_name>/status.json`

Per-model suite logs are written under:

- `/media/bryan/shared/logs/benchmarks/cohort_suite_runs/history/<run_name>/logs/`

This includes:

- `<model>_load.log`: canonical loader output for that model
- `<model>_<worker>.log`: suite container output for that model/worker
