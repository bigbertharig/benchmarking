#!/bin/bash
set -euo pipefail

PORTS="11435 11436 11437 11438 11439"
RUN_ROOT=""
RESULTS_ROOT="/mnt/shared/logs/benchmarks/bench-pipeline/history"
SCRIPTS_DIR="/mnt/shared/plans/shoulders/benchmarking"
BACKGROUND=1
USE_MODEL_PROMPTS=0
PROMPT_PROFILES="/benchmark-scripts/custom_tasks/model_prompt_profiles.json"
TUNING_PROFILES="/benchmark-scripts/model_tuning_profiles.json"
RUN_NAME=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --ports) PORTS="$2"; shift 2 ;;
    --run-root) RUN_ROOT="$2"; shift 2 ;;
    --results-root) RESULTS_ROOT="$2"; shift 2 ;;
    --scripts-dir) SCRIPTS_DIR="$2"; shift 2 ;;
    --use-model-prompts) USE_MODEL_PROMPTS=1; shift 1 ;;
    --prompt-profiles) PROMPT_PROFILES="$2"; shift 2 ;;
    --tuning-profiles) TUNING_PROFILES="$2"; shift 2 ;;
    --run-name) RUN_NAME="$2"; shift 2 ;;
    --foreground) BACKGROUND=0; shift 1 ;;
    --background) BACKGROUND=1; shift 1 ;;
    --help)
      cat <<'EOF'
Usage: start_parallel_worker_suite.sh [options]

Options:
  --ports "11435 11436 11437 11438 11439"   Space-separated runtime ports
  --run-root /mnt/shared/logs/benchmarks/... Explicit run directory
  --results-root /mnt/shared/logs/benchmarks/bench-pipeline/history Parent folder for new run dir
  --scripts-dir /mnt/shared/plans/shoulders/benchmarking Benchmark scripts mount path
  --use-model-prompts                         Enable per-model prompt profiles
  --prompt-profiles /benchmark-scripts/...    Prompt profile JSON path inside container
  --tuning-profiles /benchmark-scripts/...    Universal tuning profile JSON path inside container
  --run-name NAME                             Stable run id prefix (enables checkpoint resume)
  --foreground                               Run attached (wait for completion)
  --background                               Run detached (default)
EOF
      exit 0
      ;;
    *)
      echo "Unknown arg: $1" >&2
      exit 2
      ;;
  esac
done

if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: docker not found on rig host" >&2
  exit 1
fi

if [[ -z "$RUN_ROOT" ]]; then
  RUN_TS="$(date +%Y%m%d_%H%M%S)"
  RUN_ROOT="${RESULTS_ROOT}/parallel_worker_suite_${RUN_TS}"
fi

RESULTS_DIR="${RUN_ROOT}/results"
MANIFEST="${RUN_ROOT}/manifest.tsv"
LAUNCH_LOG="${RUN_ROOT}/launcher.out"
mkdir -p "$RESULTS_DIR"

run_attached() {
  echo -e "port\tmodel\tlog\tstatus" > "$MANIFEST"

  for PORT in $PORTS; do
    MODEL="$(curl -s "http://localhost:${PORT}/v1/models" | python3 -c "import json,sys; d=json.load(sys.stdin); data=d.get('data') or []; print((data[0].get('id') if data and isinstance(data[0],dict) else '').strip())")"
    if [[ -z "$MODEL" ]]; then
      MODEL="UNKNOWN_MODEL_PORT_${PORT}"
    fi

    LOG="${RUN_ROOT}/port_${PORT}.log"
    echo -e "${PORT}\t${MODEL}\t${LOG}\tlaunching" >> "$MANIFEST"

    (
      set +e
      CMD=(
        docker run --rm --network host
        -v "${RESULTS_DIR}:/results"
        -v "${SCRIPTS_DIR}:/benchmark-scripts:ro"
        bench-pipeline
        --model "${MODEL}"
        --runtime-base "http://localhost:${PORT}"
        --results-dir /results
        --run-name "${RUN_NAME:-port}_${PORT}"
      )
      if [[ "$USE_MODEL_PROMPTS" -eq 1 ]]; then
        CMD+=(--use-model-prompts --prompt-profiles "$PROMPT_PROFILES" --tuning-profiles "$TUNING_PROFILES")
      fi

      "${CMD[@]}" > "${LOG}" 2>&1
      CODE=$?
      echo "$CODE" > "${RUN_ROOT}/port_${PORT}.exit"
      if [[ "$CODE" -eq 0 ]]; then
        sed -i "s#^${PORT}\t\([^\t]*\)\t\([^\t]*\)\tlaunching#${PORT}\t\1\t\2\tdone#" "$MANIFEST"
      else
        sed -i "s#^${PORT}\t\([^\t]*\)\t\([^\t]*\)\tlaunching#${PORT}\t\1\t\2\tfailed(${CODE})#" "$MANIFEST"
      fi
    ) &
  done

  wait
  echo "ALL_DONE" >> "$LAUNCH_LOG"
}

if [[ "$BACKGROUND" -eq 1 ]]; then
  BG_CMD=(
    nohup "$0"
    --foreground
    --ports "$PORTS"
    --run-root "$RUN_ROOT"
    --results-root "$RESULTS_ROOT"
    --scripts-dir "$SCRIPTS_DIR"
    --prompt-profiles "$PROMPT_PROFILES"
    --tuning-profiles "$TUNING_PROFILES"
    --run-name "$RUN_NAME"
  )
  if [[ "$USE_MODEL_PROMPTS" -eq 1 ]]; then
    BG_CMD+=(--use-model-prompts)
  fi
  "${BG_CMD[@]}" > "$LAUNCH_LOG" 2>&1 &
  echo "RUN_ROOT=$RUN_ROOT"
  echo "LAUNCH_PID=$!"
  exit 0
fi

run_attached
echo "RUN_ROOT=$RUN_ROOT"
cat "$MANIFEST"
