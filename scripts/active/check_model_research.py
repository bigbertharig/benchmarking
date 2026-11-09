#!/usr/bin/env python3
"""Fail closed before downloading a new model without a reviewed trial record."""

import argparse
import datetime as dt
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RECORDS = ROOT / "research" / "candidates"
MAX_AGE_DAYS = 30


def check(model_id: str, records_dir: Path = RECORDS) -> list[str]:
    matches = []
    errors = []
    for path in records_dir.glob("*.json"):
        if path.name.startswith("_"):
            continue
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{path.name}: invalid JSON: {exc}")
            continue
        if record.get("model_id") == model_id:
            matches.append((path, record))
    if len(matches) != 1:
        return errors + [f"expected one research record for {model_id!r}; found {len(matches)}"]

    path, record = matches[0]
    if record.get("decision") != "trial":
        errors.append(f"{path.name}: decision is {record.get('decision')!r}, not 'trial'")
        return errors
    if record.get("release_status") != "released_weights":
        errors.append("release_status must be 'released_weights'")
    required = (
        "decision_reason", "official_model_url", "upstream_model_id", "license",
        "weights_url", "quant_url", "quant_file", "quant_size_gb", "target_lane",
        "fit_estimate", "local_comparator", "test_question",
    )
    for field in required:
        if not record.get(field):
            errors.append(f"missing {field}")
    for field in ("official_model_url", "weights_url", "quant_url"):
        value = record.get(field)
        if value and not str(value).startswith("https://"):
            errors.append(f"{field} must be an HTTPS URL")
    size = record.get("quant_size_gb")
    if size is not None and (not isinstance(size, (int, float)) or size <= 0):
        errors.append("quant_size_gb must be a positive number")
    try:
        reviewed = dt.date.fromisoformat(record["reviewed_at"])
        age = (dt.date.today() - reviewed).days
        if age < 0 or age > MAX_AGE_DAYS:
            errors.append(f"reviewed_at is {age} days old; review must be within {MAX_AGE_DAYS} days")
    except (KeyError, TypeError, ValueError):
        errors.append("reviewed_at must be an ISO date")
    if not isinstance(record.get("public_evidence"), list):
        errors.append("public_evidence must be a list (empty if no public score exists)")
    sources = record.get("sources")
    if not isinstance(sources, list) or not any(
        isinstance(item, dict) and item.get("kind") in {"official_model_card", "official_announcement"}
        and str(item.get("url", "")).startswith("https://") for item in sources
    ):
        errors.append("sources needs an HTTPS official model card or announcement")
    if not record.get("public_evidence") and not record.get("no_public_scores_reason"):
        errors.append("add public_evidence or no_public_scores_reason")
    if record.get("local_comparator") == model_id:
        errors.append("local_comparator must be an existing different model")
    else:
        try:
            registry = json.loads((ROOT / "model_registry.json").read_text(encoding="utf-8"))
            comparator = registry["models"].get(record.get("local_comparator"))
            if not comparator or comparator.get("status") != "active":
                errors.append("local_comparator must be an active model in model_registry.json")
        except (OSError, KeyError, json.JSONDecodeError) as exc:
            errors.append(f"cannot validate model registry: {exc}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model_id", help="candidate model_id in research/candidates/*.json")
    args = parser.parse_args()
    errors = check(args.model_id)
    if errors:
        for error in errors:
            print(f"FAIL: {error}")
        return 1
    print(f"PASS: Phase R research gate for {args.model_id}; proceed to Phase 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
