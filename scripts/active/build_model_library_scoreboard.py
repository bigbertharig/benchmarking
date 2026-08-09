#!/usr/bin/env python3
"""Build the machine-readable scoreboard from the canonical JSONL ledger."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from benchmark_records import SCHEMA_VERSION, best_by_model_test, load_records, now_iso, write_json_atomic


ROOT = Path(__file__).resolve().parents[2]


def load_model_catalog(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    models = data.get("models")
    if not isinstance(models, list):
        raise ValueError(f"models catalog must contain a models array: {path}")
    return [row for row in models if isinstance(row, dict)]


def build_model_rollup(rows: list[dict[str, Any]], selected: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_model: dict[str, dict[str, Any]] = defaultdict(lambda: {"records": 0, "successes": 0, "failures": 0, "selected_tests": 0, "suites": set(), "last_run_at": ""})
    for row in rows:
        model = str(row.get("model", ""))
        if not model:
            continue
        item = by_model[model]
        item["records"] += 1
        item["successes" if row.get("status") == "success" else "failures"] += 1
        if row.get("suite"):
            item["suites"].add(str(row["suite"]))
        item["last_run_at"] = max(item["last_run_at"], str(row.get("run_at", "")))
    for row in selected:
        by_model[str(row["model"])]["selected_tests"] += 1
    return [
        {
            "model": model,
            "records": item["records"],
            "successes": item["successes"],
            "failures": item["failures"],
            "selected_tests": item["selected_tests"],
            "suites": sorted(item["suites"]),
            "last_run_at": item["last_run_at"] or None,
        }
        for model, item in sorted(by_model.items())
    ]


def build_suite_rollup(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], dict[str, Any]] = defaultdict(
        lambda: {
            "records": 0,
            "successes": 0,
            "failures": 0,
            "harnesses": set(),
            "last_run_at": "",
        }
    )
    for row in rows:
        key = (str(row.get("model", "")), str(row.get("suite", "")))
        if not all(key):
            continue
        item = grouped[key]
        item["records"] += 1
        item["successes" if row.get("status") == "success" else "failures"] += 1
        if row.get("harness"):
            item["harnesses"].add(str(row["harness"]))
        item["last_run_at"] = max(item["last_run_at"], str(row.get("run_at", "")))
    return [
        {
            "model": key[0],
            "suite": key[1],
            "records": value["records"],
            "successes": value["successes"],
            "failures": value["failures"],
            "harnesses": sorted(value["harnesses"]),
            "last_run_at": value["last_run_at"],
        }
        for key, value in sorted(grouped.items())
    ]


def main() -> int:
    ap = argparse.ArgumentParser(description="Build scoreboard JSON from canonical benchmark records.")
    ap.add_argument("--records", default=str(ROOT / "results/model_benchmark_records.jsonl"))
    ap.add_argument("--models-catalog", default=str(ROOT / "models.catalog.json"))
    ap.add_argument("--output", default=str(ROOT / "results/model_library_scoreboard.json"))
    ap.add_argument("--allow-empty", action="store_true")
    args = ap.parse_args()

    records_path = Path(args.records).expanduser().resolve()
    catalog_path = Path(args.models_catalog).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()
    rows = load_records(records_path)
    selected = best_by_model_test(rows)
    if not selected and not args.allow_empty:
        raise SystemExit(f"refusing to write empty scoreboard from {records_path}")

    failures = sorted(
        (row for row in rows if row.get("status") == "failure"),
        key=lambda row: (str(row.get("run_at", "")), str(row.get("run_id", ""))),
        reverse=True,
    )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now_iso(),
        "source_records_path": str(records_path),
        "source_models_catalog_path": str(catalog_path),
        "notes": "Derived exclusively from the canonical JSONL ledger and model catalog.",
        "record_count": len(rows),
        "selected_count": len(selected),
        "models": load_model_catalog(catalog_path),
        "selected_per_model_test": selected,
        "model_rollup": build_model_rollup(rows, selected),
        "suite_rollup": build_suite_rollup(rows),
        "recent_failures": failures[:100],
    }
    write_json_atomic(output_path, payload)
    print(f"Wrote model library scoreboard JSON: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
