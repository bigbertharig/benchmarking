#!/usr/bin/env bash
# Phase 4 smoke: bench-reasoning at limit 10 with raw samples, against the runtime on :${PORT:-11434}.
# Env: PORT (default 11434), TASKS (default bbh,drop).
# usage: smoke_reasoning.sh <model-id> <run-name> [extra bench-reasoning flags...]
set -euo pipefail
model=$1; run=$2; shift 2
docker run --rm --network host \
  -e BENCHMARK_DISABLE_AUTO_RESERVE=1 \
  -v /mnt/shared:/mnt/shared \
  -v /mnt/shared/logs/benchmarks/bench-reasoning/history:/results \
  -v /mnt/shared/plans/shoulders/benchmarking:/benchmark-scripts:ro \
  bench-reasoning --model "$model" --runtime-base "http://localhost:${PORT:-11434}" \
  --run-name "$run" --run-class smoke --tasks "${TASKS:-bbh,drop}" --limit 10 --log-samples "$@" \
  > "/mnt/shared/logs/benchmarks/smoke_$run.log" 2>&1
grep -a -E "^\|(bbh|drop|gsm8k) " "/mnt/shared/logs/benchmarks/smoke_$run.log" | head -4
