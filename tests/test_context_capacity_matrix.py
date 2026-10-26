import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "context_capacity_matrix", ROOT / "scripts" / "integration" / "run_context_capacity_matrix.py")
MATRIX = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MATRIX
SPEC.loader.exec_module(MATRIX)


def test_receipt_requires_both_depths_and_recall(tmp_path):
    path = tmp_path / "case.json"
    record = {"load": {"seconds": 7.5, "ctx_allocated": 16384},
              "depth_probes": [{"target_fraction": 0.1, "recall_ok": True},
                               {"target_fraction": 0.9, "recall_ok": True}]}
    path.write_text(json.dumps(record))
    good = MATRIX.result_from_receipt(path, 0)
    assert good["error"] is None and good["recall_ok"] and good["observed_ctx"] == 16384
    record["depth_probes"][1]["recall_ok"] = False
    path.write_text(json.dumps(record))
    assert "recall" in MATRIX.result_from_receipt(path, 0)["error"]
    record["depth_probes"] = record["depth_probes"][:1]
    path.write_text(json.dumps(record))
    assert "missing depth" in MATRIX.result_from_receipt(path, 0)["error"]


def test_checkpoint_resume_skips_completed_case(tmp_path, monkeypatch):
    manifest = {"id": "test-matrix", "hardware": {"brain": [0], "worker": [1],
                "power_caps_w": {"0": 350, "1": 100}}, "cases": [
                    {"id": "one", "model": "m", "target": "compact", "gpus": [1], "ctx": 8192},
                    {"id": "two", "model": "m", "target": "ceiling", "gpus": [0], "ctx": 16384}]}
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest))
    output = tmp_path / "output"
    calls = []
    monkeypatch.setattr(MATRIX, "hardware_check", lambda _: None)
    def run(case, _):
        calls.append(case["id"])
        return {"error": None, "recall_ok": True, "observed_ctx": case["ctx"],
                "load_seconds": 1, "returncode": 0, "receipt": "x", "log": "y"}
    monkeypatch.setattr(MATRIX, "run_case", run)
    monkeypatch.setattr(sys, "argv", ["matrix", "--manifest", str(manifest_path), "--output", str(output)])
    assert MATRIX.main() == 0
    assert calls == ["one", "two"]
    assert MATRIX.main() == 0
    assert calls == ["one", "two"]
    terminal = json.loads((output / "terminal.json").read_text())
    assert terminal["passed"] == 2 and terminal["failed"] == 0
    assert "16384" in (output / "SUMMARY.md").read_text()
