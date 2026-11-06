#!/usr/bin/env python3
"""Repeatable llama-server placement probe for Qwen3-Coder-Next.

Run on the rig after a load is ready. The server reports timing/token counts;
this script preserves each result immediately and never modifies the model.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import time
import urllib.request

SAMPLE = "def accumulate(values):\n    total = 0\n    for value in values:\n        total += value\n    return total\n"
CASE_SETS = {
    "short": [(1, 256), (1, 256), (1, 256), (24, 256), (96, 256)],
    "depth32": [(120, 128), (1150, 128)],
    "depth262": [(1000, 128), (9400, 128)],
    "depth262_90": [(9400, 128)],
}

def run_case(port: int, repeats: int, output_tokens: int) -> dict:
    prompt = SAMPLE * repeats + "\nWrite a Python function that merges two sorted integer lists. Include a brief example.\n"
    body = json.dumps({
        "prompt": prompt,
        "n_predict": output_tokens,
        "temperature": 0,
        "seed": 42,
        "ignore_eos": True,
        "cache_prompt": False,
        "stream": False,
    }).encode()
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/completion",
        body,
        {"Content-Type": "application/json"},
    )
    started = time.monotonic()
    with urllib.request.urlopen(request, timeout=3600) as response:
        data = json.load(response)
    return {
        "sample_repeats": repeats,
        "output_limit": output_tokens,
        "wall_seconds": round(time.monotonic() - started, 3),
        "prompt_tokens": data.get("tokens_evaluated"),
        "completion_tokens": data.get("tokens_predicted"),
        "timings": data.get("timings"),
        "stop": data.get("stop"),
        "stopped_eos": data.get("stopped_eos"),
        "truncated": data.get("truncated"),
    }

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--case-set", choices=CASE_SETS, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    receipt = {
        "schema": "coder-next-placement-probe/2",
        "label": args.label,
        "case_set": args.case_set,
        "started_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "port": args.port,
        "request": {"temperature": 0, "seed": 42, "ignore_eos": True, "cache_prompt": False},
        "cases": [],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    try:
        for repeats, output_tokens in CASE_SETS[args.case_set]:
            row = run_case(args.port, repeats, output_tokens)
            receipt["cases"].append(row)
            args.output.write_text(json.dumps(receipt, indent=2) + "\n")
            print(json.dumps({
                "prompt_tokens": row["prompt_tokens"],
                "completion_tokens": row["completion_tokens"],
                "predicted_per_second": (row["timings"] or {}).get("predicted_per_second"),
                "prompt_per_second": (row["timings"] or {}).get("prompt_per_second"),
            }), flush=True)
        receipt["status"] = "complete"
    except Exception as exc:
        receipt["status"] = "failed"
        receipt["error"] = repr(exc)
        raise
    finally:
        receipt["finished_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
        args.output.write_text(json.dumps(receipt, indent=2) + "\n")

if __name__ == "__main__":
    main()