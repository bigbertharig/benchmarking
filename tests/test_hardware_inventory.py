import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1] / "scripts" / "integration"
sys.path.insert(0, str(ROOT))
import hardware_inventory as hw  # noqa: E402


class InventoryTests(unittest.TestCase):
    def test_uuid_selection_uses_reported_ids_not_cuda_ordinals(self):
        output = ("0, GPU-first, RTX 3090, 24564, 19, 350.00\n"
                  "2, GPU-third, GTX 1070, 8192, 6, 151.00\n"
                  "6, GPU-seventh, GTX 1060, 6144, 4, 100.00\n")
        with patch.object(hw.subprocess, "run", return_value=SimpleNamespace(stdout=output)):
            cards = hw.scan_cards()
        self.assertEqual(hw.docker_devices([0, 2], cards),
                         '"device=GPU-first,GPU-third"')
        self.assertEqual(hw.docker_devices([0, 2, 6], cards),
                         '"device=GPU-first,GPU-third,GPU-seventh"')
        with self.assertRaisesRegex(RuntimeError, "absent"):
            hw.require_ids([5], cards)


if __name__ == "__main__":
    unittest.main()
