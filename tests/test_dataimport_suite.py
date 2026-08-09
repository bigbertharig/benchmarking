from __future__ import annotations

import json
import subprocess
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SUITE = ROOT / "docker" / "bench-dataimport" / "run.sh"
CASES = ROOT / "docker" / "bench-dataimport" / "dataimport_cases.json"
PROMPT = ROOT / "docker" / "bench-dataimport" / "dataimport_system_prompt.md"


class MockRuntimeHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path != "/v1/models":
            self.send_error(404)
            return
        self._send_json({"object": "list", "data": [{"id": "mock:dataimport"}]})

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/v1/chat/completions":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        json.loads(self.rfile.read(length))
        content = json.dumps(
            {
                "loc_id_column": "iso_code",
                "loc_id_format": "ISO3",
                "geographic_level": "admin_0",
            }
        )
        self._send_json(
            {
                "choices": [{"message": {"content": content}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 10},
            }
        )

    def _send_json(self, payload: dict) -> None:
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format: str, *args: object) -> None:
        return


class DataImportSuiteTests(unittest.TestCase):
    def test_schema_smoke_records_and_summarizes(self) -> None:
        server = ThreadingHTTPServer(("127.0.0.1", 0), MockRuntimeHandler)
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
                        "bash",
                        str(SUITE),
                        "--model",
                        "mock:dataimport",
                        "--runtime-base",
                        f"http://127.0.0.1:{server.server_port}",
                        "--tasks",
                        "schema_understanding",
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
                self.assertEqual(rows[0]["methodology"]["id"], "bench-dataimport/capability")
                self.assertEqual(rows[0]["status"], "success")
                self.assertEqual(rows[0]["run_class"], "smoke")
                self.assertEqual(rows[0]["test_id"], "dataimport_schema_loc_id")
                self.assertEqual(rows[0]["score"], 1.0)

                run_dir = results / "bench-dataimport_mock_dataimport_localhost_smoke"
                status = json.loads((run_dir / "status.json").read_text(encoding="utf-8"))
                summary = json.loads((run_dir / "final_summary.json").read_text(encoding="utf-8"))
                self.assertEqual(status["tasks"]["schema_understanding"]["state"], "completed")
                self.assertEqual(summary["successful_cases"], 1)
                self.assertEqual(summary["failed_cases"], 0)
                self.assertTrue(reference.exists())
                self.assertTrue(scoreboard.exists())
                self.assertTrue((scoreboard.parent / "model_methodology_history.json").exists())
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
