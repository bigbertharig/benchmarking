import importlib.util
import sys
import unittest
from unittest import mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("capacity_run", ROOT / "scripts" / "integration" / "capacity_run.py")
CAP = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = CAP
SPEC.loader.exec_module(CAP)


class CapacityRunTests(unittest.TestCase):
    def test_fit_asks_for_the_largest_context_on_the_chosen_cards(self):
        args = CAP.fit_args("m:7b", [0, 1, 2], None, None)
        self.assertEqual(args, ["fit", "m:7b", "--use", "benchmark", "--profile", "default", "--json",
                                "--context-mode", "max", "--gpus", "0,1,2"])
        self.assertIn("--cards", CAP.fit_args("m:7b", None, 2, None))
        self.assertIn("--margin-mb", CAP.fit_args("m:7b", [0], None, 256))
        fixed = CAP.fit_args("m:7b", [0, 1], None, None, 131072)
        self.assertEqual(fixed[fixed.index("--ctx") + 1], "131072")
        self.assertNotIn("--context-mode", fixed)

    def test_load_is_a_benchmark_load_at_exactly_the_planned_context(self):
        args = CAP.load_args("m:7b", [0, 1], 226816, "capacity-m_7b", None)
        self.assertEqual(args[args.index("--ctx") + 1], "226816")
        self.assertEqual(args[args.index("--use") + 1], "benchmark")
        self.assertEqual(args[args.index("--profile") + 1], "default")
        self.assertEqual(args[args.index("--owner") + 1], "capacity-m_7b")

    def test_long_prompt_is_sized_to_the_target(self):
        self.assertEqual(CAP.repeats_for(10_000, 50, 100), 198)
        self.assertEqual(CAP.repeats_for(10, 50, 100), 1)

    def test_reference_depths_skip_what_the_loaded_context_cannot_hold(self):
        self.assertTrue(CAP.fits_depth(131072, 0.9, 126976, CAP.DECODE_TOKENS))
        self.assertFalse(CAP.fits_depth(131072, 0.9, 110000, CAP.DECODE_TOKENS))
        self.assertTrue(CAP.fits_depth(131072, 0.5, 110000, CAP.DECODE_TOKENS))

    def test_denied_fit_writes_a_terminal_capacity_receipt(self):
        with mock.patch.object(sys, "argv", ["capacity_run.py", "candidate", "--gpus", "0", "--ctx", "16384"]), \
             mock.patch.object(CAP, "rigctl", return_value=(4, {"error": {"message": "not approved for chat"}})), \
             mock.patch.object(CAP, "base_record", return_value={"kind": "capacity"}), \
             mock.patch.object(CAP, "write_record") as write:
            self.assertEqual(CAP.main(), 4)
        record = write.call_args.args[0]
        self.assertIs(record["fits"], False)
        self.assertEqual(record["error"], "not approved for chat")

    def test_failed_load_writes_a_terminal_capacity_receipt(self):
        plan = {"fits": True, "gpus": [0], "ctx": 16384}
        calls = [(0, plan), (1, {"error": {"message": "CUDA allocation failed"}}), (0, {})]
        with mock.patch.object(sys, "argv", ["capacity_run.py", "candidate", "--gpus", "0", "--ctx", "16384"]), \
             mock.patch.object(CAP, "rigctl", side_effect=calls), \
             mock.patch.object(CAP, "base_record", return_value={"kind": "capacity"}), \
             mock.patch.object(CAP, "write_record") as write:
            self.assertEqual(CAP.main(), 1)
        self.assertIn("CUDA allocation failed", write.call_args.args[0]["error"])

    def test_record_names_the_model_and_cards(self):
        self.assertEqual(CAP.slug("nemotron-3.5-bolt:74b-a9b"), "nemotron-3_5-bolt_74b-a9b")


if __name__ == "__main__":
    unittest.main()
