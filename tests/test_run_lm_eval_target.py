"""A single-task result must identify a registered model and explicit ready route."""

import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "active"))
from run_lm_eval_task import validate_run_target, write_run_context  # noqa: E402


def test_explicit_registered_target_and_receipt(tmp_path):
    registry = tmp_path / "model_registry.json"
    registry.write_text(json.dumps({"models": {"canonical:7b": {}}}), encoding="utf-8")
    (tmp_path / "tool_catalog.json").write_text(json.dumps({"source_sha256": "catalog-hash"}), encoding="utf-8")
    args = "model=profile/ready-7b,base_url=http://127.0.0.1:11434/v1/chat/completions,api_key=secret"

    route, url = validate_run_target(tmp_path, "canonical:7b", args)
    write_run_context(tmp_path, tmp_path, canonical_model="canonical:7b", route=route,
                      base_url=url, test_id="gsm8k", backend="local-chat-completions")
    receipt = json.loads((tmp_path / "run_context.json").read_text(encoding="utf-8"))
    assert receipt["canonical_model_id"] == "canonical:7b"
    assert receipt["served_route"] == "profile/ready-7b"
    assert receipt["model_registry_sha256"] == hashlib.sha256(registry.read_bytes()).hexdigest()
    assert receipt["tool_catalog_source_sha256"] == "catalog-hash"
    assert "secret" not in json.dumps(receipt)


def test_missing_or_unknown_target_is_rejected(tmp_path):
    (tmp_path / "model_registry.json").write_text('{"models":{"canonical:7b":{}}}', encoding="utf-8")
    with pytest.raises(SystemExit, match="Unknown canonical model"):
        validate_run_target(tmp_path, "other", "model=ready,base_url=http://localhost/v1")
    with pytest.raises(SystemExit, match="explicit model"):
        validate_run_target(tmp_path, "canonical:7b", "model=ready")
