import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "model_profiles", ROOT / "scripts" / "active" / "model_profiles.py"
)
MODEL_PROFILES = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODEL_PROFILES)


class ModelProfileTests(unittest.TestCase):
    def test_alias_inherits_canonical_fields_and_keeps_overrides(self):
        models = {
            "Canonical.gguf": {"system_prompt": "canonical", "runtime": {"ctx_size": 8192}},
            "short:1b": {"_alias_of": "Canonical.gguf", "system_prompt": "override"},
        }
        key, profile = MODEL_PROFILES.resolve_profile(models, "short:1b")
        self.assertEqual(key, "short:1b")
        self.assertEqual(profile["system_prompt"], "override")
        self.assertEqual(profile["runtime"]["ctx_size"], 8192)

    def test_alias_cycle_fails(self):
        with self.assertRaises(ValueError):
            MODEL_PROFILES.resolve_profile(
                {"a": {"_alias_of": "b"}, "b": {"_alias_of": "a"}}, "a"
            )


if __name__ == "__main__":
    unittest.main()
