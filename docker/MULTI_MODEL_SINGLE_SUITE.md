# Multi-Model Single-Suite Campaigns

This is a separate operator path from [SEQUENCED_TEST_SUITES.md](SEQUENCED_TEST_SUITES.md).

Use this when the goal is:

1. pick one benchmark suite
2. run that same suite across several models
3. keep per-model load/verify/run/release checkpoints in one campaign status file

Do not merge this path with the existing sequenced model flow.

## Model

This path is:

- one suite
- one worker target
- many models
- one model loaded at a time

The existing sequenced path remains:

- one model
- many suites

Same safety logic, different operator goal.

## Supported Suites

The standalone runner currently supports worker-backed suites:

- `bench-pipeline`
- `bench-code`
- `bench-reasoning`
- `bench-daedalmap`

`bench-knowledge` is intentionally excluded. Its runtime model is different and should stay on its own path.

## Campaign Format

Top-level fields:

- `name`: campaign name
- `target_worker`: worker name such as `gpu-5`
- `worker_port`: optional explicit port override
- `suite`: one suite id
- `stop_on_failure`: stop on first model failure when true
- `suite_args`: CLI args applied to every model run
- `env_file`: optional, mainly for `bench-daedalmap`
- `models`: list of model entries

Each `models[]` entry:

- `id`: stable short id for logs/status
- `model`: runtime model id to load
- `args`: optional extra CLI args for this model only
- `enabled`: optional bool
- `run_name`: optional explicit run name

Example:

```json
{
  "name": "daedalmap_small_models_full_example",
  "target_worker": "gpu-5",
  "worker_port": 11439,
  "suite": "bench-daedalmap",
  "stop_on_failure": true,
  "env_file": "/mnt/shared/plans/shoulders/benchmarking/docker/bench-daedalmap/.env",
  "suite_args": ["--execute"],
  "models": [
    {"id": "qwen25coder7b", "model": "qwen2.5-coder:7b"},
    {"id": "llama32_3b", "model": "llama3.2:3b"},
    {"id": "phi4mini_3p8b", "model": "phi-4-mini:3.8b"}
  ]
}
```

Reference file:

- [`campaigns/daedalmap_small_models_full_example.json`](/media/bryan/shared/plans/shoulders/benchmarking/campaigns/daedalmap_small_models_full_example.json)

## Run

Dry-run first:

```bash
python3 /mnt/shared/plans/shoulders/benchmarking/scripts/active/run_multi_model_suite_campaign.py \
  /mnt/shared/plans/shoulders/benchmarking/campaigns/daedalmap_small_models_full_example.json \
  --dry-run
```

Then run for real:

```bash
python3 /mnt/shared/plans/shoulders/benchmarking/scripts/active/run_multi_model_suite_campaign.py \
  /mnt/shared/plans/shoulders/benchmarking/campaigns/daedalmap_small_models_full_example.json
```

## Status And Logs

Status root:

- `/mnt/shared/logs/benchmarks/multi_model_suite_campaigns/history/<campaign>/<run_id>/`

Files:

- `status.json`: campaign-level checkpoint state
- `logs/<model_id>.log`: one log per model run

Each model run still writes its normal suite output into the suite's usual history folder:

- `bench-pipeline`: `/mnt/shared/logs/benchmarks/bench-pipeline/history`
- `bench-code`: `/mnt/shared/logs/benchmarks/bench-code/history`
- `bench-reasoning`: `/mnt/shared/logs/benchmarks/bench-reasoning/history`
- `bench-daedalmap`: `/mnt/shared/logs/benchmarks/bench-daedalmap/history`

## Safety Rules

- Load one model at a time.
- Verify the runtime after every load.
- Reserve the worker only for the active model run.
- Release the worker after each model finishes.
- Do not use this path for mixed-suite experiments.

## Why Separate

The existing sequenced flow answers:

- "This model is loaded. Which suites should I run next?"

This path answers:

- "I want this one suite on several models. Walk the worker through them safely."
