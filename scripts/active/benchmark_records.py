#!/usr/bin/env python3
"""Schema, validation, locking, and selection for benchmark JSONL records."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from filelock import FileLock


SCHEMA_VERSION = 2
RUN_CLASSES = ("smoke", "provisional", "validated", "full", "legacy")
RUN_CLASS_RANK = {
    "smoke": 0,
    "legacy": 1,
    "provisional": 2,
    "validated": 3,
    "full": 4,
}
FORMAT_COMPATIBILITY = ("unknown", "incompatible", "degraded", "compatible")
FORMAT_RANK = {value: rank for rank, value in enumerate(FORMAT_COMPATIBILITY)}
STATUSES = ("success", "failure")


class RecordValidationError(ValueError):
    """Raised when a benchmark record violates the canonical schema."""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_score_pct(score: float) -> float:
    pct = score * 100.0 if score <= 1.0 else score
    return min(100.0, max(0.0, pct))


def canonical_config_hash(config: dict[str, Any]) -> str:
    encoded = json.dumps(config, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _optional_float(value: Any, field: str) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise RecordValidationError(f"{field} must be numeric or null") from exc


def _optional_int(value: Any, field: str) -> int | None:
    if value is None or value == "":
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise RecordValidationError(f"{field} must be an integer or null") from exc
    if parsed < 0:
        raise RecordValidationError(f"{field} must be non-negative")
    return parsed


def normalize_record(record: dict[str, Any]) -> dict[str, Any]:
    """Return a v2 view. Legacy rows are preserved and labeled, not guessed."""
    if int(record.get("schema_version", 1)) == SCHEMA_VERSION:
        normalized = dict(record)
    else:
        score = _optional_float(record.get("score"), "score")
        normalized = {
            "schema_version": SCHEMA_VERSION,
            "run_id": str(record.get("run_id", "")).strip(),
            "run_at": str(record.get("run_at", "")).strip(),
            "model": str(record.get("model", "")).strip(),
            "test_id": str(record.get("test_id", "")).strip(),
            "status": "success" if score is not None else "failure",
            "run_class": "legacy",
            "sample_count": None,
            "score": score,
            "score_pct": _optional_float(record.get("score_pct"), "score_pct"),
            "metric": str(record.get("metric", "")).strip(),
            "raw_harness_score": score,
            "normalized_answer_score": None,
            "format_compatibility": "unknown",
            "extractor_failure_count": 0,
            "harness": str(record.get("harness", "")).strip(),
            "suite": str(record.get("suite", "")).strip(),
            "runtime": {},
            "efficiency": {},
            "failure": {},
            "notes": str(record.get("notes", "")).strip(),
            "legacy_record": True,
        }
    validate_record(normalized)
    return normalized


def validate_record(record: dict[str, Any]) -> None:
    required_text = ("run_id", "run_at", "model", "test_id", "status", "run_class")
    for field in required_text:
        if not str(record.get(field, "")).strip():
            raise RecordValidationError(f"missing required field: {field}")
    if int(record.get("schema_version", 0)) != SCHEMA_VERSION:
        raise RecordValidationError(f"schema_version must be {SCHEMA_VERSION}")
    if record["status"] not in STATUSES:
        raise RecordValidationError(f"status must be one of: {', '.join(STATUSES)}")
    if record["run_class"] not in RUN_CLASSES:
        raise RecordValidationError(f"run_class must be one of: {', '.join(RUN_CLASSES)}")
    sample_count = _optional_int(record.get("sample_count"), "sample_count")
    if record["status"] == "success":
        if _optional_float(record.get("score"), "score") is None:
            raise RecordValidationError("successful records require score")
        if not str(record.get("metric", "")).strip():
            raise RecordValidationError("successful records require metric")
        if record["run_class"] != "legacy" and (sample_count is None or sample_count == 0):
            raise RecordValidationError("new successful records require sample_count > 0")
    if record["status"] == "failure":
        failure = record.get("failure")
        if not isinstance(failure, dict) or not str(failure.get("kind", "")).strip():
            raise RecordValidationError("failure records require failure.kind")
    compatibility = str(record.get("format_compatibility", "unknown"))
    if compatibility not in FORMAT_COMPATIBILITY:
        raise RecordValidationError(
            f"format_compatibility must be one of: {', '.join(FORMAT_COMPATIBILITY)}"
        )
    for field in ("runtime", "efficiency", "failure"):
        if not isinstance(record.get(field, {}), dict):
            raise RecordValidationError(f"{field} must be an object")


def load_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"benchmark records not found: {path}")
    lock = FileLock(str(path) + ".lock", timeout=30)
    with lock:
        raw_lines = path.read_text(encoding="utf-8").splitlines()
    rows: list[dict[str, Any]] = []
    run_ids: set[str] = set()
    for line_number, raw in enumerate(raw_lines, start=1):
        text = raw.strip()
        if not text:
            continue
        try:
            decoded = json.loads(text)
        except json.JSONDecodeError as exc:
            raise RecordValidationError(f"invalid JSON at {path}:{line_number}: {exc}") from exc
        if not isinstance(decoded, dict):
            raise RecordValidationError(f"record at {path}:{line_number} must be an object")
        try:
            normalized = normalize_record(decoded)
        except RecordValidationError as exc:
            raise RecordValidationError(f"invalid record at {path}:{line_number}: {exc}") from exc
        run_id = str(normalized["run_id"])
        if run_id in run_ids:
            raise RecordValidationError(f"duplicate run_id at {path}:{line_number}: {run_id}")
        run_ids.add(run_id)
        rows.append(normalized)
    return rows


def selection_key(record: dict[str, Any]) -> tuple[int, int, int, str, str]:
    """Prefer evidence quality and sample size before recency."""
    if record.get("status") != "success":
        return (-1, -1, -1, "", "")
    run_class = str(record.get("run_class", "legacy"))
    sample_count = _optional_int(record.get("sample_count"), "sample_count")
    compatibility = str(record.get("format_compatibility", "unknown"))
    return (
        RUN_CLASS_RANK.get(run_class, -1),
        sample_count if sample_count is not None else -1,
        FORMAT_RANK.get(compatibility, -1),
        str(record.get("run_at", "")),
        str(record.get("run_id", "")),
    )


def best_by_model_test(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    selected: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        if row.get("status") != "success":
            continue
        key = (str(row.get("model", "")), str(row.get("test_id", "")))
        if not all(key):
            continue
        current = selected.get(key)
        if current is None or selection_key(row) > selection_key(current):
            selected[key] = row
    return sorted(selected.values(), key=lambda row: (row["model"], row["test_id"]))


def append_record(path: Path, record: dict[str, Any]) -> None:
    validate_record(record)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = FileLock(str(path) + ".lock", timeout=30)
    with lock:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())


def write_json_atomic(path: Path, payload: Any) -> None:
    write_text_atomic(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")


def write_text_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = FileLock(str(path) + ".lock", timeout=30)
    with lock:
        fd, temp_name = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)
