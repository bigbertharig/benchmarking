#!/usr/bin/env bash
set -u
base=/mnt/shared/experiments/kvchat-20261106
build=/data/bench-staging/kvchat-20261106-build
model=/mnt/shared/models/gpt-oss-20b/gpt-oss-20b-mxfp4.gguf
date -u +%FT%TZ > "$base/moe_run.start"
rm -f "$base/moe_run.exit"
nvidia-smi --query-gpu=timestamp,index,memory.used,utilization.gpu --format=csv,noheader -l 1 > "$base/moe_gpu_samples.csv" 2>&1 &
sampler=$!
docker run --rm --gpus all --network none \
  -v "$build:/build:ro" -v "$model:/model.gguf:ro" \
  -w /build/bin 4bfa1cb0a955 \
  /build/bin/llama-simple /model.gguf 32768 > "$base/moe_run.log" 2>&1
rc=$?
kill "$sampler" 2>/dev/null || true
wait "$sampler" 2>/dev/null || true
date -u +%FT%TZ > "$base/moe_run.finish"
echo "$rc" > "$base/moe_run.exit"
tail -35 "$base/moe_run.log"
exit "$rc"
