# bench-code

Runs EvalPlus code-generation tasks (`humaneval`, `mbpp`) against a live
llama-compatible worker endpoint.

## Quick Start

All commands run on the rig (`ssh 10.0.0.3`). Model must already be loaded on the target port.

**7B on single worker (e.g. GPU 2, port 11436):**
```bash
docker run --rm --network host \
  -v /mnt/shared:/mnt/shared \
  -v /mnt/shared/logs/benchmarks/bench-code/history:/results \
  bench-code \
  --model qwen2.5-coder:7b \
  --runtime-base http://localhost:11436 \
  --tasks humaneval,mbpp \
  --run-name code_coder7b_v1
```

**14B on split pair (e.g. GPUs 4+5, port 11438):**
```bash
docker run --rm --network host \
  -v /mnt/shared:/mnt/shared \
  -v /mnt/shared/logs/benchmarks/bench-code/history:/results \
  bench-code \
  --model qwen2.5-coder:14b \
  --runtime-base http://localhost:11438 \
  --tasks humaneval,mbpp \
  --run-name code_coder14b_v1
```

**32B on brain (GPU 0, port 11434):**
```bash
docker run --rm --network host \
  -v /mnt/shared:/mnt/shared \
  -v /mnt/shared/logs/benchmarks/bench-code/history:/results \
  bench-code \
  --model qwen2.5-coder:32b \
  --runtime-base http://localhost:11434 \
  --tasks humaneval,mbpp \
  --run-name code_coder32b_v1
```

**Run only one dataset** (e.g. just mbpp):
```bash
  --tasks mbpp
```

Runtime: humaneval ~20-40 min, mbpp ~30-90 min (varies by model speed).

## Entrypoint Args

- `--model` required model id
- `--runtime-base` worker base URL (default: `http://localhost:11436`)
- `--tasks` comma-separated EvalPlus datasets (default: `humaneval,mbpp`)
- `--results-dir` output root (default: `/results`)
- `--run-name` stable run id for resumable runs (reuses same output dir)
- `--preflight-only` run reachability/model/timeout checks and exit
- `--request-timeout` seconds for preflight completion probe (default: `30`)

## Example

```bash
docker run --rm --network host \
  -v /mnt/shared/logs/benchmarks/bench-code/history:/results \
  bench-code \
  --model Qwen2.5-Coder-7B-Instruct-Q4_K_M.gguf \
  --runtime-base http://localhost:11437 \
  --tasks humaneval,mbpp
```

## Trimmed Suite Status

Target file:
- `/media/bryan/shared/plans/shoulders/benchmarking/suites/coding_lite_v1.json`

Current blocker:
- EvalPlus evaluate enforces full problem coverage and fails subset scoring
  (`AssertionError: Missing problems in samples`), so trimmed 50-problem coding
  scoring is not yet supported by the active `bench-code` flow.

## Test Volume And Limits

- Datasets in this suite:
  - `humaneval`: **164** problems
  - `mbpp`: **378** problems
  - total full run: **542** problems per model
- Limit behavior:
  - effective scoring is **all-or-nothing per dataset** (EvalPlus evaluate requires full coverage)
  - partial generation can be checkpointed/resumed, but not scored as a final comparable run
  - practical max `L` for comparable scored runs is full dataset size:
    - humaneval: 164
    - mbpp: 378

## Output

- Result folder:
  `/results/bench-code_<model_safe>_<timestamp>/`
- EvalPlus generation files and `*_eval_results.json` files per dataset.
- Per-task checkpoint:
  `/results/bench-code_<model_safe>_<run_name>/<task>/status.json`

## Prompt Methodology

This suite generates code via the chat-completions endpoint and evaluates with EvalPlus.
The prompt is EvalPlus's built-in function-signature prompt, not a custom system prompt.

Current status:
- Per-model prompt profiles are **not** wired into `bench-code` yet.
- This suite currently does not consume `custom_tasks/model_prompt_profiles.json`.
- Use this suite for model-vs-model code benchmark comparisons with fixed EvalPlus prompting.

Every result should be traceable: what model, what configuration, what score.
Historical runs are archived in per-run result directories under
`/media/bryan/shared/logs/benchmarks/bench-code_*/`.

## Run History

All historical results for this suite live in:
- [BENCH_CODE_HISTORY.md](BENCH_CODE_HISTORY.md)

Each entry records: model, tasks, scores, timestamp, and run path.
The main MODEL_LIBRARY.md holds only the latest scores.

## Common Issues

- Runtime not reachable:
  - missing `--network host`
  - wrong port/model not loaded
- Missing sample file after generation:
  - generation step failed for that dataset; inspect container logs
- `Unknown arg: ...` for a documented flag:
  - stale Docker image; rebuild `bench-code` before rerunning

## Resumable Runs

Use a stable run name to resume generation after interruption:

```bash
docker run --rm --network host \
  -v /mnt/shared/logs/benchmarks/bench-code/history:/results \
  bench-code \
  --model Qwen2.5-Coder-7B-Instruct-Q4_K_M.gguf \
  --runtime-base http://localhost:11437 \
  --tasks humaneval,mbpp \
  --run-name coding_full_v1
```

Re-run the same command with the same `--run-name` to continue. EvalPlus
codegen resumes from existing outputs.

Preflight-only check:

```bash
docker run --rm --network host \
  bench-code \
  --model Qwen2.5-Coder-7B-Instruct-Q4_K_M.gguf \
  --runtime-base http://localhost:11437 \
  --preflight-only \
  --request-timeout 30
```
