"""Portable campaign package runs without a Benchmarking source checkout."""
import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / "scripts/active/build_campaign_bundle.py"


class CampaignBundleTests(unittest.TestCase):
    def test_clean_package_verifies_and_compiles_request(self):
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            package = temp / "campaign.zip"
            subprocess.run([sys.executable, str(BUILDER), "build", str(package)],
                           check=True, capture_output=True, text=True)
            with zipfile.ZipFile(package) as archive:
                archive.extractall(temp / "installed")
            root = temp / "installed/benchmarking-campaign"
            self.assertFalse((root / ".git").exists())
            for name in ("run_local_custom_task.py", "benchmark_catalog.json", "benchmark_methodologies.json",
                         "custom_tasks/cases.json", "scripts/active/record_benchmark_result.py"):
                self.assertTrue((root / name).is_file(), name)
            subprocess.run([sys.executable, str(root / "scripts/active/record_benchmark_result.py"),
                            "--help"], check=True, capture_output=True, text=True)
            subprocess.run([sys.executable, str(BUILDER), "verify", str(root)],
                           check=True, capture_output=True, text=True)
            records = temp / "records.jsonl"
            reference = temp / "MODEL_BENCHMARK_REFERENCE.md"
            scoreboard = temp / "model_library_scoreboard.json"
            subprocess.run([
                sys.executable, str(root / "scripts/active/record_benchmark_result.py"),
                "--model", "ministral-3:3b", "--test-id", "custom_json_schema_strict",
                "--run-class", "smoke", "--score", "0.5", "--sample-count", "1",
                "--metric", "pass_rate", "--methodology-id", "bench-pipeline/local-custom",
                "--methodology-version", "2.1.0", "--comparison-group", "pipeline-local-custom-v2",
                "--records", str(records), "--reference-output", str(reference),
                "--scoreboard-output", str(scoreboard),
            ], check=True, capture_output=True, text=True)
            self.assertEqual(json.loads(records.read_text())["score"], 0.5)
            self.assertTrue(reference.is_file())
            self.assertTrue(scoreboard.is_file())
            self.assertEqual(json.loads(scoreboard.read_text())["selected_per_model_test"][0]["model"],
                             "ministral-3:3b")
            request = temp / "request.json"
            request.write_text(json.dumps({"name": "portable-smoke",
                                           "models": ["ministral-3:3b"],
                                           "tests": [{"suite": "bench-reasoning",
                                                      "tasks": ["gsm8k"], "limit": 1}],
                                           "run_class": "smoke"}))
            command = [sys.executable, str(root / "scripts/active/submit_campaign_request.py"),
                       str(request), "--dry-run", "--pi-shared-root", str(temp / "shared"),
                       "--rig-shared-root", "/mnt/shared",
                       "--rig-campaign-package-root", "/opt/benchmarking-campaign",
                       "--rigctl", "/opt/rigctl.py"]
            receipt = json.loads(subprocess.run(command, check=True, capture_output=True,
                                                text=True).stdout)
            self.assertEqual(receipt["state"], "dry_run")
            self.assertEqual(len(receipt["compiled_campaign"]["blocks"]), 1)
            subprocess.run([sys.executable,
                            str(root / "scripts/integration/wait_for_campaign_completion.py"),
                            "--help"], check=True, capture_output=True, text=True)
            (root / "model_registry.json").write_text("{}")
            with self.assertRaises(subprocess.CalledProcessError):
                subprocess.run([sys.executable, str(BUILDER), "verify", str(root)],
                               check=True, capture_output=True, text=True)


if __name__ == "__main__":
    unittest.main()
