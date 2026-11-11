#!/usr/bin/env bash
set -euo pipefail

mode="${1:?prep_save or restore_saved}"
targets="${2:?comma-separated depths}"
label="${3:?unique label}"
resume="${4:-}"
repo=/mnt/shared/plans/shoulders/benchmarking
out="$repo/results/runtime_experiments/coder_next_chat_20261111"
build=/data/bench-staging/kvchat-b11669-build
probe=/data/bench-staging/nemo-single-20261109
model=/data/model-hotset/qwen3-coder-next/Qwen3-Coder-Next-Q4_K_S.gguf
state=/data/bench-staging/coder-chat-state-20261111

case "$mode" in
  prep_save)
    devices=0,1,2,3,4,5
    split=48,0,0,0,0,0
    overrides=/work/results/runtime_experiments/coder_next_chat_20261111/coder_experts_12345_prep.tsv
    ;;
  restore_saved)
    devices=0,1,2,3,4
    split=48,0,0,0,0
    overrides=/work/results/runtime_experiments/coder_next_chat_20261111/coder_experts_1234.tsv
    ;;
  *) echo "invalid mode: $mode" >&2; exit 2 ;;
esac

test -f "$model" && test -x "$probe/coder-chat-depth"
test ! -e "$out/$label.start"
mkdir -p "$state"
date -u +%FT%TZ > "$out/$label.start"
nvidia-smi --query-gpu=timestamp,index,memory.used,utilization.gpu --format=csv,noheader -l 1 > "$out/$label.gpu.csv" 2>&1 &
sampler=$!
finish() {
  rc=$?
  trap - EXIT TERM INT
  kill "$sampler" 2>/dev/null || true
  wait "$sampler" 2>/dev/null || true
  date -u +%FT%TZ > "$out/$label.finish"
  echo "$rc" > "$out/$label.exit"
  tail -20 "$out/$label.log" 2>/dev/null || true
  exit "$rc"
}
trap finish EXIT
trap 'exit 143' TERM
trap 'exit 130' INT

envs=(-e LD_LIBRARY_PATH=/build/bin -e KV_MODEL_DEVICES="$devices" -e KV_MODEL_SPLIT="$split"
  -e KV_TENSOR_OVERRIDES_FILE="$overrides" -e NEMO_KV_TYPE=f16 -e CODER_CHAT_CAP=250000
  -e CODER_TARGETS="$targets" -e CODER_STATE_DIR=/state)
if [[ -n "$resume" ]]; then
  envs+=(-e CODER_RESUME_FILE="/state/$resume")
fi
docker run --rm --gpus all --network none \
  -v "$repo:/work:ro" -v "$build:/build:ro" -v "$probe:/probe:ro" \
  -v "$model:/model.gguf:ro" -v "$state:/state" \
  "${envs[@]}" -w /build/bin 4bfa1cb0a955 \
  /probe/coder-chat-depth "$mode" /model.gguf 50000 100000 150000 128 > "$out/$label.log" 2>&1
