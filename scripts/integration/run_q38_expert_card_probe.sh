#!/usr/bin/env bash
set -uo pipefail

base=/mnt/shared/experiments/kv-matrix-20261107
label=${1:?label required}
host_gpus=${KV_HOST_GPU_IDS:?KV_HOST_GPU_IDS required}
sample=/data/bench-staging/q38_tiered_expert_probe_20261106_1worker
repo=/mnt/shared/plans/shoulders/benchmarking

mkdir -p "$base"
IFS=, read -ra host_ids <<< "$host_gpus"
if [ "${#host_ids[@]}" -ne 2 ]; then exit 81; fi
uuids=()
for host_id in "${host_ids[@]}"; do
  uuid=$(nvidia-smi --id "$host_id" --query-gpu=uuid --format=csv,noheader) || exit 82
  uuids+=("$uuid")
done
joined=$(IFS=,; echo "${uuids[*]}")
printf '%s\n' "${host_ids[@]}" > "$base/$label.host_gpus.txt"
printf '%s\n' "${uuids[@]}" > "$base/$label.uuids.txt"
nvidia-smi --query-gpu=index,uuid,name,pci.bus_id,memory.total --format=csv,noheader > "$base/$label.inventory.csv"
date -u +%FT%TZ > "$base/$label.start"
rm -f "$base/$label.exit"
docker run --rm --gpus "\"device=$joined\"" --network none \
  -e WORKERS=1 -v "$repo:/bench:ro" -v "$sample:/sample" \
  nvidia/cuda:12.9.2-devel-ubuntu24.04 \
  bash /bench/scripts/active/run_q38_tiered_expert_probe.sh \
  > "$base/$label.log" 2>&1
rc=$?
echo "$rc" > "$base/$label.exit"
date -u +%FT%TZ > "$base/$label.finish"
tail -8 "$base/$label.log"
exit "$rc"
