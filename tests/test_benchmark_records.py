from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ACTIVE = Path(__file__).resolve().parents[1] / "scripts" / "active"
sys.path.insert(0, str(ACTIVE))

from benchmark_records import (  # noqa: E402
    RecordValidationError,
    best_by_model_test,
    load_records,
    normalize_record,
    selection_key,
    validate_record,
)
from build_methodology_history import build_history  # noqa: E402


def record(*, run_id: str, run_class: str, sample_count: int, score: float, run_at: str) -> dict:
    return {
        "schema_version": 2,
        "run_id": run_id,
        "run_at": run_at,
        "model": "model:a",
        "test_id": "test:a",
        "status": "success",
        "run_class": run_class,
        "sample_count": sample_count,
        "score": score,
        "score_pct": score * 100,
        "metric": "accuracy",
        "raw_harness_score": score,
        "normalized_answer_score": None,
        "format_compatibility": "compatible",
        "extractor_failure_count": 0,
        "harness": "test",
        "suite": "unit",
        "runtime": {},
        "efficiency": {},
        "failure": {},
        "notes": "",
    }


class BenchmarkRecordTests(unittest.TestCase):
    def test_validated_result_beats_newer_smoke(self) -> None:
        validated = record(run_id="validated", run_class="validated", sample_count=100, score=0.8, run_at="2026-01-01T00:00:00Z")
        smoke = record(run_id="smoke", run_class="smoke", sample_count=5, score=0.99, run_at="2026-02-01T00:00:00Z")
        self.assertGreater(selection_key(validated), selection_key(smoke))
        self.assertEqual(best_by_model_test([validated, smoke]), [validated])

    def test_larger_sample_wins_within_run_class(self) -> None:
        small = record(run_id="small", run_class="validated", sample_count=50, score=0.9, run_at="2026-02-01T00:00:00Z")
        large = record(run_id="large", run_class="validated", sample_count=100, score=0.8, run_at="2026-01-01T00:00:00Z")
        self.assertEqual(best_by_model_test([small, large]), [large])

    def test_failure_is_retained_but_not_selected(self) -> None:
        success = record(run_id="success", run_class="smoke", sample_count=5, score=0.5, run_at="2026-01-01T00:00:00Z")
        failure = dict(success, run_id="failure", status="failure", score=None, metric="", failure={"kind": "oom", "message": "killed"})
        validate_record(failure)
        self.assertEqual(best_by_model_test([success, failure]), [success])

    def test_legacy_record_is_labeled_without_quality_guess(self) -> None:
        legacy = normalize_record({
            "run_id": "old", "run_at": "2026-01-01", "model": "m", "test_id": "t",
            "score": 0.5, "score_pct": 50, "metric": "accuracy", "harness": "h", "suite": "s", "notes": "",
        })
        self.assertEqual(legacy["run_class"], "legacy")
        self.assertIsNone(legacy["sample_count"])

    def test_new_success_requires_sample_count(self) -> None:
        invalid = record(run_id="bad", run_class="validated", sample_count=1, score=0.5, run_at="2026-01-01")
        invalid["sample_count"] = None
        with self.assertRaises(RecordValidationError):
            validate_record(invalid)

    def test_schema_v3_requires_explicit_methodology(self) -> None:
        invalid = record(run_id="v3", run_class="validated", sample_count=10, score=0.5, run_at="2026-01-01")
        invalid["schema_version"] = 3
        with self.assertRaisesRegex(RecordValidationError, "methodology.id"):
            validate_record(invalid)
        invalid["methodology"] = {
            "id": "suite/method",
            "version": "1.0.0",
            "comparison_group": "method-v1",
        }
        validate_record(invalid)

    def test_methodology_history_keeps_old_and_new_methods_separate(self) -> None:
        old = normalize_record(
            record(run_id="old-method", run_class="validated", sample_count=10, score=0.8, run_at="2026-01-01")
        )
        new = record(run_id="new-method", run_class="validated", sample_count=10, score=0.7, run_at="2026-02-01")
        new["schema_version"] = 3
        new["methodology"] = {
            "id": "suite/method",
            "version": "2.0.0",
            "comparison_group": "method-v2",
        }
        history = build_history([old, new])
        self.assertEqual(history["group_count"], 2)
        self.assertEqual({entry["selected_score"] for entry in history["entries"]}, {0.8, 0.7})

    def test_ledger_test_ids_are_cataloged_or_in_registered_result_families(self) -> None:
        root = ACTIVE.parents[1]
        catalog = json.loads((root / "benchmark_catalog.json").read_text(encoding="utf-8"))
        known = {item["id"] for item in catalog["tests"]}
        families = [re.compile(item["pattern"]) for item in catalog.get("result_families", [])]
        rows = load_records(root / "results" / "model_benchmark_records.jsonl")
        unknown = sorted(
            {
                row["test_id"]
                for row in rows
                if row["test_id"] not in known
                and not any(pattern.fullmatch(row["test_id"]) for pattern in families)
            }
        )
        self.assertEqual(unknown, [])

    def test_loader_fails_on_invalid_json(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "records.jsonl"
            path.write_text(json.dumps(record(run_id="ok", run_class="smoke", sample_count=5, score=0.5, run_at="2026-01-01")) + "\nnot-json\n", encoding="utf-8")
            with self.assertRaises(RecordValidationError):
                load_records(path)

    def test_loader_rejects_duplicate_run_ids(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "records.jsonl"
            row = record(run_id="duplicate", run_class="smoke", sample_count=5, score=0.5, run_at="2026-01-01")
            path.write_text(json.dumps(row) + "\n" + json.dumps(row) + "\n", encoding="utf-8")
            with self.assertRaises(RecordValidationError):
                load_records(path)

    def test_generators_refuse_to_replace_outputs_with_empty_data(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            records = root / "records.jsonl"
            models = root / "models.json"
            status = root / "status.json"
            reference = root / "reference.md"
            scoreboard = root / "scoreboard.json"
            records.write_text("", encoding="utf-8")
            models.write_text('{"models": []}\n', encoding="utf-8")
            status.write_text("{}\n", encoding="utf-8")
            reference.write_text("sentinel-reference\n", encoding="utf-8")
            scoreboard.write_text("sentinel-scoreboard\n", encoding="utf-8")

            reference_proc = subprocess.run(
                [
                    sys.executable,
                    str(ACTIVE / "build_benchmark_reference.py"),
                    "--records",
                    str(records),
                    "--status-path",
                    str(status),
                    "--output",
                    str(reference),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            scoreboard_proc = subprocess.run(
                [
                    sys.executable,
                    str(ACTIVE / "build_model_library_scoreboard.py"),
                    "--records",
                    str(records),
                    "--models-catalog",
                    str(models),
                    "--output",
                    str(scoreboard),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(reference_proc.returncode, 0)
            self.assertNotEqual(scoreboard_proc.returncode, 0)
            self.assertEqual(reference.read_text(encoding="utf-8"), "sentinel-reference\n")
            self.assertEqual(scoreboard.read_text(encoding="utf-8"), "sentinel-scoreboard\n")

    def test_scoreboard_uses_quality_selection_and_suite_rollups(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            records = root / "records.jsonl"
            models = root / "models.json"
            scoreboard = root / "scoreboard.json"
            validated = record(
                run_id="validated",
                run_class="validated",
                sample_count=100,
                score=0.8,
                run_at="2026-01-01",
            )
            validated["suite"] = "controlled"
            smoke = record(
                run_id="smoke",
                run_class="smoke",
                sample_count=5,
                score=0.99,
                run_at="2026-02-01",
            )
            smoke["suite"] = "controlled"
            records.write_text(
                json.dumps(validated) + "\n" + json.dumps(smoke) + "\n",
                encoding="utf-8",
            )
            models.write_text('{"models": []}\n', encoding="utf-8")

            proc = subprocess.run(
                [
                    sys.executable,
                    str(ACTIVE / "build_model_library_scoreboard.py"),
                    "--records",
                    str(records),
                    "--models-catalog",
                    str(models),
                    "--output",
                    str(scoreboard),
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(proc.returncode, 0, proc.stderr)
            payload = json.loads(scoreboard.read_text(encoding="utf-8"))
            self.assertNotIn("latest_per_model_test", payload)
            self.assertEqual(payload["selected_per_model_test"][0]["run_id"], "validated")
            self.assertEqual(payload["suite_rollup"][0]["suite"], "controlled")
            self.assertEqual(payload["suite_rollup"][0]["records"], 2)


if __name__ == "__main__":
    unittest.main()
