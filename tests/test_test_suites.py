"""Named test suites stay valid and cover every Benchmarking test module."""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "tests" / "suites.json"


def test_named_suites_reference_existing_unique_test_modules():
    suites = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert suites
    for name, details in suites.items():
        assert name.isidentifier()
        assert isinstance(details.get("purpose"), str) and details["purpose"]
        tests = details.get("tests")
        assert isinstance(tests, list) and tests
        assert len(tests) == len(set(tests))
        for selector in tests:
            assert selector.startswith("tests/test_") and selector.endswith(".py")
            assert ".." not in selector
            assert (ROOT / selector).is_file()


def test_every_benchmarking_test_module_belongs_to_a_named_suite():
    suites = json.loads(MANIFEST.read_text(encoding="utf-8"))
    covered = {selector for details in suites.values() for selector in details["tests"]}
    present = {path.relative_to(ROOT).as_posix() for path in (ROOT / "tests").glob("test_*.py")}
    assert covered == present
