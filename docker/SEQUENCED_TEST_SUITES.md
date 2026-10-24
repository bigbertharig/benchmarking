# Sequential and Parallel Campaigns

The unified campaign runner is the canonical path for both modes:

```text
/mnt/shared/scripts/benchmarks/run_campaign.py
```

## Sequential Blocks

Use `runtime_group` to load one model once and run its suite blocks in manifest
order. Use `depends_on` only for dependencies outside that model sequence:

```json
{
  "name": "model_core_sequence",
  "defaults": {"run_class": "smoke"},
  "blocks": [
    {
      "id": "pipeline",
      "model": "model-id",
      "gguf": "/mnt/shared/models/model/model.gguf",
      "placement": "brain",
      "suite": "bench-pipeline",
      "runtime_group": "model-id-core"
    },
    {
      "id": "reasoning",
      "model": "model-id",
      "gguf": "/mnt/shared/models/model/model.gguf",
      "placement": "brain",
      "suite": "bench-reasoning",
      "runtime_group": "model-id-core",
      "suite_args": ["--tasks", "gsm8k"],
      "limit": 5
    }
  ]
}
```

## Parallel Blocks

Blocks without dependencies may run concurrently on whatever cards the rig
manager gives them. The runner asks for one load at a time, then lets the loaded
suites execute in parallel.

Omit placement and the manager picks the cards; `gpus: [..]` pins them.

## Run and Resume

```bash
python3 /mnt/shared/scripts/benchmarks/run_campaign.py campaign.json --dry-run --verbose
python3 /mnt/shared/scripts/benchmarks/run_campaign.py campaign.json --run-id run_001
python3 /mnt/shared/scripts/benchmarks/run_campaign.py campaign.json --run-id run_001
```

Use `--max-active-models 1` when each model must finish all of its suites before
the next model loads. Omit it to allow independent model groups to occupy free
GPU lanes concurrently. Runtime groups reuse one loaded model across their
remaining suites, including when earlier suites were already checkpointed.

The second real invocation resumes `run_001`: completed blocks are skipped and
interrupted blocks restart. Direct suite launches remain useful for debugging an
entrypoint, but are not a second orchestration path.
