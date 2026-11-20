# Unified Campaign Runner

`/mnt/shared/scripts/benchmarks/run_campaign.py` is the only production
benchmark scheduler. It uses `docker/suite_contracts.json` to run sequential or
parallel suite blocks with one model-loading and checkpoint contract. Models are
placed and loaded by the rig manager (`rigctl load-model --use benchmark`), which
puts the rig in bench mode (isolated modes, 2026-10-23; see
[CAMPAIGN_RUNNER_REFACTOR.md](CAMPAIGN_RUNNER_REFACTOR.md)).

Before a campaign, publish the benchmarking model export and run
`python3 /mnt/shared/scripts/sync_model_library.py sync`. The runner reads the
imported model snapshot and tuning profiles under `/mnt/shared/agents`.

## Simple model-and-suite request

Use the Benchmarking request compiler when you want a set of registered models
to run the same tests without hand-authoring card placement or block order:

```json
{
  "name": "candidate_screen",
  "models": ["ministral-3:3b", "qwen3.5:4b"],
  "tests": [
    {"suite": "bench-reasoning", "tasks": ["gsm8k", "drop"], "limit": 10},
    {"suite": "bench-knowledge", "tasks": ["academic"], "limit": 10}
  ],
  "run_class": "smoke"
}
```

```bash
python3 scripts/active/submit_campaign_request.py request.json \
  --pi-shared-root /media/bryan/shared --rig-shared-root /mnt/shared \
  --rigctl /home/bryan/llm-gateway/tools/rigctl.py
```

The submit command reads `model_registry.json` and `suite_contracts.json`. It accepts
active and candidate models, refuses an explicitly unfinished `loading_stage`,
and checks suite task selectors and limit support. Existing registry models
without a loading-stage record remain available for explicit tests. It emits
consecutive suites in one runtime group per model so the runner reuses a load;
different model groups may run concurrently if the rig admits them. The
request contains no GPU IDs. It writes the compiled manifest and a submission
receipt under the shared `plans/shoulders/benchmarking/campaigns/requests/`
directory, then calls Gateway's `rigctl run-start --auto-resume`. The output is
a normal campaign-v1 manifest, so the checkpoint and resume behavior below
applies unchanged. The manager's run
record reports one terminal outcome; the runner writes an atomic `status.json`
and raw suite receipts. `scripts/integration/wait_for_campaign_completion.py`
can deliver a single completion alert from the receipt's `pi_status` without
repeated LLM status calls:

```bash
python3 scripts/integration/wait_for_campaign_completion.py \
  /media/bryan/shared/logs/benchmarks/campaigns/history/candidate_screen/RUN_ID/status.json
```

Start the waiter after the run creates its status directory. Gateway does not
yet expose this simple request as one submission API or push its terminal alert
to the dashboard.

## Commands

```bash
python3 /mnt/shared/scripts/benchmarks/run_campaign.py campaign.json --dry-run --verbose
python3 /mnt/shared/scripts/benchmarks/run_campaign.py campaign.json --run-id run_001
python3 /mnt/shared/scripts/benchmarks/run_campaign.py campaign.json --run-id run_001
```

The final command resumes the same run. Additional controls:

```text
--on-failure continue|stop
--limit-override N
--limit BLOCK_ID=N
--verbose
```

The rig reaches the Pi manager through key-only SSH on the isolated
<rig-subnet> Ethernet network. The Pi firewall admits SSH on that network;
preflight should verify this route before scheduling model loads.

Limit priority is block override, global override, manifest `limit`, then suite
default. An override fails preflight for suites whose contract does not support
bounded runs.

## Manifest

A block names a registry model; the manager loads it from `model_registry.json` (its GGUF, the
library's one runtime image, the profile's context, batch and extra args). A manifest carries only what
it overrides. Campaign blocks supply model IDs and optional profile/context/placement overrides; GGUF paths live in the registry.

```json
{
  "name": "model_import_smoke",
  "defaults": {
    "run_class": "smoke"
  },
  "blocks": [
    {
      "id": "data",
      "model": "model-id",
      "suite": "bench-dataimport",
      "suite_args": ["--tasks", "converter,reference"],
      "limit": 2
    },
    {
      "id": "geometry",
      "model": "model-id",
      "gpus": [0],
      "suite": "bench-geoimport",
      "suite_args": ["--tasks", "classification,prep_plan"],
      "limit": 2,
      "depends_on": ["data"]
    }
  ]
}
```

Required block fields are `id`, `model`, and `suite`. Optional fields:

| Field | Default | Meaning |
| --- | --- | --- |
| `gpus` | none: the manager picks | Pinned cards, e.g. `[0, 1, 2, 3]`; `placement: brain` (GPU 0) and `placement: gpu_1_3` mean the same. `single` and `split` are gone |
| `suite_args` | `[]` | Suite-owned flags only |
| `run_class` | default or `provisional` | Evidence class; no score gate is imposed |
| `limit` | suite default | Bounded sample count where supported |
| `depends_on` | `[]` | Completed prerequisite block IDs |
| `ctx_size` | the registry profile's | Exact context to load at (bench mode loads the profile's otherwise) |
| `profile` | `default` | Registry profile to load (e.g. a `thinking` variant) |
| `runtime_args` | none | llama-server arguments after the profile's own `extra_args` |
| `wait_s` | 7200 | How long the load may wait for busy cards (the manager collects them); -1 waits forever |
| `hardware_id` | derived from the cards | Optional explicit hardware identity |
| `env_file` | none | Optional, only for suites that declare support |
| `runtime_group` | none | Keep one compatible model runtime loaded across consecutive suite blocks |

Do not put `--model`, `--runtime-base`, `--run-name`, `--run-class`, output
paths, profile paths, hardware identity, or GGUF paths in `suite_args`. The
runner owns them.

## Supported Suites

The live suite list and capabilities come from `suite_contracts.json`:

- `bench-pipeline`
- `bench-code`
- `bench-reasoning`
- `bench-knowledge`
- `bench-dataimport`
- `bench-geoimport`
- `bench-agent`
- `bench-routing`
- `bench-runtime`
- `bench-daedalmap`

`bench-code`, `bench-pipeline`, and `bench-runtime` currently do not support a
generic `--limit`. `bench-code` runs the selected EvalPlus problem sets in full.

## Profiles

Benchmarking resolves `model_tuning_profiles.json` through
`scripts/active/model_profiles.py` when it publishes the model export. The runner
uses the imported resolved profiles under `/mnt/shared/agents`; suite containers
receive the matching imported tuning file. Aliases inherit the canonical profile,
then apply explicit alias overrides. Ambiguous matches, missing alias targets,
alias cycles, and missing required system prompts fail before a model is loaded.

The profile policy is suite-specific and declared in `suite_contracts.json`.
Some frozen harnesses intentionally own their prompts and do not inject a model
system prompt.

## One Load, Multiple Suites

Give consecutive blocks the same `runtime_group` to load a model once, run each
suite in manifest order on the same runtime, and unload after the final block.
Every block in the group must have identical model, GGUF, profile, cards, context,
runtime arguments and wait. The runner rejects mixed settings before loading.

Runtime-group order is independent of score or suite success. With
`--on-failure continue`, a failed suite is recorded and the next suite still
runs on the loaded model. With `--on-failure stop`, the campaign stops at the
failure. On resume, a group whose earlier blocks are already complete loads the
model once at its first unfinished block.

## Scheduling

The runner keeps no model of the rig. For each runtime group it asks the manager to load the model
(`rigctl load-model MODEL --use benchmark --json --owner campaign-<run-id> --wait <wait_s>`, plus `--gpus`,
`--ctx`, `--profile`, `--args` only when the block sets them) and runs the group's suites against the port
the manager answers with. With no cards named the manager picks the fewest that hold the model at its
profile's context (it placed Nemotron 3.5 Bolt on GPUs 0-3); busy cards are waited for and collected as
they free. A refusal (won't fit, the rig busy in another mode, cards never freed) fails the block with the
manager's reason. The group's model is unloaded (`rigctl unload <profile>`) after its last block, and a
finished or stopped campaign runs `rigctl cancel-owner campaign-<run-id>` so nothing it asked for remains.

One load request is in flight at a time: the rig loads one model at a time anyway, and two multi-card loads
collecting cards together could each hold cards the other needs. Loaded groups run side by side on
whatever cards the manager gave them; `--max-active-models` caps how many. `depends_on` supplies strict
ordering when required.

## Preflight and Resume

Before loading a model the runner verifies:

- manifest structure, placements and dependency references
- the registry's GGUF for each model, env-file existence
- model profile requirements
- suite limit policy and runner-owned flags
- suite image contract labels
- writable result roots and `/mnt/shared/cache/benchmarks`

`--dry-run` verifies the manifest and command contract, but does not probe the
live control hop or the manager's GPU safety guard. On 2026-11-15 it passed while
rig-to-Pi SSH was blocked, and again while four GPUs were unavailable after
Xid 79 faults. Check the manager guard, selected cards, and direct rig-to-Pi
SSH before a live campaign. A reusable campaign-readiness check belongs in
benchmarking and could later be exposed through `rig_info` for agents.

Containers receive an explicit temporary `HOME` and a persistent shared
Hugging Face cache under `/mnt/shared/cache/benchmarks`. This avoids root-home
permission failures and reuses frozen dataset downloads across model runs.

Campaign status and checkpoints are under:

```text
/mnt/shared/logs/benchmarks/campaigns/history/<campaign>/<run_id>/
```

Completed blocks are skipped on resume. Blocks interrupted during load or suite
execution restart from the beginning. Dry runs do not create or consume a
checkpoint.

## Adding a Suite

Follow `docker/SUITE_CREATION.md`. A suite is not campaign-compatible until it
is registered and `python3 scripts/active/validate_suite_contract.py` passes.

## Live contract checks (2026-11-15)

The `contract_live_smoke.json` run `contract-live-smoke-20261115d` completed one
Ministral 3B reasoning case on GPU 3 with the imported system prompt. The earlier
`...a` and `...b` attempts exposed a blocked rig-to-Pi SSH path and GPU Xid 79
faults. The `...c` suite completed but its prompt resolver failed because the
imported tuning file was mounted outside `/benchmark-scripts`; do not compare its
score with prompt-correct runs. The runner now mounts that file inside the suite
source tree.

`contract_bounded_suites_live.json` run `contract-bounded-live-20261115a`
completed one case each in reasoning, knowledge, data import, geo import, agent,
routing, and DaedalMap JSON discipline, reusing one manager-owned GPU 3 load.
`contract_second_card_live.json` run `contract-second-card-20261115a` completed
one reasoning and one geo import case using Gemma 4 E4B on GPU 2. Both campaigns
verified the served GGUF before running suites and released their model lease.
These limit-one runs establish integration behavior, not model performance.
`contract_multicard_live.json` run `contract-multicard-20261115a` loaded
Qwen3 Coder 30B A3B on GPUs 1–5, verified the GGUF and imported prompt, ran one
reasoning case, and released all five cards. GPU 0's separate chat claim was
left in place. Its 18 GB GGUF spent about four minutes loading from shared
storage; that interval is startup evidence, not a benchmark score.
`contract_operational_live.json` run `contract-operational-20261115a`
completed the runtime stability, TTFT, throughput, and context probes with no
request failures, then ran one `custom_json_schema_strict` pipeline test using
the same load. That test executed all 13 checks and scored 0/13 for this model;
the campaign status `completed` means the suite ran, not that the model met a
quality threshold. `bench-code` was dry-run contract-checked but not run live:
its smallest selectable task is the full 164-problem HumanEval set and the
suite guide estimates 20–40 minutes.
