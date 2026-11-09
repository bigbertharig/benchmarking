#!/usr/bin/env bash
set -uo pipefail
base=/mnt/shared/experiments/kv-matrix-20261107
build=${KV_BUILD_DIR:?KV_BUILD_DIR required}
model=${1:?model path required}
depth=${2:?depth required}
label=${3:?label required}
tokens=${4:-64}
date -u +%FT%TZ > "$base/$label.start"
rm -f "$base/$label.exit"
docker run --rm --gpus all --network none \
  -v "$build:/build:ro" -v "$model:/model.gguf:ro" -v "$base:/state" \
  -e KV_STATE_SOURCE_DIR=/state/qwen35_moe_two_q4_1_16k32k50k_20261109.states \
  -e KV_K_TYPE=q4_1 -e KV_V_TYPE=q4_1 \
  -e "KV_REPLAY_DEPTH=$depth" -e KV_TRACE_CUDA=1 \
  -w /build/bin 4bfa1cb0a955 \
  nvprof --profile-from-start off --devices 1 --print-gpu-trace --csv \
    --log-file "/state/$label.nvprof.csv" \
    /build/bin/llama-simple moe_one_replay /model.gguf 262144 262144 262144 "$tokens" \
  > "$base/$label.log" 2>&1
rc=$?
echo "$rc" > "$base/$label.exit"
date -u +%FT%TZ > "$base/$label.finish"
tail -10 "$base/$label.log"
exit "$rc"
