#!/usr/bin/env bash
set -uo pipefail
repo=/mnt/shared/plans/shoulders/benchmarking
base=/mnt/shared/experiments/kv-matrix-20261107
build=/data/bench-staging/ple-bus-probe-20261113
model=/data/model-hotset/qwen3.8-flash-next-ud-q4_k_xl/Qwen3.8-Flash-Next-UD-Q4_K_XL-00002-of-00004.gguf
label=${1:?label required}
host_gpus=${KV_HOST_GPU_IDS:?KV_HOST_GPU_IDS required}
mkdir -p "$base" "$build"
IFS=, read -ra host_ids <<< "$host_gpus"
uuids=()
for host_id in "${host_ids[@]}"; do
  uuid=$(nvidia-smi --id "$host_id" --query-gpu=uuid --format=csv,noheader) || exit 82
  uuids+=("$uuid")
done
joined=$(IFS=,; echo "${uuids[*]}")
printf '%s\n' "${uuids[@]}" > "$base/$label.uuids.txt"
date -u +%FT%TZ > "$base/$label.start"
python3 "$repo/scripts/analysis/inspect_ple_layout.py" \
  --gguf "$model" --gguf-py /data/bench-staging/kvchat-q41-tile-src/gguf-py \
  --output "$base/$label.layout.json" > /dev/null || exit 83
read -r rows offset <<< "$(python3 -c 'import json,sys; t=json.load(open(sys.argv[1]))["table_tensors"]; assert len(t)==1; print(t[0]["shape"][1], t[0]["data_offset"])' "$base/$label.layout.json")"
nvidia-smi --query-gpu=index,name,pci.bus_id,pcie.link.gen.current,pcie.link.width.current --format=csv,noheader -lms 100 > "$base/$label.links.csv" 2>&1 &
monitor_pid=$!
docker run --rm --gpus "\"device=$joined\"" --network none \
  -v "$repo:/bench:ro" -v "$build:/build" -v "$model:/model.gguf:ro" \
  nvidia/cuda:12.9.2-devel-ubuntu24.04 \
  bash -c "nvcc -std=c++17 -O2 /bench/scripts/integration/ple_bus_probe.cu -o /build/ple_bus_probe && /build/ple_bus_probe /model.gguf $offset $rows" \
  > "$base/$label.log" 2>&1
rc=$?
kill "$monitor_pid" 2>/dev/null || true
wait "$monitor_pid" 2>/dev/null || true
echo "$rc" > "$base/$label.exit"
date -u +%FT%TZ > "$base/$label.finish"
tail -n 18 "$base/$label.log"
exit "$rc"
