#!/usr/bin/env python3
"""Build a methodology-aware history without changing the primary scoreboard."""

from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path
from typing import Any

from benchmark_records import load_records, now_iso, selection_key, write_json_atomic


ROOT = Path(__file__).resolve().parents[2]


def build_history(rows: list[dict[str, Any]]) -> dict[str, Any]:
    attempts: dict[tuple[str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        methodology = row.get("methodology", {})
        key = (
            str(row.get("model", "")),
            str(row.get("test_id", "")),
            str(methodology.get("id", "legacy-unversioned")),
            str(methodology.get("comparison_group", f"legacy:{row.get('test_id', '')}")),
        )
        attempts[key].append(row)

    entries: list[dict[str, Any]] = []
    for (model, test_id, methodology_id, comparison_group), cohort in sorted(attempts.items()):
        successes = [row for row in cohort if row.get("status") == "success"]
        selected = max(successes, key=selection_key) if successes else None
        versions = sorted(
            {
                str(row.get("methodology", {}).get("version", "unversioned"))
                for row in cohort
            }
        )
        entries.append(
            {
                "model": model,
                "test_id": test_id,
                "methodology_id": methodology_id,
                "methodology_versions": versions,
                "comparison_group": comparison_group,
                "attempt_count": len(cohort),
                "success_count": len(successes),
                "failure_count": len(cohort) - len(successes),
                "selected_run_id": selected.get("run_id") if selected else None,
                "selected_score": selected.get("score") if selected else None,
                "selected_run_class": selected.get("run_class") if selected else None,
                "selected_sample_count": selected.get("sample_count") if selected else None,
                "selected_run_at": selected.get("run_at") if selected else None,
            }
        )
    return {
        "schema_version": 1,
        "generated_at": now_iso(),
        "policy": {
            "primary_scoreboard_unchanged": True,
            "selection": "Best evidence is selected only within one model, test, methodology, and comparison group.",
            "legacy": "Records without explicit methodology metadata remain in legacy-unversioned groups.",
        },
        "record_count": len(rows),
        "group_count": len(entries),
        "entries": entries,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build methodology-aware benchmark history.")
    parser.add_argument("--records", default=str(ROOT / "results/model_benchmark_records.jsonl"))
    parser.add_argument("--output", default=str(ROOT / "results/model_methodology_history.json"))
    args = parser.parse_args()
    rows = load_records(Path(args.records).expanduser().resolve())
    if not rows:
        raise SystemExit("refusing to replace methodology history from an empty ledger")
    output = Path(args.output).expanduser().resolve()
    write_json_atomic(output, build_history(rows))
    print(f"Wrote methodology history: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
