import importlib.util
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


class CampaignRunnerTests(unittest.TestCase):
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
                command = RUNNER.build_suite_cmd(block, RUNNER.SLOTS["brain"])
                self.assertIn(suite, command)
                self.assertIn("--model", command)
                self.assertIn("--run-name", command)
                self.assertIn("--run-class", command)
                self.assertIn("--results-dir", command)
                self.assertIn("--runtime-base", command)
                self.assertNotIn("--gguf", command)
                self.assertIn("HOME=/tmp/benchmark-home", command)
                self.assertTrue(any(value.startswith("HF_HOME=") for value in command))

    def test_profile_alias_is_resolved_before_launch(self):
        profile = RUNNER._lookup_tuning("qwen3-coder:30b-a3b")
        self.assertIsNotNone(profile)
        self.assertTrue(profile["system_prompt"].strip())
        self.assertIn("ctx_size", profile["runtime"])

    def test_split_and_single_slots_conflict(self):
        occupied = {"split_1_3": "split-block"}
        slot = RUNNER.find_free_slot("single", occupied)
        self.assertIsNotNone(slot)
        self.assertNotIn(slot.name, {"gpu_1", "gpu_3"})

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
        command = RUNNER.build_suite_cmd(block, RUNNER.SLOTS["split_1_3"])
        index = command.index("--gpus")
        self.assertEqual(command[index + 1], '"device=1,3"')
        gpu_ids_index = command.index("--gpu-ids")
        self.assertEqual(command[gpu_ids_index + 1], "0,1")

    def test_single_runtime_has_bounded_headroom(self):
        config = {
            "id": "single",
            "model": "ministral-3:3b",
            "gguf": "/tmp/model.gguf",
            "runtime_image": "runtime:test",
            "ctx_size": 8192,
            "batch_size": 64,
            "runtime_args": [],
        }
        block = RUNNER.BlockState("single", config)
        command = RUNNER.build_runtime_cmd(block, RUNNER.SLOTS["gpu_2"])
        self.assertEqual(command[command.index("--memory-limit") + 1], "8g")
        self.assertEqual(command[command.index("--memory-swap") + 1], "10g")

    def test_runtime_uses_archive_path_without_machine_config(self):
        config = {
            "id": "single",
            "model": "ministral-3:3b",
            "gguf": "/mnt/shared/models/ministral/model.gguf",
            "runtime_image": "runtime:test",
            "ctx_size": 8192,
            "runtime_args": [],
        }
        original_tree = RUNNER.TREE
        with tempfile.TemporaryDirectory() as tmp:
            RUNNER.TREE = Path(tmp)
            try:
                command = RUNNER.build_runtime_cmd(RUNNER.BlockState("single", config), RUNNER.SLOTS["gpu_2"])
            finally:
                RUNNER.TREE = original_tree
        self.assertEqual(command[command.index("--model") + 1], "/mnt/shared/models/ministral/model.gguf")

    def test_tree_is_the_checkout_holding_the_machine_config(self):
        # run_campaign.py lives at <tree>/scripts/benchmarks/; the hot-set lookup reads
        # <tree>/agents/config.json, so TREE must be the checkout root.
        self.assertEqual(RUNNER.TREE, ROOT.parents[2].resolve())
        self.assertTrue((RUNNER.TREE / "agents").is_dir())
        self.assertTrue((RUNNER.TREE / "scripts" / "benchmarks" / "run_campaign.py").is_file())

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
        command = RUNNER.build_suite_cmd(block, RUNNER.SLOTS["gpu_2"])
        gpu_ids_index = command.index("--gpu-ids")
        self.assertEqual(command[gpu_ids_index + 1], "0")

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

    def test_runtime_group_reuses_slot_for_next_suite(self):
        common = {
            "model": "qwen3-coder:30b-a3b",
            "gguf": "/tmp/model.gguf",
            "placement": "brain",
            "runtime_image": "runtime:test",
            "ctx_size": 4096,
            "batch_size": 64,
            "runtime_args": [],
            "suite_args": [],
            "run_class": "smoke",
            "runtime_group": "model-a",
            "_run_id": "unit",
        }
        first = RUNNER.BlockState("first", {**common, "id": "first", "suite": "bench-pipeline"})
        second = RUNNER.BlockState("second", {**common, "id": "second", "suite": "bench-knowledge"})
        state = RUNNER.CampaignState(
            name="unit", run_id="unit", manifest_path="unit.json",
            blocks={"first": first, "second": second}, started_at=RUNNER.now_iso(),
        )
        scheduler = RUNNER.Scheduler(state, dry_run=True)
        first.status = RUNNER.COMPLETED
        first.assigned_slot = RUNNER.SLOTS["brain"]
        first.runtime_container = "runtime-a"
        scheduler.occupied["brain"] = "first"
        self.assertTrue(scheduler.handoff_runtime(first))
        self.assertEqual(second.status, RUNNER.RUNNING_SUITE)
        self.assertEqual(second.runtime_container, "runtime-a")
        self.assertIsNone(first.runtime_container)
        self.assertEqual(scheduler.occupied["brain"], "second")

    def test_runtime_group_handoff_skips_completed_suites(self):
        common = {
            "model": "model-a", "gguf": "/tmp/model.gguf", "placement": "brain",
            "runtime_image": "runtime:test", "ctx_size": 4096, "batch_size": 64,
            "runtime_args": [], "suite_args": [], "run_class": "smoke",
            "runtime_group": "model-a", "_run_id": "unit",
        }
        first = RUNNER.BlockState("first", {**common, "id": "first", "suite": "bench-pipeline"})
        skipped = RUNNER.BlockState("skipped", {**common, "id": "skipped", "suite": "bench-knowledge"})
        last = RUNNER.BlockState("last", {**common, "id": "last", "suite": "bench-runtime"})
        skipped.status = RUNNER.COMPLETED
        state = RUNNER.CampaignState(
            name="unit", run_id="unit", manifest_path="unit.json",
            blocks={"first": first, "skipped": skipped, "last": last},
            started_at=RUNNER.now_iso(),
        )
        scheduler = RUNNER.Scheduler(state, dry_run=True)
        first.status = RUNNER.COMPLETED
        first.assigned_slot = RUNNER.SLOTS["brain"]
        first.runtime_container = "runtime-a"
        scheduler.occupied["brain"] = "first"
        self.assertTrue(scheduler.handoff_runtime(first))
        self.assertEqual(last.status, RUNNER.RUNNING_SUITE)

    def test_max_active_models_blocks_a_different_group(self):
        common = {
            "gguf": "/tmp/model.gguf", "placement": "brain",
            "runtime_image": "runtime:test", "ctx_size": 4096, "batch_size": 64,
            "runtime_args": [], "suite_args": [], "run_class": "smoke",
            "_run_id": "unit",
        }
        first = RUNNER.BlockState("first", {
            **common, "id": "first", "model": "model-a", "suite": "bench-pipeline",
            "runtime_group": "model-a",
        })
        second = RUNNER.BlockState("second", {
            **common, "id": "second", "model": "model-b", "suite": "bench-pipeline",
            "runtime_group": "model-b",
        })
        state = RUNNER.CampaignState(
            name="unit", run_id="unit", manifest_path="unit.json",
            blocks={"first": first, "second": second}, started_at=RUNNER.now_iso(),
        )
        scheduler = RUNNER.Scheduler(state, dry_run=True, max_active_models=1)
        first.status = RUNNER.RUNNING_SUITE
        first.assigned_slot = RUNNER.SLOTS["gpu_1"]
        scheduler.occupied["gpu_1"] = "first"
        second.status = RUNNER.WAITING_GPU
        scheduler.try_start_load()
        self.assertEqual(second.status, RUNNER.WAITING_GPU)

    def test_runtime_group_does_not_reuse_dead_runtime(self):
        common = {
            "model": "qwen3-coder:30b-a3b",
            "gguf": "/tmp/model.gguf",
            "placement": "brain",
            "runtime_image": "runtime:test",
            "ctx_size": 4096,
            "batch_size": 64,
            "runtime_args": [],
            "suite_args": [],
            "run_class": "smoke",
            "runtime_group": "model-a",
            "_run_id": "unit",
        }
        first = RUNNER.BlockState("first", {**common, "id": "first", "suite": "bench-pipeline"})
        second = RUNNER.BlockState("second", {**common, "id": "second", "suite": "bench-knowledge"})
        state = RUNNER.CampaignState(
            name="unit", run_id="unit", manifest_path="unit.json",
            blocks={"first": first, "second": second}, started_at=RUNNER.now_iso(),
        )
        scheduler = RUNNER.Scheduler(state)
        first.status = RUNNER.FAILED
        first.assigned_slot = RUNNER.SLOTS["brain"]
        first.runtime_container = "runtime-a"
        scheduler.occupied["brain"] = "first"

        original_served = RUNNER.served_model_id
        original_stop = RUNNER.stop_runtime
        try:
            RUNNER.served_model_id = lambda port: None
            RUNNER.stop_runtime = lambda container: None
            self.assertFalse(scheduler.handoff_runtime(first))
        finally:
            RUNNER.served_model_id = original_served
            RUNNER.stop_runtime = original_stop

        self.assertEqual(second.status, RUNNER.PENDING)
        self.assertIsNone(first.runtime_container)
        self.assertNotIn("brain", scheduler.occupied)

    # Runtime identity: campaign 20260820_modern_validation_l50_retry3 recorded three
    # brain models' results against a stale qwen3.6 server that was healthy on 11434.

    def _brain_block(self, block_id="brain-lane", gguf="/models/Qwen3.5-27B-Q4_K_M.gguf"):
        config = {
            "id": block_id, "model": "qwen3.5:27b", "gguf": gguf, "placement": "brain",
            "suite": "bench-pipeline", "runtime_image": "runtime:test", "ctx_size": 4096,
            "batch_size": 64, "runtime_args": [], "suite_args": [], "run_class": "smoke",
            "_run_id": "unit",
        }
        return RUNNER.BlockState(block_id, config)

    def _patch(self, **replacements):
        originals = {name: getattr(RUNNER, name) for name in replacements}
        for name, value in replacements.items():
            setattr(RUNNER, name, value)
        self.addCleanup(lambda: [setattr(RUNNER, n, v) for n, v in originals.items()])

    def test_stale_healthy_server_fails_preflight_before_load(self):
        block = self._brain_block()
        launched = []
        self._patch(
            docker_stop=lambda name: None,
            served_model_id=lambda port: "Qwen3.6-27B-Q4_K_M.gguf",
            build_runtime_cmd=lambda b, s: launched.append(b) or ["true"],
        )
        original_sleep = RUNNER.time.sleep
        RUNNER.time.sleep = lambda s: None
        self.addCleanup(setattr, RUNNER.time, "sleep", original_sleep)
        with self.assertRaises(RuntimeError) as raised:
            RUNNER.start_runtime(block, RUNNER.SLOTS["brain"])
        self.assertIn("already serves Qwen3.6-27B-Q4_K_M.gguf", str(raised.exception))
        self.assertEqual(launched, [])

    def _loading_scheduler(self, block):
        state = RUNNER.CampaignState(
            name="unit", run_id="unit", manifest_path="unit.json",
            blocks={block.block_id: block}, started_at=RUNNER.now_iso(),
        )
        scheduler = RUNNER.Scheduler(state)
        block.status = RUNNER.LOADING
        block.assigned_slot = RUNNER.SLOTS["brain"]
        block.runtime_container = "llama-campaign-brain-lane"
        block.load_started_at = RUNNER.now_iso()
        scheduler.occupied["brain"] = block.block_id
        scheduler.load_lock = True
        scheduler.loading_block = block.block_id
        return scheduler

    def test_identity_mismatch_fails_lane_without_starting_suite(self):
        block = self._brain_block()
        scheduler = self._loading_scheduler(block)
        stopped, suites = [], []
        self._patch(
            served_model_id=lambda port: "Qwen3.6-27B-Q4_K_M.gguf",
            container_info=lambda name: {"running": "true", "id": "abc", "image": "runtime:test"},
            stop_runtime=lambda name: stopped.append(name),
            start_suite=lambda b, s: suites.append(b),
        )
        scheduler.check_load_complete()
        self.assertEqual(block.status, RUNNER.FAILED)
        self.assertIn("serves Qwen3.6-27B-Q4_K_M.gguf, expected Qwen3.5-27B-Q4_K_M.gguf", block.error)
        self.assertEqual(suites, [])
        self.assertEqual(stopped, ["llama-campaign-brain-lane"])
        self.assertNotIn("brain", scheduler.occupied)
        self.assertFalse(scheduler.load_lock)

    def test_healthy_port_without_owned_container_is_not_ready(self):
        block = self._brain_block()
        scheduler = self._loading_scheduler(block)
        suites = []
        self._patch(
            served_model_id=lambda port: "Qwen3.5-27B-Q4_K_M.gguf",
            container_info=lambda name: None,
            stop_runtime=lambda name: None,
            start_suite=lambda b, s: suites.append(b),
        )
        scheduler.check_load_complete()
        self.assertEqual(block.status, RUNNER.FAILED)
        self.assertIn("is not running", block.error)
        self.assertEqual(suites, [])

    def test_matching_identity_starts_suite_and_records_evidence(self):
        block = self._brain_block()
        scheduler = self._loading_scheduler(block)
        self._patch(
            served_model_id=lambda port: "Qwen3.5-27B-Q4_K_M.gguf",
            container_info=lambda name: {"running": "true", "id": "abc123", "image": "runtime:test"},
            start_suite=lambda b, s: object(),
        )
        scheduler.check_load_complete()
        self.assertEqual(block.status, RUNNER.RUNNING_SUITE)
        self.assertEqual(block.identity["observed"], "Qwen3.5-27B-Q4_K_M.gguf")
        self.assertEqual(block.identity["container_id"], "abc123")
        status = RUNNER.build_status_dict(scheduler.state)
        self.assertEqual(status["blocks"]["brain-lane"]["runtime_identity"]["port"], 11434)

    def test_runtime_group_does_not_reuse_runtime_with_wrong_identity(self):
        first = self._brain_block("first")
        second = self._brain_block("second")
        for block in (first, second):
            block.config["runtime_group"] = "model-a"
        state = RUNNER.CampaignState(
            name="unit", run_id="unit", manifest_path="unit.json",
            blocks={"first": first, "second": second}, started_at=RUNNER.now_iso(),
        )
        scheduler = RUNNER.Scheduler(state)
        first.status = RUNNER.COMPLETED
        first.assigned_slot = RUNNER.SLOTS["brain"]
        first.runtime_container = "runtime-a"
        scheduler.occupied["brain"] = "first"
        self._patch(
            served_model_id=lambda port: "Qwen3.6-27B-Q4_K_M.gguf",
            container_info=lambda name: {"running": "true", "id": "abc", "image": "runtime:test"},
            stop_runtime=lambda name: None,
        )
        self.assertFalse(scheduler.handoff_runtime(first))
        self.assertEqual(second.status, RUNNER.PENDING)
        self.assertIsNone(second.runtime_container)
        self.assertNotIn("brain", scheduler.occupied)

    def test_identity_change_during_suite_invalidates_block(self):
        block = self._brain_block()
        state = RUNNER.CampaignState(
            name="unit", run_id="unit", manifest_path="unit.json",
            blocks={block.block_id: block}, started_at=RUNNER.now_iso(),
        )
        scheduler = RUNNER.Scheduler(state)
        block.status = RUNNER.RUNNING_SUITE
        block.assigned_slot = RUNNER.SLOTS["brain"]
        block.identity = {"requested": "Qwen3.5-27B-Q4_K_M.gguf"}

        class Finished:
            def poll(self):
                return 0

        block.suite_process = Finished()
        self._patch(
            served_model_id=lambda port: "Qwen3.6-27B-Q4_K_M.gguf",
            stop_runtime=lambda name: None,
        )
        scheduler.reap_finished()
        self.assertEqual(block.status, RUNNER.FAILED)
        self.assertIn("results invalid", block.error)

    def test_runtime_group_requires_identical_runtime_settings(self):
        with tempfile.NamedTemporaryFile() as gguf:
            common = {
                "model": "qwen3-coder:30b-a3b", "gguf": gguf.name,
                "placement": "brain", "runtime_image": "runtime:test",
                "batch_size": 64, "runtime_args": [], "suite_args": [],
                "run_class": "smoke", "runtime_group": "model-a",
            }
            blocks = {
                "first": RUNNER.BlockState("first", {**common, "id": "first", "suite": "bench-pipeline", "ctx_size": 4096}),
                "second": RUNNER.BlockState("second", {**common, "id": "second", "suite": "bench-knowledge", "ctx_size": 8192}),
            }
            with self.assertRaises(SystemExit) as raised:
                RUNNER.validate_resolved_blocks(blocks)
            self.assertIn("changes runtime settings", str(raised.exception))


    # Campaign leases: one `benchmarks` lease per occupied slot from the rig manager.

    def _fake_lease_helper(self, mode="ok"):
        tmp = Path(tempfile.mkdtemp())
        calls = tmp / "calls"
        helper = tmp / "harness_lease.sh"
        helper.write_text(
            "#!/bin/bash\n"
            f'echo "$*" >> {calls}\n'
            'case "$1" in\n'
            f'  acquire) case "{mode}" in ok|stuck) echo "lease-$2";; offline) exit 0;; refused) echo nope >&2; exit 2;; esac ;;\n'
            f'  release) [ "{mode}" = stuck ] && echo "release failed" >&2; exit 0 ;;\n'
            "esac\n", encoding="utf-8")
        self._patch(LEASE_HELPER=helper)
        return lambda: calls.read_text(encoding="utf-8").splitlines() if calls.exists() else []

    def test_lease_taken_once_per_slot_and_released_when_freed(self):
        calls = self._fake_lease_helper()
        leases = RUNNER.CampaignLeases("run-1")
        slots = RUNNER.OccupiedSlots(leases)
        self.assertEqual(leases.ensure(RUNNER.SLOTS["split_1_3"], "m:8b"), "lease-1,3")
        self.assertEqual(leases.ensure(RUNNER.SLOTS["split_1_3"], "m:8b"), "lease-1,3")
        slots["split_1_3"] = "block-a"
        slots.pop("split_1_3", None)
        self.assertEqual(calls(), ["acquire 1,3 campaign-split_1_3 run-1 m:8b",
                                   "release lease-1,3 campaign-split_1_3"])
        self.assertEqual(leases.held, {})

    def test_refused_card_fails_and_unreachable_manager_runs_without_lease(self):
        self._fake_lease_helper("refused")
        with self.assertRaises(RuntimeError) as raised:
            RUNNER.CampaignLeases("run-1").ensure(RUNNER.SLOTS["gpu_2"], "m")
        self.assertIn("did not lease gpu_2", str(raised.exception))
        self._fake_lease_helper("offline")
        self.assertIsNone(RUNNER.CampaignLeases("run-1").ensure(RUNNER.SLOTS["gpu_2"], "m"))

    def test_refused_card_moves_the_block_to_the_next_card(self):
        tmp = Path(tempfile.mkdtemp())
        helper = tmp / "harness_lease.sh"
        helper.write_text('#!/bin/bash\n[ "$1" = acquire ] && [ "$2" = 1 ] && { echo claimed >&2; exit 2; }\n'
                          '[ "$1" = acquire ] && echo "lease-$2"\nexit 0\n', encoding="utf-8")
        self._patch(LEASE_HELPER=helper, start_runtime=lambda b, s, lease=None: "container")
        block = self._brain_block("single-block")
        block.config["placement"] = "single"
        block.status = RUNNER.WAITING_GPU
        state = RUNNER.CampaignState("c", "run-1", "m.json", {"single-block": block}, "now")
        sched = RUNNER.Scheduler(state)
        sched.try_start_load()                       # GPU 1 refused: back to waiting, not failed
        self.assertEqual(block.status, RUNNER.WAITING_GPU)
        sched.try_start_load()                       # GPU 1 is cooling down: GPU 2 is taken
        self.assertEqual(block.status, RUNNER.LOADING)
        self.assertEqual(block.assigned_slot.name, "gpu_2")

    def test_pinned_block_fails_after_three_refusals(self):
        self._fake_lease_helper("refused")
        self._patch(LEASE_REFUSED_COOLDOWN_S=0)
        block = self._brain_block("pinned")
        block.config["placement"] = "gpu_3"
        block.status = RUNNER.WAITING_GPU
        sched = RUNNER.Scheduler(RUNNER.CampaignState("c", "run-1", "m.json", {"pinned": block}, "now"))
        for _ in range(2):
            sched.try_start_load()
            self.assertEqual(block.status, RUNNER.WAITING_GPU)
        sched.try_start_load()
        self.assertEqual(block.status, RUNNER.FAILED)
        self.assertIn("after 3 refusals", block.error)

    def test_release_refused_is_retried(self):
        self._fake_lease_helper("stuck")
        leases = RUNNER.CampaignLeases("run-1")
        leases.ensure(RUNNER.SLOTS["gpu_3"], "m")
        leases.release("gpu_3")
        self.assertEqual(leases.pending, {"gpu_3": "lease-3"})

    def test_runtime_command_carries_the_lease(self):
        block = self._brain_block()
        seen = []
        self._patch(docker_stop=lambda name: None, served_model_id=lambda port: None,
                    build_runtime_cmd=lambda b, s: ["true"])
        original_run = RUNNER.subprocess.run
        original_sleep = RUNNER.time.sleep
        RUNNER.time.sleep = lambda s: None
        RUNNER.subprocess.run = lambda cmd, **kw: seen.append(cmd) or original_run(["true"], **kw)
        self.addCleanup(setattr, RUNNER.subprocess, "run", original_run)
        self.addCleanup(setattr, RUNNER.time, "sleep", original_sleep)
        RUNNER.start_runtime(block, RUNNER.SLOTS["brain"], "lease-0")
        self.assertEqual(seen[-1], ["true", "--lease", "lease-0"])


if __name__ == "__main__":
    unittest.main()
