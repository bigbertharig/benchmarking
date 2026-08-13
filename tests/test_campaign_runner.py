import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = ROOT.parents[2] / "scripts" / "benchmarks" / "run_campaign.py"
SPEC = importlib.util.spec_from_file_location("benchmark_campaign_runner", RUNNER_PATH)
RUNNER = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = RUNNER
SPEC.loader.exec_module(RUNNER)
RUNNER.SHARED_ROOT = ROOT.parents[2]
RUNNER.BENCHMARKING_SCRIPTS = ROOT
RUNNER.TUNING_PROFILES_PATH = ROOT / "model_tuning_profiles.json"
RUNNER.SUITE_CONTRACTS_PATH = ROOT / "docker" / "suite_contracts.json"
RUNNER.load_suite_contracts()


class CampaignRunnerTests(unittest.TestCase):
    def test_registry_drives_command_for_every_suite(self):
        for suite in sorted(RUNNER.SUPPORTED_SUITES):
            with self.subTest(suite=suite):
                config = {
                    "id": suite,
                    "model": "qwen3-coder:30b-a3b",
                    "gguf": "/tmp/model.gguf",
                    "suite": suite,
                    "suite_args": [],
                    "run_class": "smoke",
                    "_run_id": "unit",
                }
                block = RUNNER.BlockState(suite, config)
                command = RUNNER.build_suite_cmd(block, RUNNER.SLOTS["brain"])
                self.assertIn(suite, command)
                self.assertIn("--model", command)
                self.assertIn("--run-name", command)
                self.assertIn("--run-class", command)
                self.assertIn("--results-dir", command)
                self.assertIn("--runtime-base", command)
                self.assertNotIn("--gguf", command)
                self.assertIn("HOME=/tmp/benchmark-home", command)
                self.assertTrue(any(value.startswith("HF_HOME=") for value in command))

    def test_profile_alias_is_resolved_before_launch(self):
        profile = RUNNER._lookup_tuning("qwen3-coder:30b-a3b")
        self.assertIsNotNone(profile)
        self.assertTrue(profile["system_prompt"].strip())
        self.assertIn("ctx_size", profile["runtime"])

    def test_split_and_single_slots_conflict(self):
        occupied = {"split_1_3": "split-block"}
        slot = RUNNER.find_free_slot("single", occupied)
        self.assertIsNotNone(slot)
        self.assertNotIn(slot.name, {"gpu_1", "gpu_3"})

    def test_limit_policy_fails_during_preflight(self):
        with tempfile.NamedTemporaryFile() as gguf:
            config = {
                "id": "pipeline",
                "model": "qwen3-coder:30b-a3b",
                "gguf": gguf.name,
                "suite": "bench-pipeline",
                "suite_args": [],
                "run_class": "smoke",
                "limit": 1,
            }
            blocks = {"pipeline": RUNNER.BlockState("pipeline", config)}
            with self.assertRaises(SystemExit) as raised:
                RUNNER.validate_resolved_blocks(blocks)
            self.assertIn("does not support bounded", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
