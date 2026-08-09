#!/usr/bin/env python3
"""Run cost-aware routing cases and record one aggregate schema-v2 result."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

from routing_score import index_tiers, score_route


def chat(base_url: str, model: str, prompt: str, timeout: int) -> str:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "Choose the cheapest sufficient route from the current tier list. Output only strict JSON: {\"route\": \"tier_id\", \"reason\": \"short reason\"}."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0,
        "stream": False,
    }
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        decoded = json.loads(response.read())
    message = decoded["choices"][0]["message"]
    text = str(message.get("content") or message.get("reasoning_content") or "").strip()
    if not text:
        raise RuntimeError("chat completion returned no content")
    return text


def strict_route(text: str) -> tuple[str, bool]:
    if text.startswith("```") or text.endswith("```"):
        return "", False
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return "", False
    if not isinstance(payload, dict) or set(payload) != {"route", "reason"}:
        return "", False
    if not isinstance(payload["route"], str) or not isinstance(payload["reason"], str):
        return "", False
    return payload["route"], True


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the cost-aware routing benchmark.")
    parser.add_argument("--model", required=True)
    parser.add_argument("--runtime-base", required=True)
    parser.add_argument("--config", default="/opt/bench/routing_cases.json")
    parser.add_argument("--run-name", required=True)
    parser.add_argument("--run-class", choices=("smoke", "provisional", "validated", "full"), default="provisional")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--results-dir", default="/results")
    parser.add_argument("--scripts-dir", default="/benchmark-scripts")
    parser.add_argument("--records", default="/mnt/shared/plans/shoulders/benchmarking/results/model_benchmark_records.jsonl")
    parser.add_argument("--reference-output", default="/mnt/shared/plans/shoulders/benchmarking/results/MODEL_BENCHMARK_REFERENCE.md")
    parser.add_argument("--scoreboard-output", default="/mnt/shared/plans/shoulders/benchmarking/results/model_library_scoreboard.json")
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--no-record", action="store_true")
    args = parser.parse_args()

    if not re.fullmatch(r"[A-Za-z0-9_.-]+", args.run_name):
        parser.error("--run-name may contain only letters, digits, dot, underscore, and hyphen")
    if args.limit is not None and args.limit <= 0:
        parser.error("--limit must be positive")

    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    tiers = index_tiers(config)
    cases = config.get("cases", [])
    if not isinstance(cases, list) or not cases:
        raise SystemExit("routing config must contain cases")
    if args.limit is not None:
        cases = cases[: args.limit]
    tier_prompt = "\n".join(
        f"- {tier_id}: capability_rank={tier['capability_rank']}, cost_units={tier['cost_units']}, use={tier['description']}"
        for tier_id, tier in tiers.items()
    )
    started = time.monotonic()
    results: list[dict[str, Any]] = []
    format_failures = 0

    try:
        for case in cases:
            prompt = f"Available routes:\n{tier_prompt}\n\nTask:\n{case['task']}"
            response = chat(args.runtime_base, args.model, prompt, args.timeout)
            route, format_valid = strict_route(response)
            if not format_valid:
                format_failures += 1
            scores = score_route(case, route, tiers) if format_valid else {
                "task_success": 0.0,
                "routing_efficiency": 0.0,
                "routing_value": 0.0,
            }
            results.append(
                {
                    "case_id": case["id"],
                    "selected_route": route,
                    "minimum_tier": case["minimum_tier"],
                    "format_valid": format_valid,
                    "scores": scores,
                    "response": response,
                }
            )
    except Exception as exc:
        if not args.no_record:
            recorder = Path(args.scripts_dir) / "scripts" / "active" / "record_benchmark_result.py"
            subprocess.run(
                [
                    sys.executable, str(recorder), "--model", args.model,
                    "--test-id", "routing_cost_awareness", "--status", "failure",
                    "--run-class", args.run_class, "--harness", "bench-routing",
                    "--suite", args.run_name, "--failure-kind", "harness_error",
                    "--failure-message", f"{type(exc).__name__}: {exc}", "--failed-request-count", "1",
                    "--records", args.records, "--reference-output", args.reference_output,
                    "--scoreboard-output", args.scoreboard_output,
                ],
                check=False,
            )
        raise

    elapsed = time.monotonic() - started
    means = {
        name: sum(row["scores"][name] for row in results) / len(results)
        for name in ("task_success", "routing_efficiency", "routing_value")
    }
    summary = {
        "model": args.model,
        "run_name": args.run_name,
        "run_class": args.run_class,
        "case_count": len(results),
        "format_failure_count": format_failures,
        "scores": means,
        "elapsed_seconds": elapsed,
        "results": results,
    }
    run_dir = Path(args.results_dir).resolve() / f"bench-routing_{re.sub(r'[^A-Za-z0-9_.-]+', '_', args.model)}_{args.run_name}"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    if not args.no_record:
        recorder = Path(args.scripts_dir) / "scripts" / "active" / "record_benchmark_result.py"
        command = [
            sys.executable, str(recorder), "--model", args.model,
            "--test-id", "routing_cost_awareness", "--score", str(means["routing_value"]),
            "--raw-harness-score", str(means["routing_efficiency"]),
            "--normalized-answer-score", str(means["task_success"]),
            "--metric", "routing_value", "--run-class", args.run_class,
            "--sample-count", str(len(results)), "--format-compatibility",
            "degraded" if format_failures else "compatible", "--extractor-failure-count", str(format_failures),
            "--harness", "bench-routing", "--suite", args.run_name,
            "--wall-time-seconds", str(elapsed), "--config-id", str(config.get("version", "")),
            "--config-json", json.dumps({"tiers": config["tiers"]}, sort_keys=True),
            "--records", args.records, "--reference-output", args.reference_output,
            "--scoreboard-output", args.scoreboard_output,
            "--notes", json.dumps(means, sort_keys=True),
        ]
        if subprocess.run(command, check=False).returncode != 0:
            return 1

    print(json.dumps({"summary": str(run_dir / "summary.json"), **means}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
