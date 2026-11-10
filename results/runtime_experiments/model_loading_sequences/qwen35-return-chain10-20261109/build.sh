#!/usr/bin/env bash
set -euo pipefail
root=/data/bench-staging
name=kvchat-return-chain10-20261109
cp -a "$root/kvchat-return-delta-20261109-src" "$root/${name}-src"
cp -a "$root/kvchat-return-delta-20261109-build" "$root/${name}-build"
patch -d "$root/${name}-src" -p1 < chain10.patch
docker run --rm --gpus all --network none \
  -v "$root/${name}-src:/src:ro" -v "$root/${name}-build:/build" \
  -w /src 4bfa1cb0a955 cmake --build /build --target llama-simple -j 4
