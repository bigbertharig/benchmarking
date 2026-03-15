# bench-pipeline

Runs worker-facing custom reliability tests from
`custom_tasks/cases.json` against a live llama-compatible worker endpoint.

## Quick Start

All commands run on the rig (`ssh 10.0.0.3`). Model must already be loaded on the target port.

**7B on single worker (e.g. GPU 2, port 11436):**
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

**14B on split pair (e.g. GPUs 1+3, port 11437):**
```bash
docker run --rm --network host \
  -e BENCHMARK_DISABLE_AUTO_RESERVE=1 \
  -v /mnt/shared:/mnt/shared \
  -v /mnt/shared/logs/benchmarks/bench-pipeline/history:/results \
  -v /mnt/shared/plans/shoulders/benchmarking:/benchmark-scripts:ro \
  bench-pipeline \
  --model qwen2.5-coder:14b \
  --runtime-base http://localhost:11437 \
  --run-name pipeline_coder14b_v1
```

**32B on brain (GPU 0, port 11434):**
```bash
docker run --rm --network host \
  -e BENCHMARK_DISABLE_AUTO_RESERVE=1 \
  -v /mnt/shared:/mnt/shared \
  -v /mnt/shared/logs/benchmarks/bench-pipeline/history:/results \
  -v /mnt/shared/plans/shoulders/benchmarking:/benchmark-scripts:ro \
  bench-pipeline \
  --model qwen2.5-coder:32b \
  --runtime-base http://localhost:11434 \
  --run-name pipeline_coder32b_v1
```

**Run only specific tests** (add `--tests`):
```bash
  --tests custom_json_schema_strict,custom_command_safety
```

Runtime: ~5 min for 3 tests, ~15 min for full 6-test suite.

## Entrypoint Args

- `--model` required model id
- `--runtime-base` worker base URL (default: `http://localhost:11436`)
- `--tests` comma-separated custom test ids
- `--results-dir` output root (default: `/results`)
- `--scripts-dir` benchmark scripts mount path (default: `/benchmark-scripts`)
- `--use-model-prompts` enable per-model prompt profiles (enabled by default in `run.sh`)
- `--prompt-profiles` prompt profile JSON path (default:
  `/benchmark-scripts/custom_tasks/model_prompt_profiles.json`)
- `--tuning-profiles` universal model tuning JSON path (default:
  `/benchmark-scripts/model_tuning_profiles.json`)
- `--require-model-prompt` fail if model-specific prompt source is missing
- `--run-name` stable run id for checkpoint/resume

## Example (Baseline)

```bash
docker run --rm --network host \
  -v /mnt/shared/logs/benchmarks/bench-pipeline/history:/results \
  -v /mnt/shared/plans/shoulders/benchmarking:/benchmark-scripts:ro \
  bench-pipeline \
  --model Qwen2.5-Coder-7B-Instruct-Q4_K_M.gguf \
  --runtime-base http://localhost:11437 \
  --run-name pipeline_worker_v1
```

## Example (Prompt-Tuned)

```bash
docker run --rm --network host \
  -v /mnt/shared/logs/benchmarks/bench-pipeline/history:/results \
  -v /mnt/shared/plans/shoulders/benchmarking:/benchmark-scripts:ro \
  bench-pipeline \
  --model Qwen2.5-Coder-7B-Instruct-Q4_K_M.gguf \
  --runtime-base http://localhost:11437 \
  --use-model-prompts \
  --prompt-profiles /benchmark-scripts/custom_tasks/model_prompt_profiles.json
```

## Output

Per run:
- `*_stage_updates.jsonl`
- `*_status.json`
- `*_final_summary.json`
- `*_checkpoint.json`

Per test group:
- `custom_<test_id>_<timestamp>/result.json`

## Prompt Methodology

Each test in this suite can have its own prompt override per model for tuning experiments.
The universal system prompt (which deploys with each model) lives in `model_tuning_profiles.json`.
Test-specific overrides live in `custom_tasks/model_prompt_profiles.json`.

When `--use-model-prompts` is enabled:
1. The runner checks `model_prompt_profiles.json` for a test-specific override (`model + test_id`)
2. If none exists, it checks `model_prompt_profiles.json` for a model-level `system_prompt`
3. If none exists, it falls back to `model_tuning_profiles.json` universal `system_prompt` for that model
4. If `--require-model-prompt` is set (default in `run.sh`), the run fails here instead of using a generic fallback.

Operational policy:
- Keep one default prompt per model.
- Do not rely on one shared generic prompt for all models.

Every run result (`result.json`) captures the exact prompt used:
- `prompts_snapshot`: run-level summary of which prompt resolved and from where
- per-case `system_prompt_used`: the exact text sent with each test case

This means historical runs are self-contained — you can always reconstruct what
prompt produced what score without cross-referencing the current profiles.

## Run History

All historical results for this suite live in:
- [BENCH_PIPELINE_HISTORY.md](BENCH_PIPELINE_HISTORY.md)

Each entry records: model, score, prompt used, timestamp, and run path.
The main MODEL_LIBRARY.md holds only the latest scores.

## Common Issues

- **Container exits immediately (no output)**:
  - missing `-e BENCHMARK_DISABLE_AUTO_RESERVE=1`; the reservation helper needs
    `filelock` which isn't in the container
- **`Use model prompts: 0` in logs**:
  - stale Docker image; rebuild with `docker build -t bench-pipeline .`
- **All tests fail in 0 seconds with empty scores**:
  - `--require-model-prompt` can't resolve the model ID; check that `--model` value
    fuzzy-matches a key in `model_tuning_profiles.json`. DeepSeek models need explicit
    aliases (e.g. `deepseek-r1:14b`) — these are already added.
- `Custom test runner not found`:
  - missing scripts mount
- Runtime unreachable:
  - wrong port or model unloaded
- Strict JSON failures:
  - use prompt profiles and post-parse validators, but keep suite prompts fixed
    for fair cross-model comparisons
- `Unknown arg: ...` for a flag that exists in repo:
  - stale Docker image; rebuild `bench-pipeline` before rerunning

## Resumable Runs

`bench-pipeline` now checkpoints per test id.

- tests already marked `passed` are skipped on rerun
- tests marked `failed` are rerun

Use a stable run name:

```bash
docker run --rm --network host \
  -v /mnt/shared/logs/benchmarks/bench-pipeline/history:/results \
  -v /mnt/shared/plans/shoulders/benchmarking:/benchmark-scripts:ro \
  bench-pipeline \
  --model Qwen2.5-Coder-7B-Instruct-Q4_K_M.gguf \
  --runtime-base http://localhost:11437 \
  --run-name pipeline_worker_v1
```
