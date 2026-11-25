#!/usr/bin/env bash
# Phase 4.5 settings experiments for one brain model on the 3090.
# usage: p45.sh <model-id> <tag> <gguf> <ctx> "<off runtime args>" "<on runtime args>"
set -euo pipefail
model=$1; tag=$2; gguf=$3; ctx=$4; off_args=$5; on_args=$6
repo=$(cd "$(dirname "$0")/../.." && pwd)
control="$repo/scripts/integration/local_runtime.py"
L="${BENCHMARK_OUTPUT_DIR:-$repo/results/p45}"
mkdir -p "$L"
profile="p45-${tag}-$(date +%s)"
loaded_profile=""
cleanup() { if [[ -n "$loaded_profile" ]]; then python3 "$control" stop --profile "$loaded_profile"; fi; }
trap cleanup EXIT
common=(--rm --network host -e BENCHMARK_DISABLE_AUTO_RESERVE=1
        -v "$repo:/benchmark-scripts:ro")
if [[ -n "${BENCHMARK_SHARED_DATA:-}" ]]; then common+=(-v "$BENCHMARK_SHARED_DATA:/mnt/shared:ro"); fi
load() {
  cleanup
  loaded_profile=""
  local settings="$L/${profile}-$RANDOM.json"
  python3 - "$model" "$gguf" "$ctx" "$1" "$settings" <<'PY'
import json,shlex,sys
from pathlib import Path
Path(sys.argv[5]).write_text(json.dumps({'model':sys.argv[1],'gguf_path':sys.argv[2],
 'ctx_size':int(sys.argv[3]),'batch_size':128,'parallel':1,'use':'benchmark','extra_args':shlex.split(sys.argv[4])}))
PY
  local selected="$(basename "$settings" .json)"
  python3 "$control" register --profile "$selected" --spec "$settings" > "$settings.register.json"
  local s; s=$(date +%s)
  python3 "$control" load --profile "$selected" > "$settings.load.json"
  loaded_profile="$selected"
  runtime_port=$(python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print(next(p["port"] for p in d["observation"]["profiles"] if p["id"]==sys.argv[2]))' "$settings.load.json" "$selected")
  echo "loaded [$1] in $(( $(date +%s) - s ))s; prompt tail: $(curl -s http://127.0.0.1:${runtime_port}/apply-template \
      -d '{"messages":[{"role":"user","content":"hi"}]}' | python3 -c 'import json,sys; print(repr(json.load(sys.stdin)["prompt"][-24:]))')"
}
reasoning() {  # run-suffix extra-flags...
  local run="${tag}_$1"; shift; local s; s=$(date +%s)
  docker run "${common[@]}" -v $L/bench-reasoning/history:/results bench-reasoning --model "$model" \
    --runtime-base http://localhost:${runtime_port} --run-name "$run" --run-class smoke --limit 10 --log-samples "$@" \
    > "$L/p45_${run}.log" 2>&1
  echo "$run exit=$? min=$(( ($(date +%s)-s)/60 ))"
}
geo() {  # run-suffix max_tokens
  local run="${tag}_$1"
  docker run "${common[@]}" -v $L/bench-geoimport/history:/results bench-geoimport --model "$model" \
    --runtime-base http://localhost:${runtime_port} --run-name "$run" --run-class smoke --results-dir /results \
    --tasks classification,prep_plan,prep_handoff --limit 5 --inference-config-json "{\"max_tokens\": $2}" \
    > "$L/p45_${run}.log" 2>&1
  echo "$run exit=$? $(grep -a 'score=' $L/p45_${run}.log | tr -d ' ' | tr '\n' ' ')"
}
pipeline() {  # run-suffix max_tokens
  local run="${tag}_$1"
  docker run "${common[@]}" -v $L/bench-pipeline/history:/results bench-pipeline --model "$model" \
    --runtime-base http://localhost:${runtime_port} --run-name "$run" --run-class smoke \
    --inference-config-json "{\"max_tokens\": $2}" > "$L/p45_${run}.log" 2>&1
  echo "$run exit=$? $(grep -a '"score"' $L/p45_${run}.log | tail -6 | tr -d ' \n')"
}
load "$off_args"
reasoning off --tasks gsm8k,bbh
geo geo_mt512 512
geo geo_mt1024 1024
load "$on_args"
reasoning think --tasks gsm8k,bbh,drop,ifeval --gen-kwargs "max_gen_toks=4096,until=</s>"
pipeline think_pipeline 4096
geo think_geo 4096
echo P45_DONE
