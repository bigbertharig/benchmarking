#!/bin/bash
# Run the custom benchmark tests on two rigs at once from the Pi and monitor both GPUs.
# Usage: dual_rig_bench.sh   (rig GPU 1 on :11435, desktop 1070 on :11450 through the tunnel)
# Pre multi-rig: the desktop runtime and the Pi tunnel are started by hand (docs/DESIGN_NOTES.md).
BENCH=/media/bryan/shared/plans/shoulders/benchmarking
# Model: the benchmarking role single_1060 unless MODEL is set (tools/role_model.py).
MODEL="${MODEL:-$(python3 "$(dirname "$0")/role_model.py")}"
OUT=~/rig_stress/dual_bench_$(date +%Y%m%d_%H%M%S)
TESTS="custom_json_schema_strict custom_tool_plan_sequence custom_ambiguity_handling custom_command_safety custom_orchestration_tradeoff custom_long_context_extract"
mkdir -p "$OUT/rig" "$OUT/desktop"
echo "out $OUT model $MODEL"

run_lane() {  # name port
  local name=$1 port=$2
  for t in $TESTS; do
    local s=$(date +%s)
    python3 "$BENCH/run_local_custom_task.py" --id "$t" --model "$MODEL" \
      --base-url "http://127.0.0.1:$port" --no-record --output-dir "$OUT/$name" \
      > "$OUT/$name/$t.log" 2>&1
    echo "$(date +%T) $name $t exit $? in $(( $(date +%s) - s ))s" | tee -a "$OUT/progress.log"
  done
  echo "$(date +%T) $name DONE" | tee -a "$OUT/progress.log"
}

monitor() {
  echo "time,rig_util,rig_mem_mib,rig_w,rig_c,desk_util,desk_mem_mib,desk_w,desk_c" > "$OUT/gpus.csv"
  while [ ! -f "$OUT/.stop" ]; do
    r=$(ssh -o BatchMode=yes -o ConnectTimeout=5 bryan@10.0.0.3 \
      "nvidia-smi -i 1 --query-gpu=utilization.gpu,memory.used,power.draw,temperature.gpu --format=csv,noheader,nounits" 2>/dev/null | tr -d " ")
    d=$(ssh -o BatchMode=yes -o ConnectTimeout=5 desktop-rig \
      "nvidia-smi --query-gpu=utilization.gpu,memory.used,power.draw,temperature.gpu --format=csv,noheader,nounits" 2>/dev/null | grep -v systemd | tr -d " ")
    echo "$(date +%T),${r:-unreachable},${d:-unreachable}" >> "$OUT/gpus.csv"
    sleep 10
  done
}

monitor & MON=$!
run_lane rig 11435 & A=$!
run_lane desktop 11450 & B=$!
wait $A $B
touch "$OUT/.stop"; wait $MON
echo "ALL DONE $OUT"
