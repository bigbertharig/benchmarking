#!/usr/bin/env bash
# One GTX 1060 lane: take models from a shared queue file and run Phases 2-4.5 for each on one
# GPU and port, until the queue is empty. Several lanes share one queue, so each card picks up the
# next model as soon as it frees up. Only ever touches its own container (llama-lane-gpuN);
# run_runtime.sh still loads one model at a time rig-wide.
# The lane holds a `benchmarks` lease on its GPU from the rig manager for its whole run
# (harness_lease.sh; refused card = the lane does not run) and passes it to every load.
# LANE_STOP_AFTER=3 stops each model after Phase 3 (load, litmus, decode record): a quick check.
# usage: worker_lane.sh <gpu-index> <queue-file>
set -uo pipefail
GPU=$1; QUEUE=$2
PORT=$((11434 + GPU))
NAME="llama-lane-gpu${GPU}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BENCH="$(cd "$HERE/../.." && pwd)"
RR="$(cd "$BENCH/../../.." && pwd)/scripts/llama_runtime/run_runtime.sh"
RX=/mnt/shared/plans/shoulders/benchmarking/results/runtime_experiments
L=/mnt/shared/logs/benchmarks
STAMP=$(date +%Y%m%d)
common=(--rm --network host -e BENCHMARK_DISABLE_AUTO_RESERVE=1 -v /mnt/shared:/mnt/shared
        -v /mnt/shared/plans/shoulders/benchmarking:/benchmark-scripts:ro)
say() { echo "$(date +%T) [gpu$GPU] $*"; }

load() {  # extra-args-string -> sets LOAD_S, returns nonzero on failure
  docker rm -f "$NAME" >/dev/null 2>&1
  local extra=() s
  eval "set -- $1"; for a in "$@"; do extra+=(--extra-arg "$a"); done
  s=$(date +%s.%N)
  "$RR" --name "$NAME" --model "$GGUF" --port "$PORT" --gpus "device=$GPU" --ctx-size "$CTX" \
      --batch-size "$BATCH" --parallel "$PARALLEL" --n-gpu-layers "$NGL" \
      --memory-limit 8g --memory-swap 10g ${LEASE:+--lease "$LEASE"} "${extra[@]}" \
      >/dev/null 2>"/tmp/lane_gpu${GPU}.err" || return 1
  LOAD_S=$(python3 -c "print(round($(date +%s.%N)-$s,1))")
}
prompt_tail() {
  curl -s "http://127.0.0.1:$PORT/apply-template" -d '{"messages":[{"role":"user","content":"hi"}]}' |
    python3 -c 'import json,sys; print(repr(json.load(sys.stdin)["prompt"][-24:]))'
}
reasoning() {  # run-name extra-flags...
  local run=$1; shift; local s; s=$(date +%s)
  docker run "${common[@]}" -v $L/bench-reasoning/history:/results bench-reasoning --model "$MODEL" \
    --runtime-base "http://localhost:$PORT" --run-name "$run" --run-class smoke --limit 10 --log-samples "$@" \
    > "$L/lane_${run}.log" 2>&1
  say "$run exit=$? min=$(( ($(date +%s)-s)/60 ))"
}

next_model() {  # pop the first line of the queue under a lock; empty output when done
  (
    flock 8
    head -n 1 "$QUEUE"
    sed -i '1d' "$QUEUE"
  ) 8>"$QUEUE.lock"
}

OWNER="lane-gpu$GPU"
RUN_ID="$(basename "$(dirname "$QUEUE")")"
LEASE=$("$HERE/harness_lease.sh" acquire "$GPU" "$OWNER" "$RUN_ID" "queue") || {
  say "LANE_REFUSED: the rig manager did not lease GPU $GPU to this lane"; exit 2; }
say "lease ${LEASE:-none (manager unreachable, running offline)}"
renewer=""
if [ -n "$LEASE" ]; then
  ( while sleep 120; do "$HERE/harness_lease.sh" renew "$LEASE" "$OWNER"; done ) &
  renewer=$!
fi
finish() {
  docker rm -f "$NAME" >/dev/null 2>&1
  [ -n "$renewer" ] && kill "$renewer" 2>/dev/null
  "$HERE/harness_lease.sh" release "$LEASE" "$OWNER"
}
trap finish EXIT
trap 'exit 143' TERM INT   # stop_all / operator: still run finish (container out, lease released)

while MODEL=$(next_model) && [ -n "$MODEL" ]; do
  slug=$(echo "$MODEL" | tr ':.' '__' | tr -cd 'A-Za-z0-9_-')
  eval "$(python3 "$HERE/resolve_model.py" "$MODEL")"
  say "== $MODEL: Phase 2 (registry args: ${EXTRA:-none}) $GGUF"
  if ! load "$EXTRA"; then say "LOAD FAILED $MODEL: $(grep -aE ' E |error' /tmp/lane_gpu${GPU}.err | tail -2 | tr '\n' ' ')"; continue; fi
  say "loaded in ${LOAD_S}s; vram $(nvidia-smi --query-gpu=memory.used --format=csv,noheader -i "$GPU"); prompt tail $(prompt_tail)"
  docker logs "$NAME" 2>&1 | grep -E "offloaded|thinking =" | sed "s/^/    /"
  thinking_capable=$(curl -s "http://127.0.0.1:$PORT/props" | python3 -c '
import json, sys
t = json.load(sys.stdin).get("chat_template", "")
print("yes" if any(k in t for k in ("<think>", "enable_thinking", "reasoning")) else "no")')
  say "Phase 3 litmus"; python3 "$HERE/litmus.py" "$PORT" | sed "s/^/    /"
  python3 "$HERE/runtime_char.py" "$MODEL" "$PORT" "$GPU" "$LOAD_S" "NVMe/SATA hot-set or archive, GTX 1060 lane" \
    "$RX/${slug}_runtime_characterization_${STAMP}.json" image=llama-runtime:b11669 ctx_size="$CTX" \
    batch_size="$BATCH" extra_args="${EXTRA:-none}" | grep -E "generation_tokens_per_second|avg_power_w" | sed "s/^/    /"
  if [ "${LANE_STOP_AFTER:-}" = "3" ]; then
    docker rm -f "$NAME" >/dev/null 2>&1
    say "== $MODEL done (LANE_STOP_AFTER=3)"
    continue
  fi
  say "Phase 4 smoke"
  "$HERE/phase4.sh" "$MODEL" "${slug}_w_smoke_v1" "$PORT" | sed "s/^/    /"
  if [ "$thinking_capable" = "yes" ]; then
    for variant in off on; do
      if ! load "$BASE_EXTRA --reasoning $variant"; then say "LOAD FAILED ($variant)"; continue; fi
      say "Phase 4.5 thinking $variant: loaded in ${LOAD_S}s, prompt tail $(prompt_tail)"
      if [ "$variant" = "on" ]; then
        reasoning "${slug}_w_p45_think" --tasks gsm8k,bbh --gen-kwargs "max_gen_toks=${THINK_TOKS},until=</s>"
      else
        reasoning "${slug}_w_p45_off" --tasks gsm8k,bbh
      fi
    done
  else
    say "Phase 4.5 thinking A/B skipped: template has no thinking control"
  fi
  docker rm -f "$NAME" >/dev/null 2>&1
  say "== $MODEL done"
done
say LANE_DONE
