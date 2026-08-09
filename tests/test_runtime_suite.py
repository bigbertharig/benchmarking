from __future__ import annotations

import json
import importlib.util
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest import mock
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SUITE = ROOT / "docker" / "bench-runtime"
RUNNER = SUITE / "run_runtime_benchmark.py"
CONFIG = SUITE / "runtime_cases.json"


def load_runner_module():
    spec = importlib.util.spec_from_file_location("bench_runtime_runner", RUNNER)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load runtime runner")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class RuntimeMockHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/v1/chat/completions":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        request = json.loads(self.rfile.read(length))
        if request.get("stream"):
            body = (
                'data: {"choices":[{"delta":{"role":"assistant"}}]}\n\n'
                'data: {"choices":[{"delta":{"content":"READY"}}]}\n\n'
                "data: [DONE]\n\n"
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        response = {
            "choices": [{"message": {"content": "OK"}}],
            "usage": {"prompt_tokens": 64, "completion_tokens": 8},
            "timings": {"prompt_per_second": 120.0, "predicted_per_second": 24.0},
        }
        body = json.dumps(response).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


class RuntimeSuiteTests(unittest.TestCase):
    def test_telemetry_ignores_failures_from_unrequested_gpus(self) -> None:
        runner = load_runner_module()
        completed = subprocess.CompletedProcess(
            args=["nvidia-smi"],
            returncode=15,
            stdout="0, 1024, 80.5\n4, 512, 35.0\n",
            stderr="Unable to determine the device handle for GPU1",
        )
        with mock.patch.object(runner.subprocess, "run", return_value=completed):
            rows = runner.telemetry_rows((0,))
        self.assertEqual(rows[0][1:], (1024.0, 80.5))

    def test_runtime_runner_mock_cli(self) -> None:
        server = ThreadingHTTPServer(("127.0.0.1", 0), RuntimeMockHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as directory:
                proc = subprocess.run(
                    [
                        sys.executable,
                        str(RUNNER),
                        "--model",
                        "mock:runtime",
                        "--runtime-base",
                        f"http://127.0.0.1:{server.server_port}",
                        "--config",
                        str(CONFIG),
                        "--run-name",
                        "localhost_smoke",
                        "--run-class",
                        "smoke",
                        "--hardware-id",
                        "localhost-mock",
                        "--results-dir",
                        directory,
                        "--no-record",
                    ],
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=30,
                )
                self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
                summary_path = Path(directory) / "bench-runtime_mock_runtime_localhost_smoke" / "summary.json"
                summary = json.loads(summary_path.read_text(encoding="utf-8"))
                self.assertEqual(summary["failures"], 0)
                self.assertEqual(summary["results"]["runtime_stability"]["score"], 1.0)
                self.assertGreaterEqual(summary["results"]["runtime_ttft"]["ttft_seconds"], 0.0)
                self.assertEqual(summary["results"]["runtime_throughput"]["generation_tps"], 24.0)
                self.assertEqual(summary["results"]["runtime_context_reliability"]["max_success_prompt_tokens"], 64)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
