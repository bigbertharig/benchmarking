# Sequenced Test Suites

This document covers the new "run several benchmark suites back to back on one worker"
flow.

## Goal

Run a sequence like:

- load model `X` on `gpu-3`
- run `bench-reasoning`
- run `bench-code`
- run `bench-pipeline`

without manually babysitting the worker between suites.

## Why This Is Separate From Normal Plans

These benchmark suites still run as Docker jobs outside the orchestrator task queue.
They are not normal plan tasks. The correct control layer is a benchmark campaign
runner, not a regular plan repo batch.

Current entrypoint:

```bash
python3 /mnt/shared/plans/shoulders/benchmarking/run_benchmark_campaign.py \
  /mnt/shared/plans/shoulders/benchmarking/campaigns/gpu3_worker_full_example.json
```

Example manifests:

- [gpu3_worker_full_example.json](/home/bryan/llm_orchestration/shared/plans/shoulders/benchmarking/campaigns/gpu3_worker_full_example.json) (worker-tier, 7B on 1060)
- [gpu0_brain_qwen25coder32b.json](/home/bryan/llm_orchestration/shared/plans/shoulders/benchmarking/campaigns/gpu0_brain_qwen25coder32b.json) (brain-tier, 32B on 3090)

Brain-tier campaigns use a separate config:

```bash
python3 /mnt/shared/plans/shoulders/benchmarking/run_benchmark_campaign.py \
  /mnt/shared/plans/shoulders/benchmarking/campaigns/gpu0_brain_qwen25coder32b.json \
  --config config.benchmark-brain.json \
  --run-id full_v1
```

## Safety Model

There are two checkpoint layers:

1. Campaign-level checkpoint
2. Suite-level checkpoint

Campaign-level:
- state lives under `/mnt/shared/logs/benchmarks/campaigns/history/<campaign>/<run_id>/status.json`
- each suite step is marked `pending`, `running`, `completed`, or `failed`
- rerunning the same campaign with the same `run_id` skips completed suites

Suite-level:
- each suite still uses its own existing `--run-name` checkpointing
- if the process dies in the middle of a suite, rerunning the campaign reuses the same
  suite `run-name`
- the suite resumes from its own checkpoint instead of starting from zero

## Runtime Validation Between Suites

The campaign runner checks the llama port directly between suites instead of assuming
the runtime stayed loaded.

That check validates:
- the worker port still answers `/v1/models`
- the requested model is still present
- the worker heartbeat still reports a healthy loaded runtime

If drift is detected, the runner can:
- targeted-unload the worker
- targeted-load the requested model again
- then continue to the next suite

This is better than blindly chaining suites because:
- an OOM or runtime crash in one suite can silently leave the next suite benchmarking
  the wrong state
- benchmark results are only meaningful if the expected runtime is still actually there

## Reservation Model

The campaign runner does not rely on each suite to reserve independently.

Instead:
- the runner repairs or verifies the worker runtime
- then reserves the worker for benchmarking
- then launches the worker-backed suite with `BENCHMARK_DISABLE_AUTO_RESERVE=1`
- the reservation stays owned by the campaign, not by the individual suite

That avoids a gap where one suite finishes, releases the lock, and a plan grabs the GPU
before the next suite starts.

## Failure Policy

Default policy should stay conservative:
- `stop_on_failure: true`

Reason:
- a suite failure often means the runtime is now suspect
- continuing automatically after a hard failure can produce junk comparisons

What usually is safe to continue after:
- ordinary benchmark assertion failure inside a suite
- non-zero suite exit where the runtime still passes the next direct port check

What is not automatically trustworthy:
- OOM / container killed (`137`)
- runtime port no longer answering
- wrong model loaded after a suite
- unhealthy worker heartbeat

The runner can recover some of those by reloading the target model between suites, but
the default stance should still be fail loud.

## Scope Of Current Runtime Checks

Implemented now:
- direct runtime check between suites
- targeted reload before the next suite when drift is detected

Not implemented now:
- direct runtime check between every individual test inside a suite

Why not inside each suite:
- it adds a lot of control complexity inside already-checkpointed suite runners
- the biggest operational boundary is between suites, where the next harness starts
  with fresh assumptions

If needed later, per-test checks belong in the suite runners themselves, not the
campaign wrapper.

## Default Suite Sequence

Default campaigns run 3 suites: **pipeline → code → reasoning**.

`bench-knowledge` is excluded from default campaigns. The orchestrator needs models
to follow instructions and use provided context, not recall training data. Knowledge
benchmarks (MMLU, ARC, etc.) measure the wrong thing for our use case, and the
runtime cost is prohibitive (4-8 hours per model at limit 5 on loglikelihood tasks).

See MODEL_LIBRARY.md "Suite Selection Rationale" for the full reasoning.

## Knowledge Step Transition (Optional)

`bench-knowledge` runs its own internal llama-server, so it needs the GPU to itself.
When a campaign includes knowledge alongside worker-backed suites, **always put
knowledge last** to avoid unnecessary load/unload cycles.

The campaign runner handles this automatically:
- when it reaches a `bench-knowledge` step, it stops the worker runtime container
  to free GPU memory
- then launches the knowledge container with `--gpus "device=X"`
- the knowledge container starts its own llama-server internally

Required manifest fields for a knowledge step:
- `gguf_path`: path to the GGUF file inside the container's model mount
- `gpu_device`: GPU device index (e.g. `"0"`)
- `model_name`: display name for results

Use knowledge only for ad-hoc sanity checks on new model families, not as part of
the standard evaluation flow.

## Heartbeat Management Without Orchestrator

When benchmarks run without the orchestrator, GPU heartbeats go stale (the orchestrator's
GPU agents normally keep them fresh every 30 seconds). The dashboard uses a 120-second
staleness threshold, so GPUs disappear within 2 minutes of the orchestrator stopping.

Solution: `benchmark_heartbeat_keeper.py` (`shared/scripts/benchmarks/` in the orchestration repo).

```bash
python3 /mnt/shared/scripts/benchmarks/benchmark_heartbeat_keeper.py --interval 30
```

What it does:
- Queries `nvidia-smi` for live thermal, VRAM, power, and clock data per GPU
- Discovers running benchmark containers via `docker ps`
- Maps bench containers to GPUs by tracing `--runtime-base` ports back to llama-server
  containers and their `NVIDIA_VISIBLE_DEVICES`
- Extracts progress info from container logs (percentage, current/total items)
- Writes enriched heartbeats with `heartbeat_owner: "benchmark"` field

Conflict avoidance with orchestrator:
- Before writing, checks `pgrep -f gpu.py.*gpu-N` — if the GPU agent process is alive,
  the keeper backs off for that GPU
- Sets `heartbeat_owner: "benchmark"` so the orchestrator can detect benchmark-managed
  heartbeats on startup
- Auto-exits after 3 consecutive idle cycles (no benchmark containers running) and clears
  the `heartbeat_owner` field

Split-load support:
- Correctly maps split-load containers (e.g., `NVIDIA_VISIBLE_DEVICES=1,3`) to both GPUs
- Shows the same benchmark task on both GPUs in a split pair

The campaign runner should start the keeper automatically. For manual benchmarks, start
it in the background before launching containers.

## Current Limitations

- worker-backed sequencing is the main supported path (`bench-reasoning`,
  `bench-code`, `bench-pipeline`)
- `bench-knowledge` is supported when placed last in the sequence and its step
  explicitly provides `gguf_path` and `gpu_device`
- the worker reservation blocks normal queued work, so the runner must repair/load
  before re-establishing the reservation

## First Live Test (2026-03-14)

First end-to-end sequenced campaign completed successfully on GPU 0 (RTX 3090).

Campaign: `gpu0_brain_qwen25coder32b_smoke` / run_id `smoke_v1`
Model: `qwen2.5-coder:32b` (Qwen2.5-Coder-32B-Instruct-Q4_K_M.gguf)
Config: `config.benchmark-brain.json`

Sequence executed:
1. bench-pipeline (3 tests) — completed, exit 0
2. bench-code (humaneval) — completed, exit 0
3. bench-reasoning (gsm8k + bbh, limit 5) — completed, exit 0

Total wall time: ~25 minutes for all 3 suites.

What was validated:
- full worker-backed sequence across 3 suites on one GPU
- runtime attestation between suites (heartbeat + port probe)
- campaign-level status.json tracking (pending → running → completed per step)
- suite-level checkpointing (each suite wrote its own run artifacts)
- reservation helper integration (reserve/release around suite steps)
- zero interference with concurrent bench-knowledge tests on other GPUs (2, 5)

Results: `/mnt/shared/logs/benchmarks/campaigns/history/gpu0_brain_qwen25coder32b_smoke/smoke_v1/`

## Split-Load Testing (2026-03-14)

14B models tested as split-load across GPU pairs (2x GTX 1060 6GB each).

Docker launch pattern for split-load:
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

Key flags: `--runtime=nvidia -e NVIDIA_VISIBLE_DEVICES=1,3` (not `--gpus` which
rejects multiple device IDs), `--split-mode layer`, `--tensor-split 1,1`.

Memory split for 14B Q4_K_M (~8.4GB): ~3.9GB CUDA0 + ~4.2GB CUDA1 + ~418MB CPU.

Validated:
- qwen2.5-coder:14b on GPUs 1+3 (port 11437)
- deepseek-r1:14b on GPUs 4+5 (port 11438)
- Both ran pipeline smoke tests concurrently with no interference
- Inference works (~131 tok/s prompt, ~19 tok/s generation on split 1060s)

## Still Needs Live Testing

Not yet validated live:
- recovery after a suite-level runtime crash or container exit `137`
- resume behavior after interrupting and rerunning the same campaign `run_id`
- interaction with a real concurrent plan submission while the campaign lock is held

Current confidence level:
- first successful end-to-end run completed
- campaign-level and suite-level checkpointing both work
- between-suite runtime attestation works
- reservation integration works

## Recommended Operator Workflow

1. Prepare a campaign manifest.
2. Use a stable `run_id` if you want resumability across reruns.
3. Keep `stop_on_failure: true` unless you explicitly want best-effort continuation.
4. Review the campaign log and per-suite logs under the campaign history dir.
