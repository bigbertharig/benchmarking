#!/usr/bin/env bash
set -u
base=/mnt/shared/experiments/kvchat-20261106
build=/data/bench-staging/kvchat-20261106-build
model=/mnt/shared/models/qwen3-1.7b/Qwen3-1.7B-Q4_K_M.gguf
date -u +%FT%TZ > "$base/run.start"
rm -f "$base/run.exit"
nvidia-smi --query-gpu=timestamp,index,memory.used,utilization.gpu --format=csv,noheader -l 1 > "$base/gpu_samples.csv" 2>&1 &
sampler=$!
docker run --rm --gpus all --network none \
  -v "$build:/build:ro" -v "$model:/model.gguf:ro" \
  -w /build/bin 4bfa1cb0a955 \
  /build/bin/llama-simple /model.gguf 32768 > "$base/run.log" 2>&1
rc=$?
kill "$sampler" 2>/dev/null || true
wait "$sampler" 2>/dev/null || true
date -u +%FT%TZ > "$base/run.finish"
echo "$rc" > "$base/run.exit"
tail -35 "$base/run.log"
exit "$rc"
