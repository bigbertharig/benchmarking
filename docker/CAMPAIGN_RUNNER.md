# Benchmark campaign runner

`scripts/active/run_campaign.py` is the Benchmarking-owned deterministic
campaign scheduler. It reads `docker/suite_contracts.json` and the local
Benchmarking model registry, groups suites by model, submits load requests
through Gateway's `rigctl` facade, and writes checkpoints and terminal receipts.
Orchestration resolves the local model, admits hardware and runs the model. The runner no longer reads a model
library mirror under `/mnt/shared/agents`.

Before submission from a source checkout, run `python3 scripts/active/export_model_library.py check`
and sync the reviewed export to any optional consumers through their normal import commands.
For a rig without a Benchmarking checkout, build the portable campaign package and
copy the zip to both the controller and rig, then extract it into a stable directory:

```bash
python3 scripts/active/build_campaign_bundle.py build /tmp/benchmarking-campaign.zip
python3 -m zipfile -e /tmp/benchmarking-campaign.zip /opt
python3 /opt/benchmarking-campaign/scripts/active/build_campaign_bundle.py verify /opt/benchmarking-campaign
```

The package contains the runner, submission entry point, registry, suite contracts,
model-library snapshot, and container-mounted suite inputs. It does not need Git
history or sibling source trees. The installed package verifies its own file hashes
before submission; the model-library source hash is checked against its canonical
contents. Use `--rig-campaign-package-root /opt/benchmarking-campaign` when
submitting from the controller package. The existing `--rig-benchmarking-root`
alias remains available for source checkouts. Managed campaigns still require
configured rig control and installed suite container images on the target rig. The scheduler
records each suite's exact Docker argv in new benchmark evidence for replay.
An extracted package writes its score ledger, generated reference, and scoreboard to
`/mnt/shared/logs/benchmarks/campaigns/history/<campaign>/<run_id>/`; it does not
require the older shared Benchmarking source checkout for recording. Source-checkout
campaigns keep their existing ledger path. Import package rows into a curated model
library only after reviewing the terminal and raw suite receipts. Rebuild the rig's
bench-code image from this checkout when updating its embedded run.sh; portable
package recording for that suite requires the revised image.

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
  --pi-shared-root /path/on/controller --rig-shared-root /path/on/rig \
  --rig-benchmarking-root /path/to/rig/benchmarking \
  --rigctl /path/to/gateway/tools/rigctl.py
```

The submit command reads `model_registry.json` and `suite_contracts.json`. It accepts
active and candidate models and checks suite task selectors and limit support.
Every requested model needs a `loading_stage`: `in_progress` permits diagnostic
`smoke` runs, while `provisional`, `validated`, and `full` require
`ready_for_benchmark`. A `blocked` model cannot be submitted. It emits
consecutive suites in one runtime group per model so the runner reuses a load;
different model groups may run concurrently if the rig admits them. The
request contains no GPU IDs. It writes the compiled manifest and a submission
receipt under shared runtime state at `logs/benchmarks/campaigns/requests/`
without modifying the Benchmarking source checkout, then calls Gateway's `rigctl run-start --auto-resume`. The output is
a normal campaign-v1 manifest, so the checkpoint and resume behavior below
applies unchanged. Orchestration's run record reports one terminal outcome; the runner writes an atomic `status.json`
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

To preview ordering and parallelism without reserving or loading hardware, emit
Gateway's narrow planning projection beside the normal campaign:

```bash
python3 scripts/active/build_campaign_request.py request.json \
  --output /tmp/campaign.json \
  --gateway-plan-output /tmp/campaign-plan.json
python3 ~/llm-gateway/tools/rigctl.py campaign-preview /tmp/campaign-plan.json
```

Benchmarking retains suite arguments, methodology, scoring, and receipts. The
projection contains only model/runtime groups, dependencies, fit intent, and
optional duration evidence. Gateway asks Orchestration for revisioned placement
alternatives and simulates them; neither command changes rig state. Orchestration
still rechecks all hardware rules when a future accepted plan is executed.

## Commands

```bash
python3 scripts/active/run_campaign.py campaign.json --dry-run --verbose
python3 scripts/active/run_campaign.py campaign.json --run-id run_001
python3 scripts/active/run_campaign.py campaign.json --run-id run_001
```

The final command resumes the same run. A live managed campaign samples the
Orchestration-owned hardware guard through `rigctl status --json --fresh` every 10 seconds.
Samples are appended with fsync to `guard_samples.jsonl` beside `status.json`,
and the latest sample is included in status. A fresh owner-reported `critical`
level stops the campaign, releases its owned work, and writes
`thermal_aborted` as the terminal status; cached controller copies do not
trigger this decision. Gateway forwards the owner status without setting
hardware thresholds. The owner publishes `rig-hardware-telemetry/1` with
`sampled_at` and `fresh`; a sample older than 30 seconds, an unavailable
guard, or a cached controller copy is treated as `unavailable`. New scheduling
pauses immediately. Three consecutive unavailable samples stop the campaign,
release its owned work, and write `telemetry_aborted`. The JSONL receipt retains
each attempt and its error, including the owner's per-GPU readings and available
memory. Orchestration owns the power and temperature thresholds.

Live acceptance on 2026-11-25 used an idle rig and a temporary 30 C critical
test threshold, then restored the site's 90 C threshold. The campaign observed
the owner's critical decision through the Pi, wrote `thermal_aborted`, and
released its owner without loading a model. The retired `rig_stress` driver
sampled per GPU every 500 ms and stopped all load at its default 88 C GPU or
95 C CPU threshold. Managed campaigns sample the owner every 10 seconds and
stop their own work; their JSONL is a durable policy receipt, not a substitute
for the retired driver's high-rate fan/clock diagnostics.

Additional controls:

```text
--on-failure continue|stop
--limit-override N
--limit BLOCK_ID=N
--verbose
```

The runner reaches the configured Gateway request facade over SSH. Gateway
forwards local-runtime operations to the Orchestration controller.
Set `BENCHMARK_GATEWAY_HOST` and `HARNESS_RIGCTL` for the deployment, then
verify that route before scheduling model loads.

Limit priority is block override, global override, manifest `limit`, then suite
default. An override fails preflight for suites whose contract does not support
bounded runs.

## Manifest

A block names a Benchmarking registry model. The runner uses `model_registry.json`
for its GGUF, runtime image, profile context, batch and extra args. Orchestration
resolves the corresponding imported profile and owns admission and loading. A
manifest carries only what it overrides. Campaign blocks supply model IDs and optional profile/context/placement overrides; GGUF paths live in the registry.

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
| `gpus` | none: Orchestration picks | Pinned cards, e.g. `[0, 1, 2, 3]`; `placement: brain` (GPU 0) and `placement: gpu_1_3` mean the same. `single` and `split` are gone |
| `suite_args` | `[]` | Suite-owned flags only |
| `run_class` | default or `provisional` | Evidence class; no score gate is imposed |
| `limit` | suite default | Bounded sample count where supported |
| `depends_on` | `[]` | Completed prerequisite block IDs |
| `ctx_size` | the registry profile's | Exact context to load at (bench mode loads the profile's otherwise) |
| `profile` | `default` | Registry profile to load (e.g. a `thinking` variant) |
| `runtime_args` | none | llama-server arguments after the profile's own `extra_args` |
| `wait_s` | 7200 | How long the load may wait for busy cards (Orchestration collects them); -1 waits forever |
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
resolves profiles from Benchmarking's own model registry; suite containers
receive its generated `model_tuning_profiles.json`. Aliases inherit the canonical profile,
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

The runner keeps no model of the rig. For each runtime group it requests an
Orchestration-owned model load through Gateway's `rigctl` facade
(`rigctl load-model MODEL --use benchmark --json --owner campaign-<run-id> --wait <wait_s>`, plus `--gpus`,
`--ctx`, `--profile`, `--args` only when the block sets them) and runs the group's suites against the port
Orchestration answers with. With no cards named Orchestration picks the fewest that hold the model at its
profile's context (it placed Nemotron 3.5 Bolt on GPUs 0-3); busy cards are waited for and collected as
they free. A refusal (won't fit, the rig busy in another mode, cards never freed) fails the block with
Orchestration's reason. The group's model is unloaded (`rigctl unload <profile>`) after its last block, and a
finished or stopped campaign runs `rigctl cancel-owner campaign-<run-id>` so nothing it asked for remains.

One load request is in flight at a time: the rig loads one model at a time anyway, and two multi-card loads
collecting cards together could each hold cards the other needs. Loaded groups run side by side on
whatever cards Orchestration admitted; `--max-active-models` caps how many. `depends_on` supplies strict
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
