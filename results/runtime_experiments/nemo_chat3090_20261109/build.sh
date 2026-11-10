#!/usr/bin/env bash
set -eu
repo=/mnt/shared/plans/shoulders/benchmarking
mkdir -p /data/bench-staging/nemo-reversed-20261109
docker run --rm --gpus all --network none \
  -v "$repo:/work:ro" \
  -v /data/bench-staging/kvchat-b11669-src:/src:ro \
  -v /data/bench-staging/kvchat-b11669-build:/build:ro \
  -v /data/bench-staging/nemo-reversed-20261109:/out \
  -w /work 4bfa1cb0a955 bash -lc \
  'g++ -O2 -std=c++17 -pthread -I/src/include -I/src/ggml/include results/runtime_experiments/nemo_single_chat_20261109/nemo_single.cpp -L/build/bin -lllama -lggml -lggml-base -lggml-cpu -lggml-cuda -Wl,-rpath,/build/bin -o /out/nemo-single'
