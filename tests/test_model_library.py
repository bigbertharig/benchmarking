import copy
import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("model_library", ROOT / "scripts" / "active" / "model_library.py")
ML = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = ML
SPEC.loader.exec_module(ML)
sys.path.insert(0, str(ROOT / "scripts" / "active"))
from model_profiles import resolve_profile  # noqa: E402


class ModelLibraryTests(unittest.TestCase):
    def setUp(self):
        self.registry = ML.load_registry()
        self.roles = ML.load_roles()

    def test_sources_validate(self):
        self.assertEqual(ML.validate(self.registry, self.roles), [])

    def test_generated_files_match_registry(self):
        self.assertEqual(ML.generated_drift(self.registry), [])

    def test_every_id_and_alias_resolves_to_its_registry_profile(self):
        tuning = ML.export_tuning(self.registry)["models"]
        for mid, entry in self.registry["models"].items():
            for name in [mid, *entry.get("aliases", [])]:
                with self.subTest(name=name):
                    resolved = resolve_profile(tuning, name)
                    self.assertIsNotNone(resolved)
                    self.assertEqual(resolved[1]["system_prompt"], entry["profiles"]["default"]["system_prompt"])

    def test_named_profile_merges_runtime_over_default(self):
        r = ML.resolve("qwen3.6:27b", "interactive", self.registry)
        default = self.registry["models"]["qwen3.6:27b"]["profiles"]["default"]
        self.assertEqual(r["runtime"]["ctx_size"], 65536)
        self.assertEqual(r["runtime"]["n_gpu_layers"], default["runtime"]["n_gpu_layers"])
        self.assertEqual(r["system_prompt"], default["system_prompt"])
        self.assertEqual(r["tensor_split"], "4,1")

    def test_alias_lookup_returns_canonical_model(self):
        self.assertEqual(ML.resolve("qwen2.5:14b", registry=self.registry)["model"], "qwen2.5-coder:14b")

    def test_role_cannot_use_archived_model(self):
        roles = copy.deepcopy(self.roles)
        roles["roles"]["brain"]["model"] = "qwen3:8b"
        errors = ML.validate(self.registry, roles)
        self.assertTrue(any("roles may only use active models" in e for e in errors), errors)

    def test_remote_profile_needs_existing_profile(self):
        roles = copy.deepcopy(self.roles)
        roles["remote_profiles"][0]["profile"] = "missing"
        errors = ML.validate(self.registry, roles)
        self.assertTrue(any("has no profile missing" in e for e in errors), errors)

    def test_job_must_name_a_role(self):
        roles = copy.deepcopy(self.roles)
        roles["jobs"][0]["role"] = "nope"
        self.assertTrue(any("unknown role nope" in e for e in ML.validate(self.registry, roles)))

    def test_superseded_by_must_exist(self):
        registry = copy.deepcopy(self.registry)
        registry["models"]["qwen3:8b"]["superseded_by"] = "qwen9:1t"
        self.assertTrue(any("superseded_by qwen9:1t" in e for e in ML.validate(registry, self.roles)))

    def test_remote_profiles_flatten_settings_for_the_rig(self):
        profiles = ML.remote_profiles(self.roles, self.registry)
        chat = profiles["chat-27b"]
        self.assertEqual(chat["model"], "qwen3.6:27b")
        self.assertTrue(chat["gguf_path"].endswith("Qwen3.6-27B-Q4_K_M.gguf"))
        for key in ("ctx_size", "batch_size", "parallel", "extra_args", "gpus_needed"):
            self.assertIn(key, chat)

    def test_job_keywords_pick_a_role(self):
        self.assertEqual(ML.job_role("extract the json schema", self.roles)[1], "single_1060")
        self.assertIsNone(ML.job_role("zzz", self.roles))


if __name__ == "__main__":
    unittest.main()
