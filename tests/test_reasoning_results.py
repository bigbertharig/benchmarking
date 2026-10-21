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


def _mc(target, response, strict=0):
    return {"target": target, "resps": [[response]], "exact_match": strict,
            "filtered_resps": [target if strict else "[invalid]"]}


def _drop(golds, response, strict=0):
    return {"doc": {"answers": golds}, "resps": [[response]], "em": strict}


class FlexibleScoringTests(unittest.TestCase):
    def test_bbh_accepts_correct_answers_without_the_phrase(self):
        samples = [
            _bbh("(D)", "(D)"),
            _bbh("(C)", '{"answer": "(C)"}'),
            _bbh("(B)", "Step one.\nStep two.\nSo the answer is **(B)**."),
            _bbh("True", "Working through it.\nTrue"),
            _bbh("(C)", "kniggt is not a word.\nAbove the above, answer is (C)."),
            _bbh("No", "Since Michaela lies, Elanor lies.\nTherefore, Elanor does not tell the truth. Answer: No."),
            _bbh("(A)", "The praise is sincere.\nTherefore, the sarcastic statement is (A)."),
            _bbh("(D)", "So the answer is (D) kite."),
            _bbh("(A)", "So the answer is (A).", strict=1),
        ]
        score, rescued, unreadable = MODULE.bbh_flexible(samples)
        self.assertEqual(score, 1.0)
        self.assertEqual((rescued, unreadable), (8, 0))

    def test_bbh_rejects_wrong_or_missing_answers(self):
        samples = [
            _bbh("(A)", "(B)"),
            _bbh("(A)", "Options are (A) owl, (B) raven. The leftmost bird is"),
            _bbh("valid", "invalid"),
            _bbh("(K)", "Two pairs of equal adjacent sides.\n\nAnswer: (D) kite"),
            _bbh("(Q)", "The cup is first, so to its right is the purple mug.\n\nAnswer: ("),
        ]
        score, rescued, unreadable = MODULE.bbh_flexible(samples)
        self.assertEqual((score, rescued), (0.0, 0))

    def test_drop_accepts_lead_ins_and_fuller_answers(self):
        samples = [
            _drop([["3"], ["2"]], "So the answer is 3"),
            _drop([["Raiders"]], "So the answer is the Raiders"),
            _drop([["2"]], "Sebastian Janikowski scored 2 field goals (33-yard and 30-yard)."),
            _drop([["2"]], "Sebastian Janikowski made two field goals."),
            _drop([["Chaz Schilens"]], "Chaz Schilens", strict=1),
        ]
        score, rescued, unreadable = MODULE.drop_flexible(samples)
        self.assertEqual(score, 1.0)
        self.assertEqual((rescued, unreadable), (4, 0))

    def test_drop_needs_every_span_and_whole_tokens(self):
        samples = [
            _drop([["Russell", "Schilens"]], "JaMarcus Russell threw it"),
            _drop([["2"]], "He kicked 24 yards"),
            _drop([["Raiders"]], "The Texans won"),
        ]
        score, rescued, unreadable = MODULE.drop_flexible(samples)
        self.assertEqual((score, rescued, unreadable), (0.0, 0, 0))   # wrong, but readable

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
        self.assertEqual(flexible[6], 0)     # unreadable answers (extractor failures)
        self.assertEqual(flexible[8], "rescued 1; unreadable 0")
        self.assertEqual(rows["drop_em"][1], 0.5)

    def test_unreadable_answers_are_counted_not_just_scored_wrong(self):
        _, _, bbh_unread = MODULE.bbh_flexible([_bbh("(A)", ""), _bbh("(A)", "{"), _bbh("(A)", "(B)")])
        self.assertEqual(bbh_unread, 2)       # empty and a bare JSON opener; "(B)" is readable, just wrong
        _, _, drop_unread = MODULE.drop_flexible([_drop([["3"]], "```json"), _drop([["3"]], "{"), _drop([["3"]], "4")])
        self.assertEqual(drop_unread, 2)
        self.assertEqual(MODULE.gsm8k_unreadable([{"resps": [["no idea"]]}, {"resps": [["#### 18"]]}]), 1)
        per_filter = [{"doc_id": 0, "filter": f, "resps": [["no idea"]]} for f in ("strict-match", "flexible-extract")]
        self.assertEqual(MODULE.gsm8k_unreadable(per_filter), 1)

    def test_mmlu_pro_reads_letters_however_they_are_written(self):
        samples = [
            _mc("E", "E"), _mc("H", "(H)."), _mc("B", "Answer: B"), _mc("C", '{"answer": "C"}'),
            _mc("D", "Option two is wrong.\nThe correct choice is (D)."), _mc("A", "So the answer is (A).", strict=1),
            _mc("A", "So the answer is (H)."),     # readable, wrong
            _mc("A", ""),                           # unreadable
        ]
        score, rescued, unreadable = MODULE.mmlu_pro_flexible(samples)
        self.assertEqual((round(score, 3), rescued, unreadable), (0.75, 5, 1))

    def test_fenced_json_answers_are_read(self):
        fenced = '```json\n{\n  "answer": "(C)"\n}\n```'
        score, rescued, _ = MODULE.bbh_flexible([_bbh("(C)", fenced), _bbh("(K)", '{"color": "teal", "option": "K"}')])
        self.assertEqual((score, rescued), (1.0, 2))
        score, _, _ = MODULE.mmlu_pro_flexible([_mc("D", '```json\n{"choice": "D"}\n```')])
        self.assertEqual(score, 1.0)

    def test_mmlu_pro_flexible_row_sits_beside_the_strict_row(self):
        data = {"n-samples": {"mmlu_pro_math": {"effective": 2}},
                "groups": {"mmlu_pro": {"exact_match,custom-extract": 0.5}}}
        rows = {r[0]: r for r in MODULE.extract_rows("mmlu_pro", data, [_mc("E", "E"), _mc("B", "So the answer is (B).", strict=1)])}
        self.assertEqual(sorted(rows), ["mmlu_pro_exact_match_custom-extract", "mmlu_pro_flexible"])
        self.assertEqual(rows["mmlu_pro_flexible"][1], 1.0)

    def test_no_samples_means_no_flexible_row(self):
        data = {"n-samples": {"drop": {"effective": 2}}, "results": {"drop": {"em,none": 0.5}}}
        self.assertEqual([r[0] for r in MODULE.extract_rows("drop", data)], ["drop_em"])

    def test_run_script_keeps_samples_for_flexible_tasks(self):
        run_script = (ROOT / "docker" / "bench-reasoning" / "run.sh").read_text()
        self.assertIn('[ "$TASK" = "bbh" ] || [ "$TASK" = "drop" ]', run_script)
        self.assertIn('[ "$TASK" = "mmlu_pro" ] || [ "$TASK" = "gsm8k" ]', run_script)
        self.assertIn('lm-eval-0.4.11-reasoning-extract-v5', run_script)

    def test_bbh_stop_is_next_question_not_any_capital_q(self):
        run_script = (ROOT / "docker" / "bench-reasoning" / "run.sh").read_text()
        self.assertIn("""src.replace('    - "Q"\\n', '    - "\\\\nQ:"\\n', 1)""", run_script)

    def test_bbh_keeps_its_1024_output_budget(self):
        run_script = (ROOT / "docker" / "bench-reasoning" / "run.sh").read_text()
        self.assertNotIn('replace("max_gen_toks: 1024", "max_gen_toks: 512")', run_script)


def _cache_block(suite):
    text = (ROOT / "docker" / suite / "run.sh").read_text()
    start = text.index("# --- Persistent download cache ---")
    end = text.index('echo "Hugging Face unreachable', start)
    return text[start:end]


class DownloadCacheTests(unittest.TestCase):
    def test_downloading_suites_share_one_cache_block(self):
        self.assertEqual(_cache_block("bench-reasoning"), _cache_block("bench-code"))

    def test_cache_covers_every_runtime_download(self):
        block = _cache_block("bench-reasoning")
        for var in ("HF_HOME", "HF_DATASETS_CACHE", "XDG_CACHE_HOME", "NLTK_DATA", "HF_HUB_OFFLINE"):
            self.assertIn(var, block)


if __name__ == "__main__":
    unittest.main()
