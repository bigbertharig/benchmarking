#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "$0")/../.." && pwd)
source_tree=${KV_THREE_SOURCE_TREE:-/data/bench-staging/kvchat-q41-tile-src}
validated_build=${KV_THREE_VALIDATED_BUILD:-/data/bench-staging/kvchat-q41-tile-build}
output=${KV_THREE_BUILD_DIR:-/data/bench-staging/kvchat-q41-deep-build}

test -f "$source_tree/include/llama.h"
test -f "$root/scripts/active/llama_simple_chat_latency.cpp"
test -f "$validated_build/bin/libllama.so.0.7.0"
mkdir -p "$output/bin"
cp -a "$validated_build/bin/." "$output/bin/"

docker run --rm --network none --gpus all \
  --user "$(id -u):$(id -g)" \
  -v "$source_tree:/src:ro" \
  -v "$validated_build:/oldbuild:ro" \
  -v "$root/scripts/active/llama_simple_chat_latency.cpp:/benchmark/simple.cpp:ro" \
  -v "$output:/out" \
  4bfa1cb0a955 \
  /bin/bash -euc '
    c++ -std=c++17 -O3 -DNDEBUG -I/src/include -I/src/ggml/include \
      -c /benchmark/simple.cpp -o /out/simple.o
    c++ -O3 -DNDEBUG /out/simple.o -o /out/bin/llama-simple \
      -Wl,-rpath,/build/bin \
      /oldbuild/bin/libllama.so.0.7.0 \
      /oldbuild/bin/libggml.so.0.27.0 \
      /oldbuild/bin/libggml-cpu.so.0.27.0 \
      /oldbuild/bin/libggml-cuda.so.0.27.0 \
      /oldbuild/bin/libggml-base.so.0.27.0
  '
sha256sum "$root/scripts/active/llama_simple_chat_latency.cpp" "$output/bin/llama-simple"
