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
PATCH_REASONING_CONTENT_FALLBACK=0
PATCH_BOOLEAN_ANSWER_CANON=0
PATCH_THINK_TAG_STRIP=0
GEN_KWARGS=""
SYSTEM_PROMPT_OVERRIDE=""
DISABLE_THINKING=0
RESERVATION_SHARED_PATH="${BENCHMARK_RESERVATION_SHARED_PATH:-/mnt/shared}"
RESERVATION_OWNER="${BENCHMARK_RESERVATION_OWNER:-bench-reasoning}"
RESERVATION_RUN_ID=""
RESERVATION_HELPER=""
RESERVATION_PORT=""
AUTO_RESERVE_ENABLED="${BENCHMARK_DISABLE_AUTO_RESERVE:-0}"
RECORD_RESULT_SCRIPT=""

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
        --patch-reasoning-content-fallback) PATCH_REASONING_CONTENT_FALLBACK=1; shift 1 ;;
        --patch-boolean-answer-canonicalization) PATCH_BOOLEAN_ANSWER_CANON=1; shift 1 ;;
        --patch-think-tag-strip) PATCH_THINK_TAG_STRIP=1; shift 1 ;;
        --gen-kwargs) GEN_KWARGS="$2"; shift 2 ;;
        --system-prompt-override) SYSTEM_PROMPT_OVERRIDE="$2"; shift 2 ;;
        --disable-thinking) DISABLE_THINKING=1; shift 1 ;;
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
RESERVATION_RUN_ID="${RUN_NAME:-$(basename "$OUTPUT_DIR")}"
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

record_result_row() {
    local test_id="$1"
    local score="$2"
    local metric="$3"
    local notes="${4:-}"
    if [ ! -f "$RECORD_RESULT_SCRIPT" ]; then
        echo "WARNING: record script missing: $RECORD_RESULT_SCRIPT"
        return 0
    fi
    python3 "$RECORD_RESULT_SCRIPT" \
        --model "$MODEL" \
        --test-id "$test_id" \
        --score "$score" \
        --metric "$metric" \
        --harness "bench-reasoning" \
        --suite "${RUN_NAME:-bench-reasoning}" \
        --run-at "$(date -Iseconds)" \
        --notes "$notes" >/dev/null || echo "WARNING: failed to record result for ${MODEL} ${test_id}"
}

record_reasoning_task_results() {
    local task="$1"
    local task_output_dir="$2"
    if [ ! -d "$task_output_dir" ]; then
        return 0
    fi
    python3 - "$task" "$task_output_dir" <<'PY' | while IFS=$'\t' read -r test_id score metric notes; do
import json, sys
from pathlib import Path

task, task_output_dir = sys.argv[1:3]
root = Path(task_output_dir)
files = sorted(root.glob("**/results_*.json"))
if not files:
    raise SystemExit(0)
data = json.loads(files[-1].read_text(encoding="utf-8"))
results = data.get("results", {})
groups = data.get("groups", {})

def emit(test_id, score, metric, notes=""):
    if score is None:
        return
    print(f"{test_id}\t{score}\t{metric}\t{notes}")

if task == "gsm8k":
    block = results.get("gsm8k", {})
    emit("gsm8k_strict", block.get("exact_match,strict-match"), "exact_match,strict-match")
    emit("gsm8k_flexible", block.get("exact_match,flexible-extract"), "exact_match,flexible-extract")
elif task == "bbh":
    block = groups.get("bbh") or results.get("bbh", {})
    emit("bbh", block.get("exact_match,get-answer"), "exact_match,get-answer")
elif task == "drop":
    block = results.get("drop", {})
    emit("drop_em", block.get("em,none"), "em,none")
    emit("drop_f1", block.get("f1,none"), "f1,none")
else:
    block = results.get(task, {})
    for key, value in block.items():
        if key == "alias" or key.endswith("_stderr"):
            continue
        if isinstance(value, (int, float)):
            emit(f"{task}_{key.replace(',', '_')}", value, key)
PY
        [ -z "$test_id" ] && continue
        record_result_row "$test_id" "$score" "$metric" "$notes"
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

init_status() {
    python3 - "$STATUS_FILE" "$MODEL" "$RUNTIME_BASE" "$TASKS" "$LIMIT" "$NUM_FEWSHOT" <<'PY'
import json, os, sys
status_file, model, runtime, tasks, limit, num_fewshot = sys.argv[1:7]
now = __import__("datetime").datetime.now().isoformat()
if os.path.exists(status_file):
    with open(status_file, "r", encoding="utf-8") as f:
        data = json.load(f)
else:
    data = {
        "run_start": now,
        "model": model,
        "runtime": runtime,
        "tasks": {},
    }
data["model"] = model
data["runtime"] = runtime
data["tasks_requested"] = [t.strip() for t in tasks.split(",") if t.strip()]
data["limit"] = limit
data["num_fewshot"] = num_fewshot
data["updated_at"] = now
with open(status_file, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2)
PY
}

filter_available_tasks() {
    readarray -t _TASK_FILTER < <(python3 - "$TASKS" <<'PY'
import subprocess
import sys

requested = [t.strip() for t in sys.argv[1].split(",") if t.strip()]
if not requested:
    print("")
    print("")
    raise SystemExit(0)

try:
    proc = subprocess.run(
        [sys.executable, "-m", "lm_eval", "ls", "tasks"],
        capture_output=True,
        text=True,
        check=True,
    )
    listing = proc.stdout
except Exception:
    print(",".join(requested))
    print("")
    raise SystemExit(0)

available = set()
for raw in listing.splitlines():
    line = raw.strip()
    if not line:
        continue
    if line.startswith("Available tasks") or line.startswith("Total tasks"):
        continue
    # Skip table separator lines (e.g. |---|---|)
    if line.replace("|", "").replace("-", "").strip() == "":
        continue
    # Skip header lines
    if "Group" in line and "Config Location" in line:
        continue
    if line.startswith("-"):
        line = line[1:].strip()
    # Handle pipe-delimited table format (lm-eval >= 0.4.8)
    if line.startswith("|"):
        cells = [c.strip() for c in line.split("|") if c.strip()]
        if cells:
            available.add(cells[0])
        continue
    if not line:
        continue
    if "," in line:
        parts = [p.strip() for p in line.split(",") if p.strip()]
        for part in parts:
            available.add(part)
        continue
    token = line.split()[0].strip()
    if token:
        available.add(token)

kept = [t for t in requested if t in available]
missing = [t for t in requested if t not in available]
print(",".join(kept))
print(",".join(missing))
PY
)

    TASKS_FILTERED="${_TASK_FILTER[0]:-}"
    TASKS_MISSING="${_TASK_FILTER[1]:-}"

    if [ -n "$TASKS_MISSING" ]; then
        echo "WARNING: skipping unavailable lm-eval tasks: $TASKS_MISSING"
    fi

    if [ -z "$TASKS_FILTERED" ]; then
        echo "ERROR: none of the requested tasks are available in this lm-eval image."
        echo "Requested: $TASKS"
        [ -n "$TASKS_MISSING" ] && echo "Missing: $TASKS_MISSING"
        exit 1
    fi

    TASKS="$TASKS_FILTERED"
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
echo "Patch reasoning_content fallback: $PATCH_REASONING_CONTENT_FALLBACK"
echo "Patch boolean answer canonicalization: $PATCH_BOOLEAN_ANSWER_CANON"
echo "Patch think-tag strip: $PATCH_THINK_TAG_STRIP"
[ -n "$GEN_KWARGS" ] && echo "Gen kwargs override: $GEN_KWARGS"
[ -n "$SYSTEM_PROMPT_OVERRIDE" ] && echo "System prompt override: enabled"
echo "Disable thinking: $DISABLE_THINKING"
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

if [ -n "$SYSTEM_PROMPT_OVERRIDE" ]; then
    SYSTEM_PROMPT="$SYSTEM_PROMPT_OVERRIDE"
    PROMPT_SOURCE="cli:system-prompt-override"
    echo "Resolved prompt source: $PROMPT_SOURCE"
fi

if [ "$PATCH_REASONING_CONTENT_FALLBACK" -eq 1 ]; then
    python3 - "$PATCH_BOOLEAN_ANSWER_CANON" <<'PY'
from pathlib import Path
import sys

patch_boolean_canon = str(sys.argv[1]).strip() == "1"
target = Path("/opt/bench/lib/python3.12/site-packages/lm_eval/models/openai_completions.py")
if not target.exists():
    print(f"ERROR: patch target missing: {target}")
    sys.exit(1)

src = target.read_text(encoding="utf-8")
old = 'tmp[choices["index"]] = choices["message"]["content"]'
if patch_boolean_canon:
    new = (
        'msg = choices.get("message", {})\n'
        '                    content = msg.get("content")\n'
        '                    if content in (None, ""):\n'
        '                        content = msg.get("reasoning_content", "")\n'
        '                    if isinstance(content, str):\n'
        '                        _re = __import__("re")\n'
        '                        _m = _re.search(r"the answer is\\\\s*(true|false)", content, _re.IGNORECASE)\n'
        '                        if _m:\n'
        '                            content = f"So the answer is {_m.group(1).capitalize()}."\n'
        '                    tmp[choices["index"]] = content'
    )
else:
    new = (
        'msg = choices.get("message", {})\n'
        '                    content = msg.get("content")\n'
        '                    if content in (None, ""):\n'
        '                        content = msg.get("reasoning_content", "")\n'
        '                    tmp[choices["index"]] = content'
    )

if old in src:
    target.write_text(src.replace(old, new, 1), encoding="utf-8")
    if patch_boolean_canon:
        print("Applied lm-eval parser patch: reasoning_content fallback + boolean canonicalization enabled")
    else:
        print("Applied lm-eval parser patch: reasoning_content fallback enabled")
else:
    print("lm-eval parser patch skipped: target pattern not found (already patched or upstream changed)")
PY
fi

if [ "$PATCH_THINK_TAG_STRIP" -eq 1 ]; then
    python3 - <<'PY'
from pathlib import Path

target = Path("/opt/bench/lib/python3.12/site-packages/lm_eval/models/openai_completions.py")
if not target.exists():
    print(f"ERROR: patch target missing: {target}")
    raise SystemExit(1)

src = target.read_text(encoding="utf-8")
patched = False

# Patch 1: Remove all stop sequences from API calls, stash on instance.
# Many models (DeepSeek-R1 think chains, Phi-4 CoT with markdown) produce
# intermediate text that matches stop sequences (\n\n, ., Q:) before the
# actual answer. We remove stops from the API call so the model generates
# a full response, then re-apply stops client-side after cleaning.
old_stop = '"stop": stop[:4],'
new_stop = '"stop": [],  # patch: stops applied client-side'
if old_stop in src:
    src = src.replace(old_stop, new_stop, 1)
    patched = True
    print("  - Removed all stop sequences from API calls")

# Patch 2: In _create_payload, stash stops on self for later use.
# Insert a line before the return dict to save stops on the instance.
old_return = '        return {\n            "messages": messages,'
new_return = '        self._stashed_stops = list(stop[:4])\n        return {\n            "messages": messages,'
if old_return in src:
    src = src.replace(old_return, new_return, 1)
    patched = True
    print("  - Stashing stop sequences on instance for client-side re-apply")

# Patch 3: Strip <think>...</think> from response content and re-apply
# all original stop sequences client-side on the cleaned content.
old_content = 'tmp[choices["index"]] = choices["message"]["content"]'
new_content = (
    'import re as _re\n'
    '                    _raw = choices.get("message", {}).get("content", "") or ""\n'
    '                    # Strip <think>...</think> blocks (Type B: DeepSeek-R1, Qwen 3.6)\n'
    '                    _clean = _re.sub(r"<think>[\\s\\S]*?</think>\\s*", "", _raw).strip()\n'
    '                    # Strip <|channel>thought prefix (Type A: Gemma 4)\n'
    '                    _clean = _re.sub(r"^<\\|channel>[a-z]+\\s*", "", _clean).strip()\n'
    '                    # If content empty, try reasoning_content fallback\n'
    '                    if not _clean:\n'
    '                        _clean = choices.get("message", {}).get("reasoning_content", "") or ""\n'
    '                        _clean = _clean.strip()\n'
    '                    tmp[choices["index"]] = _clean'
)
if old_content in src:
    src = src.replace(old_content, new_content, 1)
    patched = True
    print("  - Added think-tag strip to response parser")

if patched:
    target.write_text(src, encoding="utf-8")
    print("Applied lm-eval think-tag strip patch v3 (all stops removed, client-side re-apply)")
else:
    print("Think-tag strip patch skipped: target patterns not found (already patched or upstream changed)")

# Patch 4: In api_models.py, re-apply stops client-side after parse_generations.
# parse_generations is static so can't access instance stops. We patch the
# sync generate path (num_concurrent=1) to apply stops on parsed results.
target2 = Path("/opt/bench/lib/python3.12/site-packages/lm_eval/models/api_models.py")
if target2.exists():
    src2 = target2.read_text(encoding="utf-8")
    patched2 = False

    # Patch the sync path: wrap parse_generations result with stop re-apply
    old_sync = '''                for generated_text, context in zip(
                    self.parse_generations(
                        outputs=outputs,
                        contexts=contexts,
                    ),'''
    new_sync = '''                _parsed = self.parse_generations(outputs=outputs, contexts=contexts)
                _stops = getattr(self, "_stashed_stops", [])
                if _stops:
                    _cleaned = []
                    for _t in _parsed:
                        if _t:
                            for _s in _stops:
                                if _s and _s in _t:
                                    _t = _t[:_t.index(_s)]
                        _cleaned.append(_t)
                    _parsed = _cleaned
                for generated_text, context in zip(
                    _parsed,'''
    if old_sync in src2:
        src2 = src2.replace(old_sync, new_sync, 1)
        patched2 = True
        print("  - Patched sync generate path to re-apply stops client-side")

    # Also patch the async path (in case num_concurrent > 1 is ever used)
    old_async = '''            answers = (
                self.parse_generations(
                    outputs=outputs,
                )
                if generate'''
    new_async = '''            _raw_answers = (
                self.parse_generations(
                    outputs=outputs,
                )
                if generate'''
    if old_async in src2:
        src2 = src2.replace(old_async, new_async, 1)
        # Find where answers is used after the ternary and add stop re-apply
        old_async_use = '''            if cache_keys:
                for res, cache in zip(answers, cache_keys):'''
        new_async_use = '''            _stops = getattr(self, "_stashed_stops", [])
            if _stops and generate:
                answers = []
                for _t in _raw_answers:
                    if _t:
                        for _s in _stops:
                            if _s and _s in _t:
                                _t = _t[:_t.index(_s)]
                    answers.append(_t)
            else:
                answers = _raw_answers
            if cache_keys:
                for res, cache in zip(answers, cache_keys):'''
        if old_async_use in src2:
            src2 = src2.replace(old_async_use, new_async_use, 1)
            patched2 = True
            print("  - Patched async generate path to re-apply stops client-side")

    if patched2:
        target2.write_text(src2, encoding="utf-8")
        print("Applied api_models.py client-side stop re-apply patch")
PY
fi

# ---- Always-on extraction patches ----
# Patch BBH: make get-answer regex case-insensitive + strip markdown bold,
# enable ignore_case + ignore_punctuation on exact_match metric.
# Patch DROP: use "\n" stop instead of "." to avoid premature truncation,
# add regex filter to extract first line (answer) from model output.
python3 <<'PY_EXTRACT_FIX'
from pathlib import Path
import re

# --- BBH template fix ---
bbh_template = Path("/opt/bench/lib/python3.12/site-packages/lm_eval/tasks/bbh/cot_fewshot/_cot_fewshot_template_yaml")
if bbh_template.exists():
    src = bbh_template.read_text(encoding="utf-8")
    changed = False

    # 1. Make regex case-insensitive: (?i) prefix
    # 2. Also capture "The answer is" (capital T)
    old_regex = '        regex_pattern: "(?<=the answer is )(.*)(?=.)"'
    new_regex = '        regex_pattern: "(?i)(?<=the answer is )(.*)(?=.)"'
    if old_regex in src:
        src = src.replace(old_regex, new_regex, 1)
        changed = True
        print("  BBH: made get-answer regex case-insensitive")

    # 3. Enable ignore_case and ignore_punctuation on exact_match
    if "# ignore_case: true" in src:
        src = src.replace("# ignore_case: true", "ignore_case: true", 1)
        changed = True
        print("  BBH: enabled ignore_case on exact_match")
    if "# ignore_punctuation: true" in src:
        src = src.replace("# ignore_punctuation: true", "ignore_punctuation: true", 1)
        changed = True
        print("  BBH: enabled ignore_punctuation on exact_match")

    # 4. Remove "\n\n" stop sequence — verbose/thinking models hit paragraph
    #    breaks before stating "the answer is X", causing near-zero extraction.
    #    "Q" stop + max_gen_toks bounds generation.
    if '"\\n\\n"' in src:
        src = src.replace('    - "\\n\\n"\n', '')
        changed = True
        print("  BBH: removed \\n\\n stop sequence")

    # 5. Reduce max_gen_toks from 1024 to 512 — without \n\n stop, 1024 can
    #    OOM large models on 3090. 512 is enough for CoT + "the answer is X".
    if "max_gen_toks: 1024" in src:
        src = src.replace("max_gen_toks: 1024", "max_gen_toks: 512")
        changed = True
        print("  BBH: reduced max_gen_toks to 512")

    if changed:
        bbh_template.write_text(src, encoding="utf-8")
        print("Applied BBH extraction fix")
    else:
        print("BBH extraction fix skipped (already applied or template changed)")

# --- DROP extraction fix ---
# Problem: stop sequence "." truncates model output before the answer
# on models that produce preamble text (e.g., "Based on the passage.").
# Fix: change stop to newline with max_gen_toks=512.
# Note: 512 (not 64) needed for thinking models (Gemma 4) where reasoning
# tokens count toward max_gen_toks. Non-thinking models still stop at \n
# quickly so the higher limit doesn't affect them.
drop_yaml = Path("/opt/bench/lib/python3.12/site-packages/lm_eval/tasks/drop/default.yaml")
if drop_yaml.exists():
    lines = drop_yaml.read_text(encoding="utf-8").splitlines(keepends=True)
    new_lines = []
    changed = False
    i = 0
    while i < len(lines):
        line = lines[i]
        # Replace '    - "."' with '    - "\n"' and add max_gen_toks
        if line.strip() == '- "."' and i > 0 and "until:" in lines[i-1]:
            new_lines.append(line.replace('"."', r'"\n"'))
            # Add max_gen_toks after the until block
            indent = "  "
            new_lines.append(indent + "max_gen_toks: 512\n")
            changed = True
            print("  DROP: changed stop from '.' to newline, added max_gen_toks=512")
        else:
            new_lines.append(line)
        i += 1

    if changed:
        drop_yaml.write_text("".join(new_lines), encoding="utf-8")
        print("Applied DROP extraction fix")
    else:
        print("DROP extraction fix skipped (already applied or template changed)")

PY_EXTRACT_FIX

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

filter_available_tasks
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
    if [ "$DISABLE_THINKING" -eq 1 ]; then
      MODEL_ARGS="$(python3 - "$MODEL" "$RUNTIME_BASE" <<'PY'
import json, sys
model, runtime_base = sys.argv[1:3]
print(json.dumps({
    "model": model,
    "base_url": f"{runtime_base}/v1/chat/completions",
    "num_concurrent": 1,
    "max_retries": 3,
    "tokenized_requests": False,
    "extra_body": {"chat_template_kwargs": {"enable_thinking": False}},
}))
PY
)"
    fi

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

    if [ -n "$GEN_KWARGS" ]; then
      CMD+=(--gen_kwargs "$GEN_KWARGS")
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
      record_reasoning_task_results "$TASK" "$TASK_OUTPUT_DIR"
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
