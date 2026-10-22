import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("suggest_p45", ROOT / "scripts" / "integration" / "suggest_p45.py")
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

V5 = {"config_id": "lm-eval-0.4.11-reasoning-extract-v5"}
V4 = {"config_id": "lm-eval-0.4.11-reasoning-extract-v4"}


def row(test_id, n, unreadable, runtime=V5, run="m_w_smoke_v1", run_at="2026-10-22T01:00:00Z"):
    return {"model": "m:9b", "suite": run, "status": "success", "test_id": test_id, "sample_count": n,
            "extractor_failure_count": unreadable, "runtime": runtime, "run_at": run_at}


class SuggestTests(unittest.TestCase):
    def suggest(self, rows, answers=None, profile=None, litmus=None, thinking_template=False):
        return MODULE.suggest("m:9b", "m_w_smoke_v1", {r["test_id"]: r for r in rows}, answers or {},
                              profile or {}, litmus or [], thinking_template)

    def test_clean_run_needs_nothing(self):
        out = self.suggest([row("bbh_flexible", 270, 3), row("drop_flexible", 10, 0)])
        self.assertTrue(out[0].startswith("NOTHING TO FIX"))

    def test_json_openers_point_at_the_system_prompt(self):
        out = self.suggest([row("drop_flexible", 10, 10)], {"drop": ["{"] * 8 + ["```json"] * 2},
                           {"system_prompt": "When JSON is requested, return raw JSON only."})
        self.assertEqual(len(out), 1)
        self.assertIn("SUGGEST system-prompt", out[0])
        self.assertIn("about output formats", out[0])

    def test_empty_answers_from_a_thinking_template(self):
        out = self.suggest([row("gsm8k_flexible", 10, 10)], {"gsm8k": [""] * 10}, thinking_template=True)
        self.assertIn("thinking-or-budget", out[0])
        self.assertIn("think by default", out[0])

    def test_unexplained_unreadable_asks_for_a_look(self):
        out = self.suggest([row("mmlu_pro_flexible", 140, 40)], {"mmlu_pro": ["The answer depends."] * 140})
        self.assertIn("no single answer shape explains it", out[0])

    def test_failed_litmus_with_fences(self):
        out = self.suggest([], litmus=[("json", "'```json\\n{\"name\": \"Alice\"}\\n```'")])
        self.assertIn("litmus json failed with a fenced answer", out[0])

    def test_rows_before_extract_v5_are_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            records = Path(tmp) / "records.jsonl"
            records.write_text("\n".join(json.dumps(r) for r in [
                row("drop_flexible", 10, 9, runtime=V4),           # v4: 9 was the rescued count
                row("bbh_flexible", 270, 2, run_at="2026-10-22T02:00:00Z"),
                row("bbh_flexible", 270, 100, run_at="2026-10-22T01:00:00Z"),  # older row of the same test
                row("drop_flexible", 10, 9, run="other_run"),
            ]) + "\n", encoding="utf-8")
            rows = MODULE.run_rows(records, "m:9b", "m_w_smoke_v1")
        self.assertEqual(sorted(rows), ["bbh_flexible"])
        self.assertEqual(rows["bbh_flexible"]["extractor_failure_count"], 2)

    def test_lane_runs_the_suggester_after_phase_4(self):
        lane = (ROOT / "scripts" / "integration" / "worker_lane.sh").read_text(encoding="utf-8")
        call = '"$HERE/suggest_p45.py"'
        self.assertIn(call, lane)
        self.assertLess(lane.index('say "Phase 4 smoke"'), lane.index(call))
        self.assertLess(lane.index(call), lane.index('LANE_STOP_AFTER:-}" = "4"'))


if __name__ == "__main__":
    unittest.main()
