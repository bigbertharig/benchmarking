from __future__ import annotations

import sys
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "active"))
from build_campaign_request import compile_gateway_plan, compile_request  # noqa: E402
import submit_campaign_request as submitter  # noqa: E402


REGISTRY = {"models": {"model:a": {"status": "candidate", "loading_stage": {"state": "in_progress"}}, "model:b": {"status": "active", "loading_stage": {"state": "ready_for_benchmark"}}}}
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

    def test_gateway_projection_contains_work_intent_not_suite_execution_details(self) -> None:
        campaign = compile_request({"name": "two_models", "models": ["model:a", "model:b"],
                                    "tests": [{"suite": "bench-reasoning", "tasks": ["drop"],
                                               "limit": 10}]}, REGISTRY, CONTRACTS)
        campaign["blocks"][0].update({"ctx_size": 8192, "estimated_duration_s": 90,
                                      "runtime_args": ["--reasoning", "on"], "gpus": [1]})
        plan = compile_gateway_plan(campaign)
        self.assertEqual(plan["schema"], "benchmark-campaign-plan/1")
        self.assertEqual(plan["planning_mode"], "after_current_work")
        self.assertEqual(plan["blocks"][0]["ctx"], 8192)
        self.assertEqual(plan["blocks"][0]["estimated_duration_s"], 90)
        self.assertNotIn("suite_args", plan["blocks"][0])
        self.assertNotIn("runtime_args", plan["blocks"][0])
        self.assertNotIn("gpus", plan["blocks"][0])

    def test_existing_parallel_sequential_fixture_projects_without_old_placement_policy(self) -> None:
        campaign = json.loads((Path(__file__).resolve().parents[1] / "campaigns" /
                               "harness_sequential_parallel_smoke.json").read_text(encoding="utf-8"))
        plan = compile_gateway_plan(campaign)
        self.assertEqual([row["id"] for row in plan["blocks"]],
                         ["knowledge_lane", "data_parallel_lane", "geometry_after_knowledge"])
        self.assertEqual(plan["blocks"][2]["depends_on"], ["knowledge_lane"])
        self.assertTrue(all("placement" not in row and "gpus" not in row for row in plan["blocks"]))

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

    def test_missing_loading_stage_is_rejected(self) -> None:
        request = {"name": "legacy", "models": ["new"], "tests": ["bench-reasoning"]}
        with self.assertRaisesRegex(ValueError, "loading_stage is required"):
            compile_request(request, {"models": {"new": {"status": "active"}}}, CONTRACTS)

    def test_unfinished_onboarding_can_smoke_but_not_run_full_suites(self) -> None:
        registry = {"models": {"new": {"status": "candidate", "loading_stage": {"state": "in_progress"}}}}
        request = {"name": "diagnostic", "models": ["new"], "tests": ["bench-reasoning"]}
        self.assertEqual(compile_request(request, registry, CONTRACTS)["defaults"]["run_class"], "smoke")
        for run_class in ("provisional", "validated", "full"):
            request["run_class"] = run_class
            with self.assertRaisesRegex(ValueError, "not ready_for_benchmark"):
                compile_request(request, registry, CONTRACTS)

    def test_submission_writes_recoverable_manifest_and_one_managed_run(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "docker").mkdir()
            (root / "model_registry.json").write_text(json.dumps(REGISTRY), encoding="utf-8")
            (root / "docker/suite_contracts.json").write_text(json.dumps(CONTRACTS), encoding="utf-8")
            (root / "model_library_export.json").write_text(json.dumps({"source_sha256": "same"}), encoding="utf-8")
            request = root / "request.json"
            request.write_text(json.dumps({"name": "Two Models", "models": ["model:a", "model:b"],
                                           "tests": ["bench-reasoning", "bench-runtime"]}), encoding="utf-8")
            class Result:
                returncode = 0
                stdout = '{"run":"unit"}'
                stderr = ""
            with patch.object(submitter, "ROOT", root), patch.object(submitter, "build_export", return_value={"source_sha256": "same"}), patch.object(submitter.subprocess, "run", return_value=Result()) as run:
                receipt = submitter.submit(request, pi_shared_root=root / "pi",
                                           rig_shared_root=Path("/rig/shared"),
                                           rigctl=root / "rigctl.py", run_id="unit",
                                           rig_benchmarking_root=Path("/rig/benchmarking"))
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
            self.assertIn("/rig/benchmarking/scripts/active/run_campaign.py", command)
            self.assertNotIn("--gpus", command)

    def test_submission_rejects_export_without_source_hash_before_manager_call(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "docker").mkdir()
            (root / "model_registry.json").write_text(json.dumps(REGISTRY), encoding="utf-8")
            (root / "docker/suite_contracts.json").write_text(json.dumps(CONTRACTS), encoding="utf-8")
            (root / "model_library_export.json").write_text(json.dumps({"schema": "gpu-rig-model-library/1"}), encoding="utf-8")
            request = root / "request.json"
            request.write_text(json.dumps({"name": "stale", "models": ["model:a"],
                                           "tests": ["bench-reasoning"]}), encoding="utf-8")
            with patch.object(submitter, "ROOT", root), patch.object(submitter.subprocess, "run") as run:
                with self.assertRaisesRegex(ValueError, "no source hash"):
                    submitter.submit(request, pi_shared_root=root / "pi",
                                     rig_shared_root=Path("/rig/shared"), rigctl=root / "rigctl.py", run_id="unit",
                                     rig_benchmarking_root=Path("/rig/benchmarking"))
            run.assert_not_called()

    def test_submission_rejects_stale_benchmarking_export(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "docker").mkdir()
            (root / "model_registry.json").write_text(json.dumps(REGISTRY), encoding="utf-8")
            (root / "docker/suite_contracts.json").write_text(json.dumps(CONTRACTS), encoding="utf-8")
            (root / "model_library_export.json").write_text(json.dumps({"source_sha256": "old"}), encoding="utf-8")
            request = root / "request.json"
            request.write_text(json.dumps({"name": "stale", "models": ["model:a"],
                                           "tests": ["bench-reasoning"]}), encoding="utf-8")
            with patch.object(submitter, "ROOT", root), patch.object(submitter, "build_export", return_value={"source_sha256": "new"}), patch.object(submitter.subprocess, "run") as run:
                with self.assertRaisesRegex(ValueError, "export is stale"):
                    submitter.submit(request, pi_shared_root=root / "pi",
                                     rig_shared_root=Path("/rig/shared"), rigctl=root / "rigctl.py", run_id="unit",
                                     rig_benchmarking_root=Path("/rig/benchmarking"))
            run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
