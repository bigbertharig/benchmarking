# Sequenced Test Suites

This document describes the corrected operator path for running several
benchmark suites back to back on the same loaded runtime.

The working method is manual suite sequencing against a verified live port.
Do not use a campaign wrapper as the primary operator path for worker
benchmarks.

## Correct Sequencing Model

The sequence is:

1. load the target model runtime
2. verify the runtime answers `/v1/models` with the expected model
3. run one suite directly with `docker run --rm ... bench-*`
4. when it finishes, run the next suite against the same port
5. if the runtime disappears, stop and repair the runtime before launching the next suite

This keeps each suite independent and matches the successful 12B/14B runs from
2026-03-14 through 2026-03-16.

## Why This Is The Canonical Path

This is the pattern that already worked in live runs:

- 14B split pipeline smoke runs on ports `11437` and `11438`
- 14B split code smoke runs on those same ports
- 14B split reasoning smoke runs on those same ports
- 12B single-worker pipeline/reasoning/code smoke runs on `11435`

The historical artifacts for those runs are in:

- `/media/bryan/shared/logs/benchmarks/bench-pipeline/history`
- `/media/bryan/shared/logs/benchmarks/bench-code/history`
- `/media/bryan/shared/logs/benchmarks/bench-reasoning/history`

Examples that completed cleanly:

- `bench-pipeline_qwen2.5-coder_14b_pipeline_coder14b_split_smoke_v1`
- `bench-code_qwen2.5-coder_14b_code_coder14b_split_smoke_v1`
- `bench-reasoning_qwen2.5-coder_14b_reasoning_coder14b_split_smoke_v1`
- `bench-pipeline_gemma-3_12b_pipeline_gemma3_smoke_v1`
- `bench-code_phi-4_14b_code_phi4_smoke_v1`

## Operator Rules

- Load models one at a time.
- Verify `/v1/models` before every suite launch.
- Treat each suite as its own Docker job.
- Reuse the same `--run-name` only when intentionally resuming that same suite.
- Do not assume the runtime stayed healthy between suites; check it directly.
- If `bench-code` loses the runtime and starts reconnecting forever, stop the container and repair the runtime before retrying.

## Standard Sequence

Default order:

1. `bench-pipeline`
2. `bench-code`
3. `bench-reasoning`

Reason:

- `bench-pipeline` is the fastest way to catch broken formatting, JSON, and instruction-following failures
- `bench-code` is expensive and should only run after the runtime has already passed basic reliability checks
- `bench-reasoning` is long-running and should be launched only after the runtime path is proven stable

`bench-knowledge` is separate and should not be part of the default worker sequence.

`bench-daedalmap` is also separate from the default worker sequence. It is a custom
chat-routing suite, not a replacement for `bench-pipeline` / `bench-code` / `bench-reasoning`.
Use it when you want to evaluate DaedalMap-specific instruction following and bucket-backed
source availability on the same loaded runtime.

## Runtime Verification

Before each suite:

```bash
curl -s http://localhost:11437/v1/models
```

Confirm:

- the port responds
- the expected model is listed

If the response is wrong or empty, fix the runtime first. Do not launch the next suite.

## 7B Single-Worker Sequence

Example: GPU 2, port `11436`

Pipeline:

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

Code:

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

Reasoning:

```bash
docker run --rm --network host \
  -v /mnt/shared:/mnt/shared \
  -v /mnt/shared/logs/benchmarks/bench-reasoning/history:/results \
  -v /mnt/shared/plans/shoulders/benchmarking:/benchmark-scripts:ro \
  bench-reasoning \
  --model qwen2.5-coder:7b \
  --runtime-base http://localhost:11436 \
  --tasks gsm8k,bbh,drop \
  --limit 50 \
  --run-name reasoning_coder7b_l50_v1
```

DaedalMap smoke:

```bash
docker run --rm --network host \
  --env-file /mnt/shared/plans/shoulders/benchmarking/docker/bench-daedalmap/.env \
  -e BENCHMARK_DISABLE_AUTO_RESERVE=1 \
  -v /mnt/shared:/mnt/shared \
  -v /mnt/shared/logs/benchmarks/bench-daedalmap/history:/results \
  -v /mnt/shared/plans/shoulders/benchmarking:/benchmark-scripts:ro \
  bench-daedalmap \
  --model qwen2.5-coder:7b \
  --runtime-base http://localhost:11436 \
  --tasks json_discipline,source_grounding \
  --limit 5 \
  --run-name daedalmap_smoke_coder7b_v1
```

DaedalMap bucket-backed smoke:

```bash
docker run --rm --network host \
  --env-file /mnt/shared/plans/shoulders/benchmarking/docker/bench-daedalmap/.env \
  -e BENCHMARK_DISABLE_AUTO_RESERVE=1 \
  -v /mnt/shared:/mnt/shared \
  -v /mnt/shared/logs/benchmarks/bench-daedalmap/history:/results \
  -v /mnt/shared/plans/shoulders/benchmarking:/benchmark-scripts:ro \
  bench-daedalmap \
  --model qwen2.5-coder:7b \
  --runtime-base http://localhost:11436 \
  --tasks geographic_precision,multi_source \
  --limit 1 \
  --execute \
  --run-name daedalmap_bucket_smoke_coder7b_v1
```

## 14B Split-Worker Sequence

For 14B models on 2x 1060, first launch the split runtime, then run suites
directly against the split port.

Example runtime launch for GPUs `1+3`, port `11437`:

```bash
docker run -d --name llama-split-13 \
  --runtime=nvidia -e NVIDIA_VISIBLE_DEVICES=1,3 \
  -p 11437:8000 \
  -v /mnt/shared/models:/models:ro \
  llama-runtime:sm61-sm86 \
  --model /models/qwen2.5-coder-14b/Qwen2.5-Coder-14B-Instruct-Q4_K_M.gguf \
  --n-gpu-layers 999 --split-mode layer --tensor-split 1,1 \
  --ctx-size 8192 --host 0.0.0.0 --port 8000
```

Key flags:

- `--runtime=nvidia -e NVIDIA_VISIBLE_DEVICES=1,3`
- `--split-mode layer`
- `--tensor-split 1,1`

Then verify:

```bash
curl -s http://localhost:11437/v1/models
```

Then run suites one at a time.

Pipeline:

```bash
docker run --rm --network host \
  -e BENCHMARK_DISABLE_AUTO_RESERVE=1 \
  -v /mnt/shared:/mnt/shared \
  -v /mnt/shared/logs/benchmarks/bench-pipeline/history:/results \
  -v /mnt/shared/plans/shoulders/benchmarking:/benchmark-scripts:ro \
  bench-pipeline \
  --model qwen2.5-coder:14b \
  --runtime-base http://localhost:11437 \
  --run-name pipeline_coder14b_split_smoke_v1
```

Code:

```bash
docker run --rm --network host \
  -v /mnt/shared:/mnt/shared \
  -v /mnt/shared/logs/benchmarks/bench-code/history:/results \
  bench-code \
  --model qwen2.5-coder:14b \
  --runtime-base http://localhost:11437 \
  --tasks humaneval,mbpp \
  --run-name code_coder14b_split_smoke_v1
```

Reasoning:

```bash
docker run --rm --network host \
  -v /mnt/shared:/mnt/shared \
  -v /mnt/shared/logs/benchmarks/bench-reasoning/history:/results \
  -v /mnt/shared/plans/shoulders/benchmarking:/benchmark-scripts:ro \
  bench-reasoning \
  --model qwen2.5-coder:14b \
  --runtime-base http://localhost:11437 \
  --tasks gsm8k,bbh,drop \
  --limit 5 \
  --run-name reasoning_coder14b_split_smoke_v1
```

Use the same pattern for the `4+5` split pair on port `11438`.

## 12B Single-Worker Sequence

The 12B Gemma smoke runs that completed successfully used the same direct
per-suite method on a single worker port.

Example port:

- `gemma-3:12b` on `http://localhost:11435`

Run the three suite commands above with the correct model id and port.

## Failure Handling

If a suite fails:

1. stop that suite container
2. verify the runtime still answers `/v1/models`
3. if the runtime is gone, reload it
4. rerun only that suite with the same `--run-name` if resume is desired
5. do not launch later suites until the current suite is either completed or explicitly abandoned

## What To Avoid

Do not treat worker benchmark sequencing as a separate campaign/orchestration layer.

The stable path is:

- manual runtime preparation
- direct suite execution
- direct runtime verification between suites

That is the path to use until a different method proves itself with repeated
clean runs on worker hardware.
