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
| [EXPERT_TENSOR_SHARDING_RESEARCH.md](EXPERT_TENSOR_SHARDING_RESEARCH.md) | tiered expert execution evidence, repo boundaries, hardware/model analysis and full-model research gates |
| [EXPERT_TENSOR_PLACEMENT_TEST_PLAN.md](EXPERT_TENSOR_PLACEMENT_TEST_PLAN.md) | model choice, admission gates and matched VRAM/RAM/storage placement controls |
| [CONTEXT_PROFILE_AUDIT_2026-10-26.md](CONTEXT_PROFILE_AUDIT_2026-10-26.md) | active and candidate model context bounds, working defaults, and read-only card-fit projections |
| [CONTEXT_CAPACITY_CAMPAIGN_2026-10-26.md](CONTEXT_CAPACITY_CAMPAIGN_2026-10-26.md) | compact baseline and trained-ceiling test matrix and receipts |
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

The model's GGUF and runtime options are load requirements. Each current model's
default profile also records `context_bounds.min` (a provisional planning floor)
and `context_bounds.max` (the GGUF trained ceiling). Neither is a measured
compact baseline or proof of quality at full depth. `runtime.ctx_size`
remains the working default. The manager can currently plan at the floor
or project the maximum that fits selected cards; the intended compact
baseline is the highest validated context on the smallest preferred
homogeneous GPU group. See the context audit and gateway MANAGER.md. Context is a
request or profile target; the manager derives memory and chooses cards and
`tensor_split` at load time. It does not read the registry's legacy
`schedule.placement` label for fit. That label still feeds the generated
orchestration catalog and dashboard until their placement path is untangled.
Keep measured load time and memory observations in
[RIG_PERFORMANCE.md](RIG_PERFORMANCE.md) and
[results/RUNTIME_REFERENCE.md](results/RUNTIME_REFERENCE.md), with the JSON
receipts behind them, rather than fixed card-count recipes in the registry.

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

## Current-model limit-50 coverage (2026-10-26)

The identity-verified rerun `modern-brain-revalidate-20261025-r3`
completed GSM8K, DROP, IFEval and runtime for Qwen3.5 27B,
Qwen Coder 30B and Devstral 24B. It repaired those reasoning
comparisons, not a full six-suite Phase 5 run.

The five-model gap-fill campaign `current-models-l50-gapfill-20261026`
completed 5/5 on the rig. All five produced validated 50-sample
GSM8K, DROP and IFEval records with verified served-model identity.
Selected flexible/loose scores from that initial campaign are percentages
(the corrected Ministral DROP result follows):

| Model | GSM8K | DROP | IFEval |
| --- | ---: | ---: | ---: |
| Gemma 4 E2B Q8 | 68 | 56 | 76 |
| Gemma 4 E4B | 80 | 80 | 92 |
| MiniCPM5 2B | 78 | 46 | 86 |
| Ministral 3B | 72 | 24 | 52 |
| Qwen2.5 Coder 7B | 68 | 72 | 66 |

The follow-up `ministral-split-drop-l50-20261026` completed the
missing DROP rows for Ministral 14B (EM 56%, flexible 60%) and 8B
(EM/flexible 24%). All 24 scoped current role/recent candidate models
now have the three limit-50 metric rows. The Ministral DROP scores
were affected by the task's newline stop. The corrected validated
limit-50 reruns used a 512-token cap and a nonoccurring stop sentinel.
Flexible DROP rose from 24% to 74% for 3B, 24% to 76% for 8B, and
60% to 72% for 14B; all three had zero unreadable outputs. These
reruns have a separate config ID/hash. See
[docker/bench-reasoning/BENCH_REASONING_HISTORY.md](docker/bench-reasoning/BENCH_REASONING_HISTORY.md).
The scope excludes four older unassigned active entries
(Llama 3.2 3B, Phi-4 Mini Reasoning, Qwen2.5 Coder 14B, SmolLM3 3B)
and archived/invalid models.

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
