from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AGENT_DIR = ROOT / "docker" / "bench-agent"
sys.path.insert(0, str(AGENT_DIR))

from agent_harness import (  # noqa: E402
    ToolExecutionError,
    ToolState,
    execute_tool,
    public_tool,
    run_case,
    validate_arguments,
)
from run_agent_benchmark import load_cases  # noqa: E402


CASES_PATH = AGENT_DIR / "agent_cases.json"


class AgentMockHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length))
        messages = payload["messages"]
        case_prompt = messages[1]["content"]
        tool_messages = [message for message in messages if message.get("role") == "tool"]

        if "agent_plan_sequence" in case_prompt:
            message = {"content": "Inspect the request, select a tool, execute it, then validate the observation."}
        elif "agent_no_tool_needed" in case_prompt:
            message = {"content": "NO TOOL NEEDED"}
        elif "agent_tool_recovery" in case_prompt:
            if not tool_messages:
                message = self._tool_call(
                    "unstable_lookup",
                    {"dataset": "climate", "metric": "temperature", "location": "CAN", "year": 2024},
                    "recovery-1",
                )
            elif len(tool_messages) == 1:
                message = self._tool_call(
                    "unstable_lookup",
                    {
                        "dataset": "climate",
                        "metric": "temperature",
                        "location": "CAN",
                        "year": 2024,
                        "retry_token": "retry-ok",
                    },
                    "recovery-2",
                )
            else:
                message = {"content": "Observed value: 12.5 celsius"}
        else:
            if not tool_messages:
                message = self._tool_call(
                    "lookup_metric",
                    {"dataset": "climate", "metric": "temperature", "location": "CAN", "year": 2024},
                    "lookup-1",
                )
            else:
                message = {"content": "Observed value: 12.5 celsius"}

        self._send({"choices": [{"message": message}]})

    @staticmethod
    def _tool_call(name: str, arguments: dict, call_id: str) -> dict:
        return {
            "content": None,
            "tool_calls": [
                {
                    "id": call_id,
                    "type": "function",
                    "function": {"name": name, "arguments": json.dumps(arguments)},
                }
            ],
        }

    def _send(self, payload: dict) -> None:
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format: str, *args: object) -> None:
        return


class AgentHarnessTests(unittest.TestCase):
    def test_public_tool_removes_executor_metadata(self) -> None:
        tool = {
            "type": "function",
            "x-executor": "lookup_metric",
            "x-arg-map": {"place": "location"},
            "function": {"name": "fetch", "parameters": {"type": "object"}},
        }
        self.assertEqual(set(public_tool(tool)), {"type", "function"})

    def test_schema_validation_rejects_missing_and_extra_arguments(self) -> None:
        schema = {
            "type": "object",
            "additionalProperties": False,
            "required": ["location"],
            "properties": {"location": {"type": "string"}},
        }
        errors = validate_arguments({"extra": 1}, schema)
        self.assertIn("missing required argument: location", errors)
        self.assertIn("unexpected argument: extra", errors)

    def test_argument_accuracy_is_scored_separately(self) -> None:
        case = {
            "expected": {
                "required_tools": ["lookup_metric"],
                "expected_arguments": {"lookup_metric": {"location": "USA"}},
                "final_contains": ["340000000"],
            }
        }
        from agent_harness import score_execution

        trace = {
            "final_text": "340000000",
            "calls": [
                {
                    "name": "lookup_metric",
                    "schema_valid": True,
                    "executed": True,
                    "error": "",
                    "parsed_arguments": {"location": "CAN"},
                }
            ],
        }
        scores = score_execution(case, trace)
        self.assertEqual(scores["argument_accuracy"], 0.0)
        self.assertEqual(scores["final_task_success"], 0.0)

    def test_artifact_executor_confines_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state = ToolState(sandbox=Path(directory))
            tool = {"x-executor": "write_artifact", "function": {"name": "write"}}
            with self.assertRaises(ToolExecutionError):
                execute_tool(tool, {"name": "../escape", "content": "bad"}, state)

    def test_mutated_argument_mapping_and_return_shape_execute(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state = ToolState(sandbox=Path(directory))
            tool = {
                "x-executor": "lookup_metric",
                "x-arg-map": {"place_code": "location"},
                "x-return-shape": "nested_result",
                "function": {"name": "fetch_indicator_v2"},
            }
            result = execute_tool(
                tool,
                {
                    "dataset": "climate",
                    "metric": "temperature",
                    "place_code": "CAN",
                    "year": 2024,
                },
                state,
            )
            self.assertEqual(result["result"]["payload"]["value"], 12.5)

    def test_all_agent_cases_are_cataloged(self) -> None:
        case_ids = {case["id"] for case in json.loads(CASES_PATH.read_text(encoding="utf-8"))["cases"]}
        catalog_ids = {
            test["id"]
            for test in json.loads((ROOT / "benchmark_catalog.json").read_text(encoding="utf-8"))["tests"]
        }
        self.assertEqual(case_ids - catalog_ids, set())

    def test_multiturn_execution_recovery_and_no_tool(self) -> None:
        server = ThreadingHTTPServer(("127.0.0.1", 0), AgentMockHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            cases = load_cases(
                CASES_PATH,
                ["agent_plan_sequence", "agent_tool_select", "agent_tool_recovery", "agent_no_tool_needed"],
                None,
            )
            with tempfile.TemporaryDirectory() as directory:
                traces = {
                    case["id"]: run_case(
                        case=case,
                        base_url=f"http://127.0.0.1:{server.server_port}",
                        model="mock:agent",
                        sandbox=Path(directory) / case["id"],
                        timeout=5,
                        max_steps=5,
                        max_tokens=256,
                    )
                    for case in cases
                }
            self.assertEqual(traces["agent_tool_select"]["scores"]["final_task_success"], 1.0)
            self.assertEqual(traces["agent_plan_sequence"]["scores"]["plan_correctness"], 1.0)
            self.assertNotIn("execution_success", traces["agent_plan_sequence"]["scores"])
            self.assertEqual(traces["agent_tool_recovery"]["scores"]["recovery_success"], 1.0)
            self.assertEqual(len(traces["agent_tool_recovery"]["calls"]), 2)
            self.assertEqual(traces["agent_no_tool_needed"]["calls"], [])
            self.assertEqual(traces["agent_no_tool_needed"]["scores"]["final_task_success"], 1.0)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_runner_cli_writes_summary(self) -> None:
        server = ThreadingHTTPServer(("127.0.0.1", 0), AgentMockHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as directory:
                proc = subprocess.run(
                    [
                        sys.executable,
                        str(AGENT_DIR / "run_agent_benchmark.py"),
                        "--model",
                        "mock:agent",
                        "--runtime-base",
                        f"http://127.0.0.1:{server.server_port}",
                        "--cases-file",
                        str(CASES_PATH),
                        "--cases",
                        "agent_plan_sequence,agent_tool_select,agent_tool_recovery,agent_no_tool_needed",
                        "--run-name",
                        "localhost_smoke",
                        "--hardware-id",
                        "localhost-mock",
                        "--run-class",
                        "smoke",
                        "--results-dir",
                        directory,
                        "--no-record",
                    ],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
                summary_path = Path(directory) / "bench-agent_mock_agent_localhost_smoke" / "summary.json"
                summary = json.loads(summary_path.read_text(encoding="utf-8"))
                self.assertEqual(summary["cases_completed"], 4)
                self.assertEqual(summary["harness_failures"], 0)
                self.assertEqual(len(summary["results"]), 4)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
