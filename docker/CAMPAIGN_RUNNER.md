# Unified Campaign Runner

`/mnt/shared/scripts/benchmarks/run_campaign.py` is the only production
benchmark scheduler. It uses `docker/suite_contracts.json` to run sequential or
parallel suite blocks with one model-loading and checkpoint contract.

## Commands

```bash
python3 /mnt/shared/scripts/benchmarks/run_campaign.py campaign.json --dry-run --verbose
python3 /mnt/shared/scripts/benchmarks/run_campaign.py campaign.json --run-id run_001
python3 /mnt/shared/scripts/benchmarks/run_campaign.py campaign.json --run-id run_001
```

The final command resumes the same run. Additional controls:

```text
--on-failure continue|stop
--limit-override N
--limit BLOCK_ID=N
--verbose
```

Limit priority is block override, global override, manifest `limit`, then suite
default. An override fails preflight for suites whose contract does not support
bounded runs.

## Manifest

```json
{
  "name": "model_import_smoke",
  "defaults": {
    "runtime_image": "llama-runtime:b8884-candidate",
    "load_timeout_s": 300,
    "run_class": "smoke"
  },
  "blocks": [
    {
      "id": "data",
      "model": "model-id",
      "gguf": "/mnt/shared/models/model/model.gguf",
      "placement": "brain",
      "suite": "bench-dataimport",
      "suite_args": ["--tasks", "converter,reference"],
      "limit": 2,
      "ctx_size": 8192,
      "runtime_args": []
    },
    {
      "id": "geometry",
      "model": "model-id",
      "gguf": "/mnt/shared/models/model/model.gguf",
      "placement": "brain",
      "suite": "bench-geoimport",
      "suite_args": ["--tasks", "classification,prep_plan"],
      "limit": 2,
      "depends_on": ["data"]
    }
  ]
}
```

Required block fields are `id`, `model`, `gguf`, and `suite`. Optional fields:

| Field | Default | Meaning |
| --- | --- | --- |
| `placement` | `single` | `brain`, `single`, `split_1_3`, or `split_4_5` |
| `suite_args` | `[]` | Suite-owned flags only |
| `run_class` | default or `provisional` | Evidence class; no score gate is imposed |
| `limit` | suite default | Bounded sample count where supported |
| `depends_on` | `[]` | Completed prerequisite block IDs |
| `ctx_size` | model profile or 2048 | Runtime context size |
| `batch_size` | model profile or 128 | Runtime batch size |
| `runtime_args` | profile plus block args | Additional llama-server arguments |
| `runtime_image` | campaign default | Runtime image tag |
| `load_timeout_s` | campaign default or 300 | Runtime readiness timeout |
| `hardware_id` | derived from slot | Optional explicit hardware identity |
| `env_file` | none | Optional, only for suites that declare support |
| `runtime_group` | none | Keep one compatible model runtime loaded across consecutive suite blocks |

Do not put `--model`, `--runtime-base`, `--run-name`, `--run-class`, output
paths, profile paths, hardware identity, or GGUF paths in `suite_args`. The
runner owns them.

## Supported Suites

The live suite list and capabilities come from `suite_contracts.json`:

- `bench-pipeline`
- `bench-code`
- `bench-reasoning`
- `bench-knowledge`
- `bench-dataimport`
- `bench-geoimport`
- `bench-agent`
- `bench-routing`
- `bench-runtime`
- `bench-daedalmap`

`bench-code`, `bench-pipeline`, and `bench-runtime` currently do not support a
generic `--limit`. `bench-code` runs the selected EvalPlus problem sets in full.

## Profiles

`model_tuning_profiles.json` is resolved through
`scripts/active/model_profiles.py`. Aliases inherit the canonical profile, then
apply explicit alias overrides. Ambiguous matches, missing alias targets, alias
cycles, and missing required system prompts fail before a model is loaded.

The profile policy is suite-specific and declared in `suite_contracts.json`.
Some frozen harnesses intentionally own their prompts and do not inject a model
system prompt.

## One Load, Multiple Suites

Give consecutive blocks the same `runtime_group` to load a model once, run each
suite in manifest order on the same slot, and unload after the final block.
Every block in the group must have identical model, GGUF, placement, runtime
image, context, batch, and runtime arguments. The runner rejects mixed settings
before loading.

Runtime-group order is independent of score or suite success. With
`--on-failure continue`, a failed suite is recorded and the next suite still
runs on the loaded model. With `--on-failure stop`, the campaign stops at the
failure. On resume, a group whose earlier blocks are already complete loads the
model once at its first unfinished block.

## Scheduling

The runner exposes these rig slots:

| Placement | GPUs | Port |
| --- | --- | --- |
| `brain` | 0 | 11434 |
| `single` | first free of 1-5 | 11435-11439 |
| `split_1_3` | 1,3 | 11435 |
| `split_4_5` | 4,5 | 11438 |

Model loads are serialized to bound shared bus and storage pressure. Loaded
suites run concurrently on non-overlapping GPU sets. `depends_on` supplies
strict ordering when required.

## Preflight and Resume

Before loading a model the runner verifies:

- manifest structure and dependency references
- GGUF and optional env-file existence
- model profile requirements
- suite limit policy and runner-owned flags
- suite image contract labels
- writable result roots and `/mnt/shared/cache/benchmarks`

Containers receive an explicit temporary `HOME` and a persistent shared
Hugging Face cache under `/mnt/shared/cache/benchmarks`. This avoids root-home
permission failures and reuses frozen dataset downloads across model runs.

Campaign status and checkpoints are under:

```text
/mnt/shared/logs/benchmarks/campaigns/history/<campaign>/<run_id>/
```

Completed blocks are skipped on resume. Blocks interrupted during load or suite
execution restart from the beginning. Dry runs do not create or consume a
checkpoint.

## Adding a Suite

Follow `docker/SUITE_CREATION.md`. A suite is not campaign-compatible until it
is registered and `python3 scripts/active/validate_suite_contract.py` passes.
