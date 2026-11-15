"""Contract checks for the parameterized experiment compiler."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "integration"))
from compile_experiment import compile_experiment


def specimen():
    return {"schema": 3, "name": "paired-card", "hardware_roles": {"model": {"min_vram_mb": 20000}},
            "defaults": {"state": "ready", "timeout_s": 600, "env": {"COMMON": "same"}},
            "parameters": {"model": "model-id", "cap": 256},
            "template": {"kind": "paired_replay", "load_path": "experimental",
                         "experimental_reason": "custom saved-state replay engine",
                         "gpus": ["{gpu:model}", "${worker}"],
                         "command": ["python3", "replay.py", "${model}", "${cap}", "${case_id}"],
                         "env": {"WORKER": "${worker}"},
                         "outputs": ["results/${case_id}.json"]},
            "cases": [{"id": "a_before", "values": {"worker": "{gpu:pascal6}"}},
                      {"id": "b", "values": {"worker": "{gpu:pascal8}"},
                       "stage": {"baseline": "a_before", "env": {"LEG": "b"}}},
                      {"id": "a_after", "values": {"worker": "{gpu:pascal6}"},
                       "stage": {"baseline": "a_before"}}]}


def compile_data(data):
    return compile_experiment(data, json.dumps(data, sort_keys=True).encode())


def test_compiles_ordered_aba_with_shared_settings_and_unresolved_hardware_roles():
    result = compile_data(specimen())
    cases = result["cases"]
    assert result["schema"] == 2
    assert [case["id"] for case in cases] == ["a_before", "b", "a_after"]
    assert cases[1]["command"] == ["python3", "replay.py", "model-id", "256", "b"]
    assert cases[1]["gpus"] == ["{gpu:model}", "{gpu:pascal8}"]
    assert cases[1]["env"] == {"COMMON": "same", "WORKER": "{gpu:pascal8}", "LEG": "b"}
    assert cases[1]["baseline"] == "a_before"
    assert cases[1]["load_path"] == "experimental"
    assert cases[1]["case_values"] == {"worker": "{gpu:pascal8}"}


@pytest.mark.parametrize("change", [
    lambda data: data["cases"][1].update(id="a_before"),
    lambda data: data["cases"][0].update(stage={"baseline": "b"}),
    lambda data: data["template"].update(kind="unknown"),
    lambda data: data["template"].update(experimental_reason=""),
    lambda data: data["template"].update(load_path="unknown"),
    lambda data: data["template"].update(gpus=[]),
    lambda data: data["template"]["command"].append("${missing}"),
])
def test_rejects_invalid_case_or_comparison(change):
    data = specimen()
    change(data)
    with pytest.raises(ValueError):
        compile_data(data)


def test_source_change_changes_compiled_digest():
    before = specimen()
    after = specimen()
    after["parameters"]["cap"] = 160
    assert compile_data(before)["source_sha256"] != compile_data(after)["source_sha256"]


def test_managed_load_does_not_require_direct_card_roles():
    data = specimen()
    data["template"]["load_path"] = "managed"
    data["template"].pop("experimental_reason")
    data["template"].pop("gpus")
    assert compile_data(data)["cases"][0]["load_path"] == "managed"
