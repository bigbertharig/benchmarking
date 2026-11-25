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
            subprocess.run([sys.executable, str(BUILDER), "verify", str(root)],
                           check=True, capture_output=True, text=True)
            request = temp / "request.json"
            request.write_text(json.dumps({"name": "portable-smoke",
                                           "models": ["gemma-3:4b"],
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
