# Campaign runner refactor: isolated rig modes, the manager places and loads models

Status: planned 2026-10-22, revised 2026-10-23 for isolated modes (operator); steps 1-3 built 2026-10-24,
step 4 open. Owner files:
`llm_orchestration/shared/scripts/benchmarks/run_campaign.py` (the runner), `tests/test_campaign_runner.py`,
this folder's `CAMPAIGN_RUNNER.md`, the rig mode selector `llm_orchestration/shared/scripts/rig/rig.py`, and the
rig manager in `llm-gateway` (`src/llm_gateway/manager/`, `docs/MANAGER.md`).

## Why

The runner still carries its own model of the rig: a slot table (the 3090 as `brain`, each 1060, and since
2026-10-22 every pair of 1060s), a port per slot, a memory limit per slot tier, an even `--tensor-split`,
its own `run_runtime.sh` command line and its own lease and reservation calls through `harness_lease.sh`.
That is a second, weaker copy of what the rig manager already does:

- The manager's harness (`manager/fit.py`) chooses how many cards a model needs and which free ones, plans
  the context and a per-card layer split from the GGUF header, and refuses a load that will not fit before
  anything is leased. It placed Qwen3-Coder-Next across all six cards on 2026-10-21 (split 24,5,5,5,5,5) and
  Nemotron 3.5 Bolt on GPUs 0-3 on 2026-10-23 without any slot table.
- The rig confirms each load from llama.cpp's own log and refuses one that is not fully on the GPUs.
- Leases, claims with TTLs, multi-card waits and the operator overrides are all the manager's.
- Benchmark lanes already load this way (`scripts/integration/worker_lane.sh`: `rigctl load-model`).

The slot table cannot place a model that spans the 3090 and 1060s at all: Bolt's Phase 5 (GPUs 0-3) and
Qwen3-Coder-Next's (all six) cannot be written as campaign blocks today.

## Isolated modes (operator, 2026-10-23)

The rig is in one mode at a time, as `workspace/implement/rig_boot_modes.md` decided on 2026-10-06 ("one mode
at a time, explicit start/stop, no automatic swapping or cross-mode coordination"). Each mode owns every card
while it is active and has its own rules; nothing arbitrates between modes. Crossovers come later if usage
needs them.

| Mode | Entered by | Owns | Context | Placement |
|---|---|---|---|---|
| `bench` | a manager load with use `benchmark` (lane, campaign, `rigctl load-model --use benchmark`) | every card | exactly the registry profile's `ctx_size` unless the request names one | fewest cards that hold the model at that context; several benchmark models side by side on whatever is free, first come first served |
| `remote` | a manager load with use `chat` or `worker` (gateway, harness, `rigctl load-model`) | every card | the largest that fits (capped at the trained context or the request) | as today: the smallest card class that holds it, then the fewest cards |
| `orchestration` | `rig start orchestration` | every card | the brain's own rules | the brain's own logic (`agents/brain_resources.py`) |

Rules:
- A load whose mode differs from the active one is refused as busy (`busy: <mode>`), unless forced, which
  stops the active mode first. Idle accepts any.
- The mode ends when its last profile is unloaded (the rig goes back to idle), as `remote` does today.
- The old `bench` stack (`llm-bench.service`, `startup.py --config config.benchmark.json`) is retired:
  nothing current starts it (lanes and campaigns load their own models), and `bench` now means manager
  loads for benchmarking.

What this removes from the plan: gap 2 (demand-aware placement across callers, orchestration's demand window
in the manager, campaigns declaring later blocks). Inside one mode there is no other caller to defend cards
against, so first come first served is enough.

## Target

Placement in a block:

| Placement | Meaning | Manager request |
| --- | --- | --- |
| omitted | the manager picks the cards (fewest that hold the model at the profile's context) | no cards named |
| `gpus: [0, 1, 2, 3]` | exactly these cards, for runs that must not move | `gpu_ids: [0, 1, 2, 3]` |
| `brain` | shorthand for `gpus: [0]` (kept so existing manifests read the same) | `gpu_ids: [0]` |

There is no single vs split distinction in a manifest: one card or several is the harness's answer to how
big the model is.

For each runtime group (the blocks that share one loaded model) the runner:

1. asks the manager to load: `POST /v1/manager/models/load` with `model`, the placement's cards (or none),
   `use: benchmark`, `ctx` only when the block overrides the profile, `extra_args` from the block, `owner` (the
   campaign run id) and `wait_s` (the block's wait limit, 2 h by default);
2. takes `profile`, `port`, `gpus` and `ctx` from the answer and runs the group's suites against that port,
   handing the runtime from block to block as now;
3. unloads the profile (`POST /v1/manager/profiles/<id>/unload`) when the group ends or fails, and when the
   campaign ends or is stopped asks the manager to cancel everything its run owns (`cancel-owner`).

The runner keeps everything that is about suites: manifest parsing and validation, dependencies, runtime
groups and hand-off, the served-model identity check (against the port the manager returned), suite
commands, status and checkpoints, `--max-active-models`. A group that cannot start because the cards are
busy waits in the manager (`wait_s`); the runner starts the next group that can.

## What goes away

In `run_campaign.py`:

- `GpuSlot`, `SLOTS`, `_worker_slot`, `PLACEMENT_SLOTS`, `FLEXIBLE_PLACEMENTS`, `slots_conflict`,
  `find_free_slot`, `BRAIN_GPU`, `WORKER_GPUS`, `BASE_PORT`
- `build_runtime_cmd`, `start_runtime`, `stop_runtime`, `docker_stop`, `local_gguf`, the per-tier memory
  limits, the even tensor split, `wait_for_runtime` (the manager answers once the model serves)
- `CampaignLeases`, `LeaseRefused`, `OccupiedSlots`, `harness_lease.sh` use, `LEASE_REFUSED_COOLDOWN_S`,
  `LEASE_REFUSALS_PER_CARD`, the refusal and reservation branches in `Scheduler.try_start_load`,
  `reserved_since`, `reserved_for`, `refused_at`, `lease_refusals`
- the runner's `load_lock` (the rig already runs one load at a time)
- `ctx_size`/`batch_size` defaults from the tuning profile and the `runtime_args` merge
  (`resolve_block_config`): the manager reads the registry profile itself; a block passes only overrides
- `gguf` in manifests: the registry names each model's GGUF (keep it only as an optional cross-check)

Elsewhere:

- `rig.py`: the `bench` stack unit (`STACK_UNITS["bench"]`); `llm-bench.service`; orchestration's
  `scripts/benchmarks/start_benchmark_mode.py`, `start_custom_mode.py`, `start_empty_mode.py` (that stack's
  wrappers); all removed 2026-10-24
- `scripts/active/build_runtime_matrix_campaign.py` and `campaigns/*` that are still run: placements become
  omitted / `gpus` / `brain`
- `harness_lease.sh`: check whether anything but the runner uses `acquire`/`reserve`; delete what is unused
- `CAMPAIGN_RUNNER.md` (Scheduling, placement field), MANAGER.md (Reservations rule 5, model loads, modes),
  NEW_MODEL_INTEGRATION.md Phase 5 wording, `rig_boot_modes.md` (bench is manager loads)
- tests: the slot, refusal and lease tests go; new tests drive the runner against a fake manager

## Manager gaps (2026-10-22), status

1. **A load that names no cards collects cards as they free.** Built (MANAGER.md, Reservations rule 4a).
2. **Demand-aware placement across callers.** Dropped 2026-10-23: one mode at a time (see above). The part
   already built (a load will not spill onto a bigger card while one of the manager's own waits wants it)
   stays; it is harmless inside a mode.
3. **Cancel a run and reclaim its cards.** Built: `rigctl cancel-owner WHO`, `POST /v1/manager/owners/WHO/cancel`.
4. **Campaigns and lanes in the report, crash vs outage.** Built: runs (`rigctl run-start / runs / recover /
   run-stop / dismiss`), waits that ride out an unreachable rig.

## Order of work

1. Modes: `rig.py` takes the mode from the load's use (`benchmark` -> `bench`, otherwise `remote`), refuses a
   load for another mode, and retires the bench stack. The manager plans benchmark loads at the registry
   profile's context. Tests for both; deploy (rig checkout pull, restart `rig-plan.service`; restart the
   gateway on the Pi).
2. Runner: replace the load/lease layer with manager calls; keep suites, groups, status. Run its tests
   against a fake manager, then a dry run, then a real one-model campaign: Nemotron 3.5 Bolt's Phase 5 with
   placement omitted.
3. Delete the dead code and update the generator, docs and the campaigns still in use.
4. Re-run a small mixed campaign (one model on the 3090, two that each need two cards, one that fits on one
   card) and check: no card idle while a group waits, every profile is unloaded at the end and after
   `kill -TERM` of the runner, the rig is back to idle.

## Not in scope

- Lanes (`worker_lane.sh`) already use the manager; their card groups stay the operator's choice. A lane is
  close to a one-group campaign plus litmus, the runtime record and the Phase 4 pause; `phase4.sh` and the
  runner build the same suite commands. Merge them later, once the runner is on the manager.
- Orchestration's split reservations (`agents/gpu_split.py`) are a separate path; review after this.
- Crossovers between modes (a chat model beside a benchmark): later, if usage needs it.
