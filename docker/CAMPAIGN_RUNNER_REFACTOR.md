# Campaign runner refactor: let the manager place and load models

Status: planned 2026-10-22, not started. Owner files: `llm_orchestration/shared/scripts/benchmarks/run_campaign.py`
(the runner), `tests/test_campaign_runner.py`, this folder's `CAMPAIGN_RUNNER.md`, and the rig manager in
`llm-gateway` (`src/llm_gateway/manager/`, `docs/MANAGER.md`).

## Why

The runner still carries its own model of the rig: a slot table (the 3090 as `brain`, each 1060, and since
2026-10-22 every pair of 1060s), a port per slot, a memory limit per slot tier, an even `--tensor-split`,
its own `run_runtime.sh` command line and its own lease and reservation calls through `harness_lease.sh`.
That is a second, weaker copy of what the rig manager already does:

- The manager's harness (`manager/fit.py`) chooses how many cards a model needs and which free ones, plans
  the largest context that fits and a per-card layer split from the GGUF header, and refuses a load that
  will not fit before anything is leased. It placed Qwen3-Coder-Next across all six cards on 2026-10-21
  (split 24,5,5,5,5,5, ctx 162304) without any slot table.
- The rig confirms each load from llama.cpp's own log and refuses one that is not fully on the GPUs.
- Leases, claims with TTLs, reservations for multi-card waits and the operator overrides are all the
  manager's (MANAGER.md, "Model loads" and "Reservations").
- Benchmark lanes already load this way (`scripts/integration/worker_lane.sh`: `rigctl load-model`).

A slot table cannot scale with the rig either. Five 1060s give 10 pairs; seven 1070s would give 21 pairs,
35 triples and so on, and the runner would still not know that a model needs three cards.

So this is a cleanup: take the rig model out of the runner and let the manager do its job.

## Target

Placement in a block is one of:

| Placement | Meaning | Manager request |
| --- | --- | --- |
| `brain` | the RTX 3090 Ti | `gpu_ids: [0]` |
| `workers` | the worker cards (the 1060s today); the harness picks one card or the fewest that hold it | no cards named, worker cards only (see gap 2) |
| `gpus: [1, 3]` | exactly these cards, for runs that must not move | `gpu_ids: [1, 3]` |

There is no single vs split distinction in a manifest: one card or several is the harness's answer to how
big the model is and what context the block asks for.

For each runtime group (the blocks that share one loaded model) the runner:

1. asks the manager to load: `POST /v1/manager/models/load` with `model`, the placement's cards (or none),
   `ctx` from the block, `use: benchmark` (registry profile, no prompt cache), `extra_args` from the block,
   and `wait_s` (the block's wait limit, 2 h by default);
2. takes `profile`, `port`, `gpus` and `ctx` from the answer and runs the group's suites against that port,
   handing the runtime from block to block as now;
3. unloads the profile (`POST /v1/manager/profiles/<id>/unload`) when the group ends, fails or the campaign
   is stopped.

The runner keeps everything that is about suites: manifest parsing and validation, dependencies, runtime
groups and hand-off, the served-model identity check (against the port the manager returned), suite
commands, status and checkpoints, `--max-active-models`.

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

- `scripts/active/build_runtime_matrix_campaign.py` and `campaigns/*` that are still run: placements become
  `brain` / `workers` / `gpus`
- `harness_lease.sh`: check whether anything but the runner uses `acquire`/`reserve`; delete what is unused
- `CAMPAIGN_RUNNER.md` (Scheduling, placement field), MANAGER.md Reservations rule 5 (campaign blocks),
  NEW_MODEL_INTEGRATION.md Phase 5 wording if it names slots
- tests: the slot, refusal and lease tests go; new tests drive the runner against a fake manager

## Gaps in the manager to close first

1. **Waiting with harness-chosen cards does not reserve.** `load_model` with no cards and `wait_s` polls
   `fit_model` until a plan fits (`core.py`, the `elif wait_s > 0` branch) but holds nothing meanwhile, so
   single work can keep taking cards and a multi-card load can starve, the problem reservations were built
   for. Fix: when the best plan needs cards that are busy, reserve the cards of that plan (the same claim
   path as explicit `gpu_ids`), renew while waiting, re-plan when cards free, and drop the reservation once
   the lease holds them. Decide whether the plan may change while waiting (it should prefer the reserved
   set, but take an equal plan on other cards that free first).
2. **No way to keep a request off a card class.** With no cards named the harness takes the smallest class
   that holds the model, which is the 1060s for small models, but if every 1060 is busy a small model can
   land on the 3090 (`fit.choose`). A campaign's worker queue must not take the brain card. Fix: a request
   field such as `card_class` (`worker` / `brain`) or `exclude_gpus`; the brain card's identity belongs in
   rig config, not in the request.
3. **A load outlives a dead campaign.** The manager's lease for a load is renewed by its reconciler for as
   long as the rig profile lives, so a campaign that crashes leaves its models loaded until someone unloads
   them. Lanes avoid this with a claim that has a TTL and is renewed while the lane runs. Fix: let a load
   carry an owner and TTL (renewed by the caller, `POST .../profiles/<id>/renew` or a claim per load), and
   have the reconciler unload profiles whose owner stopped renewing. This also serves lanes and the
   gateway's chat loads.

## Order of work

1. Manager gaps 1-3, with tests in `llm-gateway/tests` (fake rig already covers claims and plan items).
2. Runner: replace the load/lease layer with manager calls; keep suites, groups, status. Run its tests
   against a fake manager, then a dry run, then a one-model real campaign on `workers` and one on `brain`.
3. Delete the dead code and update the generator, docs and the campaigns still in use.
4. Re-run a small mixed campaign (one brain model, two worker models that each need two cards, one that
   fits on one card) and check: no card idle while a block waits, multi-card blocks are not starved by
   singles, every profile is unloaded at the end and after `kill -TERM` of the runner.

## Not in scope

- Lanes (`worker_lane.sh`) already use the manager; their card groups stay the operator's choice.
- Orchestration's split reservations (`agents/gpu_split.py`) are a separate path; review after this.
- Phase 4.5 as a general "try other settings" phase (2026-10-21 note): separate change.
