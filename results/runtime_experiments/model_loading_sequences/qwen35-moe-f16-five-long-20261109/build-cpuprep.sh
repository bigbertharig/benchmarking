#!/usr/bin/env bash
set -euo pipefail
root=/data/bench-staging
cp -a "$root/kvchat-b11669-src" "$root/kvchat-f16-five-cpuprep-src"
cp -a "$root/kvchat-b11669-build" "$root/kvchat-f16-five-cpuprep-build"
patch -d "$root/kvchat-f16-five-cpuprep-src" -p1 < five-f16-cpuprep.patch
docker run --rm --gpus all --network none \
  -v "$root/kvchat-f16-five-cpuprep-src:/src:ro" -v "$root/kvchat-f16-five-cpuprep-build:/build" \
  -w /src 4bfa1cb0a955 cmake --build /build --target llama-simple -j 4
