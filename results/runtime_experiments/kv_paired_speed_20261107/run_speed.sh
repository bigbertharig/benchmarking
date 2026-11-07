#!/usr/bin/env bash
set -u
base=/mnt/shared/experiments/kv-speed-20261107
build=/data/bench-staging/kvchat-20261106-build
model="$1"
pair_ctx="$2"
single_ctx="$3"
tokens="$4"
label="$5"
mkdir -p "$base"
date -u +%FT%TZ > "$base/$label.start"
rm -f "$base/$label.exit"
nvidia-smi --query-gpu=timestamp,index,memory.used,utilization.gpu --format=csv,noheader -l 1 > "$base/$label.gpu.csv" 2>&1 &
sampler=$!
docker run --rm --gpus all --network none \
  -v "$build:/build:ro" -v "$model:/model.gguf:ro" \
  -w /build/bin 4bfa1cb0a955 \
  /build/bin/llama-simple /model.gguf "$pair_ctx" "$single_ctx" "$tokens" > "$base/$label.log" 2>&1
rc=$?
kill "$sampler" 2>/dev/null || true
wait "$sampler" 2>/dev/null || true
date -u +%FT%TZ > "$base/$label.finish"
echo "$rc" > "$base/$label.exit"
grep BENCH "$base/$label.log" || true
exit "$rc"
