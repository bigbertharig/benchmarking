#!/usr/bin/env python3
"""Inspect Qwen3.8 PLE metadata without loading model tensor payloads."""
import argparse
import json
import pathlib
import sys

ap = argparse.ArgumentParser()
ap.add_argument('--gguf', type=pathlib.Path, required=True)
ap.add_argument('--gguf-py', type=pathlib.Path, required=True)
ap.add_argument('--output', type=pathlib.Path, required=True)
args = ap.parse_args()
sys.path.insert(0, str(args.gguf_py))
from gguf import GGUFReader

reader = GGUFReader(args.gguf)
rows = []
for tensor in reader.tensors:
    if 'per_layer_token_embd' in tensor.name or 'ngram' in tensor.name.lower():
        rows.append({'name': tensor.name, 'shape': [int(x) for x in tensor.shape],
                     'tensor_type': tensor.tensor_type.name, 'n_bytes': int(tensor.n_bytes),
                     'data_offset': int(tensor.data_offset)})
report = {'gguf': str(args.gguf), 'table_tensors': rows,
          'metadata': {name: str(field.parts[-1].tolist())[:1000] for name, field in reader.fields.items()
                       if 'ple' in name.lower() or 'ngram' in name.lower()}}
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_text(json.dumps(report, indent=2) + '\n', newline='\n')
print(json.dumps(report, indent=2))
