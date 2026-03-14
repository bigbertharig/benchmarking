#!/bin/bash
set -euo pipefail

MODEL=""
RUNTIME_BASE="http://localhost:11436"
TASKS="humaneval,mbpp"
RESULTS_DIR="/results"
RUN_NAME=""
PREFLIGHT_ONLY=0
REQUEST_TIMEOUT="30"
RESERVATION_SHARED_PATH="${BENCHMARK_RESERVATION_SHARED_PATH:-/mnt/shared}"
RESERVATION_OWNER="${BENCHMARK_RESERVATION_OWNER:-bench-code}"
RESERVATION_RUN_ID=""
RESERVATION_HELPER=""
RESERVATION_PORT=""
AUTO_RESERVE_ENABLED="${BENCHMARK_DISABLE_AUTO_RESERVE:-0}"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --model) MODEL="$2"; shift 2 ;;
        --runtime-base) RUNTIME_BASE="$2"; shift 2 ;;
        --tasks) TASKS="$2"; shift 2 ;;
        --results-dir) RESULTS_DIR="$2"; shift 2 ;;
        --run-name) RUN_NAME="$2"; shift 2 ;;
        --preflight-only) PREFLIGHT_ONLY=1; shift 1 ;;
        --request-timeout) REQUEST_TIMEOUT="$2"; shift 2 ;;
        *) echo "Unknown arg: $1"; exit 1 ;;
    esac
done

if [ -z "$MODEL" ]; then
    echo "ERROR: --model is required (e.g. --model qwen2.5-coder:7b)"
    exit 1
fi

MODEL_SAFE=$(echo "$MODEL" | tr ':/' '_')
RESERVATION_RUN_ID="${RUN_NAME:-bench-code_${MODEL_SAFE}}"
RESERVATION_HELPER="${RESERVATION_SHARED_PATH}/scripts/benchmark_gpu_reservation.py"
RESERVATION_PORT="$(python3 - "$RUNTIME_BASE" <<'PY'
import sys
from urllib.parse import urlparse
value = sys.argv[1].strip()
parsed = urlparse(value if "://" in value else f"http://{value}")
print(parsed.port or "")
PY
)"

cleanup_reservation() {
    if [ "$AUTO_RESERVE_ENABLED" != "1" ] && [ -n "$RESERVATION_PORT" ] && [ -f "$RESERVATION_HELPER" ]; then
        python3 "$RESERVATION_HELPER" \
            --shared-path "$RESERVATION_SHARED_PATH" \
            --port "$RESERVATION_PORT" \
            --owner "$RESERVATION_OWNER" \
            release >/dev/null 2>&1 || true
    fi
}
trap cleanup_reservation EXIT

if [ "$AUTO_RESERVE_ENABLED" != "1" ] && [ -n "$RESERVATION_PORT" ]; then
    if [ ! -f "$RESERVATION_HELPER" ]; then
        echo "ERROR: reservation helper not found: $RESERVATION_HELPER"
        echo "Mount the shared root, e.g. -v /mnt/shared:/mnt/shared"
        exit 1
    fi
    python3 "$RESERVATION_HELPER" \
        --shared-path "$RESERVATION_SHARED_PATH" \
        --port "$RESERVATION_PORT" \
        --owner "$RESERVATION_OWNER" \
        --reserved-for benchmark \
        --run-id "$RESERVATION_RUN_ID" \
        reserve >/dev/null
fi

echo "=== bench-code ==="
echo "Model: $MODEL"
echo "Runtime: $RUNTIME_BASE"
echo "Tasks: $TASKS"
echo "Results: $RESULTS_DIR"
[ -n "$RUN_NAME" ] && echo "Run name: $RUN_NAME"
echo "Request timeout: ${REQUEST_TIMEOUT}s"

# Verify runtime is reachable
if ! curl -s "${RUNTIME_BASE}/v1/models" > /dev/null 2>&1; then
    echo "ERROR: Cannot reach llama-compatible runtime at ${RUNTIME_BASE}"
    exit 1
fi

# Verify model responds within timeout budget
PROBE_PAYLOAD="{\"model\":\"${MODEL}\",\"messages\":[{\"role\":\"user\",\"content\":\"Reply with OK.\"}],\"max_tokens\":8,\"temperature\":0,\"stream\":false}"
if ! curl -sS --max-time "${REQUEST_TIMEOUT}" \
    -H "Content-Type: application/json" \
    -d "${PROBE_PAYLOAD}" \
    "${RUNTIME_BASE}/v1/chat/completions" > /dev/null; then
    echo "ERROR: Preflight completion probe failed or timed out (${REQUEST_TIMEOUT}s)"
    exit 1
fi

if [ "$PREFLIGHT_ONLY" -eq 1 ]; then
    echo "Preflight checks passed."
    exit 0
fi

if [ -n "$RUN_NAME" ]; then
    OUTPUT_DIR="${RESULTS_DIR}/bench-code_${MODEL_SAFE}_${RUN_NAME}"
else
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    OUTPUT_DIR="${RESULTS_DIR}/bench-code_${MODEL_SAFE}_${TIMESTAMP}"
fi
mkdir -p "$OUTPUT_DIR"
RUN_STATUS_FILE="${OUTPUT_DIR}/status.json"

init_status() {
    python3 - "$RUN_STATUS_FILE" "$MODEL" "$RUNTIME_BASE" "$TASKS" <<'PY'
import json, os, sys
status_file, model, runtime_base, tasks_csv = sys.argv[1:5]
if os.path.exists(status_file):
    sys.exit(0)
tasks = [t.strip() for t in tasks_csv.split(",") if t.strip()]
data = {
    "run_start": __import__("datetime").datetime.now().isoformat(),
    "model": model,
    "runtime": runtime_base,
    "tasks_requested": tasks,
    "tasks": {},
    "current_task": "",
    "completed_tasks": 0,
    "total_tasks": len(tasks),
    "state": "running",
    "updated_at": __import__("datetime").datetime.now().isoformat(),
}
with open(status_file, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2)
PY
}

update_status() {
    local task="$1"
    local state="$2"
    local generated="$3"
    local expected="$4"
    local samples="$5"
    python3 - "$RUN_STATUS_FILE" "$task" "$state" "$generated" "$expected" "$samples" <<'PY'
import json, sys
from datetime import datetime
status_file, task, state, generated, expected, samples = sys.argv[1:7]
with open(status_file, "r", encoding="utf-8") as f:
    data = json.load(f)
tasks = data.setdefault("tasks", {})
entry = tasks.get(task, {})
entry.update({
    "state": state,
    "generated": int(generated) if str(generated).isdigit() else None,
    "expected": int(expected) if str(expected).isdigit() else None,
    "samples": samples,
    "updated_at": datetime.now().isoformat(),
})
tasks[task] = entry
order = [str(x).strip() for x in (data.get("tasks_requested") or []) if str(x).strip()]
if not order:
    order = list(tasks.keys())
completed = 0
current = ""
for name in order:
    st = str((tasks.get(name) or {}).get("state") or "").strip().lower()
    if st in {"evaluated", "completed"}:
        completed += 1
        continue
    if not current:
        current = name
data["completed_tasks"] = completed
data["total_tasks"] = len(order)
data["current_task"] = current
data["state"] = "completed" if len(order) > 0 and completed >= len(order) else "running"
data["updated_at"] = datetime.now().isoformat()
with open(status_file, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2)
PY
}

# evalplus uses OPENAI_BASE_URL to talk to the runtime
export OPENAI_BASE_URL="${RUNTIME_BASE}/v1"
export OPENAI_API_KEY="llama"

IFS=',' read -ra TASK_ARRAY <<< "$TASKS"

task_expected_count() {
    local task="$1"
    python3 - "$task" <<'PY'
import sys
task = sys.argv[1].strip().lower()
if task == "humaneval":
    from evalplus.data import get_human_eval_plus
    print(len(get_human_eval_plus()))
elif task == "mbpp":
    from evalplus.data import get_mbpp_plus
    print(len(get_mbpp_plus()))
else:
    print(0)
PY
}

task_state() {
    local status_file="$1"
    python3 - "$status_file" <<'PY'
import json, sys
p = sys.argv[1]
try:
    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)
    print(str(data.get("state", "")).strip())
except Exception:
    print("")
PY
}

INCOMPLETE_TASKS=0
init_status

for TASK in "${TASK_ARRAY[@]}"; do
    echo ""
    echo "--- Running ${TASK} ---"
    TASK_DIR="${OUTPUT_DIR}/${TASK}"
    mkdir -p "$TASK_DIR"
    STATUS_FILE="${TASK_DIR}/status.json"

    EXISTING_STATE=""
    if [ -f "$STATUS_FILE" ]; then
        EXISTING_STATE="$(task_state "$STATUS_FILE")"
    fi
    if [ "$EXISTING_STATE" = "evaluated" ]; then
        echo "--- Skipping ${TASK} (already evaluated in checkpoint) ---"
        update_status "$TASK" "evaluated" "0" "0" ""
        continue
    fi

    # evalplus codegen: positional args are MODEL DATASET
    # Note: evalplus evaluate requires ALL problems in samples.
    GEN_CMD="python3 -m evalplus.codegen ${MODEL} ${TASK} --backend openai --greedy --root ${OUTPUT_DIR}"
    echo "{\"task\":\"${TASK}\",\"state\":\"generating\",\"updated_at\":\"$(date -Iseconds)\"}" > "$STATUS_FILE"

    echo "Generating: $GEN_CMD"
    update_status "$TASK" "running" "0" "0" ""
    eval $GEN_CMD

    # Find the generated samples file
    SAMPLE_DIR="${OUTPUT_DIR}/${TASK}"
    SAMPLE_FILE=$(find "$SAMPLE_DIR" -name "*.jsonl" ! -name "*.raw.jsonl" 2>/dev/null | head -1)

    if [ -z "$SAMPLE_FILE" ]; then
        echo "ERROR: No sample file found in $SAMPLE_DIR"
        echo "{\"task\":\"${TASK}\",\"state\":\"error_missing_samples\",\"updated_at\":\"$(date -Iseconds)\"}" > "$STATUS_FILE"
        update_status "$TASK" "error_missing_samples" "0" "0" ""
        continue
    fi

    GENERATED_COUNT=$(wc -l < "$SAMPLE_FILE")
    EXPECTED_COUNT=$(task_expected_count "$TASK")
    echo "Generated ${GENERATED_COUNT}/${EXPECTED_COUNT} samples for ${TASK}"

    if [ "$EXPECTED_COUNT" -gt 0 ] && [ "$GENERATED_COUNT" -lt "$EXPECTED_COUNT" ]; then
        echo "WARNING: ${TASK} is incomplete; skipping evaluate until full coverage is available."
        echo "{\"task\":\"${TASK}\",\"state\":\"generated_partial\",\"generated\":${GENERATED_COUNT},\"expected\":${EXPECTED_COUNT},\"samples\":\"${SAMPLE_FILE}\",\"updated_at\":\"$(date -Iseconds)\"}" > "$STATUS_FILE"
        update_status "$TASK" "generated_partial" "$GENERATED_COUNT" "$EXPECTED_COUNT" "$SAMPLE_FILE"
        INCOMPLETE_TASKS=$((INCOMPLETE_TASKS + 1))
        continue
    fi

    # Evaluate generated samples
    echo "Evaluating: python3 -m evalplus.evaluate --dataset ${TASK} --samples ${SAMPLE_FILE}"
    python3 -m evalplus.evaluate --dataset "$TASK" --samples "$SAMPLE_FILE"
    echo "{\"task\":\"${TASK}\",\"state\":\"evaluated\",\"generated\":${GENERATED_COUNT},\"expected\":${EXPECTED_COUNT},\"samples\":\"${SAMPLE_FILE}\",\"updated_at\":\"$(date -Iseconds)\"}" > "$STATUS_FILE"
    update_status "$TASK" "evaluated" "$GENERATED_COUNT" "$EXPECTED_COUNT" "$SAMPLE_FILE"

    echo "--- ${TASK} done ---"
done

python3 - "$RUN_STATUS_FILE" <<'PY'
import json, sys
from datetime import datetime
status_file = sys.argv[1]
try:
    with open(status_file, "r", encoding="utf-8") as f:
        data = json.load(f)
except Exception:
    sys.exit(0)
data["state"] = "completed"
data["updated_at"] = datetime.now().isoformat()
with open(status_file, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2)
PY

echo ""
echo "=== bench-code COMPLETE ==="
echo "Results in: $OUTPUT_DIR"
[ "$INCOMPLETE_TASKS" -gt 0 ] && echo "Incomplete tasks pending full coverage: $INCOMPLETE_TASKS"

# Summarize results
python3 -c "
import json, glob, os
for f in sorted(glob.glob('${OUTPUT_DIR}/**/*_eval_results.json', recursive=True)):
    data = json.load(open(f))
    dataset = os.path.basename(os.path.dirname(f))
    base = data.get('pass@1', {}).get('base', 'N/A')
    plus = data.get('pass@1', {}).get('plus', 'N/A')
    print(f'  {dataset}: pass@1 base={base}, plus={plus}')
" 2>/dev/null || echo "(could not parse results)"
