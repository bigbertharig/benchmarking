#!/usr/bin/env bash
set -uo pipefail

base=/mnt/shared/experiments/kv-matrix-20261107
build=/data/bench-staging/ple-shard-probe-20261113
model=/data/model-hotset/qwen3.8-flash-next-ud-q4_k_xl/Qwen3.8-Flash-Next-UD-Q4_K_XL-00002-of-00004.gguf
repo=/mnt/shared/plans/shoulders/benchmarking
label=${1:?label required}
cap6=${2:?1060 MiB cap required}
cap8=${3:?1070 MiB cap required}
host_gpus=${KV_HOST_GPU_IDS:?KV_HOST_GPU_IDS required}

mkdir -p "$base" "$build"
IFS=, read -ra host_ids <<< "$host_gpus"
uuids=()
for host_id in "${host_ids[@]}"; do
  uuid=$(nvidia-smi --id "$host_id" --query-gpu=uuid --format=csv,noheader) || exit 82
  uuids+=("$uuid")
done
joined=$(IFS=,; echo "${uuids[*]}")
printf '%s\n' "${host_ids[@]}" > "$base/$label.host_gpus.txt"
printf '%s\n' "${uuids[@]}" > "$base/$label.uuids.txt"
nvidia-smi --query-gpu=index,uuid,name,pci.bus_id,memory.total,memory.free --format=csv,noheader > "$base/$label.inventory.csv"
date -u +%FT%TZ > "$base/$label.start"
rm -f "$base/$label.exit"
python3 "$repo/scripts/analysis/inspect_ple_layout.py" \
  --gguf "$model" --gguf-py /data/bench-staging/kvchat-q41-tile-src/gguf-py \
  --output "$base/$label.layout.json" > /dev/null || exit 83
read -r rows rowbytes offset <<< "$(python3 -c 'import json,sys; t=json.load(open(sys.argv[1]))["table_tensors"]; assert len(t)==1 and t[0]["n_bytes"]%t[0]["shape"][1]==0; print(t[0]["shape"][1], t[0]["n_bytes"]//t[0]["shape"][1], t[0]["data_offset"])' "$base/$label.layout.json")"
if [ -z "$rows" ] || [ -z "$rowbytes" ] || [ -z "$offset" ]; then exit 84; fi
docker run --rm --gpus "\"device=$joined\"" --network none \
  -v "$repo:/bench:ro" -v "$build:/build" -v "$model:/model.gguf:ro" \
  nvidia/cuda:12.9.2-devel-ubuntu24.04 \
  bash -c "nvcc -std=c++17 -O2 /bench/scripts/integration/ple_shard_probe.cu -o /build/ple_shard_probe && /build/ple_shard_probe /model.gguf $rows $rowbytes $offset $cap6 $cap8" \
  > "$base/$label.log" 2>&1
rc=$?
echo "$rc" > "$base/$label.exit"
date -u +%FT%TZ > "$base/$label.finish"
tail -12 "$base/$label.log"
exit "$rc"
