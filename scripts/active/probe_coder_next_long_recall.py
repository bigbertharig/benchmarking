#!/usr/bin/env python3
"""Two-marker recall probe near 90% of Coder Next's 262K context."""
import argparse
import datetime as dt
import json
import pathlib
import time
import urllib.request

SAMPLE = "def accumulate(values):\n    total = 0\n    for value in values:\n        total += value\n    return total\n"
MARKER_A = "BRONZE-7319"
MARKER_B = "ORBIT-4286"

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--short", action="store_true", help="Use about 23.5K prompt tokens as a control")
    args = parser.parse_args()
    counts = [100, 750, 90] if args.short else [1000, 7500, 900]
    prompt = (
        SAMPLE * counts[0]
        + "\nRecord marker A exactly: " + MARKER_A + "\n"
        + SAMPLE * counts[1]
        + "\nRecord marker B exactly: " + MARKER_B + "\n"
        + SAMPLE * counts[2]
        + "\nWhat were markers A and B? Return a JSON object with keys marker_a and marker_b. "
          "Use the exact marker text and nothing else.\n"
    )
    body = json.dumps({
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "seed": 42,
        "max_tokens": 128,
        "stream": False,
    }).encode()
    request = urllib.request.Request(
        f"http://127.0.0.1:{args.port}/v1/chat/completions",
        body,
        {"Content-Type": "application/json"},
    )
    started = time.monotonic()
    receipt = {
        "schema": "coder-next-long-recall/1",
        "started_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "port": args.port,
        "markers": {"marker_a": MARKER_A, "marker_b": MARKER_B},
        "filler_repeats": counts,
    }
    try:
        with urllib.request.urlopen(request, timeout=7200) as response:
            data = json.load(response)
        choice = data["choices"][0]
        content = choice["message"].get("content") or ""
        receipt.update({
            "status": "complete",
            "wall_seconds": round(time.monotonic() - started, 3),
            "usage": data.get("usage"),
            "finish_reason": choice.get("finish_reason"),
            "content": content,
            "marker_a_found": MARKER_A in content,
            "marker_b_found": MARKER_B in content,
        })
    except Exception as exc:
        receipt.update({"status": "failed", "error": repr(exc),
                        "wall_seconds": round(time.monotonic() - started, 3)})
        raise
    finally:
        receipt["finished_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({k: receipt[k] for k in ("status", "wall_seconds", "usage",
                                                "marker_a_found", "marker_b_found")}))

if __name__ == "__main__":
    main()