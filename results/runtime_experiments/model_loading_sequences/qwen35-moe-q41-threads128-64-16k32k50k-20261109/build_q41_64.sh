#!/usr/bin/env bash
set -euo pipefail
root=/data/bench-staging
source_128="$root/kvchat-b11669-src"
build_128="$root/kvchat-q41-native-build"
source_64="$root/kvchat-q41-64-src"
build_64="$root/kvchat-q41-64-build"
test ! -e "$source_64"
test ! -e "$build_64"
cp -a "$source_128" "$source_64"
cp -a "$build_128" "$build_64"
python3 - "$source_64/ggml/src/ggml-cuda/fattn-vec.cuh" <<'PY'
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
new=old.replace('return 128;', 'return 64;')
assert text.count(old)==1
path.write_text(text.replace(old,new,1))
PY
docker run --rm --gpus all --network none \
  -v "$source_64:/src:ro" -v "$build_64:/build" -w /src 4bfa1cb0a955 \
  cmake --build /build --target llama-simple -j 6 \
  > "$root/build_q41_64.log" 2>&1
grep -E 'GGML_CUDA_FA_QUANTS' "$build_64/CMakeCache.txt"
sha256sum "$build_64/bin/llama-simple" "$build_64/bin/libggml-cuda.so" 2>/dev/null || true
tail -6 "$root/build_q41_64.log"
