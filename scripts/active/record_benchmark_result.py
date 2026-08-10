#!/usr/bin/env python3
"""Append one schema-v2 benchmark result and refresh derived artifacts."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

from benchmark_file_lock import BenchmarkFileLock

from benchmark_records import (
    FORMAT_COMPATIBILITY,
    RUN_CLASSES,
    SCHEMA_VERSION,
    append_record,
    canonical_config_hash,
    normalize_score_pct,
    now_iso,
)


ROOT = Path(__file__).resolve().parents[2]


def optional_json(value: str, field: str) -> dict[str, Any]:
    if not value.strip():
        return {}
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{field} must be valid JSON: {exc}") from exc
    if not isinstance(decoded, dict):
        raise SystemExit(f"{field} must decode to a JSON object")
    return decoded


def add_optional_float(ap: argparse.ArgumentParser, name: str, help_text: str) -> None:
    ap.add_argument(name, type=float, default=None, help=help_text)


def validate_methodology(methodology_id: str, version: str, comparison_group: str) -> None:
    registry_path = ROOT / "benchmark_methodologies.json"
    try:
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"cannot load methodology registry {registry_path}: {exc}") from exc
    methods = registry.get("methodologies", []) if isinstance(registry, dict) else []
    for method in methods:
        if not isinstance(method, dict) or method.get("id") != methodology_id:
            continue
        expected = (str(method.get("version", "")), str(method.get("comparison_group", "")))
        supplied = (version, comparison_group)
        if supplied != expected:
            raise SystemExit(
                f"methodology {methodology_id} must use version={expected[0]} "
                f"comparison_group={expected[1]}"
            )
        return
    raise SystemExit(f"unregistered methodology id: {methodology_id}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Record one schema-v2 benchmark result row.")
    ap.add_argument("--model", required=True)
    ap.add_argument("--test-id", required=True)
    ap.add_argument("--status", choices=("success", "failure"), default="success")
    ap.add_argument("--run-class", choices=RUN_CLASSES[:-1], required=True)
    ap.add_argument("--sample-count", type=int, default=None)
    ap.add_argument("--score", type=float, default=None)
    ap.add_argument("--metric", default="")
    ap.add_argument("--raw-harness-score", type=float, default=None)
    ap.add_argument("--normalized-answer-score", type=float, default=None)
    ap.add_argument("--format-compatibility", choices=FORMAT_COMPATIBILITY, default="unknown")
    ap.add_argument("--extractor-failure-count", type=int, default=0)
    ap.add_argument("--harness", default="")
    ap.add_argument("--suite", default="")
    ap.add_argument("--run-at", default="")
    ap.add_argument("--notes", default="")
    ap.add_argument("--methodology-id", required=True)
    ap.add_argument("--methodology-version", required=True)
    ap.add_argument("--comparison-group", required=True)
    ap.add_argument("--runtime-id", default="")
    ap.add_argument("--runtime-image", default="")
    ap.add_argument("--config-id", default="")
    ap.add_argument("--config-json", default="{}")
    ap.add_argument("--hardware-id", default="")
    add_optional_float(ap, "--prompt-tps", "Prompt processing tokens/second")
    add_optional_float(ap, "--generation-tps", "Generation tokens/second")
    add_optional_float(ap, "--ttft-seconds", "Time to first token")
    add_optional_float(ap, "--wall-time-seconds", "Total wall-clock time")
    add_optional_float(ap, "--peak-vram-mb", "Peak VRAM use")
    add_optional_float(ap, "--kv-cache-mb", "KV-cache memory")
    add_optional_float(ap, "--gpu-seconds", "GPU-seconds consumed")
    add_optional_float(ap, "--energy-wh", "Energy consumed in Wh")
    ap.add_argument("--failure-kind", default="")
    ap.add_argument("--failure-message", default="")
    ap.add_argument("--timeout-count", type=int, default=0)
    ap.add_argument("--failed-request-count", type=int, default=0)
    ap.add_argument("--records", default=str(ROOT / "results/model_benchmark_records.jsonl"))
    ap.add_argument("--reference-output", default=str(ROOT / "results/MODEL_BENCHMARK_REFERENCE.md"))
    ap.add_argument("--scoreboard-output", default=str(ROOT / "results/model_library_scoreboard.json"))
    ap.add_argument("--no-refresh", action="store_true")
    args = ap.parse_args()
    validate_methodology(
        args.methodology_id.strip(),
        args.methodology_version.strip(),
        args.comparison_group.strip(),
    )

    if args.status == "success":
        if args.score is None or not args.metric.strip():
            ap.error("successful records require --score and --metric")
        if args.sample_count is None or args.sample_count <= 0:
            ap.error("successful records require --sample-count > 0")
    elif not args.failure_kind.strip():
        ap.error("failure records require --failure-kind")

    config = optional_json(args.config_json, "--config-json")
    score_pct = normalize_score_pct(args.score) if args.score is not None else None
    payload = {
        "schema_version": SCHEMA_VERSION,
        "run_id": str(uuid.uuid4()),
        "run_at": args.run_at.strip() or now_iso(),
        "model": args.model.strip(),
        "test_id": args.test_id.strip(),
        "status": args.status,
        "run_class": args.run_class,
        "sample_count": args.sample_count,
        "score": args.score,
        "score_pct": score_pct,
        "metric": args.metric.strip(),
        "raw_harness_score": args.raw_harness_score if args.raw_harness_score is not None else args.score,
        "normalized_answer_score": args.normalized_answer_score,
        "format_compatibility": args.format_compatibility,
        "extractor_failure_count": args.extractor_failure_count,
        "harness": args.harness.strip(),
        "suite": args.suite.strip(),
        "runtime": {
            "runtime_id": args.runtime_id.strip(),
            "image": args.runtime_image.strip(),
            "config_id": args.config_id.strip(),
            "config_hash": canonical_config_hash(config) if config else "",
            "config": config,
            "hardware_id": args.hardware_id.strip(),
        },
        "efficiency": {
            "prompt_tps": args.prompt_tps,
            "generation_tps": args.generation_tps,
            "ttft_seconds": args.ttft_seconds,
            "wall_time_seconds": args.wall_time_seconds,
            "peak_vram_mb": args.peak_vram_mb,
            "kv_cache_mb": args.kv_cache_mb,
            "gpu_seconds": args.gpu_seconds,
            "energy_wh": args.energy_wh,
            "timeout_count": args.timeout_count,
            "failed_request_count": args.failed_request_count,
        },
        "failure": {
            "kind": args.failure_kind.strip(),
            "message": args.failure_message.strip(),
        },
        "methodology": {
            "id": args.methodology_id.strip(),
            "version": args.methodology_version.strip(),
            "comparison_group": args.comparison_group.strip(),
        },
        "notes": args.notes.strip(),
    }

    records_path = Path(args.records).expanduser().resolve()
    pipeline_lock = BenchmarkFileLock(str(records_path) + ".pipeline.lock", timeout=30)
    with pipeline_lock:
        append_record(records_path, payload)
        print(f"Recorded result: {records_path}")

        if args.no_refresh:
            return 0
        commands = (
            [sys.executable, str(Path(__file__).parent / "build_benchmark_reference.py"), "--records", str(records_path), "--output", str(Path(args.reference_output).expanduser().resolve())],
            [sys.executable, str(Path(__file__).parent / "build_model_library_scoreboard.py"), "--records", str(records_path), "--output", str(Path(args.scoreboard_output).expanduser().resolve())],
            [sys.executable, str(Path(__file__).parent / "build_methodology_history.py"), "--records", str(records_path), "--output", str(Path(args.scoreboard_output).expanduser().resolve().parent / "model_methodology_history.json")],
        )
        for command in commands:
            proc = subprocess.run(command, check=False)
            if proc.returncode != 0:
                return int(proc.returncode)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
