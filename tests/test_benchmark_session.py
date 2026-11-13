import sys
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "integration"))
import benchmark_session as session  # noqa: E402
import run_model_loading_sequence as sequence  # noqa: E402


def observation():
    cards = [
        {"index": 7, "uuid": "GPU-small", "name": "small", "total_mb": 6144, "bus": "03:00.0"},
        {"index": 2, "uuid": "GPU-large", "name": "large", "total_mb": 24564, "bus": "01:00.0"},
        {"index": 4, "uuid": "GPU-mid", "name": "mid", "total_mb": 8192, "bus": "0D:00.0"},
    ]
    return {"observed_at": "now", "gpu_scan": {"ok": True, "cards": cards},
            "claims": [{"gpu_ids": [7]}], "leases": [],
            "gpus": [{"index": i, "used_mb": 10} for i in (2, 4, 7)]}


class BenchmarkSessionTests(unittest.TestCase):
    def test_role_resolution_uses_inventory_and_free_cards(self):
        snap = session.inventory(observation())
        session.assign_roles(snap, {"main": {"min_vram_mb": 20000},
                                    "helper": {"min_vram_mb": 6000, "prefer": "least_vram",
                                               "available_only": True}})
        self.assertEqual(snap["roles"]["main"]["index"], 2)
        self.assertEqual(snap["roles"]["helper"]["index"], 4)
        case = {"gpus": ["{gpu:main}", "{gpu:helper}"],
                "command": ["probe", "--card", "{gpu:helper}", "--uuid", "{uuid:helper}"]}
        self.assertEqual(session.expand(case, snap["roles"])["command"][-1], "GPU-mid")

    def test_resume_rejects_card_replaced_at_same_index(self):
        saved = session.inventory(observation())
        changed = observation()
        changed["gpu_scan"]["cards"][1]["uuid"] = "GPU-replacement"
        with self.assertRaisesRegex(RuntimeError, "changed"):
            session.verify_saved(saved, session.inventory(changed), {2})

    def test_bad_scan_and_unsatisfied_role_fail_closed(self):
        broken = observation()
        broken["gpu_scan"]["ok"] = False
        with self.assertRaisesRegex(RuntimeError, "scan failed"):
            session.inventory(broken)
        with self.assertRaisesRegex(RuntimeError, "no GPU matches"):
            session.assign_roles(session.inventory(observation()), {"impossible": {"min_vram_mb": 50000}})

    def test_sequence_check_expands_roles_without_starting_a_run(self):
        manifest = {"schema": 2, "hardware_roles": {"main": {"min_vram_mb": 20000}},
                    "defaults": {"state": "ready", "timeout_s": 10},
                    "cases": [{"id": "one", "gpus": ["{gpu:main}"],
                               "command": ["true", "{uuid:main}"]}]}
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "manifest.json"
            path.write_text(json.dumps(manifest))
            output = io.StringIO()
            with (patch.object(sys, "argv", ["sequence", str(path), "--run-id", "check", "--check"]),
                  patch.object(sequence.benchmark_session, "scan", return_value=session.inventory(observation())),
                  redirect_stdout(output)):
                self.assertEqual(sequence.main(), 0)
        result = json.loads(output.getvalue())
        self.assertEqual(result["stages"][0]["gpus"], [2])
        self.assertEqual(result["hardware_roles"]["main"]["uuid"], "GPU-large")


if __name__ == "__main__":
    unittest.main()
