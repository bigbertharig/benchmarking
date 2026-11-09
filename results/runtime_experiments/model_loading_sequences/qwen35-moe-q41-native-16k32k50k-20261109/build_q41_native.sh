#!/usr/bin/env bash
set -euo pipefail
src=/data/bench-staging/kvchat-b11669-src
build=/data/bench-staging/kvchat-q41-native-build
mkdir -p "$build"
docker run --rm --gpus all --network none \
  -v "$src:/src:ro" -v "$build:/build" -w /src 4bfa1cb0a955 \
  cmake -S /src -B /build -DCMAKE_BUILD_TYPE=Release \
    '-DCMAKE_CUDA_ARCHITECTURES=61;86' \
    -DGGML_CUDA=ON -DGGML_CUDA_FA=ON -DGGML_CUDA_NCCL=ON \
    '-DGGML_CUDA_FA_QUANTS=q4_0-q4_0;q8_0-q8_0;f16-f16;bf16-bf16;q4_1-q4_1' \
    -DGGML_AVX=OFF -DGGML_AVX2=OFF -DGGML_AVX512=OFF \
    -DLLAMA_BUILD_EXAMPLES=ON -DLLAMA_BUILD_TESTS=OFF -DLLAMA_CURL=OFF
docker run --rm --gpus all --network none \
  -v "$src:/src:ro" -v "$build:/build" -w /src 4bfa1cb0a955 \
  cmake --build /build --target llama-simple -j 8
