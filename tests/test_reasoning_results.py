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


def _bbh(target, response, strict=0):
    return {"target": target, "resps": [[response]], "exact_match": strict}


def _drop(golds, response, strict=0):
    return {"doc": {"answers": golds}, "resps": [[response]], "em": strict}


class FlexibleScoringTests(unittest.TestCase):
    def test_bbh_accepts_correct_answers_without_the_phrase(self):
        samples = [
            _bbh("(D)", "(D)"),
            _bbh("(C)", '{"answer": "(C)"}'),
            _bbh("(B)", "Step one.\nStep two.\nSo the answer is **(B)**."),
            _bbh("True", "Working through it.\nTrue"),
            _bbh("(A)", "So the answer is (A).", strict=1),
        ]
        score, rescued = MODULE.bbh_flexible(samples)
        self.assertEqual(score, 1.0)
        self.assertEqual(rescued, 4)

    def test_bbh_rejects_wrong_or_missing_answers(self):
        samples = [
            _bbh("(A)", "(B)"),
            _bbh("(A)", "Options are (A) owl, (B) raven. The leftmost bird is"),
            _bbh("valid", "invalid"),
        ]
        score, rescued = MODULE.bbh_flexible(samples)
        self.assertEqual((score, rescued), (0.0, 0))

    def test_drop_accepts_lead_ins_and_fuller_answers(self):
        samples = [
            _drop([["3"], ["2"]], "So the answer is 3"),
            _drop([["Raiders"]], "So the answer is the Raiders"),
            _drop([["2"]], "Sebastian Janikowski scored 2 field goals (33-yard and 30-yard)."),
            _drop([["2"]], "Sebastian Janikowski made two field goals."),
            _drop([["Chaz Schilens"]], "Chaz Schilens", strict=1),
        ]
        score, rescued = MODULE.drop_flexible(samples)
        self.assertEqual(score, 1.0)
        self.assertEqual(rescued, 4)

    def test_drop_needs_every_span_and_whole_tokens(self):
        samples = [
            _drop([["Russell", "Schilens"]], "JaMarcus Russell threw it"),
            _drop([["2"]], "He kicked 24 yards"),
            _drop([["Raiders"]], "The Texans won"),
        ]
        score, rescued = MODULE.drop_flexible(samples)
        self.assertEqual((score, rescued), (0.0, 0))

    def test_flexible_rows_sit_beside_strict_rows(self):
        data = {
            "n-samples": {"drop": {"effective": 2}},
            "results": {"drop": {"em,none": 0.5, "f1,none": 0.6}},
        }
        samples = [_drop([["3"]], "3", strict=1), _drop([["29"]], "So the answer is 29")]
        rows = {row[0]: row for row in MODULE.extract_rows("drop", data, samples)}
        self.assertEqual(sorted(rows), ["drop_em", "drop_f1", "drop_flexible"])
        flexible = rows["drop_flexible"]
        self.assertEqual(flexible[1], 1.0)   # score
        self.assertEqual(flexible[3], 0.5)   # raw (strict) score
        self.assertEqual(flexible[6], 1)     # answers rescued
        self.assertEqual(rows["drop_em"][1], 0.5)

    def test_no_samples_means_no_flexible_row(self):
        data = {"n-samples": {"drop": {"effective": 2}}, "results": {"drop": {"em,none": 0.5}}}
        self.assertEqual([r[0] for r in MODULE.extract_rows("drop", data)], ["drop_em"])

    def test_run_script_keeps_samples_for_flexible_tasks(self):
        run_script = (ROOT / "docker" / "bench-reasoning" / "run.sh").read_text()
        self.assertIn('[ "$TASK" = "bbh" ] || [ "$TASK" = "drop" ]', run_script)


if __name__ == "__main__":
    unittest.main()
