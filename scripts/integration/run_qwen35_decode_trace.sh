#!/usr/bin/env bash
set -uo pipefail
base=/mnt/shared/experiments/kv-matrix-20261107
build=${KV_BUILD_DIR:?KV_BUILD_DIR required}
model=${1:?model path required}
depth=${2:?depth required}
label=${3:?label required}
tokens=${4:-128}
worker_host_gpu=${KV_REPLAY_CHAT_HOST_GPU:-1}
model_host_gpu=${KV_MODEL_HOST_GPU:-0}
state_source=${KV_STATE_SOURCE_DIR:-/state/qwen35_moe_two_q4_1_16k32k50k_20261109.states}
kv_k=${KV_K_TYPE:-q4_1}
kv_v=${KV_V_TYPE:-q4_1}
mkdir -p "$base"
nvidia-smi --id "$worker_host_gpu" --query-gpu=index,uuid,name,memory.total,pcie.link.width.current,pcie.link.gen.current --format=csv,noheader > "$base/$label.worker_hardware.csv" || exit 83
nvidia-smi --id "$model_host_gpu" --query-gpu=index,uuid,name,memory.total --format=csv,noheader > "$base/$label.model_hardware.csv" || exit 84
model_uuid=$(nvidia-smi --id "$model_host_gpu" --query-gpu=uuid --format=csv,noheader) || exit 84
worker_uuid=$(nvidia-smi --id "$worker_host_gpu" --query-gpu=uuid --format=csv,noheader) || exit 83
test "$model_uuid" != "$worker_uuid" || exit 85
date -u +%FT%TZ > "$base/$label.start"
rm -f "$base/$label.exit"
docker run --rm --gpus "\"device=$model_uuid,$worker_uuid\"" --network none \
  -v /lib/x86_64-linux-gnu/libdw.so.1:/lib/x86_64-linux-gnu/libdw.so.1:ro \
  -v /lib/x86_64-linux-gnu/libelf.so.1:/lib/x86_64-linux-gnu/libelf.so.1:ro \
  -v "$build:/build:ro" -v "$model:/model.gguf:ro" -v "$base:/state" \
  -e "KV_STATE_SOURCE_DIR=$state_source" \
  -e "KV_K_TYPE=$kv_k" -e "KV_V_TYPE=$kv_v" \
  -e "KV_REPLAY_DEPTH=$depth" -e KV_TRACE_CUDA=1 \
  -e KV_REPLAY_CHAT_GPU=1 \
  -w /build/bin 4bfa1cb0a955 \
  nsys profile --trace=cuda --sample=none --cpuctxsw=none \
    --capture-range=cudaProfilerApi --capture-range-end=stop \
    --force-overwrite=true --output="/state/$label" \
    /build/bin/llama-simple moe_one_replay /model.gguf 262144 262144 262144 "$tokens" \
  > "$base/$label.log" 2>&1
rc=$?
echo "$rc" > "$base/$label.exit"
date -u +%FT%TZ > "$base/$label.finish"
if [ "$rc" -eq 0 ]; then
  docker run --rm --network none \
    -v /lib/x86_64-linux-gnu/libdw.so.1:/lib/x86_64-linux-gnu/libdw.so.1:ro \
    -v /lib/x86_64-linux-gnu/libelf.so.1:/lib/x86_64-linux-gnu/libelf.so.1:ro \
    -v "$base:/state" 4bfa1cb0a955 \
    nsys stats --report cuda_gpu_kern_sum --format csv "/state/$label.nsys-rep" \
    > "$base/$label.kernels.csv" 2> "$base/$label.stats.log" || true
fi
tail -12 "$base/$label.log"
exit "$rc"
