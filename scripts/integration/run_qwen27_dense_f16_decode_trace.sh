#!/usr/bin/env bash
set -uo pipefail
base=/mnt/shared/experiments/kv-matrix-20261107
build=${KV_BUILD_DIR:?KV_BUILD_DIR required}
model=${1:?model path required}
depth=${2:?depth required}
label=${3:?label required}
tokens=${4:-64}
mkdir -p "$base"
date -u +%FT%TZ > "$base/$label.start"
rm -f "$base/$label.exit"
docker run --rm --gpus all --network none \
  -v /lib/x86_64-linux-gnu/libdw.so.1:/lib/x86_64-linux-gnu/libdw.so.1:ro \
  -v /lib/x86_64-linux-gnu/libelf.so.1:/lib/x86_64-linux-gnu/libelf.so.1:ro \
  -v "$build:/build:ro" -v "$model:/model.gguf:ro" -v "$base:/state" \
  -e KV_STATE_SOURCE_DIR=/state/qwen27_dense_f16_tile128_64k_prep_20261109.states \
  -e KV_K_TYPE=f16 -e KV_V_TYPE=f16 \
  -e "KV_REPLAY_DEPTH=$depth" -e KV_TRACE_CUDA=1 \
  -w /build/bin 4bfa1cb0a955 \
  nsys profile --trace=cuda --sample=none --cpuctxsw=none \
    --capture-range=cudaProfilerApi --capture-range-end=stop \
    --force-overwrite=true --output="/state/$label" \
    /build/bin/llama-simple moe_one_replay /model.gguf 65536 65536 65536 "$tokens" \
  > "$base/$label.log" 2>&1
rc=$?
echo "$rc" > "$base/$label.exit"
date -u +%FT%TZ > "$base/$label.finish"
if [ "$rc" -eq 0 ]; then
  docker run --rm --network none \
    -v /lib/x86_64-linux-gnu/libdw.so.1:/lib/x86_64-linux-gnu/libdw.so.1:ro \
    -v /lib/x86_64-linux-gnu/libelf.so.1:/lib/x86_64-linux-gnu/libelf.so.1:ro \
    -v "$base:/state" 4bfa1cb0a955 \
    nsys export --type sqlite --force-overwrite=true \
      --output="/state/$label.sqlite" "/state/$label.nsys-rep" \
    > "$base/$label.export.log" 2>&1 || true
fi
tail -12 "$base/$label.log"
exit "$rc"
