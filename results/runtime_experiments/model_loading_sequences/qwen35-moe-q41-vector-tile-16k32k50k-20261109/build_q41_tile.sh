#!/usr/bin/env bash
set -euo pipefail
root=/data/bench-staging
cp -a "$root/kvchat-b11669-src" "$root/kvchat-q41-tile-src"
cp -a "$root/kvchat-b11669-build" "$root/kvchat-q41-tile-build"
python3 - "$root/kvchat-q41-tile-src/ggml/src/ggml-cuda/fattn.cu" <<'PY'
from pathlib import Path
import sys
p=Path(sys.argv[1])
s=p.read_text()
old="""            if (Q->ne[1] <= 2) {
                return BEST_FATTN_KERNEL_VEC;
            }
        }
    }
    return BEST_FATTN_KERNEL_TILE;
}"""
new=old.replace('if (Q->ne[1] <= 2)', 'if (Q->ne[1] <= 2 && !(K->type == GGML_TYPE_Q4_1 && V->type == GGML_TYPE_Q4_1 && Q->ne[0] == 256 && gqa_opt_applies))')
assert s.count(old)==1
p.write_text(s.replace(old,new,1))
PY
docker run --rm --gpus all --network none \
  -v "$root/kvchat-q41-tile-src:/src:ro" -v "$root/kvchat-q41-tile-build:/build" -w /src 4bfa1cb0a955 \
  cmake --build /build --target llama-simple -j 6 \
  > "$root/build_q41_tile.log" 2>&1
tail -8 "$root/build_q41_tile.log"
