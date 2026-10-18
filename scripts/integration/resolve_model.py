#!/usr/bin/env python3
"""Print one registry model's runtime settings as shell assignments for the integration lanes.

usage: eval "$(python3 resolve_model.py <model-id>)"
Sets GGUF (hot-set copy when present), CTX, BATCH, PARALLEL, NGL, EXTRA (registry extra args),
BASE_EXTRA (extra args without reasoning flags) and THINK_TOKS (thinking budget that fits ctx).
"""

from __future__ import annotations

import json
import shlex
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BENCH = HERE.parents[1]
TREE = BENCH.parents[2]  # <tree>/plans/shoulders/benchmarking -> <tree>
sys.path.insert(0, str(BENCH / "scripts" / "active"))
sys.path.insert(0, str(TREE / "agents"))
import model_library  # noqa: E402

REASONING_FLAGS = {"--reasoning", "--reasoning-budget"}


def strip_reasoning(args: list[str]) -> list[str]:
    out, skip = [], False
    for arg in args:
        if skip:
            skip = False
            continue
        if arg in REASONING_FLAGS:
            skip = True
            continue
        out.append(arg)
    return out


def main() -> int:
    r = model_library.resolve(sys.argv[1])
    gguf = r["gguf_path"]
    config_path = TREE / "agents" / "config.json"
    if config_path.is_file():
        from brain_core import resolve_hotset_gguf

        gguf = str(resolve_hotset_gguf(gguf, json.loads(config_path.read_text(encoding="utf-8"))))
    rt = r.get("runtime", {})
    ctx = int(rt.get("ctx_size", 4096))
    extra = [str(a) for a in r.get("extra_args", [])]
    values = {
        "GGUF": gguf,
        "CTX": str(ctx),
        "BATCH": str(rt.get("batch_size", 64)),
        "PARALLEL": str(rt.get("parallel", 1)),
        "NGL": str(rt.get("n_gpu_layers", 999)),
        "EXTRA": " ".join(shlex.quote(a) for a in extra),
        "BASE_EXTRA": " ".join(shlex.quote(a) for a in strip_reasoning(extra)),
        # Leave room for the few-shot prompt (BBH prompts run to about 1500 tokens).
        "THINK_TOKS": str(max(1024, min(4096, ctx - 2048))),
    }
    for key, value in values.items():
        print(f"{key}={shlex.quote(value)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
