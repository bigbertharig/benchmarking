#!/usr/bin/env bash
set -euo pipefail
root=/data/bench-staging
source_128="$root/kvchat-b11669-src"
build_128="$root/kvchat-q41-native-build"
source_256="$root/kvchat-q41-256-src"
build_256="$root/kvchat-q41-256-build"
test ! -e "$source_256"
test ! -e "$build_256"
cp -a "$source_128" "$source_256"
cp -a "$build_128" "$build_256"
python3 - "$source_256/ggml/src/ggml-cuda/fattn-vec.cuh" <<'PY'
from pathlib import Path
import sys
path=Path(sys.argv[1])
text=path.read_text()
old='''static int ggml_cuda_fattn_vec_get_nthreads_host(const int cc) {
    return 128;
    GGML_UNUSED(cc);
}

static constexpr __device__ int ggml_cuda_fattn_vec_get_nthreads_device() {
    return 128;
}'''
new=old.replace('return 128;', 'return 256;')
assert text.count(old)==1
path.write_text(text.replace(old,new,1))
PY
docker run --rm --gpus all --network none \
  -v "$source_256:/src:ro" -v "$build_256:/build" -w /src 4bfa1cb0a955 \
  cmake --build /build --target llama-simple -j 6 \
  > "$root/build_q41_256.log" 2>&1
grep -E 'GGML_CUDA_FA_QUANTS' "$build_256/CMakeCache.txt"
sha256sum "$build_256/bin/llama-simple" "$build_256/bin/libggml-cuda.so" 2>/dev/null || true
tail -6 "$root/build_q41_256.log"
