#!/usr/bin/env bash
set -euo pipefail
root=/data/bench-staging
cp -a "$root/kvchat-q41-tile-src" "$root/kvchat-q41-delta-src"
cp -a "$root/kvchat-q41-tile-build" "$root/kvchat-q41-delta-build"
patch -d "$root/kvchat-q41-delta-src" -p1 < live-kv-delta.patch
docker run --rm --gpus all --network none \
  -v "$root/kvchat-q41-delta-src:/src:ro" -v "$root/kvchat-q41-delta-build:/build" \
  -w /src 4bfa1cb0a955 cmake --build /build --target llama-simple -j 6
