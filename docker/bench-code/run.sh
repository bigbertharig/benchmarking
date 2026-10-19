#!/bin/bash
set -euo pipefail

MODEL=""
RUNTIME_BASE="http://localhost:11436"
TASKS="humaneval,mbpp"
RESULTS_DIR="/results"
RUN_NAME=""
RUN_CLASS="full"
# --limit N: only the first N problems of each task (a smoke; EvalPlus itself has no limit). Codegen
# gets --id_range [0,N]; EvalPlus evaluate insists on every problem, so the rest are padded with empty
# solutions (they fail at once and are not counted); pass@1 is over the N generated problems.
LIMIT=""
PREFLIGHT_ONLY=0
REQUEST_TIMEOUT="30"
RESERVATION_SHARED_PATH="${BENCHMARK_RESERVATION_SHARED_PATH:-/mnt/shared}"
RESERVATION_OWNER="${BENCHMARK_RESERVATION_OWNER:-bench-code}"
RESERVATION_RUN_ID=""
RESERVATION_HELPER=""
RESERVATION_PORT=""
AUTO_RESERVE_ENABLED="${BENCHMARK_DISABLE_AUTO_RESERVE:-0}"
RUNTIME_DOWN_GRACE_SECONDS="${BENCH_CODE_RUNTIME_DOWN_GRACE_SECONDS:-90}"
THERMAL_RUNTIME_DOWN_GRACE_SECONDS="${BENCH_CODE_THERMAL_DOWN_GRACE_SECONDS:-1200}"
WATCHDOG_POLL_SECONDS="${BENCH_CODE_WATCHDOG_POLL_SECONDS:-5}"
RECORD_RESULT_SCRIPT="${RESERVATION_SHARED_PATH}/plans/shoulders/benchmarking/scripts/active/record_benchmark_result.py"
METHODOLOGY_ID="bench-code/evalplus"
METHODOLOGY_VERSION="2.0.0"
COMPARISON_GROUP="evalplus-0.3-plus-v1"

# --- Persistent download cache ---
# lm-eval datasets (Hugging Face), EvalPlus problem files (XDG cache) and NLTK data live on
# the shared drive, so runs do not re-download them and still work when the internet is
# down. Any caller may override these; run_campaign.py sets the same paths.
BENCH_CACHE_ROOT="${BENCHMARK_CACHE_ROOT:-${RESERVATION_SHARED_PATH}/cache/benchmarks}"
if [ -d "$BENCH_CACHE_ROOT" ] && [ -w "$BENCH_CACHE_ROOT" ]; then
    export HF_HOME="${HF_HOME:-$BENCH_CACHE_ROOT/huggingface}"
    export HF_DATASETS_CACHE="${HF_DATASETS_CACHE:-$HF_HOME/datasets}"
    export XDG_CACHE_HOME="${XDG_CACHE_HOME:-$BENCH_CACHE_ROOT/xdg}"
    export NLTK_DATA="${NLTK_DATA:-$BENCH_CACHE_ROOT/nltk_data}"
    mkdir -p "$HF_DATASETS_CACHE" "$XDG_CACHE_HOME" "$NLTK_DATA"
    echo "Download cache: $BENCH_CACHE_ROOT"
else
    echo "WARNING: download cache $BENCH_CACHE_ROOT is not mounted or not writable; downloads stay in the container"
fi
if ! python3 -c "import urllib.request; urllib.request.urlopen('https://huggingface.co', timeout=5)" >/dev/null 2>&1; then
    export HF_HUB_OFFLINE=1 HF_DATASETS_OFFLINE=1
    echo "Hugging Face unreachable: using cached datasets only (HF_HUB_OFFLINE=1)"
fi

while [[ $# -gt 0 ]]; do
    case "$1" in
        --model) MODEL="$2"; shift 2 ;;
        --runtime-base) RUNTIME_BASE="$2"; shift 2 ;;
        --tasks) TASKS="$2"; shift 2 ;;
        --results-dir) RESULTS_DIR="$2"; shift 2 ;;
        --run-name) RUN_NAME="$2"; shift 2 ;;
        --run-class) RUN_CLASS="$2"; shift 2 ;;
        --limit) LIMIT="$2"; shift 2 ;;
        --preflight-only) PREFLIGHT_ONLY=1; shift 1 ;;
        --request-timeout) REQUEST_TIMEOUT="$2"; shift 2 ;;
        *) echo "Unknown arg: $1"; exit 1 ;;
    esac
done

if [ -z "$MODEL" ]; then
    echo "ERROR: --model is required (e.g. --model qwen2.5-coder:7b)"
    exit 1
fi
case "$RUN_CLASS" in
    smoke|provisional|validated|full) ;;
    *) echo "ERROR: --run-class must be smoke, provisional, validated, or full"; exit 1 ;;
esac

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

resolve_runtime_heartbeat_file() {
    python3 - "$RESERVATION_SHARED_PATH" "$RESERVATION_PORT" <<'PY'
import json, sys
from pathlib import Path
shared, port = sys.argv[1:3]
try:
    port = int(port)
except Exception:
    print("")
    raise SystemExit(0)
root = Path(shared) / "gpus"
for hb in sorted(root.glob("gpu_*/heartbeat.json")):
    try:
        data = json.load(open(hb, "r", encoding="utf-8"))
    except Exception:
        continue
    if int(data.get("runtime_port") or 0) == port:
        print(str(hb))
        raise SystemExit(0)
print("")
PY
}

RUNTIME_HEARTBEAT_FILE="$(resolve_runtime_heartbeat_file)"

runtime_reachable() {
    curl -s "${RUNTIME_BASE}/v1/models" > /dev/null 2>&1
}

runtime_watchdog_mode() {
    if [ -z "$RUNTIME_HEARTBEAT_FILE" ] || [ ! -f "$RUNTIME_HEARTBEAT_FILE" ]; then
        echo "normal"
        return
    fi
    python3 - "$RUNTIME_HEARTBEAT_FILE" <<'PY'
import json, sys
path = sys.argv[1]
try:
    data = json.load(open(path, "r", encoding="utf-8"))
except Exception:
    print("normal")
    raise SystemExit(0)
thermal = bool(data.get("thermal_pause_active", False))
phase = str(data.get("runtime_transition_phase", "") or "")
if thermal or "thermal_grace" in phase:
    print("thermal")
else:
    print("normal")
PY
}

run_codegen_with_watchdog() {
    local task="$1"
    shift
    local child_pid=""
    local down_since=0
    local last_mode=""

    "$@" &
    child_pid=$!

    while kill -0 "$child_pid" 2>/dev/null; do
        sleep "$WATCHDOG_POLL_SECONDS"

        if runtime_reachable; then
            if [ "$down_since" -gt 0 ]; then
                echo "Runtime recovered for ${task} after transient outage."
            fi
            down_since=0
            last_mode=""
            continue
        fi

        local mode grace now elapsed
        mode="$(runtime_watchdog_mode)"
        grace="$RUNTIME_DOWN_GRACE_SECONDS"
        if [ "$mode" = "thermal" ]; then
            grace="$THERMAL_RUNTIME_DOWN_GRACE_SECONDS"
        fi

        now=$(date +%s)
        if [ "$down_since" -eq 0 ]; then
            down_since="$now"
            last_mode="$mode"
            echo "WARNING: Runtime unreachable during ${task}; mode=${mode}, grace=${grace}s"
            continue
        fi

        elapsed=$((now - down_since))
        if [ "$mode" != "$last_mode" ]; then
            last_mode="$mode"
            echo "WARNING: Runtime outage mode changed during ${task}; mode=${mode}, elapsed=${elapsed}s, grace=${grace}s"
        fi

        if [ "$elapsed" -ge "$grace" ]; then
            echo "ERROR: Runtime unavailable for ${elapsed}s during ${task}; mode=${mode}, grace=${grace}s"
            kill -TERM "$child_pid" 2>/dev/null || true
            sleep 2
            kill -KILL "$child_pid" 2>/dev/null || true
            wait "$child_pid" 2>/dev/null || true
            return 1
        fi
    done

    wait "$child_pid"
}

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

record_result_row() {
    local test_id="$1"
    local score="$2"
    local metric="$3"
    local sample_count="$4"
    local notes="${5:-}"
    if [ ! -f "$RECORD_RESULT_SCRIPT" ]; then
        echo "ERROR: record script missing: $RECORD_RESULT_SCRIPT"
        return 1
    fi
    python3 "$RECORD_RESULT_SCRIPT" \
        --model "$MODEL" \
        --test-id "$test_id" \
        --score "$score" \
        --raw-harness-score "$score" \
        --metric "$metric" \
        --run-class "$RUN_CLASS" \
        --sample-count "$sample_count" \
        --harness "bench-code" \
        --suite "${RUN_NAME:-bench-code}" \
        --methodology-id "$METHODOLOGY_ID" \
        --methodology-version "$METHODOLOGY_VERSION" \
        --comparison-group "$COMPARISON_GROUP" \
        --config-id "evalplus-0.3.1-greedy" \
        --config-json '{"evalplus":"0.3.1","decoding":"greedy"}' \
        --run-at "$(date -Iseconds)" \
        --notes "$notes" >/dev/null
}

record_failure_row() {
    local test_id="$1"
    local kind="$2"
    local message="$3"
    python3 "$RECORD_RESULT_SCRIPT" \
        --model "$MODEL" \
        --test-id "$test_id" \
        --status failure \
        --run-class "$RUN_CLASS" \
        --harness "bench-code" \
        --suite "${RUN_NAME:-bench-code}" \
        --methodology-id "$METHODOLOGY_ID" \
        --methodology-version "$METHODOLOGY_VERSION" \
        --comparison-group "$COMPARISON_GROUP" \
        --failure-kind "$kind" \
        --failure-message "$message" \
        --failed-request-count 1 >/dev/null
}

record_code_task_results() {
    local task="$1"
    local task_dir="$2"
    local sample_count="$3"
    local samples="${4:-}"
    python3 - "$task" "$task_dir" "$LIMIT" "$samples" <<'PY' | while IFS=$'\t' read -r test_id score metric notes; do
import json, sys
from pathlib import Path

task, task_dir, limit, samples = sys.argv[1:5]
files = sorted(Path(task_dir).glob("*_eval_results.json"))
if not files:
    raise SystemExit(0)
data = json.loads(files[-1].read_text(encoding="utf-8"))
pass_at_1 = data.get("pass@1") or {}
base = pass_at_1.get("base")
plus = pass_at_1.get("plus")
notes = ""
if limit and samples:  # count only the problems that were generated (the padding is not)
    ids = {json.loads(l)["task_id"] for l in Path(samples).read_text(encoding="utf-8").splitlines() if l.strip()}
    data["eval"] = {k: v for k, v in (data.get("eval") or {}).items() if k in ids}
    base = plus = None
    notes = f"limit {limit}: first {len(ids)} problems"
# EvalPlus eval_results.json carries per-problem results under "eval" and no pass@1
# summary; with greedy decoding (one sample per problem) pass@1 is the pass fraction.
# "plus" means the problem passed both the base and the extra tests.
results = data.get("eval") or {}
if base is None and results:
    firsts = [samples[0] for samples in results.values() if samples]
    base = sum(s.get("base_status") == "pass" for s in firsts) / len(firsts)
    plus = sum(s.get("base_status") == "pass" and s.get("plus_status") == "pass" for s in firsts) / len(firsts)
if isinstance(base, (int, float)):
    print(f"{task}_base\t{base}\tpass@1_base\t{notes}")
if isinstance(plus, (int, float)):
    print(f"{task}_plus\t{plus}\tpass@1_plus\t{notes}")
PY
        [ -z "$test_id" ] && continue
        record_result_row "$test_id" "$score" "$metric" "$sample_count" "$notes"
    done
}

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
echo "Run class: ${RUN_CLASS}"

if [ ! -f "$RECORD_RESULT_SCRIPT" ]; then
    echo "ERROR: record script missing: $RECORD_RESULT_SCRIPT"
    exit 1
fi

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
    python3 - "$task" "$LIMIT" <<'PY'
import sys
task, limit = sys.argv[1].strip().lower(), sys.argv[2]
if task == "humaneval":
    from evalplus.data import get_human_eval_plus
    n = len(get_human_eval_plus())
elif task == "mbpp":
    from evalplus.data import get_mbpp_plus
    n = len(get_mbpp_plus())
else:
    n = 0
print(min(n, int(limit)) if limit and n else n)
PY
}

# With --limit: a copy of the samples with an empty solution for every problem not generated, so
# EvalPlus evaluate runs; prints the padded file's path.
pad_samples() {
    local task="$1" samples="$2"
    python3 - "$task" "$samples" <<'PY'
import json, sys
from pathlib import Path
task, samples = sys.argv[1].strip().lower(), Path(sys.argv[2])
if task == "humaneval":
    from evalplus.data import get_human_eval_plus as load
else:
    from evalplus.data import get_mbpp_plus as load
rows = [json.loads(l) for l in samples.read_text(encoding="utf-8").splitlines() if l.strip()]
have = {r["task_id"] for r in rows}
padded = samples.with_name(samples.stem + ".padded.jsonl")
with padded.open("w", encoding="utf-8") as f:
    for r in rows:
        f.write(json.dumps(r) + "\n")
    for tid in load():
        if tid not in have:
            f.write(json.dumps({"task_id": tid, "solution": ""}) + "\n")
print(padded)
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
    GEN_CMD=(python3 -m evalplus.codegen "$MODEL" "$TASK" --backend openai --greedy --root "$OUTPUT_DIR")
    [ -n "$LIMIT" ] && GEN_CMD+=(--id_range "[0,${LIMIT}]")
    echo "{\"task\":\"${TASK}\",\"state\":\"generating\",\"updated_at\":\"$(date -Iseconds)\"}" > "$STATUS_FILE"

    printf 'Generating:'
    printf ' %q' "${GEN_CMD[@]}"
    printf '\n'
    update_status "$TASK" "running" "0" "0" ""
    if ! run_codegen_with_watchdog "$TASK" "${GEN_CMD[@]}"; then
        echo "ERROR: ${TASK} generation aborted after runtime watchdog timeout."
        echo "{\"task\":\"${TASK}\",\"state\":\"error_runtime_timeout\",\"updated_at\":\"$(date -Iseconds)\"}" > "$STATUS_FILE"
        update_status "$TASK" "error_runtime_timeout" "0" "0" ""
        record_failure_row "${TASK}_plus" "runtime_timeout" "generation aborted after runtime watchdog timeout"
        exit 1
    fi

    # Find the generated samples file
    SAMPLE_DIR="${OUTPUT_DIR}/${TASK}"
    SAMPLE_FILE=$(find "$SAMPLE_DIR" -name "*.jsonl" ! -name "*.raw.jsonl" ! -name "*.padded.jsonl" 2>/dev/null | head -1)

    if [ -z "$SAMPLE_FILE" ]; then
        echo "ERROR: No sample file found in $SAMPLE_DIR"
        echo "{\"task\":\"${TASK}\",\"state\":\"error_missing_samples\",\"updated_at\":\"$(date -Iseconds)\"}" > "$STATUS_FILE"
        update_status "$TASK" "error_missing_samples" "0" "0" ""
        record_failure_row "${TASK}_plus" "missing_samples" "EvalPlus produced no sample file"
        INCOMPLETE_TASKS=$((INCOMPLETE_TASKS + 1))
        continue
    fi

    GENERATED_COUNT=$(wc -l < "$SAMPLE_FILE")
    EXPECTED_COUNT=$(task_expected_count "$TASK")
    echo "Generated ${GENERATED_COUNT}/${EXPECTED_COUNT} samples for ${TASK}"

    if [ "$EXPECTED_COUNT" -gt 0 ] && [ "$GENERATED_COUNT" -lt "$EXPECTED_COUNT" ]; then
        echo "WARNING: ${TASK} is incomplete; skipping evaluate until full coverage is available."
        echo "{\"task\":\"${TASK}\",\"state\":\"generated_partial\",\"generated\":${GENERATED_COUNT},\"expected\":${EXPECTED_COUNT},\"samples\":\"${SAMPLE_FILE}\",\"updated_at\":\"$(date -Iseconds)\"}" > "$STATUS_FILE"
        update_status "$TASK" "generated_partial" "$GENERATED_COUNT" "$EXPECTED_COUNT" "$SAMPLE_FILE"
        record_failure_row "${TASK}_plus" "incomplete_samples" "generated ${GENERATED_COUNT}/${EXPECTED_COUNT} required samples"
        INCOMPLETE_TASKS=$((INCOMPLETE_TASKS + 1))
        continue
    fi

    # Evaluate generated samples. Scoring runs every test in worker processes and peaked at 4.7 GB of
    # RAM for one model; several lanes scoring at once helped fill the rig's RAM on 2026-10-17. With
    # BENCH_EVAL_LOCK (a lock file on the rig's own disk, mounted in by the caller) only one scoring
    # runs at a time on the host; generation stays parallel. BENCH_EVAL_PARALLEL caps the workers.
    EVAL_SAMPLES="$SAMPLE_FILE"
    if [ -n "$LIMIT" ]; then
        EVAL_SAMPLES=$(pad_samples "$TASK" "$SAMPLE_FILE")
        echo "Limit ${LIMIT}: scoring the first ${GENERATED_COUNT} problems (the rest padded empty, not counted)"
    fi
    EVAL_CMD=(python3 -m evalplus.evaluate --dataset "$TASK" --samples "$EVAL_SAMPLES")
    [ -n "${BENCH_EVAL_PARALLEL:-}" ] && EVAL_CMD+=(--parallel "$BENCH_EVAL_PARALLEL")
    printf 'Evaluating:'; printf ' %q' "${EVAL_CMD[@]}"; printf '\n'
    set +e
    if [ -n "${BENCH_EVAL_LOCK:-}" ]; then
        echo "Waiting for the evaluation lock ${BENCH_EVAL_LOCK} (one EvalPlus scoring at a time on this host)"
        LOCK_WAIT_START=$(date +%s)
        flock "$BENCH_EVAL_LOCK" bash -c 'echo "Evaluation lock acquired after $(( $(date +%s) - $1 ))s"; shift; exec "$@"' \
            _ "$LOCK_WAIT_START" "${EVAL_CMD[@]}"
    else
        "${EVAL_CMD[@]}"
    fi
    EVAL_RC=$?
    set -e
    if [ "$EVAL_RC" -ne 0 ]; then
        update_status "$TASK" "evaluation_failed" "$GENERATED_COUNT" "$EXPECTED_COUNT" "$SAMPLE_FILE"
        record_failure_row "${TASK}_plus" "evaluation_exit" "EvalPlus evaluate exited with code ${EVAL_RC}"
        INCOMPLETE_TASKS=$((INCOMPLETE_TASKS + 1))
        continue
    fi
    echo "{\"task\":\"${TASK}\",\"state\":\"evaluated\",\"generated\":${GENERATED_COUNT},\"expected\":${EXPECTED_COUNT},\"samples\":\"${SAMPLE_FILE}\",\"updated_at\":\"$(date -Iseconds)\"}" > "$STATUS_FILE"
    update_status "$TASK" "evaluated" "$GENERATED_COUNT" "$EXPECTED_COUNT" "$SAMPLE_FILE"
    record_code_task_results "$TASK" "$TASK_DIR" "$GENERATED_COUNT" "$SAMPLE_FILE"

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
incomplete = any(
    str(item.get("state", "")) not in {"evaluated", "completed"}
    for item in (data.get("tasks") or {}).values()
)
data["state"] = "completed_with_failures" if incomplete else "completed"
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
    base = (data.get('pass@1') or {}).get('base', 'N/A')
    plus = (data.get('pass@1') or {}).get('plus', 'N/A')
    if '${LIMIT}':  # only the generated problems count
        gen = [g for g in glob.glob(os.path.dirname(f) + '/*.jsonl') if not g.endswith(('.raw.jsonl', '.padded.jsonl'))]
        ids = {json.loads(l)['task_id'] for g in gen for l in open(g) if l.strip()}
        data['eval'] = {k: v for k, v in (data.get('eval') or {}).items() if k in ids}
        base = plus = 'N/A'
    firsts = [v[0] for v in (data.get('eval') or {}).values() if v]
    if base == 'N/A' and firsts:
        base = round(sum(s.get('base_status') == 'pass' for s in firsts) / len(firsts), 3)
        plus = round(sum(s.get('base_status') == 'pass' and s.get('plus_status') == 'pass' for s in firsts) / len(firsts), 3)
    print(f'  {dataset}: pass@1 base={base}, plus={plus}')
" 2>/dev/null || echo "(could not parse results)"

if [ "$INCOMPLETE_TASKS" -gt 0 ]; then
    exit 1
fi
