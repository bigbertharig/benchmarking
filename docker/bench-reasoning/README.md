# bench-reasoning

Runs lm-eval reasoning-focused tasks against a live llama-compatible worker
endpoint (`/v1/chat/completions`).

## Entrypoint Args

- `--model` required model id (example: `Qwen2.5-Coder-7B-Instruct-Q4_K_M.gguf`)
- `--runtime-base` worker base URL (default: `http://localhost:11436`)
- `--tasks` comma-separated lm-eval task names
- `--limit` sample limit per task
- `--results-dir` output root (default: `/results`)
- `--num-fewshot` optional few-shot override
- `--tokenizer` reserved for future use
- `--run-name` stable run id for task-level checkpoint/resume
- `--scripts-dir` benchmark root mount inside container (default: `/benchmark-scripts`)
- `--use-model-prompts` / `--no-model-prompts` toggle per-model prompt resolution
- `--prompt-profiles` model prompt profile path
- `--tuning-profiles` model tuning profile path
- `--require-model-prompt` fail if model-specific prompt is missing
- `--allow-generic-prompt-fallback` allow fallback to profile default prompt

## Example

```bash
docker run --rm --network host \
  -v /mnt/shared/logs/benchmarks/bench-reasoning/history:/results \
  -v /mnt/shared/plans/shoulders/benchmarking:/benchmark-scripts:ro \
  bench-reasoning \
  --model Qwen2.5-Coder-7B-Instruct-Q4_K_M.gguf \
  --runtime-base http://localhost:11437 \
  --tasks gsm8k,bbh,drop \
  --limit 50 \
  --run-name reasoning_full_v1
```

## Trimmed Suite

Frozen config:
- `/media/bryan/shared/plans/shoulders/benchmarking/suites/reasoning_lite_v1.json`

Command:

```bash
docker run --rm --network host \
  -v /mnt/shared/logs/benchmarks/bench-reasoning/history:/results \
  -v /mnt/shared/plans/shoulders/benchmarking:/benchmark-scripts:ro \
  bench-reasoning \
  --model Qwen2.5-Coder-7B-Instruct-Q4_K_M.gguf \
  --runtime-base http://localhost:11437 \
  --tasks gsm8k,bbh,drop,math_500,aime_2024 \
  --limit 10
```

## Test Volume And Limits

- Public-size quick view (approximate; can shift by lm-eval version):
  - `bbh` group:
    - **27 subtasks**
    - most subtasks are ~250 items each
    - total BBH group is roughly **~6.5k** items
  - `gsm8k`: about **1,319** items
  - `drop`: about **9,500+** items
  - core long-run set (`bbh + gsm8k + drop`): roughly **~17k** items total
- Limit behavior:
  - this suite supports per-task `--limit L`
  - effective max `L` is each task's dataset size; setting larger than dataset size acts like full dataset
  - practical cap formula for core set with limits: up to `29 * L` scored prompts (`27` BBH subtasks + `gsm8k` + `drop`)
  - example: `L=150` => around `~4.3k` prompts total
- Trimmed suite:
  - `reasoning_lite_v1` is fixed to **50** total (`5 tasks x limit 10`)
- All-or-nothing:
  - **No**. Partial/limited runs are valid and scored.

## Output

- Result folder:
  `/results/bench-reasoning_<model_safe>_<timestamp>/`
- lm-eval JSON output files inside that folder.
- Checkpoint file (when `--run-name` is set):
  `/results/bench-reasoning_<model_safe>_<run_name>/status.json`

## Resumable Runs

`bench-reasoning` now checkpoints at task boundaries.

- completed tasks are skipped on rerun
- failed/incomplete tasks are rerun

Use a stable run name:

```bash
docker run --rm --network host \
  -v /mnt/shared/logs/benchmarks/bench-reasoning/history:/results \
  -v /mnt/shared/plans/shoulders/benchmarking:/benchmark-scripts:ro \
  bench-reasoning \
  --model Qwen2.5-Coder-7B-Instruct-Q4_K_M.gguf \
  --runtime-base http://localhost:11437 \
  --tasks gsm8k,bbh,drop \
  --limit 150 \
  --run-name reasoning_full_v1
```

## Prompt Methodology

This suite uses lm-eval's chat-completions interface with `--apply_chat_template`.
Model prompts are now resolved per model from benchmark profiles and passed via
`--system_instruction`.

Resolution order:
1. `custom_tasks/model_prompt_profiles.json` model-level `system_prompt`
2. `model_tuning_profiles.json` model-level `system_prompt`
3. Optional generic fallback only when `--allow-generic-prompt-fallback` is set

Default behavior enforces model-specific prompts (`--require-model-prompt`).

Every result should be traceable: what model, what prompt (if any), what score.
Historical runs are archived in per-run result directories under
`/media/bryan/shared/logs/benchmarks/bench-reasoning_*/`.

## Run History

All historical results for this suite live in:
- [BENCH_REASONING_HISTORY.md](BENCH_REASONING_HISTORY.md)

Each entry records: model, tasks, scores, timestamp, and run path.
The main MODEL_LIBRARY.md holds only the latest scores.

## Common Issues

- Runtime not reachable:
  - missing `--network host`
  - wrong worker port
- `No model-specific system prompt found for ...`:
  - add `system_prompt` for that model in `custom_tasks/model_prompt_profiles.json` or `model_tuning_profiles.json`
  - or run with `--allow-generic-prompt-fallback`
- Task not available in current lm-eval install:
  - verify task name with `python3 -m lm_eval --tasks list`
- `Unknown arg: ...` for a documented flag:
  - stale Docker image; rebuild `bench-reasoning` before rerunning
