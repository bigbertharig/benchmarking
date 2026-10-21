#!/usr/bin/env bash
# One lane: a card group (one GPU like 1, or several like 1+3) that takes models from a shared queue
# file and runs Phases 2-4.5 for each, until the queue is empty. Several lanes share one queue, so each
# group picks up the next model as soon as it frees up.
# Loads go through the harness (llm-gateway rig manager, `rigctl load-model` over ssh): it checks the
# model fits the group and picks the context and tensor split, the rig loads it and confirms every layer
# is on the GPUs. A model that does not fit the group is skipped (LOAD FAILED with the reason).
# The lane holds a rig claim on its cards for its whole run (`rigctl claim lane-<group>`), so they stay
# reserved between loads; a refused claim = the lane does not run (LANE_REFUSED). The claim has a TTL
# that the lane renews while it runs, so a killed lane frees its cards on its own (llm-gateway
# MANAGER.md, "Reservations"). A card still busy when a load starts (another holder finishing) is
# waited for, reserved by the claim, up to LANE_LOAD_WAIT_S (default 3600 s).
# LANE_STOP_AFTER=3 stops each model after Phase 3 (load, litmus, decode record): a quick check;
# LANE_STOP_AFTER=4 after the Phase 4 smoke. LANE_START_AT=4.5 runs only the Phase 4.5 thinking A/B
# (for a model whose Phases 2-4 already ran, e.g. after a rig restart in between).
# usage: worker_lane.sh <gpu-group> <queue-file>     e.g. worker_lane.sh 1+3 queue.txt
set -uo pipefail
GROUP=$1; QUEUE=$2
GPUS=${GROUP//+/,}                 # 1,3
TAG=${GROUP//+/-}                  # 1-3
FIRST=${GROUP%%+*}
PORT=$((11434 + FIRST))            # the manager's port rule: 11434 + the lowest GPU
CLAIM="lane-$TAG"
CLAIM_TTL=900                      # renewed every 300 s while the lane runs
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RX=/mnt/shared/plans/shoulders/benchmarking/results/runtime_experiments
L=/mnt/shared/logs/benchmarks
STAMP=$(date +%Y%m%d)
HOST="${HARNESS_HOST:-pi}"
RIGCTL="${HARNESS_RIGCTL:-~/llm-gateway/tools/rigctl.py}"
common=(--rm --network host -e BENCHMARK_DISABLE_AUTO_RESERVE=1 -v /mnt/shared:/mnt/shared
        -v /mnt/shared/plans/shoulders/benchmarking:/benchmark-scripts:ro)
say() { echo "$(date +%T) [gpu$TAG] $*"; }
rigctl() {  # ssh re-splits the remote line, so every argument is quoted for the remote shell
  local q=() a
  for a in "$@"; do q+=("$(printf '%q' "$a")"); done
  ssh -o BatchMode=yes -o ConnectTimeout=10 "$HOST" python3 "$RIGCTL" "${q[@]}"
}

PROFILE=""
LOADED_ARGS=""
unload() {
  [ -n "$PROFILE" ] || return 0
  rigctl unload "$PROFILE" > /dev/null 2>&1 || say "unload of $PROFILE failed"
  PROFILE=""
}
load() {  # extra-args-string -> sets PROFILE, CTX, LOAD_S; nonzero with the reason in LOAD_ERR
  if [ -n "$PROFILE" ] && [ "$LOADED_ARGS" = "$MODEL|$1" ]; then return 0; fi  # already loaded this way
  unload
  local s out
  s=$(date +%s.%N)
  out=$(rigctl load-model "$MODEL" --gpus "$GPUS" --claim "$CLAIM" --use benchmark "--args=$1" \
        --wait "${LANE_LOAD_WAIT_S:-3600}" --json)
  LOAD_ERR=$(python3 -c 'import json,sys; d=json.loads(sys.stdin.read() or "{}"); print((d.get("error") or {}).get("message", ""))' <<< "$out" 2>/dev/null)
  if [ -n "$LOAD_ERR" ] || ! grep -q '"state": "ready"' <<< "$out"; then
    LOAD_ERR=${LOAD_ERR:-$out}; return 1
  fi
  eval "$(python3 -c 'import json,shlex,sys; d=json.load(sys.stdin)
print("PROFILE=%s CTX=%s SPLIT=%s" % (shlex.quote(d["profile"]), d["ctx"], shlex.quote(str(d.get("tensor_split") or "-"))))' <<< "$out")"
  LOAD_S=$(python3 -c "print(round($(date +%s.%N)-$s,1))")
  LOADED_ARGS="$MODEL|$1"
}
thinking_template() {
  curl -s "http://127.0.0.1:$PORT/props" | python3 -c '
import json, sys
t = json.load(sys.stdin).get("chat_template", "")
print("yes" if any(k in t for k in ("<think>", "enable_thinking", "reasoning")) else "no")'
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

RUN_ID="$(basename "$(dirname "$QUEUE")")"
if ! out=$(rigctl claim "$CLAIM" --gpus "$GPUS" --note "benchmark lane $RUN_ID" --owner "$CLAIM" \
            --ttl "$CLAIM_TTL" --purpose "benchmark lane $RUN_ID" 2>&1); then
  say "LANE_REFUSED: the rig manager did not give cards $GPUS to this lane: $out"; exit 2
fi
say "claim $CLAIM on GPU $GPUS (ttl $CLAIM_TTL s, renewed while the lane runs)"
( while sleep 300; do rigctl renew-claim "$CLAIM" --owner "$CLAIM" --ttl "$CLAIM_TTL" > /dev/null 2>&1; done ) &
RENEWER=$!
finish() {
  kill "$RENEWER" 2>/dev/null
  unload
  rigctl unclaim "$CLAIM" > /dev/null 2>&1 || say "unclaim of $CLAIM failed"
}
trap finish EXIT
trap 'exit 143' TERM INT   # stop_all / operator: still run finish (model unloaded, claim released)

while MODEL=$(next_model) && [ -n "$MODEL" ]; do
  slug=$(echo "$MODEL" | tr ':.' '__' | tr -cd 'A-Za-z0-9_-')
  eval "$(python3 "$HERE/resolve_model.py" "$MODEL")"   # EXTRA, BASE_EXTRA (registry args); THINK_TOKS below
  if [ "${LANE_START_AT:-2}" = "4.5" ]; then
    say "== $MODEL: Phase 4.5 only (LANE_START_AT=4.5)"
    if ! load "--reasoning off"; then say "LOAD FAILED $MODEL: $LOAD_ERR"; continue; fi
    THINK_TOKS=$(( CTX - 2048 < 4096 ? (CTX - 2048 < 1024 ? 1024 : CTX - 2048) : 4096 ))
    thinking_capable=$(thinking_template)
  else
  say "== $MODEL: Phase 2 (registry args: ${EXTRA:-none})"
  if ! load ""; then say "LOAD FAILED $MODEL: $LOAD_ERR"; continue; fi
  THINK_TOKS=$(( CTX - 2048 < 4096 ? (CTX - 2048 < 1024 ? 1024 : CTX - 2048) : 4096 ))
  say "loaded $PROFILE in ${LOAD_S}s: ctx $CTX split $SPLIT; vram $(nvidia-smi --query-gpu=memory.used --format=csv,noheader -i "$GPUS" | tr '\n' ' '); prompt tail $(prompt_tail)"
  thinking_capable=$(thinking_template)
  say "Phase 3 litmus"; python3 "$HERE/litmus.py" "$PORT" | sed "s/^/    /"
  python3 "$HERE/runtime_char.py" "$MODEL" "$PORT" "$GPUS" "$LOAD_S" "harness load ($PROFILE), lane GPU $GPUS" \
    "$RX/${slug}_runtime_characterization_${STAMP}.json" image=llama-runtime:b11669 ctx_size="$CTX" \
    tensor_split="$SPLIT" extra_args="${EXTRA:-none}" | grep -E "generation_tokens_per_second|avg_power_w" | sed "s/^/    /"
  if [ "${LANE_STOP_AFTER:-}" = "3" ]; then
    unload
    say "== $MODEL done (LANE_STOP_AFTER=3)"
    continue
  fi
  say "Phase 4 smoke"
  "$HERE/phase4.sh" "$MODEL" "${slug}_w_smoke_v1" "$PORT" | sed "s/^/    /"
  if [ "${LANE_STOP_AFTER:-}" = "4" ]; then
    unload
    say "== $MODEL done (LANE_STOP_AFTER=4)"
    continue
  fi
  fi
  if [ "$thinking_capable" = "yes" ]; then
    for variant in off on; do
      # The registry's own reasoning flag is replaced: the harness appends this after the registry args.
      if ! load "--reasoning $variant"; then say "LOAD FAILED ($variant): $LOAD_ERR"; continue; fi
      say "Phase 4.5 thinking $variant: $PROFILE loaded in ${LOAD_S}s, ctx $CTX, prompt tail $(prompt_tail)"
      if [ "$variant" = "on" ]; then
        reasoning "${slug}_w_p45_think" --tasks gsm8k,bbh --gen-kwargs "max_gen_toks=${THINK_TOKS},until=</s>"
      else
        reasoning "${slug}_w_p45_off" --tasks gsm8k,bbh
      fi
    done
  else
    say "Phase 4.5 thinking A/B skipped: template has no thinking control"
  fi
  unload
  say "== $MODEL done"
done
say LANE_DONE
