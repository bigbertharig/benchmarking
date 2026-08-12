from __future__ import annotations

import json
import subprocess
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "docker" / "bench-geoimport" / "run_geoimport_benchmark.py"
CASES = ROOT / "docker" / "bench-geoimport" / "geoimport_cases.json"
PROMPT = ROOT / "docker" / "bench-geoimport" / "geoimport_system_prompt.md"


class MockGeoRuntimeHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path != "/v1/models":
            self.send_error(404)
            return
        self._send_json({"object": "list", "data": [{"id": "mock:geoimport"}]})

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/v1/chat/completions":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length))
        user = payload["messages"][-1]["content"]
        if "ASGS" in user:
            content = {
                "classification": "sidechain",
                "task_type": "country_admin_spine",
                "target_claim": "candidate_built",
                "rationale": "ASGS is internally nested but does not extend below LGA, so preserve it as a statistical sidechain and do not promote.",
                "next_actions": ["prepare candidate handoff for cloud review"],
            }
        else:
            content = {
                "claim": "blocked",
                "prep_state": "failed",
                "rationale": "the lightweight parent check failed, so the handoff is not ready for cloud QA",
                "missing_or_failed": ["parent check"],
                "next_actions": ["fix parent coverage", "rerun audit"],
            }
        self._send_json({"choices": [{"message": {"content": json.dumps(content)}}], "usage": {}})

    def _send_json(self, payload: dict) -> None:
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format: str, *args: object) -> None:
        return


class GeoImportSuiteTests(unittest.TestCase):
    def test_parser_accepts_first_valid_json_object(self) -> None:
        import importlib.util

        spec = importlib.util.spec_from_file_location("run_geoimport_benchmark", RUNNER)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        payload, valid = module.parse_json(
            '{"claim":"candidate_qa_failed","gate_state":"failed"}\n</think>\n'
            '{"claim":"candidate_qa_failed","gate_state":"failed"}'
        )

        self.assertTrue(valid)
        self.assertEqual(payload["claim"], "candidate_qa_failed")

    def test_thresholds_fail_low_average_or_low_case(self) -> None:
        import importlib.util

        spec = importlib.util.spec_from_file_location("run_geoimport_benchmark", RUNNER)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        cases_root = json.loads(CASES.read_text(encoding="utf-8"))
        passed, failures = module.classify_thresholds(
            cases_root,
            [
                {"test_id": "a", "status": "success", "score": 1.0},
                {"test_id": "b", "status": "success", "score": 0.5},
            ],
        )

        self.assertFalse(passed)
        self.assertTrue(any("below PARTIAL" in failure for failure in failures))

    def test_model_profile_alias_and_operator_override(self) -> None:
        import importlib.util

        spec = importlib.util.spec_from_file_location("run_geoimport_benchmark", RUNNER)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        with tempfile.TemporaryDirectory() as directory:
            profiles = Path(directory) / "profiles.json"
            profiles.write_text(
                json.dumps(
                    {
                        "models": {
                            "base.gguf": {
                                "system_prompt": "Return raw JSON.",
                                "inference": {"temperature": 0.0, "max_tokens": 700},
                            },
                            "alias:model": {"_alias_of": "base.gguf"},
                        }
                    }
                ),
                encoding="utf-8",
            )
            inference, system_prefix, source = module.load_run_profile(
                profiles,
                "alias:model",
                '{"max_tokens":900,"thinking":false}',
                False,
            )

        self.assertEqual(inference["temperature"], 0.0)
        self.assertEqual(inference["max_tokens"], 900)
        self.assertFalse(inference["thinking"])
        self.assertEqual(system_prefix, "Return raw JSON.")
        self.assertIn("alias:model->base.gguf", source)

    def test_scoring_requires_exact_claim_field_and_accepts_concept_alternatives(self) -> None:
        import importlib.util

        spec = importlib.util.spec_from_file_location("run_geoimport_benchmark", RUNNER)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        case = {
            "expected": {
                "claim_values": ["candidate_built"],
                "concept_groups": [["cloud qa", "orchestrator review"], ["checksum", "fingerprint"]],
            }
        }
        wrong_claim = module.score_case(
            case,
            json.dumps(
                {
                    "claim": "candidate_qa_passed",
                    "rationale": "candidate_built should be the local claim",
                    "next_actions": ["orchestrator review with candidate fingerprint"],
                }
            ),
        )

        self.assertFalse(wrong_claim["claim_matched"])
        self.assertEqual(wrong_claim["concept_groups_passed"], 2)

        structured_tokens = module.score_case(
            {"expected": {"concept_groups": [["candidate root"], ["cloud qa"], ["source count"]]}},
            json.dumps({"stages": ["isolate_candidate_root", "source_count"], "next": "cloud_qa"}),
        )
        self.assertEqual(structured_tokens["concept_groups_passed"], 3)

    def test_reviewable_prep_handoff_scores_as_candidate_built(self) -> None:
        import importlib.util

        spec = importlib.util.spec_from_file_location("run_geoimport_benchmark", RUNNER)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        cases_root = json.loads(CASES.read_text(encoding="utf-8"))
        case = cases_root["tasks"]["prep_handoff"]["cases"][1]
        result = module.score_case(
            case,
            json.dumps(
                {
                    "claim": "candidate_built",
                    "prep_state": "reviewable",
                    "rationale": (
                        "Preparation is complete under an isolated candidate root. The official source archive, "
                        "row counts and exclusions, metadata, schema checks, output checksums, and fingerprint "
                        "are recorded; this does not prove final QA."
                    ),
                    "missing_or_failed": [],
                    "next_actions": ["send handoff to cloud QA for orchestrator review"],
                }
            ),
        )

        self.assertEqual(result["score"], 1.0)

    def test_classification_smoke_records_and_summarizes(self) -> None:
        server = ThreadingHTTPServer(("127.0.0.1", 0), MockGeoRuntimeHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                results = root / "results"
                records = root / "records.jsonl"
                reference = root / "reference.md"
                scoreboard = root / "scoreboard.json"
                proc = subprocess.run(
                    [
                        "python3",
                        str(RUNNER),
                        "--model",
                        "mock:geoimport",
                        "--runtime-base",
                        f"http://127.0.0.1:{server.server_port}",
                        "--tasks",
                        "classification",
                        "--limit",
                        "1",
                        "--run-name",
                        "localhost_smoke",
                        "--run-class",
                        "smoke",
                        "--results-dir",
                        str(results),
                        "--scripts-dir",
                        str(ROOT),
                        "--cases-file",
                        str(CASES),
                        "--system-prompt-file",
                        str(PROMPT),
                        "--records",
                        str(records),
                        "--reference-output",
                        str(reference),
                        "--scoreboard-output",
                        str(scoreboard),
                    ],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )

                self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
                rows = [json.loads(line) for line in records.read_text(encoding="utf-8").splitlines()]
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]["schema_version"], 3)
                self.assertEqual(rows[0]["methodology"]["id"], "bench-geoimport/capability")
                self.assertEqual(rows[0]["methodology"]["version"], "2.0.0")
                self.assertEqual(rows[0]["status"], "success")
                self.assertEqual(rows[0]["test_id"], "geoimport_prep_classify_australia_asgs_v2")
                self.assertGreaterEqual(rows[0]["score"], 0.9)

                run_dir = results / "bench-geoimport_mock_geoimport_localhost_smoke"
                status = json.loads((run_dir / "status.json").read_text(encoding="utf-8"))
                summary = json.loads((run_dir / "final_summary.json").read_text(encoding="utf-8"))
                self.assertEqual(status["tasks"]["classification"]["state"], "completed")
                self.assertEqual(summary["successful_cases"], 1)
                self.assertEqual(summary["failed_cases"], 0)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
