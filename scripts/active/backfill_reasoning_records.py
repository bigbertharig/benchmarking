#!/usr/bin/env python3
"""Backfill bench-reasoning results into model_benchmark_records.jsonl.

This is for historical runs that completed before automatic JSONL recording was
wired into the suite runner.
"""

from __future__ import annotations

import argparse
import json
import uuid
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_existing_keys(path: Path) -> set[tuple[str, str, str, str]]:
    keys: set[tuple[str, str, str, str]] = set()
    if not path.exists():
        return keys
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text:
            continue
        try:
            row = json.loads(text)
        except json.JSONDecodeError:
            continue
        keys.add(
            (
                str(row.get("model", "")),
                str(row.get("test_id", "")),
                str(row.get("metric", "")),
                str(row.get("suite", "")),
            )
        )
    return keys


def append_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")


def build_row(model: str, run_at: str, suite: str, test_id: str, score: float, metric: str, notes: str = "") -> dict[str, Any]:
    score_pct = score * 100.0 if score <= 1.0 else score
    return {
        "run_id": str(uuid.uuid4()),
        "run_at": run_at,
        "model": model,
        "test_id": test_id,
        "score": score,
        "score_pct": score_pct,
        "metric": metric,
        "harness": "bench-reasoning",
        "suite": suite,
        "notes": notes,
    }


def extract_reasoning_rows(run_dir: Path) -> list[dict[str, Any]]:
    status_path = run_dir / "status.json"
    if not status_path.exists():
        return []
    status = load_json(status_path)
    model = str(status.get("model", "")).strip()
    suite = run_dir.name
    tasks = status.get("tasks", {}) or {}
    rows: list[dict[str, Any]] = []

    for task_name, task_info in tasks.items():
        if str(task_info.get("state", "")).strip() != "completed":
            continue
        ended_at = str(task_info.get("ended_at", "")).strip() or str(status.get("updated_at", "")).strip()
        output_dir = str(task_info.get("output_dir", "")).strip()
        if not output_dir:
            continue
        task_dir = run_dir / Path(output_dir).name
        result_files = sorted(task_dir.glob("**/results_*.json"))
        if not result_files:
            continue
        data = load_json(result_files[-1])
        results = data.get("results", {}) or {}
        groups = data.get("groups", {}) or {}

        if task_name == "gsm8k":
            block = results.get("gsm8k", {}) or {}
            strict = block.get("exact_match,strict-match")
            flex = block.get("exact_match,flexible-extract")
            if isinstance(strict, (int, float)):
                rows.append(build_row(model, ended_at, suite, "gsm8k_strict", float(strict), "exact_match,strict-match"))
            if isinstance(flex, (int, float)):
                rows.append(build_row(model, ended_at, suite, "gsm8k_flexible", float(flex), "exact_match,flexible-extract"))
        elif task_name == "bbh":
            block = groups.get("bbh") or results.get("bbh", {}) or {}
            score = block.get("exact_match,get-answer")
            if isinstance(score, (int, float)):
                rows.append(build_row(model, ended_at, suite, "bbh", float(score), "exact_match,get-answer"))
        elif task_name == "drop":
            block = results.get("drop", {}) or {}
            em = block.get("em,none")
            f1 = block.get("f1,none")
            if isinstance(em, (int, float)):
                rows.append(build_row(model, ended_at, suite, "drop_em", float(em), "em,none"))
            if isinstance(f1, (int, float)):
                rows.append(build_row(model, ended_at, suite, "drop_f1", float(f1), "f1,none"))
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description="Backfill bench-reasoning JSONL records from completed run directories.")
    ap.add_argument(
        "--history-root",
        default="/mnt/shared/logs/benchmarks/bench-reasoning/history",
    )
    ap.add_argument(
        "--records",
        default="/mnt/shared/plans/shoulders/benchmarking/results/model_benchmark_records.jsonl",
    )
    args = ap.parse_args()

    history_root = Path(args.history_root).expanduser().resolve()
    records_path = Path(args.records).expanduser().resolve()

    existing = load_existing_keys(records_path)
    pending: list[dict[str, Any]] = []
    added = 0
    skipped = 0

    for run_dir in sorted(history_root.glob("bench-reasoning_*")):
        if not run_dir.is_dir():
            continue
        for row in extract_reasoning_rows(run_dir):
            key = (
                str(row["model"]),
                str(row["test_id"]),
                str(row["metric"]),
                str(row["suite"]),
            )
            if key in existing:
                skipped += 1
                continue
            existing.add(key)
            pending.append(row)
            added += 1

    append_rows(records_path, pending)
    print(json.dumps({"added": added, "skipped": skipped, "records": str(records_path)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
