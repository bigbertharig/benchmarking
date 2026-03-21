#!/bin/bash
set -euo pipefail

MODEL=""
RUNTIME_BASE="http://localhost:11436"
RESULTS_DIR="/results"
SCRIPTS_DIR="/benchmark-scripts"
SUITE="llm_benchmark_v2.json"
TASKS=""
LIMIT="0"
RUN_NAME=""
TEMPERATURE="0.1"
MAX_TOKENS="400"
TIMEOUT="60"
MODEL_NAME=""
REQUIRES_FILTER=""
DAEDALMAP_URL=""
EXECUTE_VALIDATION="0"
AUTH_TOKEN=""
RESERVATION_SHARED_PATH="${BENCHMARK_RESERVATION_SHARED_PATH:-/mnt/shared}"
RESERVATION_OWNER="${BENCHMARK_RESERVATION_OWNER:-bench-daedalmap}"
RESERVATION_RUN_ID=""
RESERVATION_HELPER=""
RESERVATION_PORT=""
AUTO_RESERVE_ENABLED="${BENCHMARK_DISABLE_AUTO_RESERVE:-0}"
RECORD_RESULT_SCRIPT=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --model) MODEL="$2"; shift 2 ;;
        --runtime-base) RUNTIME_BASE="$2"; shift 2 ;;
        --results-dir) RESULTS_DIR="$2"; shift 2 ;;
        --scripts-dir) SCRIPTS_DIR="$2"; shift 2 ;;
        --suite) SUITE="$2"; shift 2 ;;
        --tasks) TASKS="$2"; shift 2 ;;
        --limit) LIMIT="$2"; shift 2 ;;
        --run-name) RUN_NAME="$2"; shift 2 ;;
        --temperature) TEMPERATURE="$2"; shift 2 ;;
        --max-tokens) MAX_TOKENS="$2"; shift 2 ;;
        --timeout) TIMEOUT="$2"; shift 2 ;;
        --model-name) MODEL_NAME="$2"; shift 2 ;;
        --requires) REQUIRES_FILTER="$2"; shift 2 ;;
        --daedalmap-url) DAEDALMAP_URL="$2"; shift 2 ;;
        --execute) EXECUTE_VALIDATION="1"; shift 1 ;;
        --auth-token) AUTH_TOKEN="$2"; shift 2 ;;
        *) echo "Unknown arg: $1"; exit 1 ;;
    esac
done

if [ -z "$MODEL" ]; then
    echo "ERROR: --model is required"
    exit 1
fi

MODEL_SAFE=$(echo "$MODEL" | tr ':/' '_')
if [ -n "$RUN_NAME" ]; then
    RUN_ID="$RUN_NAME"
else
    RUN_ID="$(date +%Y%m%d_%H%M%S)"
fi

if [ -n "$MODEL_NAME" ]; then
    MODEL_REQUEST_NAME="$MODEL_NAME"
else
    MODEL_REQUEST_NAME="$MODEL"
fi

SUITE_PATH="$SUITE"
if [ ! -f "$SUITE_PATH" ]; then
    SUITE_PATH="/opt/bench/$SUITE"
fi
if [ ! -f "$SUITE_PATH" ]; then
    echo "ERROR: suite file not found: $SUITE"
    exit 1
fi

RUN_ROOT="${RESULTS_DIR}/bench-daedalmap_${MODEL_SAFE}_${RUN_ID}"
STATUS_FILE="${RUN_ROOT}/status.json"
FINAL_FILE="${RUN_ROOT}/final_summary.json"
LOG_FILE="${RUN_ROOT}/bench-daedalmap.log"
RUN_START_ISO="$(date -Iseconds)"
RESERVATION_RUN_ID="$RUN_ID"
RESERVATION_HELPER="${RESERVATION_SHARED_PATH}/scripts/benchmark_gpu_reservation.py"
RECORD_RESULT_SCRIPT="${SCRIPTS_DIR}/scripts/active/record_benchmark_result.py"
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

mkdir -p "$RUN_ROOT"

record_result_row() {
    local test_id="$1"
    local score="$2"
    local metric="$3"
    local notes="${4:-}"
    if [ ! -f "$RECORD_RESULT_SCRIPT" ]; then
        echo "WARNING: record script missing: $RECORD_RESULT_SCRIPT" | tee -a "$LOG_FILE"
        return 0
    fi
    python3 "$RECORD_RESULT_SCRIPT" \
        --model "$MODEL" \
        --test-id "$test_id" \
        --score "$score" \
        --metric "$metric" \
        --harness "bench-daedalmap" \
        --suite "${RUN_NAME:-bench-daedalmap}" \
        --run-at "$(date -Iseconds)" \
        --notes "$notes" >/dev/null || echo "WARNING: failed to record result for ${MODEL} ${test_id}" | tee -a "$LOG_FILE"
}

if [ "$AUTO_RESERVE_ENABLED" != "1" ] && [ -n "$RESERVATION_PORT" ]; then
    if [ ! -f "$RESERVATION_HELPER" ]; then
        echo "ERROR: reservation helper not found: $RESERVATION_HELPER" | tee -a "$LOG_FILE"
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

if ! curl -fsS "${RUNTIME_BASE}/v1/models" >/dev/null; then
    echo "ERROR: Cannot reach llama-compatible runtime at ${RUNTIME_BASE}" | tee -a "$LOG_FILE"
    exit 1
fi

AVAILABLE_TASKS="$(
python3 - "$SUITE_PATH" <<'PY'
import json, sys
data = json.load(open(sys.argv[1], encoding="utf-8"))
cats = sorted({str(case.get("category", "")).strip() for case in data.get("cases", []) if str(case.get("category", "")).strip()})
print(",".join(cats))
PY
)"

if [ -z "$AVAILABLE_TASKS" ]; then
    echo "ERROR: No categories found in suite: $SUITE_PATH" | tee -a "$LOG_FILE"
    exit 1
fi

if [ -z "$TASKS" ]; then
    FILTERED_TASKS="$AVAILABLE_TASKS"
else
    FILTERED_TASKS="$(
    python3 - "$AVAILABLE_TASKS" "$TASKS" <<'PY'
import sys
available = {x.strip() for x in sys.argv[1].split(",") if x.strip()}
requested = [x.strip() for x in sys.argv[2].split(",") if x.strip()]
kept = [x for x in requested if x in available]
missing = [x for x in requested if x not in available]
if missing:
    print("WARNING: skipping unknown tasks: " + ",".join(missing), file=sys.stderr)
print(",".join(kept))
PY
    )"
fi

if [ -z "$FILTERED_TASKS" ]; then
    echo "ERROR: No runnable tasks remain after filtering" | tee -a "$LOG_FILE"
    exit 1
fi

python3 - "$STATUS_FILE" "$MODEL" "$RUNTIME_BASE" "$FILTERED_TASKS" "$LIMIT" "$RUN_START_ISO" "$SUITE_PATH" "$REQUIRES_FILTER" <<'PY'
import json, os, sys
status_file, model, runtime, tasks_csv, limit_value, run_start, suite_path, requires_filter = sys.argv[1:9]
tasks = [t.strip() for t in tasks_csv.split(",") if t.strip()]
if os.path.exists(status_file):
    with open(status_file, "r", encoding="utf-8") as f:
        data = json.load(f)
else:
    data = {
        "run_start": run_start,
        "model": model,
        "runtime": runtime,
        "suite_file": suite_path,
        "tasks_requested": tasks,
        "limit": limit_value,
        "requires_filter": requires_filter,
        "tasks": {},
    }
data["updated_at"] = run_start
data["tasks_requested"] = tasks
data["limit"] = limit_value
data["requires_filter"] = requires_filter
with open(status_file, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2)
PY

update_status() {
    local task="$1"
    local state="$2"
    local exit_code="$3"
    local output_dir="$4"
    local started_at="$5"
    local ended_at="$6"
    local summary_path="$7"
    python3 - "$STATUS_FILE" "$task" "$state" "$exit_code" "$output_dir" "$started_at" "$ended_at" "$summary_path" <<'PY'
import json, sys
from datetime import datetime
status_file, task, state, exit_code, output_dir, started_at, ended_at, summary_path = sys.argv[1:9]
with open(status_file, "r", encoding="utf-8") as f:
    data = json.load(f)
tasks = data.setdefault("tasks", {})
entry = tasks.get(task, {})
entry["state"] = state
entry["exit_code"] = int(exit_code)
entry["output_dir"] = output_dir
entry["started_at"] = started_at
entry["ended_at"] = ended_at
if summary_path:
    entry["summary_path"] = summary_path
entry["updated_at"] = datetime.now().isoformat()
tasks[task] = entry
data["updated_at"] = datetime.now().isoformat()
with open(status_file, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2)
PY
}

task_completed() {
    local task="$1"
    python3 - "$STATUS_FILE" "$task" <<'PY'
import json, sys
with open(sys.argv[1], "r", encoding="utf-8") as f:
    data = json.load(f)
entry = ((data.get("tasks") or {}).get(sys.argv[2]) or {})
print("1" if entry.get("state") == "completed" else "0")
PY
}

echo "=== bench-daedalmap ===" | tee -a "$LOG_FILE"
echo "Model: $MODEL" | tee -a "$LOG_FILE"
echo "Runtime: $RUNTIME_BASE" | tee -a "$LOG_FILE"
echo "Suite: $SUITE_PATH" | tee -a "$LOG_FILE"
echo "Tasks: $FILTERED_TASKS" | tee -a "$LOG_FILE"
echo "Requires filter: ${REQUIRES_FILTER:-<none>}" | tee -a "$LOG_FILE"
echo "Execution validation: $EXECUTE_VALIDATION" | tee -a "$LOG_FILE"
[ -n "$DAEDALMAP_URL" ] && echo "DaedalMap URL: $DAEDALMAP_URL" | tee -a "$LOG_FILE"
echo "Limit: $LIMIT" | tee -a "$LOG_FILE"
echo "Run root: $RUN_ROOT" | tee -a "$LOG_FILE"

IFS=',' read -r -a TASK_ARRAY <<< "$FILTERED_TASKS"
FAILED_TASKS=0

for task in "${TASK_ARRAY[@]}"; do
    if [ "$(task_completed "$task")" = "1" ]; then
        echo "--- Skipping completed task: $task ---" | tee -a "$LOG_FILE"
        continue
    fi

    TASK_DIR="${RUN_ROOT}/${task}"
    TASK_LOG="${RUN_ROOT}/${task}.log"
    SUMMARY_PATH="${TASK_DIR}/summary.json"
    STARTED_AT="$(date -Iseconds)"
    mkdir -p "$TASK_DIR"

    echo "--- Running task: $task ---" | tee -a "$LOG_FILE"
    update_status "$task" "running" "0" "$TASK_DIR" "$STARTED_AT" "" ""

    CMD=(
        python3 /opt/bench/llm_benchmark_runner.py
        --suite "$SUITE_PATH"
        --model-tag "$MODEL_SAFE"
        --model-name "$MODEL_REQUEST_NAME"
        --api-base "$RUNTIME_BASE"
        --category "$task"
        --out-dir "$TASK_DIR"
        --summary-out "$SUMMARY_PATH"
        --temperature "$TEMPERATURE"
        --max-tokens "$MAX_TOKENS"
        --timeout "$TIMEOUT"
    )
    if [ "$LIMIT" != "0" ]; then
        CMD+=(--limit "$LIMIT")
    fi
    if [ -n "$REQUIRES_FILTER" ]; then
        CMD+=(--requires "$REQUIRES_FILTER")
    fi
    if [ "$EXECUTE_VALIDATION" = "1" ]; then
        CMD+=(--execute)
    fi
    if [ -n "$DAEDALMAP_URL" ]; then
        CMD+=(--daedalmap-url "$DAEDALMAP_URL")
    fi
    if [ -n "$AUTH_TOKEN" ]; then
        CMD+=(--auth-token "$AUTH_TOKEN")
    fi

    set +e
    "${CMD[@]}" 2>&1 | tee -a "$LOG_FILE" "$TASK_LOG"
    RC=${PIPESTATUS[0]}
    set -e

    ENDED_AT="$(date -Iseconds)"
    if [ "$RC" -ne 0 ]; then
        FAILED_TASKS=$((FAILED_TASKS + 1))
        update_status "$task" "failed" "$RC" "$TASK_DIR" "$STARTED_AT" "$ENDED_AT" "$SUMMARY_PATH"
        echo "Task failed: $task (exit $RC)" | tee -a "$LOG_FILE"
        continue
    fi

    update_status "$task" "completed" "0" "$TASK_DIR" "$STARTED_AT" "$ENDED_AT" "$SUMMARY_PATH"

    if [ -f "$SUMMARY_PATH" ]; then
        while IFS=$'\t' read -r test_id score metric notes; do
            [ -n "$test_id" ] || continue
            record_result_row "$test_id" "$score" "$metric" "$notes"
        done < <(
            python3 - "$SUMMARY_PATH" "$task" <<'PY'
import json, sys
summary = json.load(open(sys.argv[1], encoding="utf-8"))
task = sys.argv[2]
rows = [
    (f"daedalmap_{task}_pass_rate", summary["pass_rate"], "pass_rate", f"{summary['pass_count']}/{summary['total_cases']} PASS"),
    (f"daedalmap_{task}_json_valid_rate", summary["json_valid_rate"], "json_valid_rate", ""),
    (f"daedalmap_{task}_type_correct_rate", summary["type_correct_rate"], "type_correct_rate", ""),
    (f"daedalmap_{task}_no_halluc_rate", summary["no_halluc_rate"], "no_halluc_rate", ""),
]
if summary.get("source_hit_rate") is not None:
    rows.append((f"daedalmap_{task}_source_hit_rate", summary["source_hit_rate"], "source_hit_rate", ""))
if summary.get("source_valid_rate") is not None:
    rows.append((f"daedalmap_{task}_source_valid_rate", summary["source_valid_rate"], "source_valid_rate", ""))
for row in rows:
    print("\t".join(str(x) for x in row))
PY
        )
    fi
done

python3 - "$RUN_ROOT" "$FINAL_FILE" "$MODEL" "$SUITE_PATH" "$FILTERED_TASKS" "$LIMIT" "$REQUIRES_FILTER" "$RUNTIME_BASE" <<'PY'
import json, sys
from datetime import datetime, timezone
from pathlib import Path

run_root = Path(sys.argv[1])
final_file = Path(sys.argv[2])
model, suite_path, tasks_csv, limit_value, requires_filter, runtime = sys.argv[3:9]
tasks = [t.strip() for t in tasks_csv.split(",") if t.strip()]

task_summaries = {}
total_cases = pass_count = partial_count = fail_count = 0
json_valid_sum = type_correct_sum = no_halluc_sum = 0.0
source_hit_num = source_hit_den = 0.0
source_valid_num = source_valid_den = 0.0

for task in tasks:
    summary_path = run_root / task / "summary.json"
    if not summary_path.exists():
        continue
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    task_summaries[task] = summary
    count = int(summary.get("total_cases", 0))
    total_cases += count
    pass_count += int(summary.get("pass_count", 0))
    partial_count += int(summary.get("partial_count", 0))
    fail_count += int(summary.get("fail_count", 0))
    json_valid_sum += float(summary.get("json_valid_rate", 0.0)) * count
    type_correct_sum += float(summary.get("type_correct_rate", 0.0)) * count
    no_halluc_sum += float(summary.get("no_halluc_rate", 0.0)) * count
    if summary.get("source_hit_rate") is not None:
        applicable = int(summary.get("source_hit_applicable", 0))
        source_hit_num += float(summary["source_hit_rate"]) * applicable
        source_hit_den += applicable
    if summary.get("source_valid_rate") is not None:
        applicable = int(summary.get("source_valid_applicable", 0))
        source_valid_num += float(summary["source_valid_rate"]) * applicable
        source_valid_den += applicable

payload = {
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "suite": "bench-daedalmap",
    "model": model,
    "suite_file": suite_path,
    "runtime": runtime,
    "tasks_requested": tasks,
    "limit": limit_value,
    "requires_filter": requires_filter,
    "completed_tasks": sorted(task_summaries),
    "total_cases": total_cases,
    "pass_count": pass_count,
    "partial_count": partial_count,
    "fail_count": fail_count,
    "pass_rate": (pass_count / total_cases) if total_cases else 0.0,
    "json_valid_rate": (json_valid_sum / total_cases) if total_cases else 0.0,
    "type_correct_rate": (type_correct_sum / total_cases) if total_cases else 0.0,
    "no_halluc_rate": (no_halluc_sum / total_cases) if total_cases else 0.0,
    "source_hit_rate": (source_hit_num / source_hit_den) if source_hit_den else None,
    "source_valid_rate": (source_valid_num / source_valid_den) if source_valid_den else None,
    "task_summaries": task_summaries,
}
final_file.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY

echo "Final summary: $FINAL_FILE" | tee -a "$LOG_FILE"

if [ "$FAILED_TASKS" -ne 0 ]; then
    echo "bench-daedalmap completed with failed tasks: $FAILED_TASKS" | tee -a "$LOG_FILE"
    exit 1
fi

echo "bench-daedalmap completed successfully" | tee -a "$LOG_FILE"
