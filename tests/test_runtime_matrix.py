from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ACTIVE = ROOT / "scripts" / "active"
sys.path.insert(0, str(ACTIVE))

from build_runtime_matrix_campaign import build_campaign  # noqa: E402
from run_local_custom_task import build_chat_payload, normalize_inference_config  # noqa: E402


MATRIX_PATH = ROOT / "runtime_matrices" / "qwen35_4b_structured_worker_matrix.json"
CAMPAIGN_PATH = ROOT / "campaigns" / "qwen35_4b_structured_worker_matrix.json"


class RuntimeMatrixTests(unittest.TestCase):
    def test_checked_in_campaign_matches_deterministic_builder(self) -> None:
        spec = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
        expected = json.loads(CAMPAIGN_PATH.read_text(encoding="utf-8"))
        generated = build_campaign(spec)
        self.assertEqual(generated, expected)
        self.assertEqual(len(generated["blocks"]), 9)
        for index, block in enumerate(generated["blocks"]):
            expected_dependency = [] if index == 0 else [generated["blocks"][index - 1]["id"]]
            self.assertEqual(block["depends_on"], expected_dependency)

    def test_profiles_have_distinct_stable_configuration_hashes(self) -> None:
        spec = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
        blocks = build_campaign(spec)["blocks"]
        hashes = {block["config_hash"] for block in blocks}
        self.assertEqual(len(hashes), len(blocks))
        for block in blocks:
            self.assertRegex(block["config_hash"], r"^[0-9a-f]{64}$")
            config_arg = block["suite_args"][block["suite_args"].index("--config-json") + 1]
            self.assertEqual(json.loads(config_arg)["profile"], block["matrix_profile"])

    def test_unknown_matrix_axis_fails_preflight(self) -> None:
        spec = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
        spec["profiles"] = [{"id": "bad", "overrides": {"runtime": {"magic": True}}}]
        with self.assertRaisesRegex(ValueError, "unknown runtime settings"):
            build_campaign(spec)

    def test_request_payload_applies_sampling_and_protocol_settings(self) -> None:
        config = normalize_inference_config(
            json.dumps(
                {
                    "temperature": 0.1,
                    "top_k": 10,
                    "top_p": 0.9,
                    "repeat_penalty": 1.05,
                    "thinking": False,
                    "json_grammar": True,
                    "system_prompt": "Return JSON only.",
                    "stop_sequences": ["END"],
                }
            )
        )
        payload = build_chat_payload("model:test", "do work", "ignored", config)
        self.assertEqual(payload["temperature"], 0.1)
        self.assertEqual(payload["top_k"], 10)
        self.assertEqual(payload["top_p"], 0.9)
        self.assertEqual(payload["repeat_penalty"], 1.05)
        self.assertEqual(payload["chat_template_kwargs"], {"enable_thinking": False})
        self.assertEqual(payload["response_format"], {"type": "json_object"})
        self.assertEqual(payload["stop"], ["END"])
        self.assertEqual(payload["messages"][0]["content"], "Return JSON only.")

    def test_builder_writes_no_implicit_cartesian_variants(self) -> None:
        spec = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
        campaign = build_campaign(spec)
        self.assertEqual(len(campaign["blocks"]), len(spec["profiles"]))


if __name__ == "__main__":
    unittest.main()
