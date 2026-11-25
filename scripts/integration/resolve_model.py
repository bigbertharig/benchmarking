#!/usr/bin/env python3
"""Print one registry model's runtime settings as shell assignments for the integration lanes.

usage: eval "$(python3 resolve_model.py <model-id>)"
Sets GGUF (registry path, or runtime-resolved path with --runtime-path), CTX, BATCH, PARALLEL, NGL, EXTRA (registry extra args),
BASE_EXTRA (extra args without reasoning flags) and THINK_TOKS (thinking budget that fits ctx).
"""

from __future__ import annotations

import argparse
import shlex
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BENCH = HERE.parents[1]
sys.path.insert(0, str(BENCH / "scripts" / "active"))
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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model")
    parser.add_argument("--runtime-path", action="store_true",
                        help="resolve the GGUF path using the installed Orchestration CLI")
    args = parser.parse_args()
    r = model_library.resolve(args.model)
    gguf = r["gguf_path"]
    if args.runtime_path:
        from orchestration_client import resolve_model_path
        gguf = resolve_model_path(gguf)
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
