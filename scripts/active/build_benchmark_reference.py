#!/usr/bin/env python3
"""Build the human-readable reference from the canonical JSONL ledger."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from benchmark_records import best_by_model_test, load_records, now_iso, write_text_atomic
from compatibility import load_status


ROOT = Path(__file__).resolve().parents[2]


def cell(value: Any) -> str:
    if value is None:
        return ""
    return str(value).replace("|", "\\|").replace("\n", " ")


def md_table(headers: list[str], rows: list[list[Any]]) -> str:
    rendered = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    rendered.extend("| " + " | ".join(cell(value) for value in row) + " |" for row in rows)
    return "\n".join(rendered)


def status_sort_key(entry: dict[str, Any], primary: str) -> tuple[str, str]:
    return (str(entry.get(primary, "")), str(entry.get("observed_at", "")))


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate benchmark reference markdown from JSONL records.")
    ap.add_argument("--records", default=str(ROOT / "results/model_benchmark_records.jsonl"))
    ap.add_argument("--output", default=str(ROOT / "results/MODEL_BENCHMARK_REFERENCE.md"))
    ap.add_argument("--recent-limit", type=int, default=40)
    ap.add_argument("--failure-limit", type=int, default=40)
    ap.add_argument("--status-path", default=str(ROOT / "benchmark_status.json"))
    ap.add_argument("--allow-empty", action="store_true")
    args = ap.parse_args()

    records_path = Path(args.records).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()
    status_path = Path(args.status_path).expanduser().resolve()
    rows = load_records(records_path)
    selected = best_by_model_test(rows)
    if not selected and not args.allow_empty:
        raise SystemExit(f"refusing to write empty benchmark reference from {records_path}")

    status = load_status(status_path)
    recent = sorted(rows, key=lambda row: (str(row.get("run_at", "")), str(row.get("run_id", ""))), reverse=True)
    failures = [row for row in recent if row.get("status") == "failure"]

    runtime_issue_rows = [
        [row.get("subject"), row.get("state"), row.get("observed_at"), row.get("note")]
        for row in sorted(status.get("runtime_issues", []), key=lambda item: status_sort_key(item, "subject"))
    ]
    certified_test_rows = [
        [row.get("backend_id"), row.get("test_id"), row.get("state"), row.get("model_id"), row.get("observed_at"), row.get("note")]
        for row in sorted(status.get("certified_tests", []), key=lambda item: status_sort_key(item, "backend_id"))
    ]
    runtime_note_rows = [
        [row.get("test_id"), row.get("runtime_class"), row.get("observed_at"), row.get("note")]
        for row in sorted(status.get("task_runtime_notes", []), key=lambda item: status_sort_key(item, "test_id"))
    ]
    selected_rows = [
        [
            row.get("model"), row.get("test_id"), row.get("score"), row.get("score_pct"),
            row.get("metric"), row.get("run_class"), row.get("sample_count"),
            row.get("format_compatibility"), row.get("run_at"), row.get("harness"), row.get("suite"),
        ]
        for row in selected
    ]
    recent_rows = [
        [
            row.get("run_at"), row.get("model"), row.get("test_id"), row.get("status"),
            row.get("run_class"), row.get("sample_count"), row.get("score"), row.get("metric"),
            row.get("harness"), row.get("suite"), row.get("run_id"),
        ]
        for row in recent[: max(1, args.recent_limit)]
    ]
    failure_rows = [
        [
            row.get("run_at"), row.get("model"), row.get("test_id"), row.get("run_class"),
            (row.get("failure") or {}).get("kind"), (row.get("failure") or {}).get("message"),
            row.get("harness"), row.get("suite"), row.get("run_id"),
        ]
        for row in failures[: max(1, args.failure_limit)]
    ]

    content = [
        "# Model Benchmark Reference", "",
        f"- Generated at: `{now_iso()}`",
        f"- Canonical records: `{records_path}`",
        f"- Status file: `{status_path}`",
        f"- Total records: `{len(rows)}`",
        f"- Selected model/test results: `{len(selected)}`", "",
        "Selection prefers run class, then sample count, format compatibility, and recency. A smoke run cannot replace validated or full evidence.", "",
        "## Operational Status", "", "### Runtime Issues", "",
        md_table(["Subject", "State", "Last Observed", "Notes"], runtime_issue_rows or [["-", "-", "-", "-"]]), "",
        "### Backend/Test Certification", "",
        md_table(["Backend", "Test ID", "State", "Probe Model", "Last Observed", "Notes"], certified_test_rows or [["-", "-", "-", "-", "-", "-"]]), "",
        "### Task Runtime Notes", "",
        md_table(["Test ID", "Runtime Class", "Last Observed", "Notes"], runtime_note_rows or [["-", "-", "-", "-"]]), "",
        "## Selected Score Per Model/Test", "",
        md_table(["Model", "Test ID", "Score", "Score %", "Metric", "Class", "N", "Format", "Run At", "Harness", "Suite"], selected_rows or [["-"] * 11]), "",
        "## Recorded Failures", "",
        md_table(["Run At", "Model", "Test ID", "Class", "Failure", "Message", "Harness", "Suite", "Run ID"], failure_rows or [["-"] * 9]), "",
        "## Recent Records", "",
        md_table(["Run At", "Model", "Test ID", "Status", "Class", "N", "Score", "Metric", "Harness", "Suite", "Run ID"], recent_rows or [["-"] * 11]), "",
    ]
    write_text_atomic(output_path, "\n".join(content))
    print(f"Wrote reference markdown: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
