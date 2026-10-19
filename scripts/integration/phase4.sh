#!/usr/bin/env bash
# NEW_MODEL_INTEGRATION Phase 4 smoke on the runtime at :PORT: pipeline (fixed set, small), code smoke
# (HumanEval only; the full HumanEval + MBPP run is Phase 5, with the chosen settings), reasoning limit 10. usage: phase4.sh <model-id> <run-tag> [port] [extra reasoning flags...]
set -uo pipefail
model=$1; tag=$2; port=${3:-11434}; shift 3 2>/dev/null || shift $#
L=/mnt/shared/logs/benchmarks/phase4_${tag}
alive() {  # on a dead runtime, say why (exit code, OOM, rig guard action, earlyoom) before giving up
  curl -sf "http://127.0.0.1:$port/v1/models" >/dev/null && return 0
  echo "RUNTIME DOWN before $1"
  rig why --port "$port" 2>&1 | sed 's/^/  /'
  exit 3
}
common=(--rm --network host -e BENCHMARK_DISABLE_AUTO_RESERVE=1 -v /mnt/shared:/mnt/shared
        -v /run/lock:/host-lock -e BENCH_EVAL_LOCK=/host-lock/bench-evalplus.lock)  # one EvalPlus scoring at a time
alive pipeline
docker run "${common[@]}" -v /mnt/shared/logs/benchmarks/bench-pipeline/history:/results \
  -v /mnt/shared/plans/shoulders/benchmarking:/benchmark-scripts:ro \
  bench-pipeline --model "$model" --runtime-base "http://localhost:$port" --run-name "${tag}" --run-class smoke \
  > "${L}_pipeline.log" 2>&1; echo "pipeline exit=$?"
alive code
docker run "${common[@]}" -v /mnt/shared/logs/benchmarks/bench-code/history:/results \
  bench-code --model "$model" --runtime-base "http://localhost:$port" --run-name "${tag}" --run-class smoke --tasks humaneval \
  > "${L}_code.log" 2>&1; echo "code exit=$?"
alive reasoning
docker run "${common[@]}" -v /mnt/shared/logs/benchmarks/bench-reasoning/history:/results \
  -v /mnt/shared/plans/shoulders/benchmarking:/benchmark-scripts:ro \
  bench-reasoning --model "$model" --runtime-base "http://localhost:$port" --run-name "${tag}" --run-class smoke \
  --limit 10 --log-samples "$@" > "${L}_reasoning.log" 2>&1; echo "reasoning exit=$?"
echo PHASE4_DONE
