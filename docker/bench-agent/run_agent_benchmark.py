#!/usr/bin/env python3
"""Run bench-agent cases against an OpenAI-compatible chat endpoint."""

from __future__ import annotations

import argparse
import copy
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agent_harness import run_case


METHODOLOGY = ("bench-agent/executable-tools", "1.0.0", "agent-execution-v1")


def safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())


def load_cases(path: Path, requested: list[str], limit: int | None) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    cases = data.get("cases")
    if not isinstance(cases, list):
        raise SystemExit(f"cases file must contain a cases array: {path}")
    by_id = {str(case.get("id", "")): case for case in cases if isinstance(case, dict)}
    missing = [case_id for case_id in requested if case_id not in by_id]
    if missing:
        raise SystemExit(f"unknown case ids: {', '.join(missing)}")
    selected = [by_id[case_id] for case_id in requested] if requested else cases
    toolsets = data.get("toolsets", {})
    expanded: list[dict[str, Any]] = []
    for original in selected:
        case = copy.deepcopy(original)
        toolset_name = case.pop("toolset", "")
        if toolset_name:
            tools = toolsets.get(toolset_name)
            if not isinstance(tools, list):
                raise SystemExit(f"case {case.get('id')} references unknown toolset: {toolset_name}")
            case["tools"] = copy.deepcopy(tools)
        expanded.append(case)
    selected = expanded
    return selected[:limit] if limit is not None else selected


def record_result(args: argparse.Namespace, case: dict[str, Any], trace: dict[str, Any], elapsed: float) -> None:
    if args.no_record:
        return
    recorder = Path(args.scripts_dir).resolve() / "scripts" / "active" / "record_benchmark_result.py"
    config = {
        "case_category": case.get("category"),
        "case_mode": case.get("mode", "execute"),
        "mutation": case.get("mutation", "none"),
        "max_steps": args.max_steps,
    }
    command = [
        sys.executable,
        str(recorder),
        "--model",
        args.model,
        "--test-id",
        case["id"],
        "--score",
        str(trace["score"]),
        "--raw-harness-score",
        str(trace["score"]),
        "--normalized-answer-score",
        str(trace["scores"].get("final_task_success", 0.0)),
        "--metric",
        "agent_component_mean",
        "--run-class",
        args.run_class,
        "--sample-count",
        "1",
        "--format-compatibility",
        "degraded" if any(not call["schema_valid"] for call in trace["calls"]) else "compatible",
        "--extractor-failure-count",
        str(sum(not call["schema_valid"] for call in trace["calls"])),
        "--harness",
        "bench-agent",
        "--suite",
        args.run_name,
        "--methodology-id",
        METHODOLOGY[0],
        "--methodology-version",
        METHODOLOGY[1],
        "--comparison-group",
        METHODOLOGY[2],
        "--config-id",
        case["id"],
        "--config-json",
        json.dumps(config, sort_keys=True),
        "--wall-time-seconds",
        str(elapsed),
        "--hardware-id",
        args.hardware_id,
        "--records",
        args.records,
        "--reference-output",
        args.reference_output,
        "--scoreboard-output",
        args.scoreboard_output,
        "--notes",
        json.dumps(trace["scores"], sort_keys=True),
    ]
    proc = subprocess.run(command, check=False)
    if proc.returncode != 0:
        raise SystemExit(proc.returncode)


def record_failure(args: argparse.Namespace, case: dict[str, Any], exc: Exception) -> None:
    if args.no_record:
        return
    recorder = Path(args.scripts_dir).resolve() / "scripts" / "active" / "record_benchmark_result.py"
    proc = subprocess.run(
        [
            sys.executable,
            str(recorder),
            "--model",
            args.model,
            "--test-id",
            case["id"],
            "--status",
            "failure",
            "--run-class",
            args.run_class,
            "--harness",
            "bench-agent",
            "--suite",
            args.run_name,
            "--failure-kind",
            "harness_error",
            "--failure-message",
            f"{type(exc).__name__}: {exc}",
            "--failed-request-count",
            "1",
            "--methodology-id",
            METHODOLOGY[0],
            "--methodology-version",
            METHODOLOGY[1],
            "--comparison-group",
            METHODOLOGY[2],
            "--hardware-id",
            args.hardware_id,
            "--records",
            args.records,
            "--reference-output",
            args.reference_output,
            "--scoreboard-output",
            args.scoreboard_output,
        ],
        check=False,
    )
    if proc.returncode != 0:
        raise SystemExit(proc.returncode)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run executable bench-agent cases.")
    parser.add_argument("--model", required=True)
    parser.add_argument("--runtime-base", required=True)
    parser.add_argument("--cases-file", default="/opt/bench/agent_cases.json")
    parser.add_argument("--cases", default="", help="Comma-separated case IDs; default is all")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--run-name", required=True)
    parser.add_argument("--hardware-id", required=True)
    parser.add_argument("--run-class", choices=("smoke", "provisional", "validated", "full"), default="provisional")
    parser.add_argument("--results-dir", default="/results")
    parser.add_argument("--scripts-dir", default="/benchmark-scripts")
    parser.add_argument("--records", default="/mnt/shared/plans/shoulders/benchmarking/results/model_benchmark_records.jsonl")
    parser.add_argument("--reference-output", default="/mnt/shared/plans/shoulders/benchmarking/results/MODEL_BENCHMARK_REFERENCE.md")
    parser.add_argument("--scoreboard-output", default="/mnt/shared/plans/shoulders/benchmarking/results/model_library_scoreboard.json")
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--max-steps", type=int, default=8)
    parser.add_argument("--no-record", action="store_true")
    args = parser.parse_args()

    if not re.fullmatch(r"[A-Za-z0-9_.-]+", args.run_name):
        parser.error("--run-name may contain only letters, digits, dot, underscore, and hyphen")
    if not re.fullmatch(r"[A-Za-z0-9_.:-]+", args.hardware_id):
        parser.error("--hardware-id may contain only letters, digits, dot, underscore, colon, and hyphen")
    if args.limit is not None and args.limit <= 0:
        parser.error("--limit must be positive")
    if args.max_steps <= 0:
        parser.error("--max-steps must be positive")

    requested = [value.strip() for value in args.cases.split(",") if value.strip()]
    cases = load_cases(Path(args.cases_file).resolve(), requested, args.limit)
    run_dir = Path(args.results_dir).resolve() / f"bench-agent_{safe_name(args.model)}_{args.run_name}"
    run_dir.mkdir(parents=True, exist_ok=True)
    sandbox_root = run_dir / "sandboxes"
    result_rows: list[dict[str, Any]] = []
    failures = 0

    for case in cases:
        case_id = str(case["id"])
        started = time.monotonic()
        try:
            trace = run_case(
                case=case,
                base_url=args.runtime_base,
                model=args.model,
                sandbox=sandbox_root / safe_name(case_id),
                timeout=args.timeout,
                max_steps=args.max_steps,
            )
            elapsed = time.monotonic() - started
            trace["elapsed_seconds"] = elapsed
            trace_path = run_dir / f"{safe_name(case_id)}.json"
            trace_path.write_text(json.dumps(trace, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            record_result(args, case, trace, elapsed)
            result_rows.append(
                {
                    "case_id": case_id,
                    "category": case.get("category"),
                    "mutation": case.get("mutation", "none"),
                    "score": trace["score"],
                    "scores": trace["scores"],
                    "trace": str(trace_path),
                }
            )
            print(f"{case_id}: {trace['score']:.4f}")
        except Exception as exc:
            failures += 1
            record_failure(args, case, exc)
            result_rows.append({"case_id": case_id, "error": f"{type(exc).__name__}: {exc}"})
            print(f"{case_id}: ERROR {type(exc).__name__}: {exc}", file=sys.stderr)

    successful_scores = [float(row["score"]) for row in result_rows if "score" in row]
    summary = {
        "suite": "bench-agent",
        "model": args.model,
        "run_name": args.run_name,
        "run_class": args.run_class,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "cases_requested": len(cases),
        "cases_completed": len(successful_scores),
        "harness_failures": failures,
        "mean_score": sum(successful_scores) / len(successful_scores) if successful_scores else 0.0,
        "results": result_rows,
    }
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({key: summary[key] for key in ("cases_completed", "harness_failures", "mean_score")}, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
