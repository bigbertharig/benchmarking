import importlib.util
import json
import subprocess
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = ROOT / "docker" / "bench-knowledge" / "run_knowledge_benchmark.py"
SPEC = importlib.util.spec_from_file_location("knowledge_runner", RUNNER_PATH)
KNOWLEDGE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(KNOWLEDGE)


class MockHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        self.rfile.read(length)
        body = json.dumps({"choices": [{"message": {"content": "B"}}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        return


class KnowledgeSuiteTests(unittest.TestCase):
    def test_answer_parser_handles_reasoning_wrappers(self):
        self.assertEqual(KNOWLEDGE.answer_letter("<think>work</think>\nB"), "B")
        self.assertEqual(KNOWLEDGE.answer_letter("Answer: C."), "C")
        self.assertEqual(KNOWLEDGE.answer_letter("I cannot decide"), "")

    def test_external_runtime_smoke_and_legacy_task_alias(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), MockHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                proc = subprocess.run(
                    [
                        "python3", str(RUNNER_PATH),
                        "--model", "qwen3-coder:30b-a3b",
                        "--runtime-base", f"http://127.0.0.1:{server.server_port}",
                        "--tasks", "mmlu", "--limit", "1",
                        "--run-name", "knowledge_unit", "--run-class", "smoke",
                        "--results-dir", temp_dir, "--scripts-dir", str(ROOT),
                        "--tuning-profiles", str(ROOT / "model_tuning_profiles.json"),
                        "--cases-file", str(ROOT / "docker" / "bench-knowledge" / "knowledge_cases.json"),
                        "--no-record",
                    ],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
                status_files = list(Path(temp_dir).glob("*/status.json"))
                self.assertEqual(len(status_files), 1)
                status = json.loads(status_files[0].read_text(encoding="utf-8"))
                self.assertEqual(status["tasks_requested"], ["academic"])
                self.assertEqual(status["tasks"]["academic"]["state"], "completed")
                self.assertEqual(status["tasks"]["academic"]["score"], 1.0)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
