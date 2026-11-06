#!/usr/bin/env python3
"""Extract one Qwen3.8 Q2_0 expert into aligned row shards for a read-only probe.

The sample is model-derived data. Keep output outside Git; do not redistribute it.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

HIDDEN = 2560
INTERMEDIATE = 640
EXPERTS = 512
BLOCK = 64
BLOCK_BYTES = 18
MATRIX_BYTES = HIDDEN * INTERMEDIATE // BLOCK * BLOCK_BYTES


def decode_q2(raw: bytes, rows: int, cols: int) -> np.ndarray:
    blocks = np.frombuffer(raw, dtype=np.uint8).reshape(-1, BLOCK_BYTES)
    scale = blocks[:, :2].copy().view("<f2").astype(np.float32).reshape(-1, 1)
    shifts = np.array([0, 2, 4, 6], dtype=np.uint8)
    q = ((blocks[:, 2:, None] >> shifts) & 3).reshape(-1, BLOCK).astype(np.float32) - 1
    return (q * scale).reshape(rows, cols)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gguf", type=Path, required=True)
    ap.add_argument("--gguf-py", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--layer", type=int, default=0)
    ap.add_argument("--expert", type=int, default=0)
    ap.add_argument("--workers", type=int, default=5)
    args = ap.parse_args()
    if not (0 <= args.expert < EXPERTS and args.workers in (1, 2, 5)):
        ap.error("expert must be 0..511; workers must divide 640 in 64-row blocks (1, 2, 5)")
    if not args.gguf.is_file():
        ap.error("GGUF file not found")
    sys.path.insert(0, str(args.gguf_py))
    from gguf import GGUFReader

    reader = GGUFReader(args.gguf)
    tensors = {t.name: t for t in reader.tensors}
    raw = {}
    for name, dims in (
        ("gate", (HIDDEN, INTERMEDIATE, EXPERTS)),
        ("up", (HIDDEN, INTERMEDIATE, EXPERTS)),
        ("down", (INTERMEDIATE, HIDDEN, EXPERTS)),
    ):
        t = tensors[f"blk.{args.layer}.ffn_{name}_exps.weight"]
        if int(t.tensor_type) != 42 or tuple(map(int, t.shape)) != dims:
            raise ValueError(f"unexpected {name} type/shape: {t.tensor_type} {t.shape}")
        offset = int(t.data_offset) + args.expert * MATRIX_BYTES
        raw[name] = bytes(reader.data[offset:offset + MATRIX_BYTES])
        if len(raw[name]) != MATRIX_BYTES:
            raise ValueError(f"short tensor: {name}")
    args.output.mkdir(parents=True, exist_ok=True)
    full_blob = raw["gate"] + raw["up"] + raw["down"]
    (args.output / "full.bin").write_bytes(full_blob)
    (args.output / "full_direct.bin").write_bytes(full_blob + bytes(-len(full_blob) % 4096))

    rows = INTERMEDIATE // args.workers
    row_bytes = HIDDEN // BLOCK * BLOCK_BYTES
    down_row_bytes = INTERMEDIATE // BLOCK * BLOCK_BYTES
    slice_bytes = rows // BLOCK * BLOCK_BYTES
    shards = []
    for worker in range(args.workers):
        start = worker * rows
        end = start + rows
        gate = raw["gate"][start * row_bytes:end * row_bytes]
        up = raw["up"][start * row_bytes:end * row_bytes]
        down = b"".join(raw["down"][h * down_row_bytes + start // BLOCK * BLOCK_BYTES:
                                     h * down_row_bytes + start // BLOCK * BLOCK_BYTES + slice_bytes]
                        for h in range(HIDDEN))
        blob = gate + up + down
        path = args.output / f"shard_{worker}.bin"
        path.write_bytes(blob + bytes(-len(blob) % 4096))
        shards.append({"name": path.name, "data_bytes": len(blob), "file_bytes": path.stat().st_size})
    x = ((np.arange(HIDDEN, dtype=np.int32) % 31) - 15).astype(np.float32) * 0.02
    gate = decode_q2(raw["gate"], INTERMEDIATE, HIDDEN)
    up = decode_q2(raw["up"], INTERMEDIATE, HIDDEN)
    down = decode_q2(raw["down"], HIDDEN, INTERMEDIATE)
    g = gate @ x
    u = up @ x
    act = (g / (1.0 + np.exp(-g))) * u
    y = (down @ act).astype(np.float32)
    (args.output / "reference.f32").write_bytes(y.tobytes())
    info = {
        "schema": 1, "model": args.gguf.name, "layer": args.layer, "expert": args.expert,
        "quant_type": "Q2_0", "hidden": HIDDEN, "intermediate": INTERMEDIATE,
        "workers": args.workers, "rows_per_worker": rows,
        "matrix_bytes": MATRIX_BYTES, "shards": shards,
        "full_sha256": hashlib.sha256((args.output / "full.bin").read_bytes()).hexdigest(),
        "reference_max_abs": float(np.max(np.abs(y))),
        "reference_sha256": hashlib.sha256(y.tobytes()).hexdigest(),
    }
    (args.output / "sample.json").write_text(json.dumps(info, indent=2) + "\n")
    print(json.dumps({"output": str(args.output), "workers": args.workers, "sample_bytes": 3 * MATRIX_BYTES,
                      "reference_max_abs": info["reference_max_abs"]}))


if __name__ == "__main__":
    main()