#!/usr/bin/env bash
# Reusable smoke stage: wait for an existing Phase 4 run, or load a named mode and run it.
set -euo pipefail

repo=$(cd "$(dirname "$0")/../.." && pwd)
logs="${BENCHMARK_OUTPUT_DIR:-$repo/results/mode-smoke}"
control="$repo/scripts/integration/local_runtime.py"
mkdir -p "$logs"

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
        --stop-container) echo 'Container control belongs to Orchestration; supply --stop-profile ID' >&2; exit 64 ;;
        --stop-profile) python3 "$control" stop --profile "$7" ;;
        *) echo "unknown stop option $6" >&2; exit 64 ;;
      esac
    fi
    [[ -f "$mode" ]] || { echo 'MODE must be an explicit local profile JSON file' >&2; exit 64; }
    profile="smoke-${tag}-$(date +%s)"
    python3 "$control" register --profile "$profile" --spec "$mode"
    python3 "$control" load --profile "$profile" > "$logs/${profile}.load.json"
    actual_port=$(python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print(next(p["port"] for p in d["observation"]["profiles"] if p["id"]==sys.argv[2]))' "$logs/${profile}.load.json" "$profile")
    trap 'python3 "$control" stop --profile "$profile"' EXIT
    [[ "$actual_port" == "$port" ]] || { echo 'Requested port differs from admitted port' >&2; exit 1; }
    wrapper="$logs/placement_${tag}.log"
    [[ ! -e "$wrapper" ]] || { echo "smoke log already exists: $wrapper" >&2; exit 1; }
    cd "$repo"
    bash scripts/integration/phase4.sh "$model" "$tag" "$port" > "$wrapper" 2>&1
    check_stages "$wrapper"
    ;;
  *) echo 'usage: run_mode_smoke_stage.sh {wait|run} ...' >&2; exit 64 ;;
esac
