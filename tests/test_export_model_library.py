"""Contract checks for the benchmark-owned model export."""

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/active"))
import export_model_library as exporter  # noqa: E402


class ModelExportContractTest(unittest.TestCase):
    def test_export_is_deterministic_and_covers_every_profile(self):
        first = exporter.build()
        self.assertEqual(first, exporter.build())
        payload = {key: value for key, value in first.items() if key != "source_sha256"}
        self.assertEqual(first["source_sha256"], hashlib.sha256(exporter.canonical_bytes(payload)).hexdigest())
        self.assertEqual(set(first["registry"]["models"]), set(first["resolved_profiles"]))
        self.assertEqual(set(first["tuning_profiles"]["models"]),
                         set(first["resolved_tuning_profiles"]))
        self.assertTrue(first["resolved_tuning_profiles"]["qwen3-coder:30b-a3b"]["system_prompt"])
        for mid, entry in first["registry"]["models"].items():
            self.assertEqual(set(entry["profiles"]), set(first["resolved_profiles"][mid]))
            for name, resolved in first["resolved_profiles"][mid].items():
                self.assertEqual((resolved["model"], resolved["profile"]), (mid, name))

    def test_published_file_matches_current_source(self):
        published = json.loads(exporter.OUTPUT.read_text(encoding="utf-8"))
        self.assertEqual(published, exporter.build())

    def test_summary_prefers_validated_and_newer_extractor(self):
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            (root / "results/runtime_experiments").mkdir(parents=True)
            records = [
                {"model": "m:9b", "test_id": "bbh_flexible", "score": 0.80,
                 "run_class": "smoke", "run_at": "2026-10-19T01:00:00Z"},
                {"model": "m:9b", "test_id": "bbh_flexible", "score": 0.85,
                 "run_class": "validated", "run_at": "2026-10-18T01:00:00Z"},
                {"model": "m:9b", "test_id": "drop_flexible", "score": 0.2,
                 "run_class": "smoke", "run_at": "2026-10-19T01:00:09Z",
                 "runtime": {"config_id": "reasoning-extract-v4"}},
                {"model": "m:9b", "test_id": "drop_flexible", "score": 0.6,
                 "run_class": "smoke", "run_at": "2026-10-19T01:00:00Z",
                 "runtime": {"config_id": "reasoning-extract-v5"},
                 "extractor_failure_count": 2, "sample_count": 10},
            ]
            (root / "results/model_benchmark_records.jsonl").write_text(
                "\n".join(json.dumps(row) for row in records) + "\n")
            (root / "results/runtime_experiments/m_9b_runtime_characterization_20261020.json").write_text(
                json.dumps({"runtime": {"ctx_size": 26880},
                            "decode": {"generation_tokens_per_second": 16.6}}))
            registry = {"models": {"m:9b": {"status": "active", "profiles": {"default": {}},
                                                "schedule": {"placement": "single_gpu", "tier": 1}},
                                   "old:7b": {"status": "archived", "profiles": {"default": {}}}}}
            roles = {"roles": {"single_1060": {"model": "m:9b"}}}
            original = exporter.ROOT
            try:
                exporter.ROOT = root
                result = exporter.summary(registry, roles)
            finally:
                exporter.ROOT = original
            first = result["models"][0]
            self.assertEqual(first["roles"], ["single_1060"])
            self.assertEqual(first["scores"]["bbh"]["score"], 0.85)
            self.assertEqual(first["scores"]["drop"]["unreadable"], 2)
            self.assertEqual(first["runtime"]["decode_tps"], 16.6)
            self.assertEqual(result["models"][-1]["model"], "old:7b")

    def test_dynamic_subagent_requires_a_complete_memory_curve(self):
        registry = {"models": {"m:9b": {}}}
        valid = {"schema_version": 1, "candidates": {"shared_worker": {
            "provider": "rig_shared_chat", "model": "m:9b",
            "context_cap": 262144, "context_allocation": "dynamic_at_attach",
            "context_min": 16384, "context_default": 65536,
            "max_attached_chats": 2,
            "memory_estimate": {"fixed_compute_mib": 100,
                                "kv_mib_at_262144": 1000,
                                "admission_reserve_mib": 256,
                                "method": "measured"}}}}
        exporter.validate_subagents(valid, registry)
        del valid["candidates"]["shared_worker"]["memory_estimate"]["admission_reserve_mib"]
        with self.assertRaisesRegex(ValueError, "invalid memory estimate"):
            exporter.validate_subagents(valid, registry)

    def test_shared_worker_evidence_must_be_published(self):
        registry = {"models": {"m:9b": {}}}
        row = {"schema_version": 1, "candidates": {"worker": {
            "provider": "rig_shared_chat", "model": "m:9b",
            "context_cap": 65536, "context_allocation": "fixed_per_chat",
            "max_attached_chats": 1,
            "evidence": "results/runtime_experiments/missing/README.md"}}}
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ValueError, "evidence is missing"):
                exporter.validate_subagents(row, registry, Path(folder))


if __name__ == "__main__":
    unittest.main()
