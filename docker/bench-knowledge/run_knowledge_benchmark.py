#!/usr/bin/env python3
"""Run frozen generation-scored knowledge probes against a shared runtime."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


METHODOLOGY = ("bench-knowledge/chat-mc", "3.0.0", "knowledge-chat-mc-v1")
TASK_ALIASES = {
    "mmlu": "academic",
    "arc_challenge": "science",
    "hellaswag": "commonsense",
    "truthfulqa_mc2": "truthfulness",
    "boolq": "reading",
}
STRICT_INSTRUCTION = (
    "For each multiple-choice question, return only the single uppercase option "
    "letter A, B, C, or D. Do not explain the answer."
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())


def load_profile(scripts_dir: Path, profiles_path: Path, model: str) -> dict[str, Any]:
    sys.path.insert(0, str(scripts_dir / "scripts" / "active"))
    from model_profiles import load_resolved_profile

    resolved = load_resolved_profile(profiles_path, model)
    if resolved is None:
        raise SystemExit(f"no unique model profile for {model}")
    profile = resolved[1]
    if not str(profile.get("system_prompt", "")).strip():
        raise SystemExit(f"resolved model profile for {model} has no system_prompt")
    return profile


def chat(base_url: str, model: str, system_prompt: str, prompt: str, timeout: int) -> str:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0,
        "max_tokens": 24,
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


def answer_letter(text: str) -> str:
    visible = re.sub(r"<think>.*?</think>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    stripped = visible.strip().upper()
    if stripped in {"A", "B", "C", "D"}:
        return stripped
    match = re.search(r"(?:^|[^A-Z])([A-D])(?:[^A-Z]|$)", stripped)
    return match.group(1) if match else ""


def format_question(case: dict[str, Any]) -> str:
    options = "\n".join(
        f"{letter}. {value}" for letter, value in zip("ABCD", case["choices"])
    )
    return f"{case['question']}\n\n{options}"


def record(
    args: argparse.Namespace,
    task: str,
    score: float | None,
    sample_count: int,
    format_failures: int,
    elapsed: float,
    error: Exception | None = None,
) -> None:
    recorder = Path(args.scripts_dir) / "scripts" / "active" / "record_benchmark_result.py"
    command = [
        sys.executable, str(recorder), "--model", args.model,
        "--test-id", f"knowledge_{task}_probe_v1", "--run-class", args.run_class,
        "--harness", "bench-knowledge", "--suite", args.run_name,
        "--methodology-id", METHODOLOGY[0], "--methodology-version", METHODOLOGY[1],
        "--comparison-group", METHODOLOGY[2], "--config-id", "knowledge-cases-v1",
        "--config-json", json.dumps({"task": task, "scoring": "single-letter-generation"}, sort_keys=True),
        "--run-at", now_iso(), "--records", args.records,
        "--reference-output", args.reference_output,
        "--scoreboard-output", args.scoreboard_output,
    ]
    if error is None:
        command.extend([
            "--score", str(score), "--raw-harness-score", str(score),
            "--normalized-answer-score", str(score), "--metric", "exact_match",
            "--sample-count", str(sample_count), "--wall-time-seconds", str(elapsed),
            "--format-compatibility", "degraded" if format_failures else "compatible",
            "--extractor-failure-count", str(format_failures),
        ])
    else:
        command.extend([
            "--status", "failure", "--failure-kind", "harness_error",
            "--failure-message", f"{type(error).__name__}: {error}",
            "--failed-request-count", "1",
        ])
    if subprocess.run(command, check=False).returncode != 0:
        raise RuntimeError("benchmark result recorder failed")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    parser.add_argument("--runtime-base", required=True)
    parser.add_argument("--tasks", default="academic,science,commonsense,truthfulness,reading")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--run-name", required=True)
    parser.add_argument("--run-class", choices=("smoke", "provisional", "validated", "full"), default="provisional")
    parser.add_argument("--results-dir", default="/results")
    parser.add_argument("--scripts-dir", default="/benchmark-scripts")
    parser.add_argument("--tuning-profiles", default="/benchmark-scripts/model_tuning_profiles.json")
    parser.add_argument("--cases-file", default="/opt/bench/knowledge_cases.json")
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--records", default="/mnt/shared/plans/shoulders/benchmarking/results/model_benchmark_records.jsonl")
    parser.add_argument("--reference-output", default="/mnt/shared/plans/shoulders/benchmarking/results/MODEL_BENCHMARK_REFERENCE.md")
    parser.add_argument("--scoreboard-output", default="/mnt/shared/plans/shoulders/benchmarking/results/model_library_scoreboard.json")
    parser.add_argument("--no-record", action="store_true")
    args = parser.parse_args()

    if args.limit is not None and args.limit <= 0:
        parser.error("--limit must be positive")
    scripts_dir = Path(args.scripts_dir).resolve()
    profile = load_profile(scripts_dir, Path(args.tuning_profiles), args.model)
    system_prompt = f"{profile['system_prompt'].strip()}\n\n{STRICT_INSTRUCTION}"

    payload = json.loads(Path(args.cases_file).read_text(encoding="utf-8"))
    cases = payload.get("cases", [])
    available = {str(case.get("task")) for case in cases if isinstance(case, dict)}
    requested_raw = [value.strip() for value in args.tasks.split(",") if value.strip()]
    requested = [TASK_ALIASES.get(value, value) for value in requested_raw]
    unknown = sorted(set(requested) - available)
    if unknown:
        raise SystemExit(f"unknown knowledge tasks: {', '.join(unknown)}")

    run_dir = Path(args.results_dir).resolve() / f"bench-knowledge_{safe_name(args.model)}_{args.run_name}"
    run_dir.mkdir(parents=True, exist_ok=True)
    status_path = run_dir / "status.json"
    status: dict[str, Any] = {
        "run_start": now_iso(), "model": args.model, "runtime": args.runtime_base,
        "tasks_requested": requested, "limit": args.limit, "tasks": {}, "updated_at": now_iso(),
    }
    if status_path.is_file():
        previous = json.loads(status_path.read_text(encoding="utf-8"))
        if isinstance(previous.get("tasks"), dict):
            status["tasks"] = previous["tasks"]

    failures = 0
    for task in requested:
        if status["tasks"].get(task, {}).get("state") == "completed":
            continue
        selected = [case for case in cases if case.get("task") == task]
        if args.limit is not None:
            selected = selected[: args.limit]
        status["tasks"][task] = {"state": "running", "started_at": now_iso()}
        status["updated_at"] = now_iso()
        status_path.write_text(json.dumps(status, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        started = time.monotonic()
        rows: list[dict[str, Any]] = []
        try:
            for case in selected:
                response = chat(args.runtime_base, args.model, system_prompt, format_question(case), args.timeout)
                parsed = answer_letter(response)
                rows.append({
                    "id": case["id"], "expected": case["answer"], "parsed": parsed,
                    "correct": parsed == case["answer"], "format_valid": bool(parsed),
                    "response": response,
                })
            elapsed = time.monotonic() - started
            score = sum(row["correct"] for row in rows) / len(rows)
            format_failures = sum(not row["format_valid"] for row in rows)
            task_path = run_dir / f"{task}.json"
            task_path.write_text(json.dumps({"task": task, "rows": rows}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            if not args.no_record:
                record(args, task, score, len(rows), format_failures, elapsed)
            status["tasks"][task] = {
                "state": "completed", "sample_count": len(rows), "score": score,
                "format_failure_count": format_failures, "output": str(task_path), "ended_at": now_iso(),
            }
        except Exception as exc:
            failures += 1
            if not args.no_record:
                record(args, task, None, 0, 0, time.monotonic() - started, exc)
            status["tasks"][task] = {"state": "failed", "error": f"{type(exc).__name__}: {exc}", "ended_at": now_iso()}
        status["updated_at"] = now_iso()
        status_path.write_text(json.dumps(status, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(json.dumps({"status": str(status_path), "failed_tasks": failures}, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
