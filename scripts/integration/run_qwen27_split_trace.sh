#!/usr/bin/env bash
set -uo pipefail

base=/mnt/shared/experiments/kv-matrix-20261107
build=${KV_BUILD_DIR:?KV_BUILD_DIR required}
model=${1:?model path required}
depth=${2:?depth required}
label=${3:?label required}
tokens=${4:-64}
host_gpus=${KV_HOST_GPU_IDS:?KV_HOST_GPU_IDS required}
model_split=${KV_MODEL_SPLIT:?KV_MODEL_SPLIT required}
source_states=${KV_STATE_SOURCE_DIR:-/state/qwen27_dense_f16_tile128_64k_prep_20261109.states}

mkdir -p "$base"
IFS=, read -ra host_ids <<< "$host_gpus"
uuids=()
for host_id in "${host_ids[@]}"; do
  uuid=$(nvidia-smi --id "$host_id" --query-gpu=uuid --format=csv,noheader) || exit 82
  uuids+=("$uuid")
done
joined=$(IFS=,; echo "${uuids[*]}")
printf '%s\n' "${host_ids[@]}" > "$base/$label.selected_host_gpus.txt"
printf '%s\n' "${uuids[@]}" > "$base/$label.selected_uuids.txt"
model_cuda=$(python3 scripts/integration/cuda_device_map.py \
  --host-gpus "$host_gpus" --chat-host-gpus "$host_gpus" \
  --output "$base/$label.cuda_map.json") || exit 83
chat_cuda=${model_cuda%%,*}
nvidia-smi --query-gpu=index,uuid,name,pci.bus_id,memory.total --format=csv,noheader \
  > "$base/$label.host_inventory.csv"

date -u +%FT%TZ > "$base/$label.start"
rm -f "$base/$label.exit"
docker run --rm --gpus "\"device=$joined\"" --network none \
  -v /lib/x86_64-linux-gnu/libdw.so.1:/lib/x86_64-linux-gnu/libdw.so.1:ro \
  -v /lib/x86_64-linux-gnu/libelf.so.1:/lib/x86_64-linux-gnu/libelf.so.1:ro \
  -v "$build:/build:ro" -v "$model:/model.gguf:ro" -v "$base:/state" \
  -e "KV_STATE_SOURCE_DIR=$source_states" \
  -e KV_K_TYPE=f16 -e KV_V_TYPE=f16 \
  -e "KV_MODEL_DEVICES=$model_cuda" -e "KV_MODEL_SPLIT=$model_split" \
  -e "KV_REPLAY_CHAT_GPU=$chat_cuda" \
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
tail -12 "$base/$label.log"
exit "$rc"
