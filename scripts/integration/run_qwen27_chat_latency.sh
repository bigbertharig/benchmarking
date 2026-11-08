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
if [ "$mode" = five_distinct_disk ] || [ "$mode" = recall_handoff ]; then
  mkdir -p "$base/$label.states"
fi
date -u +%FT%TZ > "$base/$label.start"
rm -f "$base/$label.exit"
nvidia-smi --query-gpu=timestamp,index,memory.used,utilization.gpu --format=csv,noheader -l 1 > "$base/$label.gpu.csv" 2>&1 &
sampler=$!
nvidia-smi dmon -s t -d 1 > "$base/$label.pcie.txt" 2>&1 &
pcie_sampler=$!
finish_run() {
  rc=$?
  trap - EXIT TERM INT
  kill "$sampler" "$pcie_sampler" 2>/dev/null || true
  wait "$sampler" 2>/dev/null || true
  wait "$pcie_sampler" 2>/dev/null || true
  date -u +%FT%TZ > "$base/$label.finish"
  echo "$rc" > "$base/$label.exit"
  if [ -f "$base/$label.log" ]; then tail -20 "$base/$label.log"; fi
  exit "$rc"
}
trap finish_run EXIT
trap 'exit 143' TERM
trap 'exit 130' INT
docker run --rm --gpus all --network none \
  -v "$build:/build:ro" -v "$model:/model.gguf:ro" \
  -v "$base:/state" -e "KV_STATE_DIR=/state/$label.states" \
  -e "KV_MODEL_DEVICES=${KV_MODEL_DEVICES-}" -e "KV_MODEL_SPLIT=${KV_MODEL_SPLIT-}" \
  -w /build/bin 4bfa1cb0a955 \
  /build/bin/llama-simple "$mode" /model.gguf "$local_cap" "$pair_cap" "$single_cap" "$tokens" > "$base/$label.log" 2>&1
exit $?
