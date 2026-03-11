# bench-knowledge

Runs lm-eval knowledge/loglikelihood-heavy tasks using a GGUF model served by
`llama_cpp.server` inside the container.

## Entrypoint

Positional argument:
- `<path-to-gguf>` (required)

Optional args:
- `--tasks` comma-separated lm-eval task names
- `--limit` sample limit per task
- `--results-dir` output root (default: `/results`)
- `--model-name` override model label in output path
- `--run-name` stable run id for task-level checkpoint/resume
- `--scripts-dir` benchmark root mount inside container (default: `/benchmark-scripts`)
- `--use-model-prompts` / `--no-model-prompts` toggle per-model prompt resolution
- `--prompt-profiles` model prompt profile path
- `--tuning-profiles` model tuning profile path
- `--require-model-prompt` fail if model-specific prompt is missing
- `--allow-generic-prompt-fallback` allow fallback to profile default prompt

## Example

```bash
docker run --rm --gpus '"device=1"' \
  -v /mnt/shared/models:/models:ro \
  -v /mnt/shared/logs/benchmarks/bench-knowledge/history:/results \
  -v /mnt/shared/plans/shoulders/benchmarking:/benchmark-scripts:ro \
  bench-knowledge \
  /models/qwen2.5-coder-7b/Qwen2.5-Coder-7B-Instruct-Q4_K_M.gguf \
  --tasks mmlu,arc_challenge,hellaswag,boolq \
  --limit 50 \
  --run-name knowledge_full_v1
```

## Trimmed Suite

Frozen config:
- `/media/bryan/shared/plans/shoulders/benchmarking/suites/knowledge_lite_v1.json`

Command:

```bash
docker run --rm --gpus '"device=1"' \
  -v /mnt/shared/models:/models:ro \
  -v /mnt/shared/logs/benchmarks/bench-knowledge/history:/results \
  -v /mnt/shared/plans/shoulders/benchmarking:/benchmark-scripts:ro \
  bench-knowledge \
  /models/<model-folder>/<model-file>.gguf \
  --tasks mmlu,arc_challenge,hellaswag,truthfulqa_mc2,boolq \
  --limit 10
```

## Test Volume And Limits

- Public-size quick view (approximate; can shift by lm-eval version):
  - `mmlu`: ~14k
  - `arc_challenge`: ~1.1k
  - `hellaswag`: ~10k
  - `truthfulqa_mc2`: ~800
  - `boolq`: ~3.3k
  - default full set total: roughly **~29k** items
- Limit behavior:
  - this suite supports per-task `--limit L`
  - effective max `L` is each task's dataset size; setting larger than dataset size acts like full dataset
  - cap formula with default 5 tasks: up to `5 * L` scored prompts
  - examples:
    - `L=10` => up to **50** total
    - `L=150` => up to **750** total
- All-or-nothing:
  - **No**. Partial/limited runs are valid and scored.

## Output

- Result folder:
  `/results/bench-knowledge_<model_name>_<timestamp>/`
- lm-eval JSON output files inside that folder.
- Checkpoint file (when `--run-name` is set):
  `/results/bench-knowledge_<model_safe>_<run_name>/status.json`

## Resumable Runs

`bench-knowledge` now checkpoints at task boundaries.

- completed tasks are skipped on rerun
- failed/incomplete tasks are rerun

Use a stable run name:

```bash
docker run --rm --gpus '"device=1"' \
  -v /mnt/shared/models:/models:ro \
  -v /mnt/shared/logs/benchmarks/bench-knowledge/history:/results \
  -v /mnt/shared/plans/shoulders/benchmarking:/benchmark-scripts:ro \
  bench-knowledge \
  /models/qwen2.5-coder-7b/Qwen2.5-Coder-7B-Instruct-Q4_K_M.gguf \
  --tasks mmlu,arc_challenge,hellaswag,truthfulqa_mc2,boolq \
  --limit 150 \
  --run-name knowledge_full_v1
```

## Prompt Methodology

This suite runs MC/loglikelihood-heavy tasks via llama.cpp's endpoint inside the
container. The runner now supports per-model system prompts through lm-eval
`--system_instruction`.

Resolution order:
1. `custom_tasks/model_prompt_profiles.json` model-level `system_prompt`
2. `model_tuning_profiles.json` model-level `system_prompt`
3. Optional generic fallback only when `--allow-generic-prompt-fallback` is set

Default behavior enforces model-specific prompts (`--require-model-prompt`).

Historical runs are archived in per-run result directories under
`/media/bryan/shared/logs/benchmarks/bench-knowledge_*/`.

## Run History

All historical results for this suite live in:
- [BENCH_KNOWLEDGE_HISTORY.md](BENCH_KNOWLEDGE_HISTORY.md)

Each entry records: model (GGUF file), tasks, scores, timestamp, and run path.
The main MODEL_LIBRARY.md holds only the latest scores.

## Common Issues

- GGUF path not mounted correctly:
  - confirm `/models/...` path and `:ro` mount
- `No model-specific system prompt found for ...`:
  - add `system_prompt` for that model in `custom_tasks/model_prompt_profiles.json` or `model_tuning_profiles.json`
  - or run with `--allow-generic-prompt-fallback`
- Server start failure:
  - verify GPU visibility and free VRAM
- Slow startup:
  - larger GGUFs take longer to map/load before evaluation starts
- `Unknown arg: ...` for a documented flag:
  - stale Docker image; rebuild `bench-knowledge` before rerunning
