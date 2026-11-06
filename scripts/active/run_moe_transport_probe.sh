#!/usr/bin/env bash
set -euo pipefail
nvcc -O3 -std=c++17 -gencode arch=compute_61,code=sm_61 -gencode arch=compute_86,code=sm_86 /work/scripts/active/moe_transport_probe.cu -o /tmp/moe_transport_probe
for workers in 1 4 5; do
  for width in 2048 4096; do
    for mode in copy kernel; do
      /tmp/moe_transport_probe "$workers" "$width" "$mode" 300
    done
  done
done