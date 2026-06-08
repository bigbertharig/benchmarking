# Unified Campaign Runner

`run_campaign.py` runs arbitrary combinations of models and benchmark suites
across all available GPUs with parallel scheduling and checkpoint/resume.

Script: `/mnt/shared/scripts/benchmarks/run_campaign.py`
Manifests: `/mnt/shared/plans/shoulders/benchmarking/campaigns/*.json`

## Quick Start

```bash
# Dry-run to verify schedule
ssh 10.0.0.3
python3 /mnt/shared/scripts/benchmarks/run_campaign.py \
  /mnt/shared/plans/shoulders/benchmarking/campaigns/gemma4_reasoning_rerun.json \
  --dry-run

# Run for real
python3 /mnt/shared/scripts/benchmarks/run_campaign.py \
  /mnt/shared/plans/shoulders/benchmarking/campaigns/gemma4_reasoning_rerun.json

# Resume a previous run
python3 /mnt/shared/scripts/benchmarks/run_campaign.py \
  /mnt/shared/plans/shoulders/benchmarking/campaigns/gemma4_reasoning_rerun.json \
  --run-id 20260607_143000
```

## CLI

```
python3 run_campaign.py MANIFEST [--run-id ID] [--dry-run] [--on-failure continue|stop]
    [--limit-override N] [--limit BLOCK_ID=N ...] [--verbose]
```

| Flag | Default | Description |
|------|---------|-------------|
| `MANIFEST` | required | Path to campaign manifest JSON |
| `--run-id` | timestamp | Run identifier (reuse to resume) |
| `--dry-run` | off | Print schedule, don't start containers |
| `--on-failure` | `continue` | `stop` halts entire campaign on first failure |
| `--limit-override N` | manifest | Override limit for ALL blocks (e.g. `--limit-override 10` for smoke) |
| `--limit BLOCK=N` | manifest | Override limit for one block (repeatable; wins over `--limit-override`) |
| `--verbose` | off | Print docker commands and debug details |

**Limit priority**: `--limit BLOCK=N` > `--limit-override N` > manifest `limit` field > suite default

## Manifest Format

```json
{
  "name": "my_campaign",
  "defaults": {
    "runtime_image": "llama-runtime:b8884-candidate",
    "load_timeout_s": 300
  },
  "blocks": [
    {
      "id": "unique_block_id",
      "model": "gemma-4:e4b",
      "gguf": "/mnt/shared/models/gemma-4-e4b/gemma-4-e4b-it-Q4_K_M.gguf",
      "placement": "single",
      "suite": "bench-reasoning",
      "suite_args": ["--tasks", "gsm8k,bbh,drop", "--patch-think-tag-strip"],
      "limit": 50,
      "runtime_args": ["--reasoning-budget", "0"],
      "ctx_size": 4096,
      "depends_on": []
    }
  ]
}
```

### Block Fields

| Field | Required | Default | Description |
|-------|----------|---------|-------------|
| `id` | yes | — | Unique block identifier |
| `model` | yes | — | Model ID (passed to suite `--model`) |
| `gguf` | yes | — | Full path to GGUF file on rig |
| `suite` | yes | — | Suite name: `bench-pipeline`, `bench-code`, `bench-reasoning`, `bench-knowledge` |
| `placement` | no | `single` | GPU placement: `brain`, `single`, `split_1_3`, `split_4_5` |
| `suite_args` | no | `[]` | Extra args passed to suite container |
| `limit` | no | suite default | Convenience for `--limit N` (explicit `--limit` in suite_args wins) |
| `runtime_args` | no | `[]` | Extra llama-server args (e.g., `["--reasoning-budget", "0"]`) |
| `runtime_image` | no | from defaults | Docker image for llama-server |
| `ctx_size` | no | tuning profile or 2048 | Context window size |
| `batch_size` | no | tuning profile or 128 | Batch size |
| `load_timeout_s` | no | from defaults or 300 | Max seconds to wait for model load |
| `depends_on` | no | `[]` | Block IDs that must complete first |

### Defaults Section

Fields in `defaults` apply to all blocks unless overridden per-block:
- `runtime_image`
- `load_timeout_s`

### Config Lookup Chain

For `ctx_size` and `batch_size`, if not specified in the block:
1. Look up model in `model_tuning_profiles.json` `runtime` section
2. Fall back to hardcoded defaults (2048, 128)

For `runtime_args`, the block's list is merged with `extra_args` from tuning profiles.

## GPU Layout

| Slot | GPUs | Port | Tier | Notes |
|------|------|------|------|-------|
| `brain` | 0 | 11434 | brain | 3090 24GB |
| `gpu_1` | 1 | 11435 | single | 1060 6GB |
| `gpu_2` | 2 | 11436 | single | 1060 6GB |
| `gpu_3` | 3 | 11437 | single | 1060 6GB |
| `gpu_4` | 4 | 11438 | single | 1060 6GB |
| `gpu_5` | 5 | 11439 | single | 1060 6GB |
| `split_1_3` | 1,3 | 11435 | split | 14B models |
| `split_4_5` | 4,5 | 11438 | split | 14B models |

Placement values: `brain`, `single`, `split_1_3`, `split_4_5`

Conflict rule: two blocks conflict if their GPU sets overlap. A `split_1_3`
block conflicts with any `single` block on GPU 1 or GPU 3.

## Scheduling

1. Parse manifest, build dependency graph
2. Main loop (3s ticks):
   - Reap finished suite processes
   - Advance blocks whose `depends_on` resolved
   - If load lock free: pick next ready block with a free GPU slot, start loading
   - When load completes: release load lock, start suite container
   - On suite completion: release GPU slot, stop runtime
3. Blocks needing the same GPU auto-wait (no explicit `depends_on` needed)

**Key constraint**: only one model loads at a time (shared PCIe bus). Once
loaded, suites run in parallel across different GPUs.

### Block State Machine

```
pending -> waiting_deps -> waiting_gpu -> loading -> running_suite -> completed
                                                                   -> failed
```

## Checkpoint/Resume

Checkpoint: `campaigns/history/<name>/<run_id>/campaign_state.json`
Status: `campaigns/history/<name>/<run_id>/status.json`

On restart with the same `--run-id`:
- Completed blocks are skipped
- Blocks that were mid-load or mid-suite restart from scratch (orphan
  containers are stopped first)

## Container Naming

- Runtime: `llama-campaign-{block_id}` (e.g., `llama-campaign-e4b_reasoning`)
- Suite: `bench-{suite_short}-campaign-{block_id}` (e.g., `bench-reasoning-campaign-e4b_reasoning`)

The heartbeat keeper auto-detects containers matching `llama-*` and `bench-*`.

## Error Handling

- Load timeout: block marked failed, slot released, other blocks continue
- Suite exit != 0: block marked failed, other blocks continue
- `--on-failure stop`: halt entire campaign on first failure
- SIGINT/SIGTERM: stop all running containers, write final checkpoint

## Suite Logs

Per-block logs are captured to:
```
/mnt/shared/logs/benchmarks/campaigns/history/<name>/<run_id>/logs/<block_id>.log
```

Suite results go to the standard suite history directories:
```
/mnt/shared/logs/benchmarks/bench-{suite}/history/
```

## Example: Gemma 4 Reasoning Re-Run

```bash
python3 /mnt/shared/scripts/benchmarks/run_campaign.py \
  /mnt/shared/plans/shoulders/benchmarking/campaigns/gemma4_reasoning_rerun.json \
  --dry-run
```

Expected schedule:
- E4B loads on GPU 1, E2B waits (load lock)
- E2B loads on GPU 3 after E4B load completes
- 26B loads on brain after both workers start their suites
- E4B + E2B + 26B suites run in parallel
- When brain finishes 26B, loads 31B
- Workers may still be running (reasoning is slower on 1060s)
