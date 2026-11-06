#!/usr/bin/env python3
"""Read GGUF headers only; inventory expert tensors without loading weights."""
import argparse
import collections
import datetime as dt
import json
import pathlib
import re
import sys

EXPERT = re.compile(r"^blk\.(\d+)\.ffn_(up|down|gate)_exps\.weight$")
NGRAM = re.compile(r"per_layer_token_embd|ngram", re.I)

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--gguf", type=pathlib.Path, nargs="+", required=True)
    p.add_argument("--gguf-py", type=pathlib.Path, required=True)
    p.add_argument("--output", type=pathlib.Path, required=True)
    a = p.parse_args()
    sys.path.insert(0, str(a.gguf_py))
    from gguf import GGUFReader
    files, layers, quant_types = [], collections.defaultdict(lambda: collections.defaultdict(list)), collections.Counter()
    ngram_bytes = expert_bytes = tensor_bytes = 0
    for path in a.gguf:
        if not path.is_file():
            p.error(f"missing GGUF shard: {path}")
        reader = GGUFReader(path)
        count = 0
        for t in reader.tensors:
            count += 1
            size = int(t.n_bytes)
            tensor_bytes += size
            quant_types[str(t.tensor_type.name)] += 1
            m = EXPERT.match(t.name)
            if m:
                expert_bytes += size
                layers[int(m.group(1))][m.group(2)].append({
                    "name": t.name, "shape": [int(x) for x in t.shape],
                    "bytes": size, "quant": t.tensor_type.name})
            if NGRAM.search(t.name):
                ngram_bytes += size
        files.append({"path": str(path), "bytes": path.stat().st_size,
                      "tensor_count": count})
        del reader
    report = {"schema": "expert-model-inventory/1",
              "observed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
              "files": files, "model_file_bytes": sum(x["bytes"] for x in files),
              "tensor_payload_bytes": tensor_bytes, "expert_tensor_bytes": expert_bytes,
              "ngram_tensor_bytes": ngram_bytes, "tensor_types": dict(quant_types),
              "expert_layers": {str(k): dict(v) for k,v in sorted(layers.items())},
              "expert_layer_count": len(layers)}
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"output": str(a.output), "expert_layers": len(layers),
                      "model_file_bytes": report["model_file_bytes"],
                      "ngram_tensor_bytes": ngram_bytes}))

if __name__ == "__main__":
    main()
