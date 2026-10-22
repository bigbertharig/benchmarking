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
| `workers` | the harness picks one card or the fewest that hold it, from what the queue can spare | no cards named (see gaps 1 and 2) |
| `gpus: [1, 3]` | exactly these cards, for runs that must not move | `gpu_ids: [1, 3]` |

There is no single vs split distinction in a manifest: one card or several is the harness's answer to how
big the model is and what context the block asks for.

For each runtime group (the blocks that share one loaded model) the runner:

1. asks the manager to load: `POST /v1/manager/models/load` with `model`, the placement's cards (or none),
   `ctx` from the block, `use: benchmark` (registry profile, no prompt cache), `extra_args` from the block,
   and `wait_s` (the block's wait limit, 2 h by default);
2. takes `profile`, `port`, `gpus` and `ctx` from the answer and runs the group's suites against that port,
   handing the runtime from block to block as now;
3. unloads the profile (`POST /v1/manager/profiles/<id>/unload`) when the group ends or fails, and when
   the campaign ends or is stopped asks the manager to cancel everything its run owns (gap 3).

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

Decisions recorded 2026-10-22 (operator).

1. **A load that names no cards must collect cards as they free.** Built 2026-10-22 (MANAGER.md,
   Reservations rule 4a: one claim extended card by card, no time limit with `wait_s` -1, cancelled by
   removing the claim). Today `load_model` with no cards and
   `wait_s` polls `fit_model` until a plan fits (`core.py`, the `elif wait_s > 0` branch) and holds nothing
   meanwhile, so single work keeps taking each card as it frees and a multi-card load starves. Fix: the
   waiting load claims single cards one at a time as they finish (a claim it grows), so it always has
   something to load into, and loads once the cards it holds make a plan that fits. It plans for the
   cards it holds plus what it still needs, and gives back any card the final plan does not use.
2. **Card choice depends on the queue, not a fixed rule.** Built in part 2026-10-22 (MANAGER.md, "Runs,
   cancel by owner, and demand"): a load that names no cards will not spill onto a bigger card while a wait
   or a run's declared `needs` wants that size. Still to do: reading orchestration's demand window, and a
   campaign declaring its later blocks. The 3090 may take small models; whether it
   should depends on what is waiting for it next. Orchestration already does this for plans: the brain
   watches a window of upcoming tasks and inserts model load and unload tasks
   (`agents/brain_resources.py`: `_collect_llm_demand_window_snapshot`, `_update_llm_demand_timers`,
   `_choose_single_model_for_demand`, `_make_resource_decisions`). The manager should take the same
   approach for every caller: a request carries enough about the work behind it (its queue, or what the
   caller has waiting), and placement looks at pending demand before putting a small model on a big card.
   Start by reading that orchestration logic and moving the reusable part into the manager rather than
   writing a second version. Until then a campaign's `workers` placement can name the worker cards
   explicitly through rig config.
3. **The manager must be able to cancel a run and reclaim its cards.** Built 2026-10-22: `rigctl
   cancel-owner WHO` and `POST /v1/manager/owners/WHO/cancel`; loads carry `owner` (`requested_by` on the lease). No timeouts on loads. Instead every
   load, claim and reservation carries the owner that asked for it (a campaign run id, a lane, the
   gateway), and the manager gets one operation that cancels an owner: stop its queued loads, unload its
   profiles, release its leases, drop its claims and reservations, and log what it cleaned up. The
   campaign runner calls it on a normal finish and from its signal handler; an operator calls it with
   `rigctl` for a run that died. Leases and claims already record an owner, so this is mostly one
   endpoint and a `rigctl cancel-owner` command next to `rigctl kill` (which cleans up by card, not by
   owner).

4. **Campaigns and lanes must be in the report, so a crash and an outage are told apart.** Built
   2026-10-22: runs (`job` plan items, `rigctl run-start / runs / recover / run-stop / dismiss`, dashboard
   Resume / Stop / Dismiss), and waits that ride out an unreachable rig. The report
   and its two copies already do this for model loads (MANAGER.md rule 1c: the rig keeps the plan with a
   version and its boot id, the controller keeps a copy; after a reboot the rig marks the running item
   `interrupted` and holds the plan; a lost network is not a hold and the rig finishes its work). The gap
   is written there too: jobs are not plan items, so after a reboot they do not come back and the manager
   does not know they existed. Decisions (operator, 2026-10-22):
   - A campaign run and a lane become a plan item kind (`job`) the rig runs as a detached unit, like loads
     (`hw_jobs.py`), with its run id, owner and resume command (for a campaign: the same command with its
     `--run-id`, which resumes from `campaign_state.json`).
   - Rig rebooted with a job that was running: the manager does not restart it on its own. It reports the
     job as interrupted (which blocks finished, which were lost mid-run) and offers "resume from
     checkpoint?" on the dashboard and as `rigctl recover <run>` / `rigctl dismiss <run>` (dismiss is the
     cancel-by-owner cleanup of gap 3). A job may opt in to resuming automatically.
   - Rig unreachable without a reboot: wait. The rig keeps working; the manager answers from its copy,
     keeps every wait it is running alive (collecting waits and named-card waits today fail on the first
     unreachable observation), and acts when the rig comes back or the operator says otherwise.

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
