#!/usr/bin/env python3
"""One practical coding response for matched MoE placement timing."""
import argparse
import datetime as dt
import json
import pathlib
import time
import urllib.request

PROMPT = (
    "Implement a Python LRUCache class with get(key) returning -1 for missing keys "
    "and put(key, value), both O(1). Capacity is a positive integer. Include a small "
    "unittest.TestCase covering eviction, update, and access-order behavior, then "
    "briefly explain the data structure choices."
)

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, required=True)
    p.add_argument("--label", required=True)
    p.add_argument("--output", type=pathlib.Path, required=True)
    a = p.parse_args()
    body = json.dumps({
        "messages": [{"role": "user", "content": PROMPT}],
        "temperature": 0,
        "seed": 42,
        "max_tokens": 1024,
        "stream": False,
    }).encode()
    request = urllib.request.Request(
        f"http://127.0.0.1:{a.port}/v1/chat/completions",
        body,
        {"Content-Type": "application/json"},
    )
    started = time.monotonic()
    with urllib.request.urlopen(request, timeout=600) as response:
        data = json.load(response)
    choice = data["choices"][0]
    receipt = {
        "schema": "moe-practical-task/1",
        "label": a.label,
        "recorded_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "prompt": PROMPT,
        "request": {"temperature": 0, "seed": 42, "max_tokens": 1024},
        "usage": data.get("usage"),
        "finish_reason": choice.get("finish_reason"),
        "content": choice["message"].get("content"),
        "wall_seconds": round(time.monotonic() - started, 3),
    }
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({k: receipt[k] for k in ("label", "usage", "finish_reason", "wall_seconds")}))

if __name__ == "__main__":
    main()