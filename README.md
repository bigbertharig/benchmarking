# Benchmarking

Which models are good on the local rig, for which jobs, and at what cost. This repo holds the model
registry (every model we test and how it loads), the roles other repos read (which model for which job),
the benchmark suites, the integration process for a new model, campaigns, and the results.

The previous long README (procedure, inventory, runtime notes as of 2026-10-15) is kept at
[archive/docs/README_pre_2026-10-23.md](archive/docs/README_pre_2026-10-23.md).

## Start here

| Doc | For |
|---|---|
| [NEW_MODEL_INTEGRATION.md](NEW_MODEL_INTEGRATION.md) | the entry point for running anything: the phases from download to full run (2 load, 3 litmus, 3.5 runtime, 4 smoke, 4.5 optional settings experiments, 5 full run, 6 finalize), with decision trees for common failures |
| [MODEL_LIBRARY.md](MODEL_LIBRARY.md) | picking a model: the library, latest scores, prompt methodology |
| [MODEL_BEST_OF.md](MODEL_BEST_OF.md) | the current best model per job and rig lane |
| [results/MODEL_BENCHMARK_REFERENCE.md](results/MODEL_BENCHMARK_REFERENCE.md) | every model's scores (generated from the records) |
| [docker/README.md](docker/README.md) | the suites; each `docker/bench-*/` has its README and run history |
| [docker/CAMPAIGN_RUNNER.md](docker/CAMPAIGN_RUNNER.md) | campaigns (Phase 5 at scale); [CAMPAIGN_RUNNER_REFACTOR.md](docker/CAMPAIGN_RUNNER_REFACTOR.md) is the planned move onto the rig manager |
| [scripts/integration/README.md](scripts/integration/README.md) | the lane tools for Phases 3-4.5 |
| [RIG_PERFORMANCE.md](RIG_PERFORMANCE.md) | how fast the rig runs models and why: card vs bus, splits, context capacity, PCIe; open questions; which tool measures what |
| [results/RUNTIME_REFERENCE.md](results/RUNTIME_REFERENCE.md) | every speed, capacity and power measurement (generated from `results/runtime_experiments/`) |
| [BENCHMARK_LESSONS_LEARNED.md](BENCHMARK_LESSONS_LEARNED.md), [MODEL_SELECTION_GUIDE.md](MODEL_SELECTION_GUIDE.md), [MODEL_RUNTIME_GUIDE.md](MODEL_RUNTIME_GUIDE.md) | background |

## The four repos

| Repo | Owns | Start at |
|---|---|---|
| [llm-gateway](https://github.com/bigbertharig/llm-gateway) | the machines and the API: rig manager (leases, placement, model loads, runs, waits), gateway, dashboard, `rigctl` | `docs/MANAGER.md` |
| [llm_orchestration](https://github.com/bigbertharig/llm_orchestration) | parallel batch work (brain, workers, plans), the rig hardware scripts, CPU workers | `shared/workspace/CONTEXT.md` |
| **benchmarking** (this one) | which models are good: registry, roles, suites, campaigns, results | `NEW_MODEL_INTEGRATION.md` |
| [llm-harness](https://github.com/bigbertharig/llm-harness) | one model in an interactive loop (no code yet) | `README.md` |

Every load goes through the rig manager (llm-gateway): lanes and campaigns ask it for cards; nothing here
starts a model on a card by itself. The suites run on the rig and read this repo from the shared drive
(`/mnt/shared/plans/shoulders/benchmarking` today; moving beside the other repos).

## The model library

Edit only these two, then run `scripts/active/model_library.py export` (and `check`):

- `model_registry.json`: every tested model: status, archive GGUF, source URL, scheduling, named profiles
  (`default` = benchmark settings, `interactive` = gateway use, `orchestration`, and optional variants such
  as `thinking`)
- `model_roles.json`: which model and profile per rig lane and job (what other repos read)

Generated from the registry (do not edit): `models.catalog.json`, `model_tuning_profiles.json`,
`custom_tasks/model_prompt_profiles.json`.

## Running benchmarks

`rigctl` is llm-gateway's `tools/rigctl.py` and runs on the Pi; the commands it starts run on the rig,
so their paths are the rig's (`/mnt/shared/...`).

```bash
# Phases 2-4 for one or more models on one card group, as a run in the rig's report
# (a reboot shows it as interrupted and offers to resume it)
rigctl run-start --run lanes-NAME -- /bin/bash /mnt/shared/plans/shoulders/benchmarking/scripts/integration/run_worker_lanes.sh 4+5 gemma-4:12b
#   stops after the Phase 4 smoke; LANE_STOP_AFTER=3 stops after litmus; LANE_START_AT=4.5 runs the
#   thinking A/B once you have read the smoke and chosen it (--env K=V)

# After a smoke: what Phase 4.5 might fix (the lanes print this themselves)
python3 scripts/integration/suggest_p45.py MODEL RUN_NAME

# Phase 5: a campaign manifest, dry run first
python3 /mnt/shared/scripts/benchmarks/run_campaign.py campaigns/NAME.json --dry-run
rigctl run-start --run NAME --resume "python3 /mnt/shared/scripts/benchmarks/run_campaign.py campaigns/NAME.json --run-id NAME" -- \
    python3 /mnt/shared/scripts/benchmarks/run_campaign.py campaigns/NAME.json --run-id NAME --max-active-models 3
```

Placements in a campaign: `brain` (the 3090), `single` (any free worker card), `split` (any free pair),
or pinned cards (`gpu_3`, `gpu_2_4`). Reasoning is scored leniently (extract v5: a correct answer counts
however it is written; unreadable answers are counted separately), see
`docker/bench-reasoning/BENCH_REASONING_HISTORY.md`.

## Results

- `results/model_benchmark_records.jsonl`: the append-only ledger every suite writes to
  (`scripts/active/record_benchmark_result.py`)
- `results/MODEL_BENCHMARK_REFERENCE.md`, `results/model_library_scoreboard.json`,
  `results/model_methodology_history.json`: generated from the ledger on every record
- `results/runtime_experiments/`: speed, power and runtime measurements (power cap sweeps, runtime
  characterizations)
- Raw run outputs (samples, logs): `/mnt/shared/logs/benchmarks/` on the drive, not in git
- `scripts/active/rescore_reasoning_records.py`: re-score past runs from their samples after a scoring change
- `results/imported_lessons/<repo>/`: the other repos' lessons folders, copied by
  `scripts/active/collect_lessons.py` (with `MANIFEST.json`: from where, which commit, when)

## Sharing with the other repos

Each of the four repos runs without the others. Benchmarking's lessons go out through the model library:
every other repo has its own importer that reads `model_registry.json` and `model_roles.json` and writes its
own copy (llm-gateway `tools/generate_profiles.py`; llm_orchestration and llm-harness to build). Their lessons
come back through their `lessons/` folders, which `collect_lessons.py` copies here when wanted. Nothing here
writes into another repo, and no other repo reads this one at runtime.

## Layout

- `scripts/active/`: the implementations; root-level `*.py` files forward there
- `scripts/integration/`: lane tools (litmus, runtime characterization, Phase 4 and 4.5, suggestions)
- `docker/bench-*/`: one folder per suite (Dockerfile, `run.sh`, README, history)
- `campaigns/`: campaign manifests; `runtime_matrices/`: controlled runtime definitions
- `custom_tasks/`: local custom tests; `tests/`: unit tests (`python3 -m unittest discover tests`)
- `repos/`: cached upstream benchmark repos; `archive/`: older docs, reports and scripts
