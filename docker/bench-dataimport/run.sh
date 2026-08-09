#!/bin/bash
set -euo pipefail

# bench-dataimport: Data import capability benchmark
# Tests a model's ability to write converters, generate reference.json, and
# understand data schemas for the DaedalMap data pipeline.

SUITE="dataimport"

# --- Defaults ---
MODEL=""
RUNTIME_BASE=""
TASKS=""
LIMIT=""
RUN_NAME=""
RUN_CLASS="provisional"
RESULTS_DIR="/results"
SCRIPTS_DIR="/benchmark-scripts"
CASES_FILE="/opt/bench/dataimport_cases.json"
SYSTEM_PROMPT_FILE="/opt/bench/dataimport_system_prompt.md"
USE_MODEL_PROMPTS=1
TUNING_PROFILES=""
RAW_DIR="/raw"
RECORDS_PATH="/mnt/shared/plans/shoulders/benchmarking/results/model_benchmark_records.jsonl"
REFERENCE_OUTPUT="/mnt/shared/plans/shoulders/benchmarking/results/MODEL_BENCHMARK_REFERENCE.md"
SCOREBOARD_OUTPUT="/mnt/shared/plans/shoulders/benchmarking/results/model_library_scoreboard.json"
METHODOLOGY_ID="bench-dataimport/capability"
METHODOLOGY_VERSION="1.0.0"
COMPARISON_GROUP="dataimport-capability-v1"

# --- Argument parsing ---
while [[ $# -gt 0 ]]; do
  case "$1" in
    --model) MODEL="$2"; shift 2 ;;
    --runtime-base) RUNTIME_BASE="$2"; shift 2 ;;
    --tasks) TASKS="$2"; shift 2 ;;
    --limit) LIMIT="$2"; shift 2 ;;
    --run-name) RUN_NAME="$2"; shift 2 ;;
    --run-class) RUN_CLASS="$2"; shift 2 ;;
    --results-dir) RESULTS_DIR="$2"; shift 2 ;;
    --scripts-dir) SCRIPTS_DIR="$2"; shift 2 ;;
    --cases-file) CASES_FILE="$2"; shift 2 ;;
    --system-prompt-file) SYSTEM_PROMPT_FILE="$2"; shift 2 ;;
    --use-model-prompts) USE_MODEL_PROMPTS="$2"; shift 2 ;;
    --tuning-profiles) TUNING_PROFILES="$2"; shift 2 ;;
    --raw-dir) RAW_DIR="$2"; shift 2 ;;
    --records) RECORDS_PATH="$2"; shift 2 ;;
    --reference-output) REFERENCE_OUTPUT="$2"; shift 2 ;;
    --scoreboard-output) SCOREBOARD_OUTPUT="$2"; shift 2 ;;
    *) echo "Unknown arg: $1"; exit 1 ;;
  esac
done

if [[ -z "$MODEL" || -z "$RUNTIME_BASE" ]]; then
  echo "ERROR: --model and --runtime-base are required"
  exit 1
fi
if [[ ! "$RUN_CLASS" =~ ^(smoke|provisional|validated|full)$ ]]; then
  echo "ERROR: --run-class must be smoke, provisional, validated, or full"
  exit 1
fi
if [[ "$USE_MODEL_PROMPTS" != "0" && "$USE_MODEL_PROMPTS" != "1" ]]; then
  echo "ERROR: --use-model-prompts must be 0 or 1"
  exit 1
fi
if [[ -n "$LIMIT" && "$LIMIT" != "all" && ! "$LIMIT" =~ ^[1-9][0-9]*$ ]]; then
  echo "ERROR: --limit must be a positive integer or 'all'"
  exit 1
fi
if [[ ! -f "$CASES_FILE" ]]; then
  echo "ERROR: cases file not found: $CASES_FILE"
  exit 1
fi

MODEL_SAFE=$(printf '%s' "$MODEL" | sed 's/[^A-Za-z0-9_.-]/_/g')
RUN_ID="${RUN_NAME:-$(date +%Y%m%d_%H%M%S)}"
if [[ ! "$RUN_ID" =~ ^[A-Za-z0-9_.-]+$ ]]; then
  echo "ERROR: --run-name may contain only letters, digits, dot, underscore, and hyphen"
  exit 1
fi
RUN_DIR="${RESULTS_DIR}/bench-${SUITE}_${MODEL_SAFE}_${RUN_ID}"
STATUS_FILE="${RUN_DIR}/status.json"
STAGE_FILE="${RUN_DIR}/stage_updates.jsonl"
FINAL_FILE="${RUN_DIR}/final_summary.json"
WORK_DIR="/tmp/bench_dataimport_${MODEL_SAFE}_${RUN_ID}"

mkdir -p "$RUN_DIR" "$WORK_DIR"

# --- Available tasks ---
ALL_TASKS="converter,reference,schema_understanding"
if [[ -z "$TASKS" ]]; then
  TASKS="$ALL_TASKS"
fi
IFS=',' read -ra REQUESTED_TASKS <<< "$TASKS"
for task in "${REQUESTED_TASKS[@]}"; do
  case "$task" in
    converter|reference|schema_understanding) ;;
    *) echo "ERROR: unknown task: $task"; exit 1 ;;
  esac
done

echo "=== bench-dataimport ==="
echo "Model:   $MODEL"
echo "Runtime: $RUNTIME_BASE"
echo "Tasks:   $TASKS"
echo "Limit:   ${LIMIT:-all}"
echo "Run:     $RUN_ID"
echo "Output:  $RUN_DIR"
echo ""

# --- Verify runtime ---
echo "Checking runtime..."
if ! MODELS_RESPONSE=$(python3 - "$RUNTIME_BASE" <<'PYEOF'
import json, sys, urllib.request
with urllib.request.urlopen(f"{sys.argv[1].rstrip('/')}/v1/models", timeout=10) as response:
    data = json.loads(response.read())
if not isinstance(data.get("data"), list):
    raise SystemExit("response does not contain a data array")
print(json.dumps(data))
PYEOF
); then
  echo "ERROR: Runtime returned an invalid /v1/models response"
  exit 1
fi
echo "Runtime OK"

# --- Resolve system prompt ---
# Use DATA_IMPORT_RIG.md as system prompt (the same doc used in real pipeline)
SYSTEM_PROMPT=""
if [[ "$USE_MODEL_PROMPTS" == "1" && -f "$SYSTEM_PROMPT_FILE" ]]; then
  SYSTEM_PROMPT=$(cat "$SYSTEM_PROMPT_FILE")
  echo "System prompt: $SYSTEM_PROMPT_FILE ($(wc -c < "$SYSTEM_PROMPT_FILE") bytes)"
elif [[ "$USE_MODEL_PROMPTS" == "1" && -n "$TUNING_PROFILES" && -f "$TUNING_PROFILES" ]]; then
  # Try to extract from tuning profiles
  SYSTEM_PROMPT=$(python3 - "$TUNING_PROFILES" "$MODEL" <<'PYEOF'
import json, sys
profiles_path, model = sys.argv[1:3]
with open(profiles_path, encoding="utf-8") as f:
    profiles = json.load(f)
for key in profiles.get('models', {}):
    if model in key or key in model:
        sp = profiles['models'][key].get('system_prompt', '')
        if sp:
            print(sp)
            sys.exit(0)
print('')
PYEOF
)
  if [[ -n "$SYSTEM_PROMPT" ]]; then
    echo "System prompt: from tuning profiles"
  fi
fi

if [[ -z "$SYSTEM_PROMPT" ]]; then
  echo "WARN: No system prompt found. Using minimal fallback."
  SYSTEM_PROMPT="You are a data engineering assistant. Follow instructions exactly. Output only what is requested."
fi

# --- Init status ---
python3 - "$STATUS_FILE" "$MODEL" "$RUNTIME_BASE" "$TASKS" "$LIMIT" <<'PYEOF'
import json, os, sys
from datetime import datetime
status_file, model, runtime, tasks_str, limit = sys.argv[1:6]
tasks = tasks_str.split(",")
if os.path.exists(status_file):
    with open(status_file, encoding="utf-8") as handle:
        existing = json.load(handle)
    expected = (model, runtime, tasks)
    actual = (existing.get("model"), existing.get("runtime"), existing.get("tasks_requested"))
    if actual != expected:
        raise SystemExit(f"existing run checkpoint does not match requested run: {status_file}")
    raise SystemExit(0)
status = {
    "run_start": datetime.now().isoformat(),
    "model": model,
    "runtime": runtime,
    "tasks_requested": tasks,
    "limit": limit or "all",
    "tasks": {t: {"state": "pending", "exit_code": None, "started_at": None, "ended_at": None} for t in tasks},
    "updated_at": datetime.now().isoformat()
}
with open(status_file, 'w') as f:
    json.dump(status, f, indent=2)
PYEOF
echo "Status initialized"

# --- Helper: send prompt to model ---
send_prompt() {
  local user_prompt="$1"
  local max_tokens="${2:-4096}"
  local temp="${3:-0.1}"

  python3 - "$RUNTIME_BASE" "$MODEL" "$SYSTEM_PROMPT" "$user_prompt" "$max_tokens" "$temp" <<'PYEOF'
import json, sys, urllib.request, time

runtime_base, model, system_prompt, user_prompt, max_tokens, temp = sys.argv[1:7]

payload = {
    "model": model,
    "messages": [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ],
    "temperature": float(temp),
    "max_tokens": int(max_tokens)
}

req = urllib.request.Request(
    f"{runtime_base}/v1/chat/completions",
    data=json.dumps(payload).encode(),
    headers={"Content-Type": "application/json"}
)

t0 = time.time()
try:
    with urllib.request.urlopen(req, timeout=600) as resp:
        result = json.loads(resp.read())
    message = result["choices"][0]["message"]
    content = message.get("content") or message.get("reasoning_content") or ""
    if not content.strip():
        raise ValueError("chat completion returned no content")
    usage = result.get("usage", {})
    elapsed = time.time() - t0
    output = {
        "content": content,
        "usage": usage,
        "time": elapsed,
        "error": None
    }
except Exception as e:
    output = {
        "content": "",
        "usage": {},
        "time": time.time() - t0,
        "error": str(e)
    }

print(json.dumps(output))
PYEOF
}

load_cases() {
  local task="$1"
  python3 - "$CASES_FILE" "$task" "$LIMIT" <<'PYEOF'
import json, sys

cases_path, task, limit = sys.argv[1:4]
with open(cases_path, encoding="utf-8") as handle:
    data = json.load(handle)
cases = data["tasks"][task]["cases"]
if limit and limit != "all":
    cases = cases[:int(limit)]
print(json.dumps(cases))
PYEOF
}

# --- Helper: update task status ---
update_task_status() {
  local task="$1"
  local state="$2"
  local exit_code="${3:-null}"

  python3 - "$STATUS_FILE" "$task" "$state" "$exit_code" <<'PYEOF'
import json, sys
from datetime import datetime
status_file, task, state, exit_code = sys.argv[1:5]
with open(status_file) as f:
    status = json.load(f)
if exit_code == "null":
    exit_code = None
else:
    exit_code = int(exit_code)
if state == "running":
    status["tasks"][task]["started_at"] = datetime.now().isoformat()
elif state in ("completed", "failed"):
    status["tasks"][task]["ended_at"] = datetime.now().isoformat()
status["tasks"][task]["state"] = state
status["tasks"][task]["exit_code"] = exit_code
status["updated_at"] = datetime.now().isoformat()
with open(status_file, 'w') as f:
    json.dump(status, f, indent=2)
PYEOF
}

# --- Helper: record result to JSONL ledger ---
record_result() {
  local test_id="$1"
  local score="$2"
  local metric="$3"
  local notes="${4:-}"

  local recorder="${SCRIPTS_DIR}/scripts/active/record_benchmark_result.py"
  if [[ ! -f "$recorder" ]]; then
    echo "ERROR: recorder not found: $recorder"
    return 1
  fi
  python3 "$recorder" \
    --model "$MODEL" \
    --test-id "$test_id" \
    --score "$score" \
    --raw-harness-score "$score" \
    --metric "$metric" \
    --run-class "$RUN_CLASS" \
    --sample-count 1 \
    --harness "bench-${SUITE}" \
    --suite "$RUN_ID" \
    --methodology-id "$METHODOLOGY_ID" \
    --methodology-version "$METHODOLOGY_VERSION" \
    --comparison-group "$COMPARISON_GROUP" \
    --run-at "$(date -Iseconds)" \
    --notes "$notes" \
    --records "$RECORDS_PATH" \
    --reference-output "$REFERENCE_OUTPUT" \
    --scoreboard-output "$SCOREBOARD_OUTPUT"

  python3 - "$STAGE_FILE" "$test_id" "$score" "$metric" "$notes" <<'PYEOF'
import json
import sys
from datetime import datetime
stage_file, test_id, score, metric, notes = sys.argv[1:6]
row = {'test_id': test_id, 'status': 'success', 'score': float(score), 'metric': metric, 'notes': notes, 'at': datetime.now().isoformat()}
with open(stage_file, 'a', encoding='utf-8') as f:
    f.write(json.dumps(row) + '\n')
PYEOF
}

record_failure() {
  local test_id="$1"
  local failure_kind="$2"
  local failure_message="$3"
  local recorder="${SCRIPTS_DIR}/scripts/active/record_benchmark_result.py"
  if [[ ! -f "$recorder" ]]; then
    echo "ERROR: recorder not found: $recorder"
    return 1
  fi
  python3 "$recorder" \
    --model "$MODEL" \
    --test-id "$test_id" \
    --status failure \
    --run-class "$RUN_CLASS" \
    --harness "bench-${SUITE}" \
    --suite "$RUN_ID" \
    --methodology-id "$METHODOLOGY_ID" \
    --methodology-version "$METHODOLOGY_VERSION" \
    --comparison-group "$COMPARISON_GROUP" \
    --run-at "$(date -Iseconds)" \
    --failure-kind "$failure_kind" \
    --failure-message "$failure_message" \
    --failed-request-count 1 \
    --records "$RECORDS_PATH" \
    --reference-output "$REFERENCE_OUTPUT" \
    --scoreboard-output "$SCOREBOARD_OUTPUT"

  python3 - "$STAGE_FILE" "$test_id" "$failure_kind" "$failure_message" <<'PYEOF'
import json
import sys
from datetime import datetime
stage_file, test_id, failure_kind, failure_message = sys.argv[1:5]
row = {'test_id': test_id, 'status': 'failure', 'score': None, 'failure_kind': failure_kind, 'notes': failure_message, 'at': datetime.now().isoformat()}
with open(stage_file, 'a', encoding='utf-8') as f:
    f.write(json.dumps(row) + '\n')
PYEOF
}

# --- Helper: strip markdown fences ---
strip_fences() {
  python3 -c "
import sys
text = sys.stdin.read()
if text.strip().startswith('\`\`\`'):
    lines = text.strip().split('\n')
    lines = [l for l in lines if not l.strip().startswith('\`\`\`')]
    text = '\n'.join(lines)
print(text)
"
}

score_converter_structure() {
  local script_file="$1"
  python3 - "$script_file" <<'PYEOF'
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    code = handle.read()
checks = (
    "pandas" in code or "pd" in code,
    "to_parquet" in code or "write_table" in code,
    "loc_id" in code,
    "to_numeric" in code or "float64" in code or "astype" in code,
    "print" in code,
    "snappy" in code,
)
print(f"{sum(checks) / len(checks):.4f}")
PYEOF
}

# ==========================================================
# TASK: converter
# ==========================================================
run_converter_task() {
  echo ""
  echo "--- Running task: converter ---"
  update_task_status "converter" "running"

  local task_dir="${RUN_DIR}/converter"
  mkdir -p "$task_dir"

  local cases_json
  cases_json=$(load_cases "converter")

  local total_cases
  total_cases=$(echo "$cases_json" | python3 -c "import json,sys; print(len(json.loads(sys.stdin.read())))")
  local passed=0
  local failed=0
  local case_idx=0

  while IFS= read -r case_line; do
    [[ -z "$case_line" ]] && continue
    case_idx=$((case_idx + 1))
    local case_id test_id case_name raw_snippet source_id
    case_id=$(echo "$case_line" | python3 -c "import json,sys; print(json.loads(sys.stdin.read())['case_id'])")
    test_id=$(echo "$case_line" | python3 -c "import json,sys; print(json.loads(sys.stdin.read())['test_id'])")
    case_name=$(echo "$case_line" | python3 -c "import json,sys; print(json.loads(sys.stdin.read())['name'])")
    source_id=$(echo "$case_line" | python3 -c "import json,sys; print(json.loads(sys.stdin.read())['source_id'])")

    echo "  Case $case_idx/$total_cases: $case_id ($case_name)"

    # Build the user prompt from the case
    local user_prompt
    user_prompt=$(echo "$case_line" | python3 -c "
import json, sys
case = json.loads(sys.stdin.read())
parts = []
parts.append(f'Write a Python converter for {case[\"source_id\"]}.')
parts.append(f'')
if 'raw_data_url' in case:
    parts.append(f'Raw data location: /tmp/bench_raw/{case[\"raw_filename\"]}')
elif 'raw_data_snippet' in case:
    parts.append(f'Sample of the raw data:')
    parts.append(case['raw_data_snippet'])
parts.append(f'Output parquet to: /tmp/bench_out/{case[\"source_id\"]}.parquet')
parts.append(f'')
if 'hints' in case:
    h = case['hints']
    if 'loc_id_source' in h:
        parts.append(f'- loc_id source: {h[\"loc_id_source\"]}')
    if 'drop_aggregates' in h:
        parts.append(f'- {h[\"drop_aggregates\"]}')
    if 'time_column' in h:
        parts.append(f'- Time column: {h[\"time_column\"]}')
    if 'drop_columns' in h:
        parts.append(f'- Drop columns: {json.dumps(h[\"drop_columns\"])}')
    if 'format' in h:
        parts.append(f'- Format note: {h[\"format\"]}')
    if 'gotcha' in h:
        parts.append(f'- Gotcha: {h[\"gotcha\"]}')
parts.append(f'')
parts.append('Requirements:')
parts.append('- loc_id as FIRST column, using ISO3 format')
parts.append('- All metric columns as float64')
parts.append('- Year as int64')
parts.append('- Snappy compression')
parts.append('- Print row count, unique loc_id count, and column list when done')
parts.append('')
parts.append('Output ONLY the Python script. No explanation.')
print('\n'.join(parts))
")

    # Send prompt
    local response
    response=$(send_prompt "$user_prompt" 4096 0.1)

    local content error
    content=$(echo "$response" | python3 -c "import json,sys; print(json.loads(sys.stdin.read())['content'])")
    error=$(echo "$response" | python3 -c "import json,sys; print(json.loads(sys.stdin.read()).get('error') or '')")

    if [[ -n "$error" ]]; then
      echo "    ERROR: $error"
      failed=$((failed + 1))
      record_failure "$test_id" "request_failure" "$error"
      continue
    fi

    # Strip fences and save
    local script_file="${task_dir}/${case_id}_convert.py"
    echo "$content" | strip_fences > "$script_file"

    # Save response metadata
    python3 - "${task_dir}/${case_id}_response.json" "$response" <<'PYEOF'
import json, sys
r = json.loads(sys.argv[2])
r['content'] = r['content'][:200] + '...'
with open(sys.argv[1], 'w', encoding='utf-8') as f:
    json.dump(r, f, indent=2)
PYEOF

    # For CV-001 (owid_co2), we can actually run the converter if data is available
    if [[ "$case_id" == "CV-001" ]]; then
      mkdir -p /tmp/bench_raw /tmp/bench_out
      local raw_filename raw_file
      raw_filename=$(echo "$case_line" | python3 -c "import json,sys; print(json.loads(sys.stdin.read()).get('raw_filename',''))")
      raw_file="${RAW_DIR}/${raw_filename}"
      if [[ -n "$raw_filename" && -f "$raw_file" ]]; then
          ln -sf "$raw_file" "/tmp/bench_raw/$raw_filename"
          echo "    Running converter..."
          local run_output run_rc
          set +e
          run_output=$(python3 "$script_file" 2>&1)
          run_rc=$?
          set -e

          echo "$run_output" > "${task_dir}/${case_id}_run_output.txt"

          if [[ $run_rc -eq 0 && -f "/tmp/bench_out/owid_co2.parquet" ]]; then
            echo "    Converter ran successfully"

            # Validate output
            local val_score
            val_score=$(python3 - "$case_line" <<'VALEOF'
import json, sys, pyarrow.parquet as pq

case = json.loads(sys.argv[1])
expected = case.get("expected", {})
t = pq.read_table("/tmp/bench_out/owid_co2.parquet")
df = t.to_pandas()
s = t.schema
cols = [f.name for f in s]

checks = 0
passes = 0

# Row count
checks += 1
if expected.get("min_rows", 0) <= len(df) <= expected.get("max_rows", 999999):
    passes += 1

# loc_id count
checks += 1
nloc = df["loc_id"].nunique()
if expected.get("min_loc_ids", 0) <= nloc <= expected.get("max_loc_ids", 999):
    passes += 1

# loc_id first
checks += 1
if cols[0] == "loc_id":
    passes += 1

# No duplicates
checks += 1
if df.duplicated(["loc_id", "year"]).sum() == 0:
    passes += 1

# All metrics float64
checks += 1
non_double = [f.name for f in s if f.name not in ("loc_id", "year", "timestamp", "source") and str(f.type) != "double"]
if len(non_double) == 0:
    passes += 1

# Year range
checks += 1
if df["year"].min() <= expected.get("year_min", 9999) and df["year"].max() >= expected.get("year_max_gte", 0):
    passes += 1

score = passes / checks if checks > 0 else 0
print(f"{score:.4f}")
VALEOF
)
            echo "    Validation score: $val_score"
            record_result "$test_id" "$val_score" "converter_correct" ""
          else
            echo "    Converter FAILED (exit $run_rc)"
            record_result "$test_id" "0.0" "converter_runs" "exit_code=$run_rc"
          fi
      else
        local struct_score
        struct_score=$(score_converter_structure "$script_file")
        echo "    Raw fixture not staged; structure score: $struct_score"
        record_result "$test_id" "$struct_score" "converter_structure" "raw fixture not staged at $raw_file"
      fi
    else
      local struct_score
      struct_score=$(score_converter_structure "$script_file")
      echo "    Structure score: $struct_score"
      record_result "$test_id" "$struct_score" "converter_structure" ""
    fi
  done < <(printf '%s' "$cases_json" | python3 -c "
import json, sys
cases = json.loads(sys.stdin.read())
for c in cases:
    print(json.dumps(c))
")

  if [[ "$failed" -gt 0 ]]; then
    update_task_status "converter" "failed" "1"
  else
    update_task_status "converter" "completed" "0"
  fi
  echo "  Converter task complete"
}

# ==========================================================
# TASK: reference
# ==========================================================
run_reference_task() {
  echo ""
  echo "--- Running task: reference ---"
  update_task_status "reference" "running"

  local task_dir="${RUN_DIR}/reference"
  mkdir -p "$task_dir"

  local cases_json
  cases_json=$(load_cases "reference")

  local total_cases
  total_cases=$(echo "$cases_json" | python3 -c "import json,sys; print(len(json.loads(sys.stdin.read())))")
  local case_idx=0
  local failed=0

  while IFS= read -r case_line; do
    [[ -z "$case_line" ]] && continue
    case_idx=$((case_idx + 1))
    local case_id test_id case_name
    case_id=$(echo "$case_line" | python3 -c "import json,sys; print(json.loads(sys.stdin.read())['case_id'])")
    test_id=$(echo "$case_line" | python3 -c "import json,sys; print(json.loads(sys.stdin.read())['test_id'])")
    case_name=$(echo "$case_line" | python3 -c "import json,sys; print(json.loads(sys.stdin.read())['name'])")

    echo "  Case $case_idx/$total_cases: $case_id ($case_name)"

    # Build prompt based on case type
    local user_prompt
    user_prompt=$(echo "$case_line" | python3 -c "
import json, sys
case = json.loads(sys.stdin.read())

if case['case_id'] == 'RF-003':
    metrics = case['metric_columns']
    parts = [
        'For the following metric columns, assign the correct aggregation rule.',
        'Rules: sum (for totals), weighted_avg (for per-capita/per-unit), skip (for percentages/shares/growth rates).',
        '',
        f'Metric columns: {metrics}',
        '',
        'Output a JSON object mapping each metric to its aggregation rule.',
        'Example: {\"population\": \"sum\", \"co2_per_capita\": \"weighted_avg\"}',
        '',
        'Output ONLY valid JSON. No explanation.'
    ]
else:
    si = case.get('source_info', {})
    parts = [
        f'Write reference.json for {si.get(\"source_id\", \"unknown\")}.',
        '',
        'Source info:',
        f'- Name: {si.get(\"source_name\", \"\")}',
        f'- URL: {si.get(\"source_url\", \"\")}',
        f'- License: {si.get(\"license\", \"\")}',
        f'- Category: {si.get(\"category\", \"\")}',
        f'- Geographic level: {si.get(\"geographic_level\", \"\")}',
        f'- Geographic coverage: {si.get(\"geographic_coverage\", \"\")}',
        '',
        f'Metric columns: {case.get(\"metric_columns\", \"\")}',
        '',
        'Requirements:',
        '- Must use the nested structure: {\"source\": {...}, \"metrics\": {...}}',
        '- Every metric column needs a human-readable name, unit, and aggregation rule',
        '- Keywords must include common synonyms and acronyms that users would search for',
        '',
        'Output ONLY valid JSON. No markdown fences, no explanation.'
    ]

print('\n'.join(parts))
")

    local response
    response=$(send_prompt "$user_prompt" 8192 0.1)

    local content error
    content=$(echo "$response" | python3 -c "import json,sys; print(json.loads(sys.stdin.read())['content'])")
    error=$(echo "$response" | python3 -c "import json,sys; print(json.loads(sys.stdin.read()).get('error') or '')")

    if [[ -n "$error" ]]; then
      echo "    ERROR: $error"
      failed=$((failed + 1))
      record_failure "$test_id" "request_failure" "$error"
      continue
    fi

    local clean_content
    clean_content=$(echo "$content" | strip_fences)
    echo "$clean_content" > "${task_dir}/${case_id}_output.json"

    local score_output
    score_output=$(python3 - "$case_line" "$clean_content" <<'SCOREEOF'
import json, sys

case = json.loads(sys.argv[1])
raw_text = sys.argv[2]
results = {}
try:
    ref = json.loads(raw_text)
    results["valid_json"] = True
except json.JSONDecodeError:
    results["valid_json"] = False
    results["score"] = 0.0
    print(json.dumps(results))
    sys.exit(0)

expected = case.get("expected", {})
checks = 0
passes = 0
if case["case_id"] == "RF-003":
    for metric, exp_rule in case.get("expected_aggregations", {}).items():
        checks += 1
        actual = ref.get(metric, "")
        if isinstance(actual, dict):
            actual = actual.get("aggregation", "")
        if actual == exp_rule:
            passes += 1
        else:
            results[f"mismatch_{metric}"] = f"expected={exp_rule}, got={actual}"
else:
    checks += 1
    if "source" in ref and "metrics" in ref:
        passes += 1
        results["has_nested"] = True
    else:
        results["has_nested"] = False
    metrics = ref.get("metrics", {})
    if expected.get("metric_count"):
        checks += 1
        if len(metrics) == expected["metric_count"]:
            passes += 1
        results["metric_count"] = len(metrics)
    for field in ["name", "unit", "aggregation"]:
        if expected.get(f"all_have_{field}"):
            checks += 1
            has_all = all(isinstance(v, dict) and field in v for v in metrics.values())
            if has_all:
                passes += 1
            results[f"all_have_{field}"] = has_all
    keywords = ref.get("source", {}).get("keywords", [])
    results["keyword_count"] = len(keywords)
    expected_kws = case.get("expected_keywords", [])
    if expected_kws:
        kw_lower = [k.lower() for k in keywords]
        gaps = [t for t in expected_kws if not any(t.lower() in s for s in kw_lower)]
        results["keyword_gaps"] = gaps
        results["keyword_gap_count"] = len(gaps)
        checks += 1
        if len(gaps) <= expected.get("max_keyword_gaps", 3):
            passes += 1
    if expected.get("min_keywords"):
        checks += 1
        if len(keywords) >= expected["min_keywords"]:
            passes += 1
results["score"] = passes / checks if checks > 0 else 0
print(json.dumps(results))
SCOREEOF
)

    local score
    score=$(echo "$score_output" | python3 -c "import json,sys; print(json.loads(sys.stdin.read()).get('score', 0))")
    echo "    Score: $score"
    echo "$score_output" | python3 -c "import json,sys; print(json.dumps(json.loads(sys.stdin.read()), indent=2))" > "${task_dir}/${case_id}_score.json"

    local metric_name="reference_quality"
    if [[ "$case_id" == "RF-003" ]]; then
      metric_name="aggregation_accuracy"
    fi
    record_result "$test_id" "$score" "$metric_name" ""
  done < <(printf '%s' "$cases_json" | python3 -c "
import json, sys
cases = json.loads(sys.stdin.read())
for c in cases:
    print(json.dumps(c))
")

  if [[ "$failed" -gt 0 ]]; then
    update_task_status "reference" "failed" "1"
  else
    update_task_status "reference" "completed" "0"
  fi
  echo "  Reference task complete"
}

# ==========================================================
# TASK: schema_understanding
# ==========================================================
run_schema_understanding_task() {
  echo ""
  echo "--- Running task: schema_understanding ---"
  update_task_status "schema_understanding" "running"

  local task_dir="${RUN_DIR}/schema_understanding"
  mkdir -p "$task_dir"

  local cases_json
  cases_json=$(load_cases "schema_understanding")

  local total_cases
  total_cases=$(echo "$cases_json" | python3 -c "import json,sys; print(len(json.loads(sys.stdin.read())))")
  local case_idx=0
  local failed=0

  while IFS= read -r case_line; do
    [[ -z "$case_line" ]] && continue
    case_idx=$((case_idx + 1))
    local case_id test_id case_name
    case_id=$(echo "$case_line" | python3 -c "import json,sys; print(json.loads(sys.stdin.read())['case_id'])")
    test_id=$(echo "$case_line" | python3 -c "import json,sys; print(json.loads(sys.stdin.read())['test_id'])")
    case_name=$(echo "$case_line" | python3 -c "import json,sys; print(json.loads(sys.stdin.read())['name'])")

    echo "  Case $case_idx/$total_cases: $case_id ($case_name)"

    local prompt_context
    prompt_context=$(echo "$case_line" | python3 -c "import json,sys; print(json.loads(sys.stdin.read())['prompt_context'])")
    local description
    description=$(echo "$case_line" | python3 -c "import json,sys; print(json.loads(sys.stdin.read())['description'])")
    local user_prompt="$description

Here is the data context:
$prompt_context

Analyze this and provide your assessment as JSON. Output ONLY valid JSON with your findings."

    local response
    response=$(send_prompt "$user_prompt" 2048 0.1)

    local content error
    content=$(echo "$response" | python3 -c "import json,sys; print(json.loads(sys.stdin.read())['content'])")
    error=$(echo "$response" | python3 -c "import json,sys; print(json.loads(sys.stdin.read()).get('error') or '')")

    if [[ -n "$error" ]]; then
      echo "    ERROR: $error"
      failed=$((failed + 1))
      record_failure "$test_id" "request_failure" "$error"
      continue
    fi

    local clean_content output_file
    clean_content=$(echo "$content" | strip_fences)
    output_file="${task_dir}/${case_id}_output.json"
    echo "$clean_content" > "$output_file"

    local score
    score=$(python3 - "$case_line" "$output_file" <<'PYEOF'
import json, sys

case = json.loads(sys.argv[1])
expected = case.get("expected", {})
with open(sys.argv[2], encoding="utf-8") as handle:
    response_text = handle.read().lower()
checks = 0
passes = 0
for value in expected.values():
    checks += 1
    if isinstance(value, str):
        passes += value.lower() in response_text
    elif isinstance(value, bool):
        passes += str(value).lower() in response_text
    elif isinstance(value, list):
        hits = sum(1 for item in value if str(item).lower() in response_text)
        passes += hits >= len(value) / 2
print(f"{passes / checks if checks else 0:.4f}")
PYEOF
)

    echo "    Score: $score"
    record_result "$test_id" "$score" "schema_understanding" ""
  done < <(printf '%s' "$cases_json" | python3 -c "
import json, sys
cases = json.loads(sys.stdin.read())
for c in cases:
    print(json.dumps(c))
")

  if [[ "$failed" -gt 0 ]]; then
    update_task_status "schema_understanding" "failed" "1"
  else
    update_task_status "schema_understanding" "completed" "0"
  fi
  echo "  Schema understanding task complete"
}

# ==========================================================
# Main task loop
# ==========================================================
IFS=',' read -ra TASK_LIST <<< "$TASKS"
FAILURES=0

for task in "${TASK_LIST[@]}"; do
  # Check if already completed (resume support)
  local_state=$(python3 - "$STATUS_FILE" "$task" <<'PYEOF'
import json
import sys
with open(sys.argv[1], encoding="utf-8") as f:
    s = json.load(f)
print(s.get('tasks', {}).get(sys.argv[2], {}).get('state', 'pending'))
PYEOF
)

  if [[ "$local_state" == "completed" ]]; then
    echo "Skipping completed task: $task"
    continue
  fi

  case "$task" in
    converter) run_converter_task ;;
    reference) run_reference_task ;;
    schema_understanding) run_schema_understanding_task ;;
    *) echo "ERROR: unknown task after preflight: $task"; exit 1 ;;
  esac
done

FAILURES=$(python3 - "$STATUS_FILE" <<'PYEOF'
import json, sys
with open(sys.argv[1], encoding="utf-8") as handle:
    status = json.load(handle)
print(sum(1 for task in status.get("tasks", {}).values() if task.get("state") == "failed"))
PYEOF
)

# --- Final summary ---
echo ""
echo "=== Summary ==="
python3 - "$STATUS_FILE" "$STAGE_FILE" "$FINAL_FILE" <<'SUMEOF'
import json, sys
from datetime import datetime

status_file, stage_file, final_file = sys.argv[1:4]

with open(status_file) as f:
    status = json.load(f)

# Read all stage results
results = []
try:
    with open(stage_file) as f:
        for line in f:
            if line.strip():
                results.append(json.loads(line))
except FileNotFoundError:
    pass

# Compute summary
successful = [row for row in results if row.get("status") == "success"]
failed = [row for row in results if row.get("status") == "failure"]
total = len(results)
avg_score = sum(row["score"] for row in successful) / len(successful) if successful else 0

summary = {
    "model": status["model"],
    "run_id": status.get("run_start", ""),
    "tasks_completed": sum(1 for t in status["tasks"].values() if t["state"] == "completed"),
    "tasks_total": len(status["tasks"]),
    "total_cases": total,
    "successful_cases": len(successful),
    "failed_cases": len(failed),
    "average_score": round(avg_score, 4),
    "results": results,
    "completed_at": datetime.now().isoformat()
}

with open(final_file, 'w') as f:
    json.dump(summary, f, indent=2)

print(f"Tasks: {summary['tasks_completed']}/{summary['tasks_total']} completed")
print(f"Cases: {summary['total_cases']}")
print(f"Average score: {summary['average_score']:.2%}")
print(f"Results: {final_file}")
SUMEOF

exit $FAILURES
