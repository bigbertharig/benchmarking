import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "active" / "extract_reasoning_results.py"
SPEC = importlib.util.spec_from_file_location("extract_reasoning_results", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class ReasoningResultTests(unittest.TestCase):
    def test_reasoning_image_has_ifeval_dependencies(self):
        dockerfile = (ROOT / "docker" / "bench-reasoning" / "Dockerfile").read_text()
        self.assertIn("langdetect==1.0.9", dockerfile)
        self.assertIn("immutabledict==4.2.1", dockerfile)

    def test_mmlu_fewshot_is_single_turn_for_template_portability(self):
        run_script = (ROOT / "docker" / "bench-reasoning" / "run.sh").read_text()
        self.assertIn('if [ "$TASK" = "mmlu_pro" ]', run_script)
        self.assertIn('CMD+=(--fewshot_as_multiturn false)', run_script)

    def test_direct_sample_count(self):
        data = {"n-samples": {"gsm8k": {"effective": 5, "original": 10}}}
        self.assertEqual(MODULE.sample_count_for("gsm8k", data), 5)

    def test_group_sample_count_sums_children(self):
        data = {
            "n-samples": {
                "bbh_one": {"effective": 5, "original": 250},
                "bbh_two": {"effective": 4, "original": 250},
            }
        }
        self.assertEqual(MODULE.sample_count_for("bbh", data), 9)

    def test_group_score_uses_group_block(self):
        data = {
            "n-samples": {
                "bbh_one": {"effective": 5},
                "bbh_two": {"effective": 5},
            },
            "groups": {"bbh": {"exact_match,get-answer": 0.8}},
            "results": {},
        }
        rows = MODULE.extract_rows("bbh", data)
        self.assertEqual(rows[0][0], "bbh")
        self.assertEqual(rows[0][1], 0.8)
        self.assertEqual(rows[0][7], 10)

    def test_missing_sample_count_fails(self):
        with self.assertRaisesRegex(ValueError, "missing sample count"):
            MODULE.sample_count_for("drop", {"n-samples": {}})

    def test_group_stderr_metric_is_not_a_score(self):
        data = {
            "n-samples": {"mmlu_pro_math": {"effective": 5}},
            "groups": {
                "mmlu_pro": {
                    "exact_match,custom-extract": 0.8,
                    "exact_match_stderr,custom-extract": 0.1,
                }
            },
        }
        rows = MODULE.extract_rows("mmlu_pro", data)
        self.assertEqual([row[0] for row in rows], ["mmlu_pro_exact_match_custom-extract"])


if __name__ == "__main__":
    unittest.main()
