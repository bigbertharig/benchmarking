#!/usr/bin/env bash
set -u
kv_type="$1"
label="nemo_experts1234_single5_${kv_type}_16k32k50k_r2_20261109"
repo=/mnt/shared/plans/shoulders/benchmarking
out="$repo/results/runtime_experiments/nemo_single_chat_20261109"
build=/data/bench-staging/kvchat-b11669-build
probe=/data/bench-staging/nemo-single-20261109
model=/data/model-hotset/nemotron-3.5-bolt-74b-a9b/NVIDIA-Nemotron-3.5-Bolt-74B-A9B-UD-Q3_K_XL.gguf
test -f "$model" && test -x "$probe/nemo-single" || exit 10
if test -e "$out/$label.start"; then echo "label already used: $label" >&2; exit 11; fi
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
  tail -18 "$out/$label.log" 2>/dev/null || true
  exit "$rc"
}
trap finish EXIT
trap 'exit 143' TERM
trap 'exit 130' INT
docker run --rm --gpus all --network none \
  -v "$repo:/work:ro" -v "$build:/build:ro" -v "$probe:/probe:ro" -v "$model:/model.gguf:ro" \
  -e LD_LIBRARY_PATH=/build/bin -e KV_MODEL_DEVICES=0,1,2,3,4 -e KV_MODEL_SPLIT=88,0,0,0,0 \
  -e KV_TENSOR_OVERRIDES_FILE=/work/results/runtime_experiments/kv_expert_chat_20261107/nemo_experts_1234.tsv \
  -e NEMO_KV_TYPE="$kv_type" -w /build/bin 4bfa1cb0a955 \
  /probe/nemo-single single_worker5_depth /model.gguf 16384 32768 50000 128 > "$out/$label.log" 2>&1
