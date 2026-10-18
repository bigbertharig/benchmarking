#!/usr/bin/env bash
# Work through a queue of single-GPU models on several GTX 1060s under one thermal guard.
# Each card takes the next model as soon as it finishes the last one.
# usage: run_worker_lanes.sh <gpu-list> <model-id> [model-id ...]
# Example: run_worker_lanes.sh 1,2,3,4 qwen2.5-coder:7b ministral-3:8b gemma-4:e4b minicpm5:2b
# Queue order is pick-up order: put the slowest models first. A SIGTERM (thermal guard or operator)
# stops every lane and its container.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TREE="$(cd "$HERE/../../../../.." && pwd)"
GPUS=$1; shift
TS=$(date +%Y%m%d_%H%M%S)
LOGDIR=/mnt/shared/logs/benchmarks/worker_lanes_$TS
mkdir -p "$LOGDIR"
QUEUE="$LOGDIR/queue.txt"
printf '%s\n' "$@" > "$QUEUE"
IFS=',' read -r -a gpus <<< "$GPUS"
pids=()
stop_all() {
  echo "$(date +%T) stopping all lanes"
  : > "$QUEUE"
  for p in "${pids[@]}"; do pkill -TERM -P "$p" 2>/dev/null; kill "$p" 2>/dev/null; done
  for g in "${gpus[@]}"; do docker rm -f "llama-lane-gpu$g" >/dev/null 2>&1; done
  exit 1
}
trap stop_all TERM INT
for gpu in "${gpus[@]}"; do
  "$HERE/worker_lane.sh" "$gpu" "$QUEUE" > "$LOGDIR/lane_gpu$gpu.log" 2>&1 &
  pids+=($!)
  echo "$(date +%T) lane gpu$gpu pid $!"
  sleep 5   # stagger start-up; loads are serialized by run_runtime.sh anyway
done
python3 -u "$TREE/scripts/startup_thermal_monitor.py" --output "$LOGDIR/thermal.csv" --duration 86400 \
  --interval 2 --abort-cpu-c 95 --abort-pid $$ --fast-gpu-ms 500 > /dev/null 2>&1 &
monitor=$!
echo "queue: $# models -> $QUEUE; logs: $LOGDIR; monitor pid $monitor"
wait "${pids[@]}"
kill "$monitor" 2>/dev/null
echo "$(date +%T) ALL_LANES_DONE"
