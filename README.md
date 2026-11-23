# Benchmarking

Benchmarking measures local models and runtimes: quality, speed, memory, power, context, and concurrent chats. It owns the model registry, roles, load recipes, test suites, campaigns, and result records. Gateway imports its reviewed evidence for model offers; live scheduling and hardware reservations belong to Gateway and Orchestration.

`load_recipes.json` records evidence-linked configurations. Reviewed model profiles become Gateway offers through its explicit offer generator and sync; a research recipe ID alone never launches a runtime.

## Project map

Big Bertha runs across a Pi control host, an isolated GPU rig, and optional CPU workers. Four repositories divide the system's work:

| Repository | Responsibility |
|---|---|
| [llm-gateway](https://github.com/bigbertharig/llm-gateway) | Serves the dashboard, conversations, model API, tool policy, and work coordination. Its Manager also coordinates some model placement and loading. |
| [llm_orchestration](https://github.com/bigbertharig/llm_orchestration) | Observes and controls rig hardware, enforces admission and reservations, and manages model runtimes. |
| [benchmarking](https://github.com/bigbertharig/benchmarking) | Measures models and runtimes; publishes the model library, roles, load recipes, evaluation suites, and results. |
| [llm-harness](https://github.com/bigbertharig/llm-harness) | Builds the default project-owned tool and agent layer and defines the integration contract for additional harness engines. |

Benchmarking publishes a validated model library. Gateway imports it, serves model routes, and manages dashboard work. Harness supplies reviewed tool schemas and tests model interactions through Gateway routes. Orchestration enforces rig hardware rules and runs admitted model services. [The work-organization guide](https://github.com/bigbertharig/llm-gateway/blob/main/docs/WORK_ORGANIZATION_DIRECTION.md) tracks the remaining Manager-to-Orchestration migration.

Private site configuration supplies host addresses, credentials, model files, and mounts. The published examples use role placeholders. For another card mix, run a hardware survey and validate fit, context, concurrency, and speed before offering a load recipe. The four repositories are joined by versioned artifacts and APIs rather than cross-repo code imports; [the cross-repo contract](CROSS_REPO_CONTRACT.md#portability-and-replaceable-implementations) defines the extension boundaries and the [porting guide](https://github.com/bigbertharig/llm-gateway/blob/main/docs/PORTABILITY.md) gives installation steps.

## Read this repo

- [New model integration](NEW_MODEL_INTEGRATION.md): registry, roles, validation gates, and evidence status.
- [Model selection](MODEL_SELECTION.md): one guide to the current registry, roles, scores, and recipes.
- [Cross-repo contract](CROSS_REPO_CONTRACT.md): what evidence is exported and what live state belongs elsewhere.
- [Benchmark reference](results/MODEL_BENCHMARK_REFERENCE.md): generated model scores and their source records.

## Start by task

| Task | First guide |
|---|---|
| Survey a different rig | Run `rig scan` on the rig, then [rig limit test](RIG_LIMIT_TEST.md) with the Manager and rig installed, then [model loading and chat placement](MODEL_LOADING_AND_CHAT_PLACEMENT.md) |
| Add or validate a model | [New model integration](NEW_MODEL_INTEGRATION.md) |
| Choose a tested model | [Model selection](MODEL_SELECTION.md) |
| Understand an existing load recipe | [Model loading and chat placement](MODEL_LOADING_AND_CHAT_PLACEMENT.md), then [cross-repo contract](CROSS_REPO_CONTRACT.md) |

## Documentation index

| Doc | For |
|---|---|
| [EXTERNAL_REPOS.md](EXTERNAL_REPOS.md) | outside runtimes and source projects, local revisions, and update checks |
| [MODEL_LOADING_AND_CHAT_PLACEMENT.md](MODEL_LOADING_AND_CHAT_PLACEMENT.md) | GPU/RAM/storage model placement, independent chat state, measured layouts, and promotion to Manager |
| [NEW_MODEL_INTEGRATION.md](NEW_MODEL_INTEGRATION.md) | model validation phases from download to full run (2 load, 3 litmus, 3.5 runtime, 4 smoke, 4.5 optional settings experiments, 5 full run, 6 finalize), with decision trees for common failures |
| [MODEL_SELECTION.md](MODEL_SELECTION.md) | current selection entry point and source map |
| [results/MODEL_BENCHMARK_REFERENCE.md](results/MODEL_BENCHMARK_REFERENCE.md) | every model's scores (generated from the records) |
| [docker/README.md](docker/README.md) | the main evaluation suites; each `docker/bench-*/` has its README and run history |
| [suites/vision/README.md](suites/vision/README.md) | frozen local image-understanding smoke/full cases and the separate generation track |
| [docker/CAMPAIGN_RUNNER.md](docker/CAMPAIGN_RUNNER.md) | Benchmarking-owned deterministic campaign runner and managed submission |
| [scripts/integration/README.md](scripts/integration/README.md) | the lane tools for Phases 3-4.5 |
| [RIG_PERFORMANCE.md](RIG_PERFORMANCE.md) | how fast the rig runs models and why: card vs bus, splits, context capacity, PCIe; open questions; which tool measures what |
| [RIG_LIMIT_TEST.md](RIG_LIMIT_TEST.md) | guarded small or deep rig survey and its starting-guidance report |
| [SYNTHETIC_WORK_SCAN.md](SYNTHETIC_WORK_SCAN.md) | model-free weight, expert, KV, lookup, and shared-bus work classes; run presets and limits |
| [REPEATABLE_RIG_EXPERIMENTS.md](REPEATABLE_RIG_EXPERIMENTS.md) | repeatable runner contract for depth, placement, Strata, expert tensor, and transfer tests |
| [TEST_RUNNER_GUIDE.md](TEST_RUNNER_GUIDE.md) | how to create a new experiment runner, when to use a direct loader, and how to reuse the managed sequence |
| [EXPERIMENT_RUNNER_INVENTORY.md](EXPERIMENT_RUNNER_INVENTORY.md) | the recent Strata, expert, PLE, and chat entry points and their internal runner destinations |
| [EXPERT_TENSOR_SHARDING_RESEARCH.md](EXPERT_TENSOR_SHARDING_RESEARCH.md) | tiered expert execution evidence, repo boundaries, hardware/model analysis and full-model research gates |
| [EXPERT_TENSOR_PLACEMENT_TEST_PLAN.md](EXPERT_TENSOR_PLACEMENT_TEST_PLAN.md) | model choice, admission gates and matched VRAM/RAM/storage placement controls |
| [CONTEXT_PROFILE_AUDIT_2026-10-26.md](reports/CONTEXT_PROFILE_AUDIT_2026-10-26.md) | active and candidate model context bounds, working defaults, and read-only card-fit projections |
| [CONTEXT_CAPACITY_CAMPAIGN_2026-10-26.md](reports/CONTEXT_CAPACITY_CAMPAIGN_2026-10-26.md) | compact baseline and trained-ceiling test matrix and receipts |
| [results/RUNTIME_REFERENCE.md](results/RUNTIME_REFERENCE.md) | every speed, capacity and power measurement (generated from `results/runtime_experiments/`) |
| [BENCHMARK_LESSONS_LEARNED.md](BENCHMARK_LESSONS_LEARNED.md) | lessons from prior runs |

Ordinary model loads are requested through Gateway. Its current Manager still
handles some admission and placement; the orchestration-owned rig layer enforces
hardware rules and reports readiness. Complete-capacity reservations and placement
are moving to that layer. Benchmarking never infers current availability from its
static recipes.
Experimental Strata and tensor probes may launch an unsupported engine directly
under a Manager run and card claim; see [TEST_RUNNER_GUIDE.md](TEST_RUNNER_GUIDE.md).
The suites run on the rig against a mounted copy of this repo; the mount path is deployment-specific.

For a standalone `lm-eval` task, load the model through `rigctl load-model --use benchmark --json`
first and use its ready route in `scripts/active/run_lm_eval_task.py --model-args`.
Pass `--model-id` with the canonical key from `model_registry.json`; the served route may be a
profile name and must not become the ledger's model ID. The runner rejects missing model or endpoint
arguments and writes `run_context.json` beside its result with the canonical ID, served route,
benchmark ID, registry hash, and imported tool-catalog source hash. The receipt excludes API keys.

## The model library

The [cross-repo contract](CROSS_REPO_CONTRACT.md) defines model, tool, and live-state
ownership. Edit these source files, then run `scripts/active/model_library.py export`
and `scripts/active/export_model_library.py sync` (and `check` for both):

- `model_registry.json`: every tested model: status, archive GGUF, source URL, scheduling, named profiles
  (`default` = benchmark settings, `interactive` = gateway use, `orchestration`, and optional variants such
  as `thinking`)
- `model_roles.json`: which model and profile per rig lane and job (what other repos read)
- `load_recipes.json`: passive, evidence-linked experimental and validated load
  layouts imported by the gateway; they are not executable Manager offers

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
`schedule.placement` label for fit. That label remains in imported model metadata; it is not a hardware admission rule.
Keep measured load time and memory observations in
[RIG_PERFORMANCE.md](RIG_PERFORMANCE.md) and
[results/RUNTIME_REFERENCE.md](results/RUNTIME_REFERENCE.md), with the JSON
receipts behind them, rather than fixed card-count recipes in the registry.

Generated from the registry (do not edit): `models.catalog.json`, `model_tuning_profiles.json`,
`custom_tasks/model_prompt_profiles.json`.
`model_library_export.json` is the versioned, hash-checked interchange artifact. Gateway,
orchestration, and harness import it instead of importing benchmarking Python or reading
its source files directly. Importing a model describes what can be planned; the gateway's
ready roster and rig status APIs describe what is callable and running now.

## Harness tool capability input

The harness owns the versioned dashboard tool catalog. For model/tool trials, import its
`tools/dashboard_tool_catalog.json` with `python3 scripts/active/sync_harness_tools.py --source PATH what-new|sync|check`.
The local `tool_catalog.json` records the source hash and import time; tests and receipts
should pin that hash alongside canonical model ID, served route, tool name, valid call,
result, and answer quality. This snapshot is a test input, not a runtime tool registry.
The gateway imports the same harness artifact independently for dashboard use.

## Running benchmarks

For code changes, use the repository environment and the smallest relevant named suite. The full suite remains the release check:

```bash
.venv/bin/python tools/run_test_suite.py --list
.venv/bin/python tools/run_test_suite.py model_library campaigns
.venv/bin/python -m pytest -q
```

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

# Phase 5: a campaign manifest, dry run first. Set this to the checkout path
# visible on the rig; a local checkout works as well as a shared-drive mount.
RIG_BENCHMARKING_ROOT=/path/to/benchmarking
python3 "$RIG_BENCHMARKING_ROOT/scripts/active/run_campaign.py" \
  "$RIG_BENCHMARKING_ROOT/campaigns/NAME.json" --dry-run
rigctl run-start --run NAME --auto-resume -- \
  python3 "$RIG_BENCHMARKING_ROOT/scripts/active/run_campaign.py" \
  "$RIG_BENCHMARKING_ROOT/campaigns/NAME.json" --run-id NAME
```

Campaign blocks omit `gpus` for manager placement or use explicit `gpus: [0, 2]`
for a pinned experiment. The current rig inventory comes from `rig scan`.
Reasoning scoring and prior campaign receipts are in
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

Benchmarking publishes the validated `model_library_export.json` artifact with
`python3 scripts/active/export_model_library.py sync`. Gateway, Orchestration, and Harness each explicitly
import a hash-checked local projection; none reads Benchmarking's checkout during ordinary runtime.
Gateway's importer turns reviewed evidence into model offers, while live fit and readiness remain separate.
The other repos record their own lessons, which `collect_lessons.py` can copy here for review.
See [the cross-repo contract](CROSS_REPO_CONTRACT.md) for the artifact, import commands, and live-state boundary.

## Layout

- `scripts/active/`: the implementations; root-level `*.py` files forward there
- `scripts/integration/`: lane tools (litmus, runtime characterization, Phase 4 and 4.5, suggestions)
- `docker/bench-*/`: one folder per suite (Dockerfile, `run.sh`, README, history)
- `campaigns/`: campaign manifests; `runtime_matrices/`: controlled runtime definitions
- `custom_tasks/`: local custom tests; `tests/`: unit tests (`python3 -m unittest discover tests`)
- `repos/`: cached upstream benchmark repos; `archive/`: older docs, reports and scripts
