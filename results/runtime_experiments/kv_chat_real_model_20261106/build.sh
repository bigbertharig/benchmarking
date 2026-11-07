#!/usr/bin/env bash
set -u
base=/mnt/shared/experiments/kvchat-20261106
build=/data/bench-staging/kvchat-20261106-build
mkdir -p "$build"
date -u +%FT%TZ > "$base/build.start"
set -o pipefail
docker run --rm --gpus all \
  -v "$base/llama.cpp:/src" -v "$build:/build" \
  -w /src 4bfa1cb0a955 \
  bash -c 'cmake -S /src -B /build -DGGML_CUDA=ON -DCMAKE_BUILD_TYPE=Release -DCMAKE_CUDA_ARCHITECTURES="61;86" -DLLAMA_BUILD_TESTS=OFF -DLLAMA_BUILD_TOOLS=OFF -DLLAMA_BUILD_APP=OFF -DLLAMA_BUILD_SERVER=OFF -DLLAMA_CURL=OFF && cmake --build /build --target llama-simple -j6' \
  > "$base/build.log" 2>&1
rc=$?
date -u +%FT%TZ > "$base/build.finish"
echo "$rc" > "$base/build.exit"
tail -25 "$base/build.log"
exit "$rc"
