#!/bin/bash
set -euo pipefail

MODEL=""
RUNTIME_BASE="http://localhost:11436"
TASKS="humaneval,mbpp"
RESULTS_DIR="/results"
RUN_NAME=""
PREFLIGHT_ONLY=0
REQUEST_TIMEOUT="30"

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
        continue
    fi

    # evalplus codegen: positional args are MODEL DATASET
    # Note: evalplus evaluate requires ALL problems in samples.
    GEN_CMD="python3 -m evalplus.codegen ${MODEL} ${TASK} --backend openai --greedy --root ${OUTPUT_DIR}"
    echo "{\"task\":\"${TASK}\",\"state\":\"generating\",\"updated_at\":\"$(date -Iseconds)\"}" > "$STATUS_FILE"

    echo "Generating: $GEN_CMD"
    eval $GEN_CMD

    # Find the generated samples file
    SAMPLE_DIR="${OUTPUT_DIR}/${TASK}"
    SAMPLE_FILE=$(find "$SAMPLE_DIR" -name "*.jsonl" ! -name "*.raw.jsonl" 2>/dev/null | head -1)

    if [ -z "$SAMPLE_FILE" ]; then
        echo "ERROR: No sample file found in $SAMPLE_DIR"
        echo "{\"task\":\"${TASK}\",\"state\":\"error_missing_samples\",\"updated_at\":\"$(date -Iseconds)\"}" > "$STATUS_FILE"
        continue
    fi

    GENERATED_COUNT=$(wc -l < "$SAMPLE_FILE")
    EXPECTED_COUNT=$(task_expected_count "$TASK")
    echo "Generated ${GENERATED_COUNT}/${EXPECTED_COUNT} samples for ${TASK}"

    if [ "$EXPECTED_COUNT" -gt 0 ] && [ "$GENERATED_COUNT" -lt "$EXPECTED_COUNT" ]; then
        echo "WARNING: ${TASK} is incomplete; skipping evaluate until full coverage is available."
        echo "{\"task\":\"${TASK}\",\"state\":\"generated_partial\",\"generated\":${GENERATED_COUNT},\"expected\":${EXPECTED_COUNT},\"samples\":\"${SAMPLE_FILE}\",\"updated_at\":\"$(date -Iseconds)\"}" > "$STATUS_FILE"
        INCOMPLETE_TASKS=$((INCOMPLETE_TASKS + 1))
        continue
    fi

    # Evaluate generated samples
    echo "Evaluating: python3 -m evalplus.evaluate --dataset ${TASK} --samples ${SAMPLE_FILE}"
    python3 -m evalplus.evaluate --dataset "$TASK" --samples "$SAMPLE_FILE"
    echo "{\"task\":\"${TASK}\",\"state\":\"evaluated\",\"generated\":${GENERATED_COUNT},\"expected\":${EXPECTED_COUNT},\"samples\":\"${SAMPLE_FILE}\",\"updated_at\":\"$(date -Iseconds)\"}" > "$STATUS_FILE"

    echo "--- ${TASK} done ---"
done

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
