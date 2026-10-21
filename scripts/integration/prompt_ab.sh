#!/usr/bin/env bash
# Phase 4.5 system-prompt A/B for one single-1060 model, through the harness: a `benchmarks` lease on
# its GPU (harness_lease.sh), the registry load settings (resolve_model.py), run_runtime.sh with the
# lease, then bench-reasoning bbh,drop,gsm8k at limit 10 with raw samples, once per system prompt:
#   worker   the model's registry system prompt (no override)
#   answer   answer-format prompt: reason briefly, end with "So the answer is (X)", plain text
#   plain    "You are a helpful assistant."
#   examples the worker prompt without its JSON emphasis: follow the question's examples and answer
#            format, plain text, JSON only when asked (2026-10-20: ministral answered bbh in JSON)
# usage: prompt_ab.sh <gpu> <model-id> <tag> [variant ...]   (default: worker answer plain)
set -uo pipefail
GPU=$1; MODEL=$2; TAG=$3; shift 3
VARIANTS=("${@:-worker answer plain}"); [ $# -eq 0 ] && VARIANTS=(worker answer plain)
PORT=$((11434 + GPU))
NAME="llama-ab-gpu${GPU}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BENCH="$(cd "$HERE/../.." && pwd)"
RR="$(cd "$BENCH/../../.." && pwd)/scripts/llama_runtime/run_runtime.sh"
ANSWER_PROMPT="You are a helpful assistant. When answering multiple choice questions, reason briefly then conclude with exactly: So the answer is (X). Use plain text only, no markdown formatting. When JSON is requested, return raw JSON only, no code blocks."
PLAIN_PROMPT="You are a helpful assistant."
EXAMPLES_PROMPT="You are a strict worker assistant. Follow the instructions and any examples exactly, including the answer format they show, and keep output minimal. Answer in plain text. Return JSON only when JSON is explicitly requested, and then raw JSON with no code blocks."
say() { echo "$(date +%T) [gpu$GPU $MODEL] $*"; }

eval "$(python3 "$HERE/resolve_model.py" "$MODEL")"   # GGUF CTX BATCH PARALLEL NGL EXTRA ...
OWNER="ab-gpu$GPU"
LEASE=$("$HERE/harness_lease.sh" acquire "$GPU" "$OWNER" "$TAG" "$MODEL") || { say "REFUSED: no lease for GPU $GPU"; exit 2; }
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
trap 'exit 143' TERM INT

docker rm -f "$NAME" >/dev/null 2>&1
extra=(); eval "set -- ${EXTRA:-}"; for a in "$@"; do extra+=(--extra-arg "$a"); done
say "lease ${LEASE:-none}; loading $GGUF (ctx $CTX)"
"$RR" --name "$NAME" --model "$GGUF" --port "$PORT" --gpus "device=$GPU" --ctx-size "$CTX" \
    --batch-size "$BATCH" --parallel "$PARALLEL" --n-gpu-layers "$NGL" --memory-limit 8g --memory-swap 10g \
    ${LEASE:+--lease "$LEASE"} "${extra[@]}" >/dev/null 2>"/tmp/ab_gpu${GPU}.err" || {
  say "LOAD FAILED: $(tail -2 /tmp/ab_gpu${GPU}.err | tr '\n' ' ')"; exit 1; }

for variant in "${VARIANTS[@]}"; do
  run="${TAG}_${variant}"
  case "$variant" in
    worker) flags=() ;;
    answer) flags=(--system-prompt-override "$ANSWER_PROMPT") ;;
    plain)  flags=(--system-prompt-override "$PLAIN_PROMPT") ;;
    examples) flags=(--system-prompt-override "$EXAMPLES_PROMPT") ;;
    *) say "unknown variant $variant"; continue ;;
  esac
  s=$(date +%s)
  if ! curl -sf "http://127.0.0.1:$PORT/v1/models" >/dev/null; then
    say "RUNTIME DOWN before $variant"; rig why --port "$PORT" 2>&1 | sed 's/^/  /'; exit 3
  fi
  PORT=$PORT TASKS=bbh,drop,gsm8k "$HERE/smoke_reasoning.sh" "$MODEL" "$run" "${flags[@]}" | sed "s/^/    /"
  say "$run done in $(( ($(date +%s) - s) / 60 )) min"
done
say AB_DONE
