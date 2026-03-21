"""
Suite validator for bench-daedalmap.

Checks a suite JSON file for structural correctness before running.
Run before accepting any edits to suite files.

Usage:
  python validate_suite.py llm_benchmark_v2.json
  python validate_suite.py llm_benchmark_v1.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


VALID_CATEGORIES = {
    "json_discipline",
    "type_routing",
    "source_grounding",
    "catalog_discipline",
    "geographic_precision",
    "multi_source",
}

VALID_EXPECTED_TYPES = {
    "order",
    "navigate",
    "disambiguate",
    "overlay_toggle",
    "clarify",
    "chat",
}

VALID_REQUIRES = {"catalog", "data_s3"}
VALID_PRIORITIES = {"p0", "p1", "p2"}

REQUIRED_FIELDS = [
    "case_id", "category", "query", "expected_type",
    "expected_source_ids", "must_not_hallucinate", "clarify_ok",
]


def load_catalog_source_ids() -> set:
    catalog_path = Path(__file__).parent / "benchmark_catalog.json"
    if not catalog_path.exists():
        return set()
    with open(catalog_path, encoding="utf-8") as f:
        catalog = json.load(f)
    return {s["source_id"] for s in catalog.get("sources", [])}


def validate(suite_path: str) -> bool:
    path = Path(suite_path)
    if not path.is_absolute():
        path = Path(__file__).parent / suite_path

    if not path.exists():
        print(f"ERROR: File not found: {path}")
        return False

    with open(path, encoding="utf-8") as f:
        try:
            suite = json.load(f)
        except json.JSONDecodeError as e:
            print(f"ERROR: JSON parse failed: {e}")
            return False

    cases = suite.get("cases", [])
    if not cases:
        print("ERROR: No cases found in suite.")
        return False

    catalog_ids = load_catalog_source_ids()
    if not catalog_ids:
        print("WARNING: benchmark_catalog.json not found. Skipping source ID validation.")

    errors = []
    warnings = []
    seen_ids = {}
    category_counts = {}

    for i, case in enumerate(cases):
        case_id = case.get("case_id", f"(case {i})")
        loc = f"case {case_id}"

        # Duplicate IDs
        if case_id in seen_ids:
            errors.append(f"{loc}: duplicate case_id (first at case {seen_ids[case_id]})")
        else:
            seen_ids[case_id] = i

        # Required fields
        for field in REQUIRED_FIELDS:
            if field not in case:
                errors.append(f"{loc}: missing required field '{field}'")

        # Category
        cat = case.get("category", "")
        if cat not in VALID_CATEGORIES:
            errors.append(f"{loc}: invalid category '{cat}' (allowed: {sorted(VALID_CATEGORIES)})")
        else:
            category_counts[cat] = category_counts.get(cat, 0) + 1

        # Expected type
        et = case.get("expected_type", "")
        if et not in VALID_EXPECTED_TYPES:
            errors.append(f"{loc}: invalid expected_type '{et}' (allowed: {sorted(VALID_EXPECTED_TYPES)})")

        # Priority
        pri = case.get("priority", "")
        if pri and pri not in VALID_PRIORITIES:
            warnings.append(f"{loc}: unexpected priority '{pri}'")

        # requires
        req = case.get("requires", "")
        if req and req not in VALID_REQUIRES:
            errors.append(f"{loc}: invalid requires '{req}' (allowed: {sorted(VALID_REQUIRES)})")

        # expected_source_ids must be a list
        esids = case.get("expected_source_ids", [])
        if not isinstance(esids, list):
            errors.append(f"{loc}: expected_source_ids must be a list")
        elif catalog_ids:
            for sid in esids:
                if sid not in catalog_ids:
                    errors.append(f"{loc}: expected_source_id '{sid}' not in catalog")

        # must_not_hallucinate must be a list
        mnh = case.get("must_not_hallucinate", [])
        if not isinstance(mnh, list):
            errors.append(f"{loc}: must_not_hallucinate must be a list")

        # Non-order types should have empty expected_source_ids
        if et not in ("order", "") and esids:
            warnings.append(f"{loc}: type='{et}' has expected_source_ids {esids} (only scored for order)")

    suite_id = suite.get("suite_id", path.stem)
    total = len(cases)

    print(f"Suite:  {suite_id}")
    print(f"Cases:  {total}")
    print()

    print("Category counts:")
    for cat in sorted(VALID_CATEGORIES):
        count = category_counts.get(cat, 0)
        print(f"  {cat:<30} {count}")
    print()

    if warnings:
        print(f"Warnings ({len(warnings)}):")
        for w in warnings:
            print(f"  WARN  {w}")
        print()

    if errors:
        print(f"Errors ({len(errors)}):")
        for e in errors:
            print(f"  ERROR {e}")
        print()
        print(f"FAIL - {len(errors)} error(s) found.")
        return False

    print("PASS - no errors found.")
    return True


def main():
    if len(sys.argv) < 2:
        print("Usage: python validate_suite.py <suite_file.json>")
        sys.exit(1)

    ok = validate(sys.argv[1])
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
