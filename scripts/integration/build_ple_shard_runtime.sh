#!/usr/bin/env bash
set -euo pipefail

repo=/mnt/shared/plans/shoulders/benchmarking
source_base=/data/bench-staging/kvchat-q41-tile-src
source_new=/data/bench-staging/ple-shard-llama-src-20261113
build=/data/bench-staging/ple-shard-llama-build-20261113
image=4bfa1cb0a955

test -f "$source_base/src/models/qwen4exp.cpp"
mkdir -p "$build"
if [ ! -f "$source_new/src/models/qwen4exp.cpp" ]; then
  cp -a "$source_base" "$source_new"
  python3 "$repo/scripts/integration/patch_qwen4exp_ple.py" --source "$source_new"
fi
docker run --rm --network none --gpus all --user "$(id -u):$(id -g)" \
  -v "$repo:/bench:ro" -v "$source_new:/src:ro" -v "$build:/out" \
  "$image" /bin/bash -euc '
    nvcc -std=c++17 -O2 -shared -Xcompiler=-fPIC \
      /bench/scripts/integration/ple_shard_store.cu -o /out/libple_shard_store.so
    cmake -S /src -B /out/llama -DCMAKE_BUILD_TYPE=Release \
      -DGGML_CUDA=ON -DLLAMA_BUILD_SERVER=ON -DLLAMA_BUILD_TESTS=OFF \
      -DCMAKE_CUDA_ARCHITECTURES="61;86"
    cmake --build /out/llama --target llama-server -j 4
  '
test -f "$build/libple_shard_store.so"
test -f "$build/llama/bin/llama-server"
sha256sum "$repo/scripts/integration/ple_shard_store.cu" \
  "$source_new/src/models/qwen4exp.cpp" "$build/libple_shard_store.so" \
  "$build/llama/bin/llama-server"
