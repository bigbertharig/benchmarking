#!/bin/bash
set -euo pipefail

MODEL=""
RUNTIME_BASE="http://localhost:11436"
RESULTS_DIR="/results"
SCRIPTS_DIR="/benchmark-scripts"
TESTS="custom_json_schema_strict,custom_command_safety,custom_ambiguity_handling,custom_tool_plan_sequence,custom_orchestration_tradeoff,custom_long_context_extract"
USE_MODEL_PROMPTS=1
PROMPT_PROFILES="/benchmark-scripts/custom_tasks/model_prompt_profiles.json"
TUNING_PROFILES="/benchmark-scripts/model_tuning_profiles.json"
RUN_NAME=""
RESERVATION_SHARED_PATH="${BENCHMARK_RESERVATION_SHARED_PATH:-/mnt/shared}"
RESERVATION_OWNER="${BENCHMARK_RESERVATION_OWNER:-bench-pipeline}"
RESERVATION_RUN_ID=""
RESERVATION_HELPER=""
RESERVATION_PORT=""
AUTO_RESERVE_ENABLED="${BENCHMARK_DISABLE_AUTO_RESERVE:-0}"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --model) MODEL="$2"; shift 2 ;;
        --runtime-base) RUNTIME_BASE="$2"; shift 2 ;;
        --results-dir) RESULTS_DIR="$2"; shift 2 ;;
        --scripts-dir) SCRIPTS_DIR="$2"; shift 2 ;;
        --tests) TESTS="$2"; shift 2 ;;
        --use-model-prompts) USE_MODEL_PROMPTS=1; shift 1 ;;
        --prompt-profiles) PROMPT_PROFILES="$2"; shift 2 ;;
        --tuning-profiles) TUNING_PROFILES="$2"; shift 2 ;;
        --run-name) RUN_NAME="$2"; shift 2 ;;
        *) echo "Unknown arg: $1"; exit 1 ;;
    esac
done

if [ -z "$MODEL" ]; then
    echo "ERROR: --model is required (e.g. --model qwen2.5-coder:7b)"
    exit 1
fi

MODEL_SAFE=$(echo "$MODEL" | tr ':/' '_')
if [ -n "$RUN_NAME" ]; then
    RUN_ID="$RUN_NAME"
else
    RUN_ID="$(date +%Y%m%d_%H%M%S)"
fi

STAGE_FILE="${RESULTS_DIR}/bench-pipeline_${MODEL_SAFE}_${RUN_ID}_stage_updates.jsonl"
STATUS_FILE="${RESULTS_DIR}/bench-pipeline_${MODEL_SAFE}_${RUN_ID}_status.json"
FINAL_FILE="${RESULTS_DIR}/bench-pipeline_${MODEL_SAFE}_${RUN_ID}_final_summary.json"
CHECKPOINT_FILE="${RESULTS_DIR}/bench-pipeline_${MODEL_SAFE}_${RUN_ID}_checkpoint.json"
RUN_START_EPOCH=$(date +%s)
RUN_START_ISO=$(date -Iseconds)
RESERVATION_RUN_ID="$RUN_ID"
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

init_checkpoint() {
    python3 - "$CHECKPOINT_FILE" "$MODEL" "$RUNTIME_BASE" "$TESTS" "$RUN_START_ISO" <<'PY'
import json, os, sys
cp_file, model, runtime, tests_csv, run_start = sys.argv[1:6]
if os.path.exists(cp_file):
    sys.exit(0)

tests = [t.strip() for t in tests_csv.split(",") if t.strip()]
data = {
    "run_start": run_start,
    "model": model,
    "runtime": runtime,
    "tests_requested": tests,
    "tests": {},
    "updated_at": run_start,
}
with open(cp_file, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2)
PY
}

test_state() {
    local test_id="$1"
    python3 - "$CHECKPOINT_FILE" "$test_id" <<'PY'
import json, sys
cp_file, test_id = sys.argv[1:3]
try:
    with open(cp_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    state = ((data.get("tests") or {}).get(test_id) or {}).get("state", "")
    print(state)
except Exception:
    print("")
PY
}

checkpoint_counts() {
    python3 - "$CHECKPOINT_FILE" <<'PY'
import json, sys
cp_file = sys.argv[1]
with open(cp_file, "r", encoding="utf-8") as f:
    data = json.load(f)
entries = (data.get("tests") or {}).values()
passed = sum(1 for e in entries if e.get("state") == "passed")
failed = sum(1 for e in entries if e.get("state") == "failed")
print(f"{passed} {failed}")
PY
}

update_checkpoint() {
    local test_id="$1"
    local state="$2"
    local exit_code="$3"
    local result_path="$4"
    local score="$5"
    local passes="$6"
    local total="$7"
    local started_at="$8"
    local ended_at="$9"

    python3 - "$CHECKPOINT_FILE" "$test_id" "$state" "$exit_code" "$result_path" "$score" "$passes" "$total" "$started_at" "$ended_at" <<'PY'
import json, sys
from datetime import datetime
(
    cp_file,
    test_id,
    state,
    exit_code,
    result_path,
    score,
    passes,
    total,
    started_at,
    ended_at,
) = sys.argv[1:11]

with open(cp_file, "r", encoding="utf-8") as f:
    data = json.load(f)

tests = data.setdefault("tests", {})
entry = tests.get(test_id, {})
entry["state"] = state
entry["exit_code"] = int(exit_code)
entry["result_path"] = result_path
entry["score"] = score
entry["passes"] = passes
entry["total"] = total
entry["started_at"] = started_at
entry["ended_at"] = ended_at
entry["attempts"] = int(entry.get("attempts", 0)) + 1
entry["updated_at"] = datetime.now().isoformat()
tests[test_id] = entry

data["updated_at"] = datetime.now().isoformat()
with open(cp_file, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2)
PY
}

checkpoint_test_summary() {
    python3 - "$CHECKPOINT_FILE" <<'PY'
import json, sys
cp_file = sys.argv[1]
with open(cp_file, "r", encoding="utf-8") as f:
    data = json.load(f)

tests = data.get("tests", {})
passed = sorted([k for k, v in tests.items() if v.get("state") == "passed"])
failed = sorted([k for k, v in tests.items() if v.get("state") == "failed"])
print(f"Passed tests: {len(passed)}")
if passed:
    print("  " + ", ".join(passed))
print(f"Failed tests: {len(failed)}")
if failed:
    print("  " + ", ".join(failed))
PY
}

echo "=== bench-pipeline ==="
echo "Model: $MODEL"
echo "Runtime: $RUNTIME_BASE"
echo "Tests: $TESTS"
echo "Results: $RESULTS_DIR"
echo "Scripts: $SCRIPTS_DIR"
echo "Use model prompts: $USE_MODEL_PROMPTS"
echo "Prompt profiles: $PROMPT_PROFILES"
echo "Tuning profiles: $TUNING_PROFILES"
[ -n "$RUN_NAME" ] && echo "Run name: $RUN_NAME"
echo "Stage updates: $STAGE_FILE"
echo "Status file: $STATUS_FILE"
echo "Final summary: $FINAL_FILE"
echo "Checkpoint file: $CHECKPOINT_FILE"

# Verify runtime is reachable
if ! curl -s "${RUNTIME_BASE}/v1/models" > /dev/null 2>&1; then
    echo "ERROR: Cannot reach llama-compatible runtime at ${RUNTIME_BASE}"
    exit 1
fi

# Verify the custom runner and cases exist
RUNNER="${SCRIPTS_DIR}/run_local_custom_task.py"
CASES="${SCRIPTS_DIR}/custom_tasks/cases.json"
CATALOG="${SCRIPTS_DIR}/benchmark_catalog.json"

if [ ! -f "$RUNNER" ]; then
    echo "ERROR: Custom test runner not found: $RUNNER"
    echo "Mount the benchmarks scripts dir with -v /mnt/shared/scripts/benchmarks:/benchmark-scripts:ro"
    exit 1
fi

init_checkpoint

if [ ! -f "$STAGE_FILE" ]; then
    : > "$STAGE_FILE"
fi

read PREV_PASSED PREV_FAILED <<< "$(checkpoint_counts)"
PASSED_TESTS=$PREV_PASSED
FAILED_TESTS=$PREV_FAILED
SKIPPED_TESTS=0

IFS=',' read -ra TEST_ARRAY <<< "$TESTS"
TOTAL_TESTS=${#TEST_ARRAY[@]}

for TEST_ID in "${TEST_ARRAY[@]}"; do
    TEST_ID="$(echo "$TEST_ID" | xargs)"
    [ -z "$TEST_ID" ] && continue

    CURRENT_STATE="$(test_state "$TEST_ID")"
    if [ "$CURRENT_STATE" = "passed" ]; then
        SKIPPED_TESTS=$((SKIPPED_TESTS + 1))
        echo ""
        echo "--- Skipping ${TEST_ID} (already passed in checkpoint) ---"
        continue
    fi

    echo ""
    echo "--- Running ${TEST_ID} ---"
    STAGE_START_EPOCH=$(date +%s)
    STAGE_START_ISO=$(date -Iseconds)

    RUN_CMD=(
      python3 "$RUNNER"
      --id "$TEST_ID"
      --model "$MODEL"
      --base-url "$RUNTIME_BASE"
      --catalog "$CATALOG"
      --cases "$CASES"
      --output-dir "$RESULTS_DIR"
      --suite "bench-pipeline"
      --no-record
    )
    if [ "$USE_MODEL_PROMPTS" -eq 1 ]; then
      RUN_CMD+=(--use-model-prompts --prompt-profiles "$PROMPT_PROFILES" --tuning-profiles "$TUNING_PROFILES" --require-model-prompt)
    fi

    set +e
    RUN_OUTPUT="$("${RUN_CMD[@]}" 2>&1)"
    RUN_CODE=$?
    set -e

    echo "$RUN_OUTPUT"

    if [ "$RUN_CODE" -eq 0 ]; then
        STAGE_STATUS="passed"
    else
        STAGE_STATUS="failed"
    fi

    RESULT_PATH=$(printf '%s\n' "$RUN_OUTPUT" | grep -Eo '"result_path":\s*"[^"]+"' | tail -n1 | sed -E 's/.*"([^"]+)"/\1/' || true)
    SCORE=$(printf '%s\n' "$RUN_OUTPUT" | grep -Eo '"score":\s*[^,]+' | tail -n1 | sed -E 's/.*:\s*//' || true)
    CASE_PASSES=$(printf '%s\n' "$RUN_OUTPUT" | grep -Eo '"passes":\s*[0-9]+' | tail -n1 | sed -E 's/.*:\s*//' || true)
    CASE_TOTAL=$(printf '%s\n' "$RUN_OUTPUT" | grep -Eo '"total":\s*[0-9]+' | tail -n1 | sed -E 's/.*:\s*//' || true)

    STAGE_END_EPOCH=$(date +%s)
    STAGE_END_ISO=$(date -Iseconds)
    STAGE_DURATION=$((STAGE_END_EPOCH - STAGE_START_EPOCH))
    ELAPSED_TOTAL=$((STAGE_END_EPOCH - RUN_START_EPOCH))

    update_checkpoint "$TEST_ID" "$STAGE_STATUS" "$RUN_CODE" "${RESULT_PATH:-}" "${SCORE:-}" "${CASE_PASSES:-}" "${CASE_TOTAL:-}" "$STAGE_START_ISO" "$STAGE_END_ISO"

    read PASSED_TESTS FAILED_TESTS <<< "$(checkpoint_counts)"

    printf '{"time":"%s","model":"%s","runtime":"%s","test_id":"%s","status":"%s","exit_code":%s,"score":"%s","passes":"%s","total":"%s","result_path":"%s","stage_index":%s,"total_stages":%s,"passed_stages":%s,"failed_stages":%s,"stage_start":"%s","stage_end":"%s","duration_seconds":%s,"elapsed_total_seconds":%s}\n' \
      "$STAGE_END_ISO" "$MODEL" "$RUNTIME_BASE" "$TEST_ID" "$STAGE_STATUS" "$RUN_CODE" \
      "${SCORE:-}" "${CASE_PASSES:-}" "${CASE_TOTAL:-}" "${RESULT_PATH:-}" \
      "$((PASSED_TESTS + FAILED_TESTS))" "$TOTAL_TESTS" "$PASSED_TESTS" "$FAILED_TESTS" \
      "$STAGE_START_ISO" "$STAGE_END_ISO" "$STAGE_DURATION" "$ELAPSED_TOTAL" >> "$STAGE_FILE"

    printf '{"time":"%s","run_start":"%s","model":"%s","runtime":"%s","current_test":"%s","completed_stages":%s,"total_stages":%s,"passed_stages":%s,"failed_stages":%s,"skipped_stages":%s,"last_status":"%s","last_result_path":"%s","last_duration_seconds":%s,"elapsed_total_seconds":%s,"checkpoint_file":"%s"}\n' \
      "$STAGE_END_ISO" "$RUN_START_ISO" "$MODEL" "$RUNTIME_BASE" "$TEST_ID" "$((PASSED_TESTS + FAILED_TESTS))" "$TOTAL_TESTS" "$PASSED_TESTS" "$FAILED_TESTS" "$SKIPPED_TESTS" "$STAGE_STATUS" "${RESULT_PATH:-}" "$STAGE_DURATION" "$ELAPSED_TOTAL" "$CHECKPOINT_FILE" > "$STATUS_FILE"

    echo "--- ${TEST_ID} done ---"
done

echo ""
echo "=== bench-pipeline SUMMARY ==="
checkpoint_test_summary
echo "Skipped tests this invocation: ${SKIPPED_TESTS}"

RUN_END_EPOCH=$(date +%s)
RUN_END_ISO=$(date -Iseconds)
RUN_DURATION=$((RUN_END_EPOCH - RUN_START_EPOCH))
printf '{"run_start":"%s","run_end":"%s","model":"%s","runtime":"%s","total_stages":%s,"passed_stages":%s,"failed_stages":%s,"skipped_stages":%s,"duration_seconds":%s,"stage_updates_file":"%s","status_file":"%s","checkpoint_file":"%s"}\n' \
  "$RUN_START_ISO" "$RUN_END_ISO" "$MODEL" "$RUNTIME_BASE" "$TOTAL_TESTS" "$PASSED_TESTS" "$FAILED_TESTS" "$SKIPPED_TESTS" "$RUN_DURATION" "$STAGE_FILE" "$STATUS_FILE" "$CHECKPOINT_FILE" > "$FINAL_FILE"

echo "=== bench-pipeline COMPLETE ==="
