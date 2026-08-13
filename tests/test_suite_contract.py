import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "validate_suite_contract", ROOT / "scripts" / "active" / "validate_suite_contract.py"
)
VALIDATOR = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(VALIDATOR)


class SuiteContractTests(unittest.TestCase):
    def test_all_docker_suites_implement_registered_contract(self):
        errors = VALIDATOR.validate(
            ROOT / "docker", ROOT / "docker" / "suite_contracts.json"
        )
        self.assertEqual(errors, [], "\n".join(errors))


if __name__ == "__main__":
    unittest.main()
