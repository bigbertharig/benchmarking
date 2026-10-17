#!/usr/bin/env bash
# Phase 4.5 settings experiments for one brain model on the 3090.
# usage: p45.sh <model-id> <tag> <gguf> <ctx> "<off runtime args>" "<on runtime args>"
set -uo pipefail
model=$1; tag=$2; gguf=$3; ctx=$4; off_args=$5; on_args=$6
RR=~/llm_orchestration/shared/scripts/llama_runtime/run_runtime.sh
L=/mnt/shared/logs/benchmarks
common=(--rm --network host -e BENCHMARK_DISABLE_AUTO_RESERVE=1 -v /mnt/shared:/mnt/shared
        -v /mnt/shared/plans/shoulders/benchmarking:/benchmark-scripts:ro)
load() {
  docker ps -q --filter label=org.llm-orchestration.llama-runtime=1 | xargs -r docker rm -f >/dev/null
  local extra=(); for a in $1; do extra+=(--extra-arg "$a"); done
  local s; s=$(date +%s)
  $RR --name llama-p45 --model "$gguf" --port 11434 --gpus device=0 --ctx-size "$ctx" --batch-size 128 \
      --memory-limit 10g --memory-swap 12g "${extra[@]}" >/dev/null 2>&1 || { echo "LOAD FAILED ($1)"; exit 3; }
  echo "loaded [$1] in $(( $(date +%s) - s ))s; prompt tail: $(curl -s http://127.0.0.1:11434/apply-template \
      -d '{"messages":[{"role":"user","content":"hi"}]}' | python3 -c 'import json,sys; print(repr(json.load(sys.stdin)["prompt"][-24:]))')"
}
reasoning() {  # run-suffix extra-flags...
  local run="${tag}_$1"; shift; local s; s=$(date +%s)
  docker run "${common[@]}" -v $L/bench-reasoning/history:/results bench-reasoning --model "$model" \
    --runtime-base http://localhost:11434 --run-name "$run" --run-class smoke --limit 10 --log-samples "$@" \
    > "$L/p45_${run}.log" 2>&1
  echo "$run exit=$? min=$(( ($(date +%s)-s)/60 ))"
}
geo() {  # run-suffix max_tokens
  local run="${tag}_$1"
  docker run "${common[@]}" -v $L/bench-geoimport/history:/results bench-geoimport --model "$model" \
    --runtime-base http://localhost:11434 --run-name "$run" --run-class smoke --results-dir /results \
    --tasks classification,prep_plan,prep_handoff --limit 5 --inference-config-json "{\"max_tokens\": $2}" \
    > "$L/p45_${run}.log" 2>&1
  echo "$run exit=$? $(grep -a 'score=' $L/p45_${run}.log | tr -d ' ' | tr '\n' ' ')"
}
pipeline() {  # run-suffix max_tokens
  local run="${tag}_$1"
  docker run "${common[@]}" -v $L/bench-pipeline/history:/results bench-pipeline --model "$model" \
    --runtime-base http://localhost:11434 --run-name "$run" --run-class smoke \
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
