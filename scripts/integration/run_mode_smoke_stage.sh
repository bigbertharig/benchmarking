#!/usr/bin/env bash
# Reusable smoke stage: wait for an existing Phase 4 run, or load a named mode and run it.
set -euo pipefail

repo=/mnt/shared/plans/shoulders/benchmarking
logs=/mnt/shared/logs/benchmarks
mode_cli=/home/bryan/llm_orchestration/shared/scripts/rig/model_modes.py

check_stages() {
  local wrapper=$1 stage
  for stage in pipeline code reasoning; do
    grep -qx "$stage exit=0" "$wrapper" || {
      echo "missing successful $stage stage in $wrapper" >&2
      return 1
    }
  done
}

case "${1:-}" in
  wait)
    [[ $# -eq 3 ]] || { echo 'usage: wait RUN_TAG WRAPPER' >&2; exit 64; }
    tag=$2
    wrapper=$3
    while ! grep -q '^reasoning exit=' "$wrapper" 2>/dev/null; do
      if ! pgrep -af "phase4.sh .* $tag " | grep -qv 'run_mode_smoke_stage'; then
        echo "Phase 4 for $tag ended without a reasoning receipt" >&2
        exit 1
      fi
      sleep 600
    done
    check_stages "$wrapper"
    ;;
  run)
    [[ $# -ge 5 && $# -le 7 ]] || { echo 'usage: run MODEL MODE PORT TAG [--stop-container NAME | --stop-profile ID]' >&2; exit 64; }
    model=$2 mode=$3 port=$4 tag=$5
    if [[ $# -eq 7 ]]; then
      case "$6" in
        --stop-container) /home/bryan/llm_orchestration/shared/scripts/llama_runtime/stop_runtime.sh "$7" ;;
        --stop-profile) rig stop "$7" ;;
        *) echo "unknown stop option $6" >&2; exit 64 ;;
      esac
    fi
    python3 "$mode_cli" start "$model" "$mode" --port "$port"
    wrapper="$logs/placement_${tag}.log"
    [[ ! -e "$wrapper" ]] || { echo "smoke log already exists: $wrapper" >&2; exit 1; }
    cd "$repo"
    bash scripts/integration/phase4.sh "$model" "$tag" "$port" > "$wrapper" 2>&1
    check_stages "$wrapper"
    ;;
  *) echo 'usage: run_mode_smoke_stage.sh {wait|run} ...' >&2; exit 64 ;;
esac
