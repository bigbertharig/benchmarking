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
ACTIVE = ROOT / "scripts" / "active"
ROUTING = ROOT / "docker" / "bench-routing"
sys.path.insert(0, str(ACTIVE))
sys.path.insert(0, str(ROUTING))

from build_pareto_frontier import build_frontiers, build_points  # noqa: E402
from routing_score import index_tiers, score_route  # noqa: E402


ROUTING_CONFIG = ROUTING / "routing_cases.json"


def benchmark_record(run_id: str, model: str, score: float, costs: dict) -> dict:
    return {
        "schema_version": 2,
        "run_id": run_id,
        "run_at": f"2026-01-0{len(run_id)}T00:00:00Z",
        "model": model,
        "test_id": "agent_tool_select",
        "status": "success",
        "run_class": "validated",
        "sample_count": 10,
        "score": score,
        "score_pct": score * 100,
        "metric": "accuracy",
        "raw_harness_score": score,
        "normalized_answer_score": score,
        "format_compatibility": "compatible",
        "extractor_failure_count": 0,
        "harness": "test",
        "suite": "unit",
        "runtime": {"runtime_id": "runtime", "config_id": run_id},
        "efficiency": costs,
        "failure": {},
        "notes": "",
    }


class RoutingMockHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        json.loads(self.rfile.read(length))
        content = json.dumps({"route": "tiny_worker", "reason": "cheapest sufficient route"})
        encoded = json.dumps({"choices": [{"message": {"content": content}}]}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format: str, *args: object) -> None:
        return


class RoutingParetoTests(unittest.TestCase):
    def test_routing_penalizes_overprovision_and_rejects_undercapacity(self) -> None:
        config = json.loads(ROUTING_CONFIG.read_text(encoding="utf-8"))
        tiers = index_tiers(config)
        tiny_case = {"id": "tiny", "minimum_tier": "tiny_worker"}
        hard_case = {"id": "hard", "minimum_tier": "brain_model"}
        over = score_route(tiny_case, "brain_model", tiers)
        under = score_route(hard_case, "single_worker", tiers)
        self.assertEqual(over["task_success"], 1.0)
        self.assertAlmostEqual(over["routing_efficiency"], 1 / 12)
        self.assertEqual(under["routing_value"], 0.0)

    def test_human_required_case_cannot_be_automated(self) -> None:
        config = json.loads(ROUTING_CONFIG.read_text(encoding="utf-8"))
        tiers = index_tiers(config)
        case = {"id": "unsafe", "minimum_tier": "human_escalation", "requires_human": True}
        self.assertEqual(score_route(case, "brain_model", tiers)["task_success"], 0.0)
        self.assertEqual(score_route(case, "human_escalation", tiers)["routing_value"], 1.0)

    def test_pareto_builder_removes_only_dominated_comparable_points(self) -> None:
        rows = [
            benchmark_record("a", "model-a", 0.8, {"wall_time_seconds": 10, "peak_vram_mb": 100}),
            benchmark_record("bb", "model-b", 0.7, {"wall_time_seconds": 12, "peak_vram_mb": 120}),
            benchmark_record("ccc", "model-c", 0.9, {"wall_time_seconds": 20, "peak_vram_mb": 100}),
            benchmark_record("dddd", "model-d", 0.95, {"ttft_seconds": 1}),
        ]
        points, diagnostics = build_points(rows)
        frontiers = build_frontiers(points)
        self.assertEqual(diagnostics["missing_cost_records"], 0)
        grouped = {tuple(frontier["cost_dimensions"]): frontier for frontier in frontiers}
        main_ids = {point["run_id"] for point in grouped[("peak_vram_mb", "wall_time_seconds")]["frontier"]}
        self.assertEqual(main_ids, {"a", "ccc"})
        self.assertEqual(grouped[("ttft_seconds",)]["frontier_count"], 1)

    def test_routing_runner_cli_smoke(self) -> None:
        server = ThreadingHTTPServer(("127.0.0.1", 0), RoutingMockHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as directory:
                proc = subprocess.run(
                    [
                        sys.executable,
                        str(ROUTING / "run_routing_benchmark.py"),
                        "--model",
                        "mock:routing",
                        "--runtime-base",
                        f"http://127.0.0.1:{server.server_port}",
                        "--config",
                        str(ROUTING_CONFIG),
                        "--limit",
                        "2",
                        "--run-name",
                        "localhost_smoke",
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
                summary_path = Path(directory) / "bench-routing_mock_routing_localhost_smoke" / "summary.json"
                summary = json.loads(summary_path.read_text(encoding="utf-8"))
                self.assertEqual(summary["case_count"], 2)
                self.assertEqual(summary["scores"]["routing_value"], 1.0)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
