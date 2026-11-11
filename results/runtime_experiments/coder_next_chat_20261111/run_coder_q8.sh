#!/usr/bin/env bash
set -euo pipefail
repo=/mnt/shared/plans/shoulders/benchmarking
out="$repo/results/runtime_experiments/coder_next_chat_20261111"
build=/data/bench-staging/kvchat-b11669-build
probe=/data/bench-staging/nemo-single-20261109
model=/data/model-hotset/qwen3-coder-next/Qwen3-Coder-Next-Q4_K_S.gguf
label=coder_24x4_worker5_q8_0_16k32k50k_nvme
test -f "$model" && test -x "$probe/nemo-single"
test ! -e "$out/$label.start"
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
docker run --rm --gpus all --network none \
  -v "$repo:/work:ro" -v "$build:/build:ro" -v "$probe:/probe:ro" -v "$model:/model.gguf:ro" \
  -e LD_LIBRARY_PATH=/build/bin -e KV_MODEL_DEVICES=0,1,2,3,4 -e KV_MODEL_SPLIT=48,0,0,0,0 \
  -e KV_TENSOR_OVERRIDES_FILE=/work/results/runtime_experiments/coder_next_chat_20261111/coder_experts_1234.tsv \
  -e NEMO_KV_TYPE=q8_0 -w /build/bin 4bfa1cb0a955 \
  /probe/coder-chat-q8 single_worker5_depth /model.gguf 16384 32768 50000 128 > "$out/$label.log" 2>&1
