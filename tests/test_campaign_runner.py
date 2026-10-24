import importlib.util
import json
import shlex
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = ROOT.parents[2] / "scripts" / "benchmarks" / "run_campaign.py"
SPEC = importlib.util.spec_from_file_location("benchmark_campaign_runner", RUNNER_PATH)
RUNNER = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = RUNNER
SPEC.loader.exec_module(RUNNER)
RUNNER.SHARED_ROOT = ROOT.parents[2]
RUNNER.BENCHMARKING_SCRIPTS = ROOT
RUNNER.TUNING_PROFILES_PATH = ROOT / "model_tuning_profiles.json"
RUNNER.SUITE_CONTRACTS_PATH = ROOT / "docker" / "suite_contracts.json"
RUNNER.load_suite_contracts()


def runtime(gpus=(0,), port=11434, profile="m-g0"):
    return RUNNER.Runtime(profile=profile, port=port, gpu_ids=list(gpus), ctx=16384)


class FakeLoad:
    """A finished `rigctl load-model --json` process."""

    def __init__(self, answer, returncode=0):
        self.answer, self.returncode = answer, returncode

    def poll(self):
        return self.returncode

    def communicate(self):
        return json.dumps(self.answer), ""


class CampaignRunnerTests(unittest.TestCase):
    def _patch(self, **replacements):
        originals = {name: getattr(RUNNER, name) for name in replacements}
        for name, value in replacements.items():
            setattr(RUNNER, name, value)
        self.addCleanup(lambda: [setattr(RUNNER, n, v) for n, v in originals.items()])

    def test_registry_drives_command_for_every_suite(self):
        for suite in sorted(RUNNER.SUPPORTED_SUITES):
            with self.subTest(suite=suite):
                config = {
                    "id": suite,
                    "model": "qwen3-coder:30b-a3b",
                    "gguf": "/tmp/model.gguf",
                    "suite": suite,
                    "suite_args": [],
                    "run_class": "smoke",
                    "_run_id": "unit",
                }
                block = RUNNER.BlockState(suite, config)
                command = RUNNER.build_suite_cmd(block, runtime())
                self.assertIn(suite, command)
                self.assertIn("--model", command)
                self.assertIn("--run-name", command)
                self.assertIn("--run-class", command)
                self.assertIn("--results-dir", command)
                self.assertIn("http://localhost:11434", command)
                self.assertNotIn("--gguf", command)
                self.assertIn("HOME=/tmp/benchmark-home", command)
                self.assertTrue(any(value.startswith("HF_HOME=") for value in command))

    def test_profile_alias_is_resolved_before_launch(self):
        profile = RUNNER._lookup_tuning("qwen3-coder:30b-a3b")
        self.assertIsNotNone(profile)
        self.assertTrue(profile["system_prompt"].strip())
        self.assertIn("ctx_size", profile["runtime"])

    def test_multi_gpu_suite_command_quotes_device_list(self):
        config = {
            "id": "runtime",
            "model": "ministral-3:14b",
            "gguf": "/tmp/model.gguf",
            "suite": "bench-runtime",
            "suite_args": [],
            "run_class": "smoke",
            "_run_id": "unit",
        }
        block = RUNNER.BlockState("runtime", config)
        command = RUNNER.build_suite_cmd(block, runtime((1, 3), 11435))
        index = command.index("--gpus")
        self.assertEqual(command[index + 1], '"device=1,3"')
        gpu_ids_index = command.index("--gpu-ids")
        self.assertEqual(command[gpu_ids_index + 1], "0,1")
        self.assertEqual(command[command.index("--hardware-id") + 1], "rig-gpu_1_3-gpu1-3")

    def test_single_gpu_runtime_telemetry_uses_container_gpu_zero(self):
        config = {
            "id": "runtime",
            "model": "ministral-3:3b",
            "gguf": "/tmp/model.gguf",
            "suite": "bench-runtime",
            "suite_args": [],
            "run_class": "smoke",
            "_run_id": "unit",
        }
        block = RUNNER.BlockState("runtime", config)
        command = RUNNER.build_suite_cmd(block, runtime((2,), 11436))
        gpu_ids_index = command.index("--gpu-ids")
        self.assertEqual(command[gpu_ids_index + 1], "0")

    # Placement: omitted (the manager picks), pinned cards, or the old slot names for pinned cards.

    def test_placement_is_pinned_cards_or_the_managers_choice(self):
        self.assertIsNone(RUNNER.block_gpus({}))
        self.assertEqual(RUNNER.block_gpus({"gpus": [3, 0, 1, 2]}), [0, 1, 2, 3])
        self.assertEqual(RUNNER.block_gpus({"placement": "brain"}), [0])
        self.assertEqual(RUNNER.block_gpus({"placement": "gpu_1_3"}), [1, 3])
        self.assertEqual(RUNNER.block_gpus({"placement": "gpu_4"}), [4])
        for gone in ("single", "split"):
            with self.assertRaises(ValueError) as raised:
                RUNNER.block_gpus({"placement": gone})
            self.assertIn("omit placement", str(raised.exception))

    def test_load_request_names_only_what_the_block_sets(self):
        block = RUNNER.BlockState("b", {"id": "b", "model": "nemotron-3.5-bolt:74b-a9b"})
        cmd = RUNNER.load_cmd(block, "campaign-run-1")
        remote = " ".join(cmd[cmd.index("python3"):])
        self.assertIn("load-model nemotron-3.5-bolt:74b-a9b --use benchmark --json --owner campaign-run-1", remote)
        self.assertIn("--wait 7200", remote)
        for absent in ("--gpus", "--ctx", "--args", "--profile"):
            self.assertNotIn(absent, remote)
        pinned = RUNNER.BlockState("p", {"id": "p", "model": "m", "gpus": [0, 1, 2, 3], "ctx_size": 8192,
                                         "runtime_args": ["--reasoning", "on"], "wait_s": -1})
        remote = " ".join(RUNNER.load_cmd(pinned, "o"))
        self.assertIn("--gpus 0,1,2,3", remote)
        self.assertIn("--ctx 8192", remote)
        self.assertIn("--wait forever", remote)
        self.assertIn(shlex.quote("--reasoning on"), remote)  # one argument for the remote shell

    def test_manager_answer_becomes_the_runtime(self):
        ok = FakeLoad({"state": "ready", "profile": "bolt-g0-1-2-3", "port": 11434, "gpus": [0, 1, 2, 3],
                       "ctx": 16384, "estimate": {"gguf_path": "/mnt/shared/models/b/Bolt-Q3.gguf"}})
        rt, gguf = RUNNER.finish_load(ok)
        self.assertEqual((rt.profile, rt.port, rt.gpu_ids, rt.ctx), ("bolt-g0-1-2-3", 11434, [0, 1, 2, 3], 16384))
        self.assertEqual(rt.container, "rig-remote-bolt-g0-1-2-3")
        self.assertEqual(gguf, "Bolt-Q3.gguf")
        refused = FakeLoad({"error": {"message": "busy: remote (ready)"}}, returncode=1)
        with self.assertRaises(RuntimeError) as raised:
            RUNNER.finish_load(refused)
        self.assertIn("busy: remote", str(raised.exception))

    # Scheduling

    def _common(self, **extra):
        return {"model": "qwen3-coder:30b-a3b", "gguf": "/tmp/model.gguf", "runtime_args": [],
                "suite_args": [], "run_class": "smoke", "_run_id": "unit", **extra}

    def _state(self, *blocks):
        return RUNNER.CampaignState(name="unit", run_id="unit", manifest_path="unit.json",
                                    blocks={b.block_id: b for b in blocks}, started_at=RUNNER.now_iso())

    def test_one_load_request_in_flight(self):
        a = RUNNER.BlockState("a", {**self._common(), "id": "a", "suite": "bench-pipeline"})
        b = RUNNER.BlockState("b", {**self._common(model="ministral-3:3b"), "id": "b", "suite": "bench-pipeline"})
        a.status = b.status = RUNNER.WAITING_GPU
        started = []
        self._patch(start_load=lambda block, owner: started.append((block.block_id, owner)) or object())
        sched = RUNNER.Scheduler(self._state(a, b))
        sched.try_start_load()
        sched.try_start_load()
        self.assertEqual(started, [("a", "campaign-unit")])
        self.assertEqual((a.status, b.status), (RUNNER.LOADING, RUNNER.WAITING_GPU))

    def test_refused_load_fails_the_block_with_the_managers_reason(self):
        block = RUNNER.BlockState("a", {**self._common(), "id": "a", "suite": "bench-pipeline"})
        sched = RUNNER.Scheduler(self._state(block))
        block.status, sched.loading_block = RUNNER.LOADING, "a"
        sched.load_proc = FakeLoad({"error": {"message": "won't fit on GPU [1]"}}, returncode=4)
        sched.check_load_complete()
        self.assertEqual(block.status, RUNNER.FAILED)
        self.assertIn("won't fit", block.error)
        self.assertIsNone(sched.loading_block)

    def test_runtime_group_reuses_runtime_for_next_suite(self):
        common = self._common(runtime_group="model-a")
        first = RUNNER.BlockState("first", {**common, "id": "first", "suite": "bench-pipeline"})
        second = RUNNER.BlockState("second", {**common, "id": "second", "suite": "bench-knowledge"})
        scheduler = RUNNER.Scheduler(self._state(first, second), dry_run=True)
        first.status = RUNNER.COMPLETED
        first.runtime = runtime()
        self.assertTrue(scheduler.handoff_runtime(first))
        self.assertEqual(second.status, RUNNER.RUNNING_SUITE)
        self.assertEqual(second.runtime.profile, "m-g0")
        self.assertIsNone(first.runtime)

    def test_runtime_group_handoff_skips_completed_suites(self):
        common = self._common(model="model-a", runtime_group="model-a")
        first = RUNNER.BlockState("first", {**common, "id": "first", "suite": "bench-pipeline"})
        skipped = RUNNER.BlockState("skipped", {**common, "id": "skipped", "suite": "bench-knowledge"})
        last = RUNNER.BlockState("last", {**common, "id": "last", "suite": "bench-runtime"})
        skipped.status = RUNNER.COMPLETED
        scheduler = RUNNER.Scheduler(self._state(first, skipped, last), dry_run=True)
        first.status = RUNNER.COMPLETED
        first.runtime = runtime()
        self.assertTrue(scheduler.handoff_runtime(first))
        self.assertEqual(last.status, RUNNER.RUNNING_SUITE)

    def test_max_active_models_blocks_a_different_group(self):
        first = RUNNER.BlockState("first", {**self._common(model="model-a", runtime_group="model-a"),
                                            "id": "first", "suite": "bench-pipeline"})
        second = RUNNER.BlockState("second", {**self._common(model="model-b", runtime_group="model-b"),
                                              "id": "second", "suite": "bench-pipeline"})
        scheduler = RUNNER.Scheduler(self._state(first, second), dry_run=True, max_active_models=1)
        first.status = RUNNER.RUNNING_SUITE
        first.runtime = runtime((1,), 11435)
        second.status = RUNNER.WAITING_GPU
        scheduler.try_start_load()
        self.assertEqual(second.status, RUNNER.WAITING_GPU)

    def test_runtime_group_does_not_reuse_dead_runtime(self):
        common = self._common(runtime_group="model-a")
        first = RUNNER.BlockState("first", {**common, "id": "first", "suite": "bench-pipeline"})
        second = RUNNER.BlockState("second", {**common, "id": "second", "suite": "bench-knowledge"})
        scheduler = RUNNER.Scheduler(self._state(first, second))
        first.status = RUNNER.FAILED
        first.runtime = runtime()
        unloaded = []
        self._patch(served_model_id=lambda port: None, unload_runtime=lambda rt: unloaded.append(rt.profile))
        self.assertFalse(scheduler.handoff_runtime(first))
        self.assertEqual(second.status, RUNNER.PENDING)
        self.assertIsNone(first.runtime)
        self.assertEqual(unloaded, ["m-g0"])

    def test_shutdown_unloads_and_cancels_what_the_run_owns(self):
        block = RUNNER.BlockState("a", {**self._common(), "id": "a", "suite": "bench-pipeline"})
        block.status, block.runtime = RUNNER.RUNNING_SUITE, runtime()
        calls = []
        self._patch(unload_runtime=lambda rt: calls.append(("unload", rt.profile)),
                    cancel_owner=lambda owner, reason: calls.append(("cancel", owner)),
                    write_status=lambda state: None, write_checkpoint=lambda state: None)
        RUNNER.Scheduler(self._state(block)).shutdown()
        self.assertEqual(calls, [("unload", "m-g0"), ("cancel", "campaign-unit")])
        self.assertEqual(block.status, RUNNER.FAILED)

    # Runtime identity: campaign 20260820_modern_validation_l50_retry3 recorded three
    # brain models' results against a stale qwen3.6 server that was healthy on 11434.

    def _brain_block(self, block_id="brain-lane", gguf="/models/Qwen3.5-27B-Q4_K_M.gguf"):
        config = {
            "id": block_id, "model": "qwen3.5:27b", "gguf": gguf, "placement": "brain",
            "suite": "bench-pipeline", "runtime_args": [], "suite_args": [], "run_class": "smoke",
            "_run_id": "unit",
        }
        return RUNNER.BlockState(block_id, config)

    def _loaded_scheduler(self, block, served_gguf="Qwen3.5-27B-Q4_K_M.gguf"):
        scheduler = RUNNER.Scheduler(self._state(block))
        block.status = RUNNER.LOADING
        block.load_started_at = RUNNER.now_iso()
        scheduler.loading_block = block.block_id
        scheduler.load_proc = FakeLoad({"state": "ready", "profile": "qwen3.5-27b-g0", "port": 11434,
                                        "gpus": [0], "ctx": 16384,
                                        "estimate": {"gguf_path": f"/mnt/shared/models/q/{served_gguf}"}})
        return scheduler

    def test_identity_mismatch_fails_lane_without_starting_suite(self):
        block = self._brain_block()
        scheduler = self._loaded_scheduler(block)
        unloaded, suites = [], []
        self._patch(
            served_model_id=lambda port: "Qwen3.6-27B-Q4_K_M.gguf",
            container_info=lambda name: {"running": "true", "id": "abc", "image": "runtime:test"},
            unload_runtime=lambda rt: unloaded.append(rt.profile),
            start_suite=lambda b, r: suites.append(b),
        )
        scheduler.check_load_complete()
        self.assertEqual(block.status, RUNNER.FAILED)
        self.assertIn("serves Qwen3.6-27B-Q4_K_M.gguf, expected Qwen3.5-27B-Q4_K_M.gguf", block.error)
        self.assertEqual(suites, [])
        self.assertEqual(unloaded, ["qwen3.5-27b-g0"])
        self.assertIsNone(scheduler.loading_block)

    def test_manager_loading_another_file_is_an_identity_mismatch(self):
        block = self._brain_block()
        scheduler = self._loaded_scheduler(block, served_gguf="Other.gguf")
        self._patch(
            served_model_id=lambda port: "Qwen3.5-27B-Q4_K_M.gguf",
            container_info=lambda name: {"running": "true", "id": "abc", "image": "runtime:test"},
            unload_runtime=lambda rt: None, start_suite=lambda b, r: object(),
        )
        scheduler.check_load_complete()
        self.assertEqual(block.status, RUNNER.FAILED)
        self.assertIn("the manager loaded Other.gguf", block.error)

    def test_healthy_port_without_owned_container_is_not_ready(self):
        block = self._brain_block()
        scheduler = self._loaded_scheduler(block)
        suites = []
        self._patch(
            served_model_id=lambda port: "Qwen3.5-27B-Q4_K_M.gguf",
            container_info=lambda name: None,
            unload_runtime=lambda rt: None,
            start_suite=lambda b, r: suites.append(b),
        )
        scheduler.check_load_complete()
        self.assertEqual(block.status, RUNNER.FAILED)
        self.assertIn("rig-remote-qwen3.5-27b-g0 is not running", block.error)
        self.assertEqual(suites, [])

    def test_matching_identity_starts_suite_and_records_evidence(self):
        block = self._brain_block()
        scheduler = self._loaded_scheduler(block)
        self._patch(
            served_model_id=lambda port: "Qwen3.5-27B-Q4_K_M.gguf",
            container_info=lambda name: {"running": "true", "id": "abc123", "image": "runtime:test"},
            start_suite=lambda b, r: object(),
        )
        scheduler.check_load_complete()
        self.assertEqual(block.status, RUNNER.RUNNING_SUITE)
        self.assertEqual(block.identity["observed"], "Qwen3.5-27B-Q4_K_M.gguf")
        self.assertEqual(block.identity["container_id"], "abc123")
        self.assertEqual(block.identity["profile"], "qwen3.5-27b-g0")
        status = RUNNER.build_status_dict(scheduler.state)
        self.assertEqual(status["blocks"]["brain-lane"]["runtime_identity"]["port"], 11434)
        self.assertEqual(status["blocks"]["brain-lane"]["gpu_slot"], "brain")

    def test_runtime_group_does_not_reuse_runtime_with_wrong_identity(self):
        first = self._brain_block("first")
        second = self._brain_block("second")
        for block in (first, second):
            block.config["runtime_group"] = "model-a"
        scheduler = RUNNER.Scheduler(self._state(first, second))
        first.status = RUNNER.COMPLETED
        first.runtime = runtime()
        self._patch(
            served_model_id=lambda port: "Qwen3.6-27B-Q4_K_M.gguf",
            container_info=lambda name: {"running": "true", "id": "abc", "image": "runtime:test"},
            unload_runtime=lambda rt: None,
        )
        self.assertFalse(scheduler.handoff_runtime(first))
        self.assertEqual(second.status, RUNNER.PENDING)
        self.assertIsNone(second.runtime)

    def test_identity_change_during_suite_invalidates_block(self):
        block = self._brain_block()
        scheduler = RUNNER.Scheduler(self._state(block))
        block.status = RUNNER.RUNNING_SUITE
        block.runtime = runtime()
        block.identity = {"requested": "Qwen3.5-27B-Q4_K_M.gguf"}

        class Finished:
            def poll(self):
                return 0

        block.suite_process = Finished()
        self._patch(
            served_model_id=lambda port: "Qwen3.6-27B-Q4_K_M.gguf",
            unload_runtime=lambda rt: None,
        )
        scheduler.reap_finished()
        self.assertEqual(block.status, RUNNER.FAILED)
        self.assertIn("results invalid", block.error)

    # Preflight

    def test_limit_policy_fails_during_preflight(self):
        with tempfile.NamedTemporaryFile() as gguf:
            config = {
                "id": "pipeline",
                "model": "qwen3-coder:30b-a3b",
                "gguf": gguf.name,
                "suite": "bench-pipeline",
                "suite_args": [],
                "run_class": "smoke",
                "limit": 1,
            }
            blocks = {"pipeline": RUNNER.BlockState("pipeline", config)}
            with self.assertRaises(SystemExit) as raised:
                RUNNER.validate_resolved_blocks(blocks)
            self.assertIn("does not support bounded", str(raised.exception))

    def test_runtime_group_requires_identical_runtime_settings(self):
        with tempfile.NamedTemporaryFile() as gguf:
            common = {
                "model": "qwen3-coder:30b-a3b", "gguf": gguf.name, "placement": "brain",
                "runtime_args": [], "suite_args": [], "run_class": "smoke", "runtime_group": "model-a",
            }
            blocks = {
                "first": RUNNER.BlockState("first", {**common, "id": "first", "suite": "bench-pipeline", "ctx_size": 4096}),
                "second": RUNNER.BlockState("second", {**common, "id": "second", "suite": "bench-knowledge", "ctx_size": 8192}),
            }
            with self.assertRaises(SystemExit) as raised:
                RUNNER.validate_resolved_blocks(blocks)
            self.assertIn("changes runtime settings", str(raised.exception))

    def test_block_takes_its_gguf_from_the_registry(self):
        block = RUNNER.resolve_block_config({"id": "b", "model": "qwen3-coder:30b-a3b", "suite": "bench-pipeline",
                                             "ctx_size": 16384, "batch_size": 64, "runtime_image": "x"}, {})
        self.assertTrue(block["gguf"].endswith(".gguf"))
        self.assertNotIn("batch_size", block)
        self.assertNotIn("runtime_image", block)
        self.assertNotIn("_gguf_mismatch", block)
        wrong = RUNNER.resolve_block_config({"id": "w", "model": "qwen3-coder:30b-a3b", "suite": "bench-pipeline",
                                             "gguf": "/models/other.gguf"}, {})
        self.assertIn("not the registry's", wrong["_gguf_mismatch"])


if __name__ == "__main__":
    unittest.main()
