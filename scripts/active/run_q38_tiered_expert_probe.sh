#!/usr/bin/env bash
set -euo pipefail
workers="${WORKERS:-5}"
nvcc -std=c++17 -O2 -Xcompiler=-pthread \
  -gencode arch=compute_61,code=sm_61 \
  -gencode arch=compute_86,code=sm_86 \
  /bench/scripts/active/q38_tiered_expert_probe.cu -o /sample/q38_tiered_expert_probe
results="/sample/results_${workers}workers_$(date -u +%Y%m%dT%H%M%S).jsonl"
for mode in gpu0 gpu0_ram gpu0_nvme resident ram nvme; do
  /sample/q38_tiered_expert_probe /sample "$mode" "$workers" 100
done | tee "$results"