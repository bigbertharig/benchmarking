#!/usr/bin/env python3
"""Extract canonical result rows from one lm-eval reasoning task output."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _count(block: Any) -> int | None:
    if isinstance(block, dict):
        value = block.get("effective") or block.get("original")
    elif isinstance(block, (int, float)):
        value = block
    else:
        return None
    if value is None or int(value) <= 0:
        return None
    return int(value)


def sample_count_for(task: str, data: dict[str, Any]) -> int:
    samples = data.get("n-samples") or {}
    direct = _count(samples.get(task))
    if direct is not None:
        return direct

    child_counts = [
        count
        for name, block in samples.items()
        if str(name).startswith(f"{task}_")
        if (count := _count(block)) is not None
    ]
    if child_counts:
        return sum(child_counts)
    raise ValueError(f"missing sample count for {task}")


def extract_rows(task: str, data: dict[str, Any]) -> list[tuple[Any, ...]]:
    results = data.get("results", {})
    groups = data.get("groups", {})
    sample_count = sample_count_for(task, data)
    rows: list[tuple[Any, ...]] = []

    def emit(
        test_id: str,
        score: Any,
        metric: str,
        raw: Any = None,
        normalized: Any = None,
        compatibility: str = "unknown",
        extractor_failures: int = 0,
        notes: str = "",
    ) -> None:
        if score is None:
            return
        raw = score if raw is None else raw
        normalized = score if normalized is None else normalized
        rows.append(
            (
                test_id,
                score,
                metric,
                raw,
                normalized,
                compatibility,
                extractor_failures,
                sample_count,
                notes,
            )
        )

    if task == "gsm8k":
        block = results.get("gsm8k", {})
        strict = block.get("exact_match,strict-match")
        flexible = block.get("exact_match,flexible-extract")
        failures = round(max(0.0, float(flexible or 0) - float(strict or 0)) * sample_count)
        compatibility = "degraded" if failures else "compatible"
        emit("gsm8k_strict", strict, "exact_match,strict-match", strict, flexible, compatibility, failures)
        emit("gsm8k_flexible", flexible, "exact_match,flexible-extract", strict, flexible, compatibility, failures)
    elif task == "bbh":
        block = groups.get("bbh") or results.get("bbh", {})
        emit("bbh", block.get("exact_match,get-answer"), "exact_match,get-answer")
    elif task == "drop":
        block = results.get("drop", {})
        emit("drop_em", block.get("em,none"), "em,none")
        emit("drop_f1", block.get("f1,none"), "f1,none")
    else:
        block = groups.get(task) or results.get(task, {})
        for key, value in block.items():
            metric_name = key.split(",", 1)[0]
            if key == "alias" or metric_name.endswith("_stderr"):
                continue
            if isinstance(value, (int, float)):
                emit(f"{task}_{key.replace(',', '_')}", value, key)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("task")
    parser.add_argument("task_output_dir")
    args = parser.parse_args()

    files = sorted(Path(args.task_output_dir).glob("**/results_*.json"))
    if not files:
        return 0
    data = json.loads(files[-1].read_text(encoding="utf-8"))
    try:
        rows = extract_rows(args.task, data)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    for row in rows:
        print("\t".join(str(value) for value in row))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
