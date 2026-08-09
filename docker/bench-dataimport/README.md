# bench-dataimport

Tests a model's ability to perform data import tasks from the DaedalMap pipeline:
writing Python converters, generating reference.json metadata, and understanding
data schemas.

## What it tests

| Task | Cases | What's measured |
|------|-------|-----------------|
| **converter** | 3 | Can the model write a working Python converter that produces correct parquet? |
| **reference** | 3 | Can the model generate valid, complete reference.json with keywords and aggregation rules? |
| **schema_understanding** | 4 | Can the model identify loc_id columns, detect aggregates, recognize wide-vs-long format, and handle type coercion? |

### Scoring

- **converter_correct**: Output parquet validation (row count, loc_id first, float64 metrics, no dupes). CV-001 runs when its raw fixture is staged at `/raw`.
- **converter_structure**: Static analysis of generated code (has pandas, parquet write, loc_id, type coercion, snappy).
- **reference_quality**: JSON validity + nested structure + metric completeness + keyword coverage.
- **aggregation_accuracy**: Correct aggregation rule assignment (sum vs weighted_avg vs skip).
- **schema_understanding**: Key concept detection in model's analysis output.

## Quick start

### Build

```bash
cd /mnt/shared/plans/shoulders/benchmarking/docker/bench-dataimport
docker build -t bench-dataimport .
```

### Run (smoke test)

```bash
docker run --rm --network host \
  -e BENCHMARK_DISABLE_AUTO_RESERVE=1 \
  -v /mnt/shared:/mnt/shared \
  -v /mnt/shared/logs/benchmarks/bench-dataimport/history:/results \
  -v /mnt/shared/plans/shoulders/benchmarking:/benchmark-scripts:ro \
  bench-dataimport \
  --model qwen3.6:27b \
  --runtime-base http://localhost:11434 \
  --tasks converter,reference \
  --limit 1 \
  --run-class smoke \
  --run-name dataimport_smoke_v1
```

### Run (full suite)

```bash
docker run --rm --network host \
  -e BENCHMARK_DISABLE_AUTO_RESERVE=1 \
  -v /mnt/shared:/mnt/shared \
  -v /mnt/shared/logs/benchmarks/bench-dataimport/history:/results \
  -v /mnt/shared/plans/shoulders/benchmarking:/benchmark-scripts:ro \
  bench-dataimport \
  --model qwen3.6:27b \
  --runtime-base http://localhost:11434 \
  --run-name dataimport_full_v1
```

## Entrypoint args

| Arg | Required | Description |
|-----|----------|-------------|
| `--model` | yes | Model ID (e.g., `qwen3.6:27b`) |
| `--runtime-base` | yes | LLM endpoint (e.g., `http://localhost:11434`) |
| `--tasks` | no | Comma-separated: `converter,reference,schema_understanding` (default: all) |
| `--limit` | no | Max cases per task (default: all) |
| `--run-name` | no | Stable ID for resume (default: timestamp) |
| `--run-class` | no | Evidence class: `smoke`, `provisional`, `validated`, or `full` |
| `--results-dir` | no | Output root (default: `/results`) |
| `--tuning-profiles` | no | Path to model_tuning_profiles.json |
| `--system-prompt-file` | no | Explicit data-import system prompt path |
| `--raw-dir` | no | Directory containing pre-staged raw fixtures (default: `/raw`) |
| `--records` | no | Canonical schema-v2 JSONL ledger path |
| `--reference-output` | no | Derived Markdown reference path |
| `--scoreboard-output` | no | Derived scoreboard JSON path |

The suite never downloads raw datasets. Mount a pre-staged fixture directory at
`/raw` to execute `CV-001`; without it, that case receives a deterministic
static converter-structure score. API and recorder failures are retained as
schema-v2 failure rows and make the affected task fail.

## Output layout

```
/results/bench-dataimport_<model>_<run_name>/
  status.json              # Live-updated task state
  stage_updates.jsonl       # Per-case score records
  final_summary.json        # Aggregate results
  converter/
    CV-001_convert.py       # Generated converter script
    CV-001_response.json    # API response metadata
    CV-001_run_output.txt   # Converter stdout (if run)
    CV-001_score.json       # Validation results
  reference/
    RF-001_output.json      # Generated reference.json
    RF-001_score.json       # Scoring breakdown
  schema_understanding/
    SU-001_output.json      # Model's schema analysis
```

## Adding new cases

Edit `dataimport_cases.json`. Each task has a `cases` array. Follow the existing
structure for the task type. Rebuild the Docker image after changes.

## Relationship to calibration runs

The calibration runs in `gpu_rig/calibration_runs/` were manual tests that
informed this benchmark's design. This suite automates and standardizes those
tests so new models can be compared consistently.

## Local harness smoke

The repository test suite runs `schema_understanding` against a localhost mock
OpenAI-compatible endpoint and verifies the checkpoint, JSONL record, reference,
scoreboard, and final summary:

```bash
python3 -m unittest tests.test_dataimport_suite -v
```

This validates runner integration without claiming model-quality or Docker
runtime validation.
