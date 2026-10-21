#!/usr/bin/env bash
# Work through a queue of models on several lanes under one thermal guard. A lane is one card or a
# group of cards joined with + (one model split across them); the harness checks each model fits its
# lane and picks the context and split (worker_lane.sh). Each lane takes the next model as soon as it
# finishes the last one; a model that does not fit a lane is skipped there.
# usage: run_worker_lanes.sh <lane-list> <model-id> [model-id ...]
# Examples: run_worker_lanes.sh 1,2,3,4 qwen2.5-coder:7b ministral-3:8b gemma-4:e4b minicpm5:2b
#           run_worker_lanes.sh 1+3,4+5 mellum2.1:12b-a2.5b ornith-1.5:9b
# Run it detached as the bryan user: lanes reach the rig manager through bryan's ssh alias for the Pi,
# which root does not have (as root every lane is refused). For example:
#   sudo systemd-run --unit=bench-lanes-NAME -p User=bryan -p WorkingDirectory=/home/bryan \
#        [--setenv=LANE_STOP_AFTER=4 --setenv=LANE_RUN_SUFFIX=_r2] /bin/bash $0 4+5 gemma-4:12b
# Queue order is pick-up order: put the slowest models first. A SIGTERM (thermal guard or operator)
# stops every lane and its container.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TREE="$(cd "$HERE/../../../../.." && pwd)"
GPUS=$1; shift
TS=$(date +%Y%m%d_%H%M%S)
LOGDIR=/mnt/shared/logs/benchmarks/worker_lanes_$TS
# Two runs started in the same second must not share a queue: the later one takes the next free second.
while ! mkdir "$LOGDIR" 2>/dev/null; do
  sleep 1; TS=$(date +%Y%m%d_%H%M%S); LOGDIR=/mnt/shared/logs/benchmarks/worker_lanes_$TS
done
QUEUE="$LOGDIR/queue.txt"
printf '%s\n' "$@" > "$QUEUE"
IFS=',' read -r -a gpus <<< "$GPUS"
pids=()
stop_all() {
  echo "$(date +%T) stopping all lanes"
  : > "$QUEUE"
  for p in "${pids[@]}"; do pkill -TERM -P "$p" 2>/dev/null; kill "$p" 2>/dev/null; done
  # each lane unloads its model and releases its claim on TERM (worker_lane.sh finish)
  exit 1
}
trap stop_all TERM INT
for gpu in "${gpus[@]}"; do
  "$HERE/worker_lane.sh" "$gpu" "$QUEUE" > "$LOGDIR/lane_gpu${gpu//+/-}.log" 2>&1 &
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
