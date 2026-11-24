import importlib.util
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/integration/shared_kv_capacity_probe.py"
SPEC = importlib.util.spec_from_file_location("shared_kv_capacity_probe", SCRIPT)
probe = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(probe)


class SharedKvCapacityProbeTests(unittest.TestCase):
    def test_fit_line_recovers_fixed_and_per_token_cost(self):
        rows = [
            {"context_cap": 16384, "worker_allocation_mib": 132},
            {"context_cap": 65536, "worker_allocation_mib": 516},
            {"context_cap": 262144, "worker_allocation_mib": 2052},
        ]

        result = probe.fit_line(rows)

        self.assertAlmostEqual(result["fixed_mib"], 4.0, places=3)
        self.assertAlmostEqual(result["mib_per_token"], 1 / 128, places=7)
        self.assertEqual(result["mib_at_262144"], 2052)
        self.assertEqual(result["max_absolute_error_mib"], 0.0)

    def test_parse_ints_rejects_duplicates(self):
        with self.assertRaises(Exception):
            probe.parse_ints("1,1")


if __name__ == "__main__":
    unittest.main()
