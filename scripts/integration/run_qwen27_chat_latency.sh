#!/usr/bin/env bash
set -u
base=/mnt/shared/experiments/kv-matrix-20261107
build=${KV_BUILD_DIR:-/data/bench-staging/kvchat-20261106-build}
mode="$1"
model="$2"
local_cap="$3"
pair_cap="$4"
single_cap="$5"
tokens="$6"
label="$7"
mkdir -p "$base"
if [ "$mode" = large_chat_latency ]; then
  source_states="$base/overnight_qwen27_recall_256k.states"
  target_states="$base/$label.states"
  for worker in 1 2 3 4 5; do
    test -f "$source_states/worker${worker}_depth90.bin" || {
      echo "missing validated 256K state for worker $worker" >&2
      exit 80
    }
  done
  if [ ! -e "$target_states" ] && [ ! -L "$target_states" ]; then
    ln -s overnight_qwen27_recall_256k.states "$target_states"
  fi
  test "$(readlink -f "$target_states")" = "$(readlink -f "$source_states")" || {
    echo "state target differs from expected source" >&2
    exit 81
  }
fi
if [ "$mode" = five_distinct_disk ] || [ "$mode" = recall_handoff ] || [ "$mode" = five_ongoing_depths ] || [ "$mode" = moe_five_f16_curve ] || [ "$mode" = moe_two_depths ] || [ "$mode" = moe_two_short ] || [ "$mode" = moe_two_curve ]; then
  mkdir -p "$base/$label.states"
fi
date -u +%FT%TZ > "$base/$label.start"
rm -f "$base/$label.exit"
nvidia-smi --query-gpu=index,uuid,name,pci.bus_id,memory.total --format=csv,noheader > "$base/$label.host_inventory.csv"
gpu_args=(--gpus all)
if [ -n "${KV_HOST_GPU_IDS-}" ]; then
  IFS=, read -ra host_gpu_ids <<< "$KV_HOST_GPU_IDS"
  gpu_uuids=()
  for host_gpu in "${host_gpu_ids[@]}"; do
    uuid=$(nvidia-smi --id "$host_gpu" --query-gpu=uuid --format=csv,noheader) || exit 82
    gpu_uuids+=("$uuid")
  done
  joined=$(IFS=,; echo "${gpu_uuids[*]}")
  gpu_args=(--gpus "\"device=$joined\"")
  printf '%s\n' "${host_gpu_ids[@]}" > "$base/$label.selected_host_gpus.txt"
  printf '%s\n' "${gpu_uuids[@]}" > "$base/$label.selected_uuids.txt"
  if [ -n "${KV_REPLAY_CHAT_HOST_GPUS-}" ]; then
    chat_cuda=$(python3 scripts/integration/cuda_device_map.py --host-gpus "$KV_HOST_GPU_IDS" --chat-host-gpus "$KV_REPLAY_CHAT_HOST_GPUS" --output "$base/$label.cuda_map.json") || exit 86
    export KV_REPLAY_CHAT_GPUS="$chat_cuda"
  fi
fi
nvidia-smi --query-gpu=timestamp,index,memory.used,utilization.gpu --format=csv,noheader -l 1 > "$base/$label.gpu.csv" 2>&1 &
sampler=$!
nvidia-smi dmon -s t -d 1 > "$base/$label.pcie.txt" 2>&1 &
pcie_sampler=$!
if [ "${KV_SAMPLE_DETAIL-}" = 1 ]; then
  nvidia-smi --query-gpu=timestamp,index,utilization.gpu,utilization.memory,clocks.sm,power.draw,pcie.link.gen.current,pcie.link.width.current --format=csv,noheader -l 1 > "$base/$label.gpu_detail.csv" 2>&1 &
  detail_sampler=$!
fi
finish_run() {
  rc=$?
  trap - EXIT TERM INT
  kill "$sampler" "$pcie_sampler" 2>/dev/null || true
  wait "$sampler" 2>/dev/null || true
  wait "$pcie_sampler" 2>/dev/null || true
  if [ -n "${detail_sampler-}" ]; then
    kill "$detail_sampler" 2>/dev/null || true
    wait "$detail_sampler" 2>/dev/null || true
  fi
  date -u +%FT%TZ > "$base/$label.finish"
  echo "$rc" > "$base/$label.exit"
  if [ -f "$base/$label.log" ]; then tail -20 "$base/$label.log"; fi
  exit "$rc"
}
trap finish_run EXIT
trap 'exit 143' TERM
trap 'exit 130' INT
docker run --rm "${gpu_args[@]}" --network none \
  -v "$build:/build:ro" -v "$model:/model.gguf:ro" \
  -v "$base:/state" -e "KV_STATE_DIR=/state/$label.states" \
  -e "KV_STATE_SOURCE_DIR=${KV_STATE_SOURCE_DIR-}" \
  -e "KV_REPLAY_CHAT_GPUS=${KV_REPLAY_CHAT_GPUS-}" \
  -e "KV_DELTA_SOURCE_DEPTH=${KV_DELTA_SOURCE_DEPTH-}" \
  -e "KV_DELTA_COMPARE_MODE=${KV_DELTA_COMPARE_MODE-}" \
  -e "KV_RETURN_TURNS=${KV_RETURN_TURNS-}" \
  -e "KV_DURABLE_DIR=${KV_DURABLE_DIR-}" \
  -e "KV_MIRROR_CHATS=${KV_MIRROR_CHATS-}" \
  -e "KV_MIRROR_CAP=${KV_MIRROR_CAP-}" \
  -e "KV_PREP_CPU_FROM_DEPTH=${KV_PREP_CPU_FROM_DEPTH-}" \
  -e "KV_ADMISSION_TARGET=${KV_ADMISSION_TARGET-}" \
  -e "KV_ADMISSION_PATH=${KV_ADMISSION_PATH-}" \
  -e "KV_KV_TYPE=${KV_KV_TYPE-}" \
  -e "KV_K_TYPE=${KV_K_TYPE-}" -e "KV_V_TYPE=${KV_V_TYPE-}" \
  -e "KV_WORKER_UBATCH=${KV_WORKER_UBATCH-}" \
  -e "GGML_CUDA_DISABLE_FUSION=${GGML_CUDA_DISABLE_FUSION-}" \
  -e "GGML_CUDA_GRAPH_OPT=${GGML_CUDA_GRAPH_OPT-}" \
  -e "KV_TENSOR_OVERRIDES_FILE=${KV_TENSOR_OVERRIDES_FILE-}" \
  -e "KV_MODEL_DEVICES=${KV_MODEL_DEVICES-}" -e "KV_MODEL_SPLIT=${KV_MODEL_SPLIT-}" \
  -w /build/bin 4bfa1cb0a955 \
  /build/bin/llama-simple "$mode" /model.gguf "$local_cap" "$pair_cap" "$single_cap" "$tokens" > "$base/$label.log" 2>&1
exit $?
