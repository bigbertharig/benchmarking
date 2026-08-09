#!/usr/bin/env python3
"""Build measured quality/reliability/cost Pareto frontiers from schema-v2 records."""

from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path
from typing import Any

from benchmark_records import load_records, now_iso, write_json_atomic


ROOT = Path(__file__).resolve().parents[2]
COST_FIELDS = (
    "wall_time_seconds",
    "ttft_seconds",
    "peak_vram_mb",
    "gpu_seconds",
    "energy_wh",
)


def _numeric(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def build_points(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    attempts: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        attempts[(str(row.get("model", "")), str(row.get("test_id", "")))].append(row)

    points: list[dict[str, Any]] = []
    diagnostics = {
        "successful_records": 0,
        "legacy_records": 0,
        "missing_cost_records": 0,
        "missing_hardware_records": 0,
    }
    for row in rows:
        if row.get("status") != "success":
            continue
        diagnostics["successful_records"] += 1
        if row.get("run_class") == "legacy":
            diagnostics["legacy_records"] += 1
            continue
        efficiency = row.get("efficiency", {})
        costs = {
            field: value
            for field in COST_FIELDS
            if (value := _numeric(efficiency.get(field))) is not None
        }
        if not costs:
            diagnostics["missing_cost_records"] += 1
            continue
        model = str(row["model"])
        test_id = str(row["test_id"])
        cohort = attempts[(model, test_id)]
        reliability = sum(item.get("status") == "success" for item in cohort) / len(cohort)
        runtime = row.get("runtime", {})
        if not str(runtime.get("hardware_id", "")).strip():
            diagnostics["missing_hardware_records"] += 1
            continue
        points.append(
            {
                "run_id": row["run_id"],
                "run_at": row["run_at"],
                "model": model,
                "test_id": test_id,
                "run_class": row["run_class"],
                "sample_count": row.get("sample_count"),
                "quality": float(row["score"]),
                "reliability": reliability,
                "cost_dimensions": sorted(costs),
                "costs": costs,
                "runtime_id": runtime.get("runtime_id", ""),
                "runtime_image": runtime.get("image", ""),
                "config_id": runtime.get("config_id", ""),
                "config_hash": runtime.get("config_hash", ""),
                "hardware_id": runtime.get("hardware_id", ""),
            }
        )
    return points, diagnostics


def dominates(left: dict[str, Any], right: dict[str, Any]) -> bool:
    if left["cost_dimensions"] != right["cost_dimensions"]:
        return False
    no_worse = left["quality"] >= right["quality"] and left["reliability"] >= right["reliability"]
    strictly_better = left["quality"] > right["quality"] or left["reliability"] > right["reliability"]
    for field in left["cost_dimensions"]:
        no_worse = no_worse and left["costs"][field] <= right["costs"][field]
        strictly_better = strictly_better or left["costs"][field] < right["costs"][field]
    return no_worse and strictly_better


def build_frontiers(points: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, tuple[str, ...]], list[dict[str, Any]]] = defaultdict(list)
    for point in points:
        key = (point["test_id"], tuple(point["cost_dimensions"]))
        groups[key].append(point)
    frontiers: list[dict[str, Any]] = []
    for (test_id, dimensions), candidates in sorted(groups.items()):
        frontier = [
            candidate
            for candidate in candidates
            if not any(other is not candidate and dominates(other, candidate) for other in candidates)
        ]
        frontiers.append(
            {
                "test_id": test_id,
                "cost_dimensions": list(dimensions),
                "candidate_count": len(candidates),
                "frontier_count": len(frontier),
                "frontier": sorted(
                    frontier,
                    key=lambda item: (-item["quality"], -item["reliability"], item["model"], item["run_id"]),
                ),
            }
        )
    return frontiers


def main() -> int:
    parser = argparse.ArgumentParser(description="Build measured Pareto frontiers from benchmark JSONL.")
    parser.add_argument("--records", default=str(ROOT / "results/model_benchmark_records.jsonl"))
    parser.add_argument("--output", default=str(ROOT / "results/model_pareto_frontier.json"))
    args = parser.parse_args()

    records_path = Path(args.records).expanduser().resolve()
    rows = load_records(records_path)
    points, diagnostics = build_points(rows)
    frontiers = build_frontiers(points)
    payload = {
        "schema_version": 1,
        "generated_at": now_iso(),
        "source_records_path": str(records_path),
        "policy": {
            "maximize": ["quality", "reliability"],
            "minimize": list(COST_FIELDS),
            "comparison_rule": "Points compete only when they have the same measured cost dimensions.",
            "missing_data_rule": "Missing cost dimensions are never guessed or treated as zero.",
            "hardware_rule": "Cost points require an explicit hardware_id.",
        },
        "diagnostics": {**diagnostics, "eligible_points": len(points), "frontier_groups": len(frontiers)},
        "frontiers": frontiers,
    }
    write_json_atomic(Path(args.output).expanduser().resolve(), payload)
    print(f"Wrote model Pareto frontier JSON: {Path(args.output).expanduser().resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
