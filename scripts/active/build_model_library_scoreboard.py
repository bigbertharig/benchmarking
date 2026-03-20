#!/usr/bin/env python3
"""Build machine-readable model library data from MODEL_LIBRARY.md.

Canonical source is the markdown doc. This script parses the markdown tables and
notes, then writes a JSON scoreboard for downstream consumers.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TABLE_SECTIONS = {
    "Model inventory and GGUF availability": "inventory",
    "bench-pipeline (worker reliability)": "bench_pipeline",
    "bench-code (EvalPlus generation)": "bench_code",
    "bench-reasoning (lm-eval generation)": "bench_reasoning",
    "bench-knowledge (lm-eval loglikelihood)": "bench_knowledge",
}

BENCHMARK_SECTION_KEYS = {
    "bench_pipeline",
    "bench_code",
    "bench_reasoning",
    "bench_knowledge",
}


def strip_md(text: str) -> str:
    value = text.strip()
    if value.startswith("`") and value.endswith("`"):
        value = value[1:-1]
    value = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", value)
    return value.strip()


def slugify(text: str) -> str:
    value = strip_md(text).lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    return value.strip("_")


def parse_numeric(value: str) -> float | None:
    text = strip_md(value)
    if not text or text in {"—", "-"}:
        return None
    if text.endswith("%"):
        try:
            return float(text[:-1]) / 100.0
        except ValueError:
            return None
    try:
        return float(text)
    except ValueError:
        return None


def parse_table(lines: list[str], start: int) -> tuple[list[dict[str, str]], int]:
    header = [strip_md(part) for part in lines[start].strip().strip("|").split("|")]
    rows: list[dict[str, str]] = []
    i = start + 2
    while i < len(lines):
        line = lines[i]
        if not line.strip().startswith("|"):
            break
        parts = [strip_md(part) for part in line.strip().strip("|").split("|")]
        if len(parts) != len(header):
            break
        rows.append(dict(zip(header, parts)))
        i += 1
    return rows, i


def build_latest_benchmark_rows(section_rows: dict[str, list[dict[str, str]]]) -> list[dict[str, Any]]:
    latest: dict[tuple[str, str, str], dict[str, Any]] = {}
    for section_key, rows in section_rows.items():
        if section_key not in BENCHMARK_SECTION_KEYS:
            continue
        for row in rows:
            model = row.get("Model", "").strip()
            test_name = row.get("Test", "").strip()
            if not model or not test_name:
                continue
            limit = row.get("Limit", "").strip()
            date_utc = row.get("Date (UTC)", "").strip()
            latest[(model, test_name, section_key)] = {
                "model": model,
                "test": test_name,
                "suite": section_key,
                "date_utc": date_utc,
                "limit": limit,
                "row": row,
            }
    return sorted(latest.values(), key=lambda item: (item["model"], item["suite"], item["test"]))


def build_model_rollup(latest: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for item in latest:
        model = item["model"]
        group = grouped.setdefault(
            model,
            {
                "model": model,
                "tests": 0,
                "suites": set(),
                "last_date_utc": "",
            },
        )
        group["tests"] += 1
        group["suites"].add(item["suite"])
        if item["date_utc"] > group["last_date_utc"]:
            group["last_date_utc"] = item["date_utc"]
    output: list[dict[str, Any]] = []
    for model in sorted(grouped):
        item = grouped[model]
        output.append(
            {
                "model": item["model"],
                "tests": item["tests"],
                "suites": sorted(item["suites"]),
                "last_date_utc": item["last_date_utc"] or None,
            }
        )
    return output


def build_suite_rollup(latest: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for item in latest:
        key = (item["model"], item["suite"])
        group = grouped.setdefault(
            key,
            {
                "model": item["model"],
                "suite": item["suite"],
                "tests": 0,
                "last_date_utc": "",
            },
        )
        group["tests"] += 1
        if item["date_utc"] > group["last_date_utc"]:
            group["last_date_utc"] = item["date_utc"]
    output: list[dict[str, Any]] = []
    for key in sorted(grouped):
        item = grouped[key]
        output.append(item)
    return output


def parse_model_library(path: Path) -> dict[str, Any]:
    lines = path.read_text(encoding="utf-8").splitlines()
    sections: dict[str, dict[str, Any]] = {}
    notes: list[dict[str, str]] = []
    current_section_title: str | None = None
    current_section_key: str | None = None
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if stripped.startswith("### "):
            current_section_title = stripped[4:].strip()
            current_section_key = None
            i += 1
            continue

        if stripped.startswith("#### "):
            current_section_title = stripped[5:].strip()
            current_section_key = TABLE_SECTIONS.get(current_section_title, slugify(current_section_title))
            sections.setdefault(
                current_section_key,
                {"title": current_section_title, "rows": [], "notes": []},
            )
            i += 1
            continue

        if current_section_title == "Model inventory and GGUF availability" and stripped.startswith("|"):
            current_section_key = "inventory"
            sections.setdefault(
                current_section_key,
                {"title": current_section_title, "rows": [], "notes": []},
            )

        if stripped.startswith("|") and i + 1 < len(lines) and lines[i + 1].strip().startswith("| ---"):
            rows, next_i = parse_table(lines, i)
            section_key = current_section_key or slugify(current_section_title or "root")
            section_title = current_section_title or section_key
            section = sections.setdefault(section_key, {"title": section_title, "rows": [], "notes": []})
            section["rows"].extend(rows)
            i = next_i
            continue

        if current_section_key and stripped and not stripped.startswith("#") and not stripped.startswith("```"):
            if not stripped.startswith("- ") and not stripped.startswith("|"):
                sections[current_section_key]["notes"].append(stripped)
                if current_section_key in BENCHMARK_SECTION_KEYS:
                    notes.append({"section": current_section_key, "text": stripped})
        i += 1

    latest = build_latest_benchmark_rows({key: value["rows"] for key, value in sections.items()})
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_md_path": str(path),
        "notes": "Generated from MODEL_LIBRARY.md. Canonical source is markdown.",
        "sections": sections,
        "benchmark_notes": notes,
        "latest_per_model_test": latest,
        "model_rollup": build_model_rollup(latest),
        "suite_rollup": build_suite_rollup(latest),
    }
    return payload


def main() -> int:
    ap = argparse.ArgumentParser(description="Build model library latest scoreboard JSON from MODEL_LIBRARY.md.")
    ap.add_argument(
        "--model-library",
        default="/mnt/shared/plans/shoulders/benchmarking/MODEL_LIBRARY.md",
    )
    ap.add_argument(
        "--output",
        default="/mnt/shared/plans/shoulders/benchmarking/results/model_library_scoreboard.json",
    )
    args = ap.parse_args()

    model_library_path = Path(args.model_library).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    payload = parse_model_library(model_library_path)
    output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote model library scoreboard JSON: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
