from __future__ import annotations

import sys
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "active"))
from build_campaign_request import compile_request  # noqa: E402
import submit_campaign_request as submitter  # noqa: E402


REGISTRY = {"models": {"model:a": {"status": "candidate"}, "model:b": {"status": "active"}}}
CONTRACTS = {"suites": {
    "bench-reasoning": {"task_selector": "--tasks", "limit_supported": True},
    "bench-runtime": {"task_selector": None, "limit_supported": False},
}}


class CampaignRequestTests(unittest.TestCase):
    def test_two_models_reuse_each_load_and_leave_placement_to_rig(self) -> None:
        request = {"name": "two_models", "models": ["model:a", "model:b"],
                   "tests": [{"suite": "bench-reasoning", "tasks": ["gsm8k", "drop"], "limit": 10},
                             "bench-runtime"]}
        campaign = compile_request(request, REGISTRY, CONTRACTS)
        blocks = campaign["blocks"]
        self.assertEqual(len(blocks), 4)
        self.assertEqual([block["runtime_group"] for block in blocks],
                         ["model_1", "model_1", "model_2", "model_2"])
        self.assertEqual(blocks[0]["suite_args"], ["--tasks", "gsm8k,drop"])
        self.assertEqual(blocks[0]["limit"], 10)
        self.assertTrue(all("gpus" not in block and "placement" not in block for block in blocks))
        self.assertEqual(campaign["defaults"], {"run_class": "smoke"})

    def test_rejects_unsupported_limit_before_campaign(self) -> None:
        request = {"name": "bad", "models": ["model:a"],
                   "tests": [{"suite": "bench-runtime", "limit": 1}]}
        with self.assertRaisesRegex(ValueError, "does not support"):
            compile_request(request, REGISTRY, CONTRACTS)

    def test_candidate_is_available_for_explicit_benchmarks(self) -> None:
        campaign = compile_request({"name": "candidate", "models": ["model:a"],
                                    "tests": ["bench-reasoning"]}, REGISTRY, CONTRACTS)
        self.assertEqual(campaign["blocks"][0]["model"], "model:a")
        self.assertNotIn("runtime_group", campaign["blocks"][0])

    def test_explicit_unfinished_onboarding_is_rejected(self) -> None:
        registry = {"models": {"new": {"status": "candidate", "loading_stage": {"state": "in_progress"}}}}
        request = {"name": "too_early", "models": ["new"], "tests": ["bench-reasoning"]}
        with self.assertRaisesRegex(ValueError, "not ready_for_benchmark"):
            compile_request(request, registry, CONTRACTS)

    def test_submission_writes_recoverable_manifest_and_one_managed_run(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "docker").mkdir()
            (root / "model_registry.json").write_text(json.dumps(REGISTRY), encoding="utf-8")
            (root / "docker/suite_contracts.json").write_text(json.dumps(CONTRACTS), encoding="utf-8")
            (root / "model_library_export.json").write_text(json.dumps({"source_sha256": "same"}), encoding="utf-8")
            imported = root / "pi/agents/model_library.json"
            imported.parent.mkdir(parents=True)
            imported.write_text(json.dumps({"source_sha256": "same"}), encoding="utf-8")
            shared_contracts = root / "pi/plans/shoulders/benchmarking/docker/suite_contracts.json"
            shared_contracts.parent.mkdir(parents=True)
            shared_contracts.write_text(json.dumps(CONTRACTS), encoding="utf-8")
            request = root / "request.json"
            request.write_text(json.dumps({"name": "Two Models", "models": ["model:a", "model:b"],
                                           "tests": ["bench-reasoning", "bench-runtime"]}), encoding="utf-8")
            class Result:
                returncode = 0
                stdout = '{"run":"unit"}'
                stderr = ""
            with patch.object(submitter, "ROOT", root), patch.object(submitter.subprocess, "run", return_value=Result()) as run:
                receipt = submitter.submit(request, pi_shared_root=root / "pi",
                                           rig_shared_root=Path("/rig/shared"),
                                           rigctl=root / "rigctl.py", run_id="unit")
            self.assertEqual(receipt["state"], "submitted")
            self.assertEqual(receipt["blocks"], 4)
            self.assertEqual(receipt["model_library_sha256"], "same")
            self.assertIn("/rig/shared/logs/benchmarks/campaigns/history/two_models/unit/status.json",
                          receipt["rig_status"])
            self.assertEqual(receipt["pi_status"], str(root / "pi/logs/benchmarks/campaigns/history/two_models/unit/status.json"))
            self.assertTrue(Path(receipt["manifest"]).is_file())
            self.assertTrue((root / "pi/logs/benchmarks/campaigns/requests/unit.submission.json").is_file())
            command = run.call_args.args[0]
            self.assertIn("--auto-resume", command)
            self.assertIn("/rig/shared/scripts/benchmarks/run_campaign.py", command)
            self.assertNotIn("--gpus", command)

    def test_submission_rejects_stale_import_before_manager_call(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "docker").mkdir()
            (root / "model_registry.json").write_text(json.dumps(REGISTRY), encoding="utf-8")
            (root / "docker/suite_contracts.json").write_text(json.dumps(CONTRACTS), encoding="utf-8")
            (root / "model_library_export.json").write_text(json.dumps({"source_sha256": "new"}), encoding="utf-8")
            imported = root / "pi/agents/model_library.json"
            imported.parent.mkdir(parents=True)
            imported.write_text(json.dumps({"source_sha256": "old"}), encoding="utf-8")
            request = root / "request.json"
            request.write_text(json.dumps({"name": "stale", "models": ["model:a"],
                                           "tests": ["bench-reasoning"]}), encoding="utf-8")
            with patch.object(submitter, "ROOT", root), patch.object(submitter.subprocess, "run") as run:
                with self.assertRaisesRegex(ValueError, "import is stale"):
                    submitter.submit(request, pi_shared_root=root / "pi",
                                     rig_shared_root=Path("/rig/shared"), rigctl=root / "rigctl.py", run_id="unit")
            run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
