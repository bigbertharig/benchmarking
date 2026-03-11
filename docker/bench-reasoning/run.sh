#!/bin/bash
set -euo pipefail

# Defaults
MODEL=""
RUNTIME_BASE="http://localhost:11436"
TASKS="gsm8k,bbh,drop,mmlu_pro,ifeval"
LIMIT="150"
RESULTS_DIR="/results"
NUM_FEWSHOT=""
TOKENIZER=""
RUN_NAME=""
SCRIPTS_DIR="/benchmark-scripts"
USE_MODEL_PROMPTS=1
PROMPT_PROFILES=""
TUNING_PROFILES=""
REQUIRE_MODEL_PROMPT=1

while [[ $# -gt 0 ]]; do
    case "$1" in
        --model) MODEL="$2"; shift 2 ;;
        --runtime-base) RUNTIME_BASE="$2"; shift 2 ;;
        --tasks) TASKS="$2"; shift 2 ;;
        --limit) LIMIT="$2"; shift 2 ;;
        --results-dir) RESULTS_DIR="$2"; shift 2 ;;
        --num-fewshot) NUM_FEWSHOT="$2"; shift 2 ;;
        --tokenizer) TOKENIZER="$2"; shift 2 ;;
        --run-name) RUN_NAME="$2"; shift 2 ;;
        --scripts-dir) SCRIPTS_DIR="$2"; shift 2 ;;
        --use-model-prompts) USE_MODEL_PROMPTS=1; shift 1 ;;
        --no-model-prompts) USE_MODEL_PROMPTS=0; shift 1 ;;
        --prompt-profiles) PROMPT_PROFILES="$2"; shift 2 ;;
        --tuning-profiles) TUNING_PROFILES="$2"; shift 2 ;;
        --require-model-prompt) REQUIRE_MODEL_PROMPT=1; shift 1 ;;
        --allow-generic-prompt-fallback) REQUIRE_MODEL_PROMPT=0; shift 1 ;;
        *) echo "Unknown arg: $1"; exit 1 ;;
    esac
done

if [ -z "$MODEL" ]; then
    echo "ERROR: --model is required (e.g. --model qwen2.5-coder:7b)"
    exit 1
fi

if [ -z "$PROMPT_PROFILES" ]; then
    PROMPT_PROFILES="${SCRIPTS_DIR}/custom_tasks/model_prompt_profiles.json"
fi
if [ -z "$TUNING_PROFILES" ]; then
    TUNING_PROFILES="${SCRIPTS_DIR}/model_tuning_profiles.json"
fi

MODEL_SAFE=$(echo "$MODEL" | tr ':/' '_')

if [ -n "$RUN_NAME" ]; then
    OUTPUT_DIR="${RESULTS_DIR}/bench-reasoning_${MODEL_SAFE}_${RUN_NAME}"
else
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    OUTPUT_DIR="${RESULTS_DIR}/bench-reasoning_${MODEL_SAFE}_${TIMESTAMP}"
fi

STATUS_FILE="${OUTPUT_DIR}/status.json"
mkdir -p "$OUTPUT_DIR"

init_status() {
    python3 - "$STATUS_FILE" "$MODEL" "$RUNTIME_BASE" "$TASKS" "$LIMIT" "$NUM_FEWSHOT" <<'PY'
import json, os, sys
status_file, model, runtime, tasks, limit, num_fewshot = sys.argv[1:7]
if os.path.exists(status_file):
    sys.exit(0)
data = {
    "run_start": __import__("datetime").datetime.now().isoformat(),
    "model": model,
    "runtime": runtime,
    "tasks_requested": [t.strip() for t in tasks.split(",") if t.strip()],
    "limit": limit,
    "num_fewshot": num_fewshot,
    "tasks": {},
    "updated_at": __import__("datetime").datetime.now().isoformat(),
}
with open(status_file, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2)
PY
}

update_task_status() {
    local task="$1"
    local state="$2"
    local exit_code="$3"
    local task_output_dir="$4"
    local started_at="$5"
    local ended_at="$6"

    python3 - "$STATUS_FILE" "$task" "$state" "$exit_code" "$task_output_dir" "$started_at" "$ended_at" <<'PY'
import json, sys
status_file, task, state, exit_code, task_output_dir, started_at, ended_at = sys.argv[1:8]
with open(status_file, "r", encoding="utf-8") as f:
    data = json.load(f)

tasks = data.setdefault("tasks", {})
entry = tasks.get(task, {})
entry.update({
    "state": state,
    "exit_code": int(exit_code),
    "output_dir": task_output_dir,
    "started_at": started_at,
    "ended_at": ended_at,
})
tasks[task] = entry

data["updated_at"] = __import__("datetime").datetime.now().isoformat()
with open(status_file, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2)
PY
}

task_completed() {
    local task="$1"
    python3 - "$STATUS_FILE" "$task" <<'PY'
import json, sys
status_file, task = sys.argv[1:3]
try:
    with open(status_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    state = ((data.get("tasks") or {}).get(task) or {}).get("state", "")
    print("yes" if state == "completed" else "no")
except Exception:
    print("no")
PY
}

summarize_status() {
    python3 - "$STATUS_FILE" <<'PY'
import json, sys
status_file = sys.argv[1]
with open(status_file, "r", encoding="utf-8") as f:
    data = json.load(f)

tasks = data.get("tasks", {})
completed = sorted([k for k, v in tasks.items() if v.get("state") == "completed"])
failed = sorted([k for k, v in tasks.items() if v.get("state") == "failed"])
print(f"Completed tasks: {len(completed)}")
if completed:
    print("  " + ", ".join(completed))
print(f"Failed tasks: {len(failed)}")
if failed:
    print("  " + ", ".join(failed))
PY
}

echo "=== bench-reasoning ==="
echo "Model: $MODEL"
echo "Runtime: $RUNTIME_BASE"
echo "Tasks: $TASKS"
echo "Results: $RESULTS_DIR"
[ -n "$LIMIT" ] && echo "Limit: $LIMIT samples per task"
[ -n "$RUN_NAME" ] && echo "Run name: $RUN_NAME"
echo "Use model prompts: $USE_MODEL_PROMPTS"
echo "Prompt profiles: $PROMPT_PROFILES"
echo "Tuning profiles: $TUNING_PROFILES"
echo "Require model prompt: $REQUIRE_MODEL_PROMPT"
echo "Checkpoint file: $STATUS_FILE"

# Verify runtime is reachable
if ! curl -s "${RUNTIME_BASE}/v1/models" > /dev/null 2>&1; then
    echo "ERROR: Cannot reach llama-compatible runtime at ${RUNTIME_BASE}"
    exit 1
fi

SYSTEM_PROMPT=""
PROMPT_SOURCE="disabled"
if [ "$USE_MODEL_PROMPTS" -eq 1 ]; then
    if [ ! -f "$PROMPT_PROFILES" ] || [ ! -f "$TUNING_PROFILES" ]; then
        echo "ERROR: prompt profile files missing."
        echo "Expected:"
        echo "  $PROMPT_PROFILES"
        echo "  $TUNING_PROFILES"
        echo "Mount benchmark scripts, e.g. -v /mnt/shared/plans/shoulders/benchmarking:/benchmark-scripts:ro"
        exit 1
    fi
    readarray -t _PROMPT_INFO < <(python3 - "$MODEL" "$PROMPT_PROFILES" "$TUNING_PROFILES" "$REQUIRE_MODEL_PROMPT" <<'PY'
import base64, json, re, sys
model, prompt_profiles_path, tuning_profiles_path, require_flag = sys.argv[1:5]
require_model_prompt = str(require_flag).strip() == "1"

def norm(v: str) -> str:
    s = v.strip().lower()
    if s.endswith(".gguf"):
        s = s[:-5]
    return re.sub(r"[^a-z0-9]+", "", s)

def lookup(models_obj, model_name: str):
    model_l = model_name.strip().lower()
    model_n = norm(model_name)
    if isinstance(models_obj, list):
        exact_norm = []
        fuzzy = []
        for item in models_obj:
            if not isinstance(item, dict):
                continue
            mid = str(item.get("id", "")).strip()
            if not mid:
                continue
            if mid.lower() == model_l:
                return item
            mid_n = norm(mid)
            if mid_n == model_n:
                exact_norm.append(item)
            elif model_n and mid_n and (model_n in mid_n or mid_n in model_n):
                fuzzy.append(item)
        if len(exact_norm) == 1:
            return exact_norm[0]
        if len(fuzzy) == 1:
            return fuzzy[0]
        return None
    if isinstance(models_obj, dict):
        exact_norm = []
        fuzzy = []
        for key, value in models_obj.items():
            if not isinstance(value, dict):
                continue
            key_s = str(key).strip()
            if key_s.lower() == model_l:
                return value
            key_n = norm(key_s)
            if key_n == model_n:
                exact_norm.append(value)
            elif model_n and key_n and (model_n in key_n or key_n in model_n):
                fuzzy.append(value)
        if len(exact_norm) == 1:
            return exact_norm[0]
        if len(fuzzy) == 1:
            return fuzzy[0]
    return None

profiles = json.load(open(prompt_profiles_path, "r", encoding="utf-8"))
tuning = json.load(open(tuning_profiles_path, "r", encoding="utf-8"))
prompt = ""
source = "none"

item = lookup(profiles.get("models", []), model)
if item:
    sp = str(item.get("system_prompt", "")).strip()
    if sp:
        prompt = sp
        source = "prompt_profiles:model_system_prompt"

if not prompt:
    t_item = lookup(tuning.get("models", {}), model)
    if t_item:
        sp = str(t_item.get("system_prompt", "")).strip()
        if sp:
            prompt = sp
            source = "tuning_profiles:model_system_prompt"

if not prompt and not require_model_prompt:
    dp = str(profiles.get("default_system_prompt", "")).strip()
    if dp:
        prompt = dp
        source = "prompt_profiles:default_system_prompt"

if not prompt and require_model_prompt:
    raise SystemExit(
        f"No model-specific system prompt found for '{model}'. "
        "Add system_prompt for this model in prompt/tuning profiles."
    )

print(source)
print(base64.b64encode(prompt.encode("utf-8")).decode("ascii"))
PY
)
    PROMPT_SOURCE="${_PROMPT_INFO[0]:-none}"
    if [ "${#_PROMPT_INFO[@]}" -ge 2 ] && [ -n "${_PROMPT_INFO[1]}" ]; then
        SYSTEM_PROMPT="$(printf '%s' "${_PROMPT_INFO[1]}" | base64 -d)"
    fi
fi
echo "Resolved prompt source: $PROMPT_SOURCE"

# Verify runtime has a model loaded
if ! curl -s "${RUNTIME_BASE}/v1/models" | python3 -c "
import sys, json

data = json.load(sys.stdin)
models = [str(m.get('id', '')).strip() for m in data.get('data', []) if isinstance(m, dict)]
if not models:
    print('ERROR: No models reported by runtime')
    sys.exit(1)
print(f'Runtime loaded model(s): {models}')
"; then
    exit 1
fi

init_status

IFS=',' read -ra TASK_ARRAY <<< "$TASKS"
FAILED_COUNT=0

for TASK in "${TASK_ARRAY[@]}"; do
    TASK="$(echo "$TASK" | xargs)"
    [ -z "$TASK" ] && continue

    if [ "$(task_completed "$TASK")" = "yes" ]; then
        echo ""
        echo "--- Skipping ${TASK} (already completed in checkpoint) ---"
        continue
    fi

    TASK_OUTPUT_DIR="${OUTPUT_DIR}/${TASK}"
    mkdir -p "$TASK_OUTPUT_DIR"

    MODEL_ARGS="model=${MODEL},base_url=${RUNTIME_BASE}/v1/chat/completions,num_concurrent=1,max_retries=3,tokenized_requests=False"

    CMD=(
      lm_eval
      --model local-chat-completions
      --model_args "$MODEL_ARGS"
      --tasks "$TASK"
      --output_path "$TASK_OUTPUT_DIR"
      --apply_chat_template
      --batch_size 1
    )

    if [ -n "$SYSTEM_PROMPT" ]; then
      CMD+=(--system_instruction "$SYSTEM_PROMPT")
    fi

    if [ -n "$LIMIT" ]; then
      CMD+=(--limit "$LIMIT")
    fi

    if [ -n "$NUM_FEWSHOT" ]; then
      CMD+=(--num_fewshot "$NUM_FEWSHOT")
    fi

    STAGE_START=$(date -Iseconds)

    echo ""
    echo "--- Running task: $TASK ---"
    echo "Running: ${CMD[*]}"

    set +e
    "${CMD[@]}"
    EXIT_CODE=$?
    set -e

    STAGE_END=$(date -Iseconds)

    if [ "$EXIT_CODE" -eq 0 ]; then
      update_task_status "$TASK" "completed" "$EXIT_CODE" "$TASK_OUTPUT_DIR" "$STAGE_START" "$STAGE_END"
      echo "--- ${TASK} complete ---"
    else
      update_task_status "$TASK" "failed" "$EXIT_CODE" "$TASK_OUTPUT_DIR" "$STAGE_START" "$STAGE_END"
      echo "--- ${TASK} failed (exit ${EXIT_CODE}) ---"
      FAILED_COUNT=$((FAILED_COUNT + 1))
    fi
done

echo ""
echo "=== bench-reasoning SUMMARY ==="
summarize_status
echo "Status file: $STATUS_FILE"
echo "Results root: $OUTPUT_DIR"

if [ "$FAILED_COUNT" -gt 0 ]; then
    echo "=== bench-reasoning FAILED (task failures: $FAILED_COUNT) ==="
    exit 1
fi

echo "=== bench-reasoning COMPLETE ==="
exit 0
