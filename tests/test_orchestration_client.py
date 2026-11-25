"""Consumer contracts reject unavailable, incompatible or incomplete runtime evidence."""
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest

INTEGRATION = Path(__file__).resolve().parents[1] / "scripts/integration"
sys.path.insert(0, str(INTEGRATION))
import orchestration_client as client
import hardware_inventory

POWER = {"schema": "rig-power-check/1", "ok": True, "gpu_ids": [2],
         "checks": [{"gpu_id": 2, "actual_w": 100., "planned_w": 100., "matches": True}]}


def test_public_command_and_exact_gpu_evidence(monkeypatch):
    monkeypatch.setenv("BENCHMARK_ORCHESTRATION_COMMAND", '["site-rig"]')
    with patch.object(client.subprocess, "run", return_value=SimpleNamespace(returncode=0, stdout=json.dumps(POWER))) as run:
        hardware_inventory.check_planned_power([2])
    assert run.call_args.args[0] == ["site-rig", "inspect", "power", "--gpus", "2"]
    assert run.call_args.kwargs["timeout"] == 20
    assert not run.call_args.kwargs.get("shell")


@pytest.mark.parametrize("payload", [
    {**POWER, "schema": "rig-power-check/2"}, {**POWER, "ok": 1},
    {**POWER, "gpu_ids": [3]}, {**POWER, "checks": []},
    {**POWER, "checks": [{"gpu_id": 2, "actual_w": 80., "planned_w": 100., "matches": True}]},
    {**POWER, "checks": [{"gpu_id": 2, "actual_w": float("nan"), "planned_w": 100., "matches": True}]},
    {"schema": "rig-power-check/1", "ok": False, "kind": "unavailable", "error": "no telemetry"},
])
def test_invalid_or_failed_evidence_cannot_pass(payload):
    with patch.object(client.subprocess, "run", return_value=SimpleNamespace(returncode=0, stdout=json.dumps(payload))):
        with pytest.raises(RuntimeError):
            client.check_power([2])


@pytest.mark.parametrize("failure", [FileNotFoundError(), subprocess.TimeoutExpired("rig", 20)])
def test_unavailable_runtime_never_falls_back(failure):
    with patch.object(client.subprocess, "run", side_effect=failure) as run:
        with pytest.raises(RuntimeError, match="no fallback"):
            client.check_power([2])
    assert run.call_count == 1


@pytest.mark.parametrize("command", ['"rig"', '[]', '[42]', 'not-json'])
def test_malformed_command_never_executes(monkeypatch, command):
    monkeypatch.setenv("BENCHMARK_ORCHESTRATION_COMMAND", command)
    with patch.object(client.subprocess, "run") as run:
        with pytest.raises(RuntimeError, match="argv array"):
            client.check_power([2])
    run.assert_not_called()


def test_nonzero_success_and_malformed_json_are_rejected():
    for code, text in [(1, json.dumps(POWER)), (0, "not JSON")]:
        with patch.object(client.subprocess, "run", return_value=SimpleNamespace(returncode=code, stdout=text)):
            with pytest.raises(RuntimeError):
                client.check_power([2])


def test_configured_executable_roundtrip_and_path_spaces(tmp_path, monkeypatch):
    # The provider is an installed executable, not an imported repository module.
    server = tmp_path / "fake runtime.py"
    server.write_text("import sys,json\nassert sys.argv[1:4] == ['inspect','model-path','--path']\n"
                      "print(json.dumps({'schema':'rig-model-path/1','ok':True,"
                      "'requested_path':sys.argv[4],'resolved_path':'/runtime/model with spaces.gguf'}))\n")
    monkeypatch.setenv("BENCHMARK_ORCHESTRATION_COMMAND", json.dumps([sys.executable, str(server)]))
    assert client.resolve_model_path("/archive/model with spaces.gguf") == "/runtime/model with spaces.gguf"


def test_wrong_model_path_identity_is_rejected():
    packet = {"schema": "rig-model-path/1", "ok": True, "requested_path": "/wrong", "resolved_path": "/file"}
    with patch.object(client.subprocess, "run", return_value=SimpleNamespace(returncode=0, stdout=json.dumps(packet))):
        with pytest.raises(RuntimeError, match="identity"):
            client.resolve_model_path("/expected")


def test_registry_resolution_has_no_runtime_dependency(monkeypatch, capsys):
    import resolve_model
    monkeypatch.setattr(sys, "argv", ["resolve_model.py", "example"])
    monkeypatch.setattr(resolve_model.model_library, "resolve", lambda _: {"gguf_path": "/archive/model.gguf"})
    with patch.object(client.subprocess, "run") as run:
        assert resolve_model.main() == 0
    run.assert_not_called()
    assert "GGUF=/archive/model.gguf" in capsys.readouterr().out
