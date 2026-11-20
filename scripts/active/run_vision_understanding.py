#!/usr/bin/env python3
"""Run the local-only understanding suite against a localhost endpoint."""

from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
import os
import re
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlparse


def normalize(value: object) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", str(value).casefold()))


def parse_answer(text: str) -> tuple[str, bool]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.I | re.S)
    try:
        value = json.loads(cleaned)
        valid = isinstance(value, dict) and isinstance(value.get("answer"), (str, int, float))
        valid = valid and isinstance(value.get("evidence"), list) and isinstance(value.get("visible_text"), list)
        valid = valid and isinstance(value.get("confidence"), (int, float))
        return str(value.get("answer", "")), bool(valid)
    except (json.JSONDecodeError, TypeError):
        return cleaned, False


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:11436/v1")
    parser.add_argument("--model", required=True)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--max-tokens", type=int, default=1024)
    args = parser.parse_args()
    if args.max_tokens < 1:
        parser.error("--max-tokens must be positive")

    host = urlparse(args.base_url).hostname
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise SystemExit(f"refusing non-local endpoint: {args.base_url}")

    suite = args.manifest.resolve().parent
    cases = [json.loads(line) for line in args.manifest.read_text(encoding="utf-8").splitlines() if line.strip()]
    if args.limit is not None:
        cases = cases[: args.limit]
    for case in cases:
        image_path = suite / case["image"]
        if not image_path.is_file():
            raise SystemExit(f"missing local asset: {image_path}")

    args.output.mkdir(parents=True, exist_ok=True)
    results_file = args.output / "results.jsonl"
    if results_file.exists() or (args.output / "summary.json").exists():
        raise SystemExit(f"refusing to overwrite an existing run: {args.output}")
    context_file = args.output / "run_context.json"
    context = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "status": "running",
        "model": args.model,
        "base_url": args.base_url,
        "manifest": str(args.manifest),
        "manifest_sha256": hashlib.sha256(args.manifest.read_bytes()).hexdigest(),
        "planned_cases": len(cases),
        "max_tokens": args.max_tokens,
        "temperature": 0,
    }
    context_file.write_text(json.dumps(context, indent=2) + "\n", encoding="utf-8")
    results_file.touch()
    results = []
    for index, case in enumerate(cases, 1):
        image_path = suite / case["image"]
        encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
        instruction = (
            'Return only JSON with this schema: {"answer":"short answer",'
            '"evidence":["visible evidence"],"visible_text":[],"confidence":0.0}. '
            + case["prompt"]
        )
        payload = {
            "model": args.model,
            "temperature": 0,
            "max_tokens": args.max_tokens,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": instruction},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{encoded}"}},
                    ],
                }
            ],
        }
        request = urllib.request.Request(
            args.base_url.rstrip("/") + "/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": "Bearer EMPTY"},
        )
        started = time.monotonic()
        try:
            with urllib.request.urlopen(request, timeout=600) as response:
                body = json.load(response)
            raw = body["choices"][0]["message"]["content"]
            answer, schema_ok = parse_answer(raw)
            expected = case["expected"]["answers"]
            correct = normalize(answer) in {normalize(item) for item in expected}
            error = None
        except Exception as exc:  # preserve per-case failures in the report
            raw, answer, schema_ok, correct = "", "", False, False
            error = f"{type(exc).__name__}: {exc}"
        result = {
            "id": case["id"],
            "category": case["category"],
            "answer": answer,
            "expected": case["expected"]["answers"],
            "correct": correct,
            "schema_ok": schema_ok,
            "seconds": round(time.monotonic() - started, 3),
            "raw": raw,
            "error": error,
        }
        results.append(result)
        with results_file.open("a", encoding="utf-8") as receipt:
            receipt.write(json.dumps(result) + "\n")
            receipt.flush()
            os.fsync(receipt.fileno())
        print(f"[{index}/{len(cases)}] {case['id']}: correct={correct} schema={schema_ok}", flush=True)

    categories = {}
    for category in sorted({item["category"] for item in results}):
        group = [item for item in results if item["category"] == category]
        categories[category] = {
            "correct": sum(item["correct"] for item in group),
            "total": len(group),
            "accuracy": sum(item["correct"] for item in group) / len(group),
        }
    summary = {
        "suite": "local-understanding-full-v1" if suite.name == "local-full-v1" else "local-understanding-v1",
        "model": args.model,
        "max_tokens": args.max_tokens,
        "cases": len(results),
        "correct": sum(item["correct"] for item in results),
        "accuracy": sum(item["correct"] for item in results) / len(results) if results else 0,
        "schema_rate": sum(item["schema_ok"] for item in results) / len(results) if results else 0,
        "categories": categories,
        "cloud_dependencies": False,
    }
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    context["status"] = "complete"
    context["finished_at"] = datetime.now(timezone.utc).isoformat()
    context["completed_cases"] = len(results)
    context_file.write_text(json.dumps(context, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
