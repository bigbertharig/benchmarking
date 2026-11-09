#!/usr/bin/env bash
set -euo pipefail
root=/data/bench-staging
base_src="$root/kvchat-f16-five-cpuprep-src"
base_build="$root/kvchat-f16-five-cpuprep-build"
for arm in direct split dedicated; do
  if [ "$arm" = direct ]; then name=kvchat-admission-20261109;
  elif [ "$arm" = split ]; then name=kvchat-split-admission-20261109;
  else name=kvchat-dedicated-prep-20261109; fi
  cp -a "$base_src" "$root/${name}-src"
  cp -a "$base_build" "$root/${name}-build"
  patch -d "$root/${name}-src" -p1 < "${arm}.patch"
  docker run --rm --gpus all --network none \
    -v "$root/${name}-src:/src:ro" -v "$root/${name}-build:/build" \
    -w /src 4bfa1cb0a955 cmake --build /build --target llama-simple -j 4
done
