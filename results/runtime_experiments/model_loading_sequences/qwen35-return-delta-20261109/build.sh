#!/usr/bin/env bash
set -euo pipefail
root=/data/bench-staging
name=kvchat-return-delta-20261109
cp -a "$root/kvchat-q41-delta-src" "$root/${name}-src"
cp -a "$root/kvchat-q41-delta-build" "$root/${name}-build"
patch -d "$root/${name}-src" -p1 < return_delta.patch
docker run --rm --gpus all --network none \
  -v "$root/${name}-src:/src:ro" -v "$root/${name}-build:/build" \
  -w /src 4bfa1cb0a955 cmake --build /build --target llama-simple -j 4
