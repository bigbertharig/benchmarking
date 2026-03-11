#!/usr/bin/env python3
"""Build latest-only machine-readable scoreboard for MODEL_LIBRARY.md."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text:
            continue
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            rows.append(data)
    return rows


def parse_score(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def latest_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    latest: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in sorted(rows, key=lambda r: str(r.get("run_at", ""))):
        model = str(row.get("model", "")).strip()
        test_id = str(row.get("test_id", "")).strip()
        suite = str(row.get("suite", "")).strip()
        if not model or not test_id:
            continue
        latest[(model, test_id, suite)] = row
    return sorted(
        latest.values(),
        key=lambda r: (
            str(r.get("model", "")),
            str(r.get("suite", "")),
            str(r.get("test_id", "")),
        ),
    )


def build_model_rollup(latest: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for row in latest:
        model = str(row.get("model", "")).strip()
        if not model:
            continue
        score = parse_score(row.get("score"))
        group = grouped.setdefault(
            model,
            {
                "model": model,
                "tests": 0,
                "score_sum": 0.0,
                "score_count": 0,
                "last_tested": "",
                "suites": set(),
            },
        )
        group["tests"] += 1
        if score is not None:
            group["score_sum"] += score
            group["score_count"] += 1
        run_at = str(row.get("run_at", ""))
        if run_at > str(group["last_tested"]):
            group["last_tested"] = run_at
        suite = str(row.get("suite", "")).strip()
        if suite:
            group["suites"].add(suite)

    output: list[dict[str, Any]] = []
    for model in sorted(grouped):
        item = grouped[model]
        avg_score = (item["score_sum"] / item["score_count"]) if item["score_count"] else None
        output.append(
            {
                "model": model,
                "tests": int(item["tests"]),
                "avg_score": avg_score,
                "avg_score_pct": (avg_score * 100.0) if avg_score is not None else None,
                "last_tested": str(item["last_tested"]),
                "suites": sorted(item["suites"]),
            }
        )
    return output


def build_suite_rollup(latest: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for row in latest:
        model = str(row.get("model", "")).strip()
        suite = str(row.get("suite", "")).strip()
        if not model:
            continue
        key = (model, suite)
        score = parse_score(row.get("score"))
        group = grouped.setdefault(
            key,
            {"model": model, "suite": suite, "tests": 0, "score_sum": 0.0, "score_count": 0, "last_tested": ""},
        )
        group["tests"] += 1
        if score is not None:
            group["score_sum"] += score
            group["score_count"] += 1
        run_at = str(row.get("run_at", ""))
        if run_at > str(group["last_tested"]):
            group["last_tested"] = run_at

    output: list[dict[str, Any]] = []
    for key in sorted(grouped):
        item = grouped[key]
        avg_score = (item["score_sum"] / item["score_count"]) if item["score_count"] else None
        output.append(
            {
                "model": item["model"],
                "suite": item["suite"],
                "tests": int(item["tests"]),
                "avg_score": avg_score,
                "avg_score_pct": (avg_score * 100.0) if avg_score is not None else None,
                "last_tested": str(item["last_tested"]),
            }
        )
    return output


def main() -> int:
    ap = argparse.ArgumentParser(description="Build model library latest scoreboard JSON.")
    ap.add_argument(
        "--records",
        default="/mnt/shared/plans/shoulders/benchmarking/results/model_benchmark_records.jsonl",
    )
    ap.add_argument(
        "--output",
        default="/mnt/shared/plans/shoulders/benchmarking/results/model_library_scoreboard.json",
    )
    args = ap.parse_args()

    records_path = Path(args.records).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    rows = load_jsonl(records_path)
    latest = latest_rows(rows)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "records_path": str(records_path),
        "notes": "Latest-only scoreboard. Historical results remain in model_benchmark_records.jsonl.",
        "latest_per_model_test": latest,
        "model_rollup": build_model_rollup(latest),
        "suite_rollup": build_suite_rollup(latest),
    }
    output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote model library scoreboard JSON: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
