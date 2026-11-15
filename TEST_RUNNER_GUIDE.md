# Test runner guide for rig experiments

Use this guide when a test changes model size, card placement, context depth,
Strata expert budget, tensor residence, or transfer path. The goal is to put
the scientific question in a manifest and keep executable code reusable across
models and cards. The [repeatable-experiments contract](REPEATABLE_RIG_EXPERIMENTS.md)
defines the case types, common receipts, and comparison rules. The
[runner inventory](EXPERIMENT_RUNNER_INVENTORY.md) maps the recent scripts to
their internal destinations. These are benchmarking procedures and code, not
tools offered to gateway, harness, or orchestration. A future cross-repo tool
surface needs its own use case and contract review.

For Strata requests, use [STRATA_RUNNER_GUIDE.md](STRATA_RUNNER_GUIDE.md) to
resolve the question, pack, placement mechanism, memory tier, and comparison.
For expert tensor or PLE placement requests, use
[EXPERT_TENSOR_RUNNER_GUIDE.md](EXPERT_TENSOR_RUNNER_GUIDE.md) to separate
component, transfer, and full-model evidence.

## Why this guide exists

From November 1 through November 15, 2026, `git log --diff-filter=A -- scripts`
shows 90 new script files in benchmarking. Forty-three are new `run_*.py` or
`run_*.sh` entry points: 15 Strata, 8 expert/PLE/transport, 16 Qwen/BigMoe
chat and traces, and 4 other. This counts entry points by filename, not 43
duplicate implementations; some are reusable probes and some are independent
scientific controls. It does show that repeated settings and lifecycles have
been landing as new launchers. The last week added 34 script files total.

## From a rough request to a runnable case

Treat a natural-language request as an experiment draft. Resolve it against
the model library, supported engine recipes, current hardware inventory, and
existing fixtures before compiling a case. Ask only for choices that change
the scientific question or cannot be inferred from those sources. A request
is runnable once these fields have an explicit value and source:

| Field | Resolve from request or existing source | Ask when |
|---|---|---|
| Subject | canonical model ID, exact quant/pack and artifact hash; component ID for tensor probes | model size/name matches several artifacts, model is absent, or requested engine does not support it |
| Engine and load path | supported orchestration recipe through Manager, or experimental adapter with reason and pinned build | the named engine and model are incompatible or the user must choose whether to test an unsupported build |
| Question and result class | fit/health, speed, recall/quality, chat isolation, component correctness, or transfer cost | “test” leaves the success criterion unclear beyond a first smoke |
| Placement | physical GPU roles and which bytes are intended for GPU, host RAM and storage | “mostly RAM”, “on the 3090”, or similar wording could refer to weights, experts, KV, or additional worker cards |
| Scenario | context/reservation, occupied tokens, prompt or saved state, output cap, cold/warm policy and repetitions | a benchmark comparison is requested but no comparable fixture or settings exist |
| Control | baseline placement or budget, varied dimension, order and allowed drift | the user asks whether a change is faster/better but has not identified the comparison |
| Safety | Manager claim, memory/swap floor, timeout, output location and cleanup | these cannot be derived from the runner's standard guard or rig scan |

For a fit/health smoke, use the model's tested working profile and the standard
short fixture when available; label the result a smoke. For speed or quality,
do not substitute a convenient prompt, context, quant or engine without making
the choice explicit. The runner records defaults and their source in the
resolved case. Missing optional telemetry does not block a run but appears as
unavailable in the receipt. A failed compatibility or memory preflight writes
a failed/blocked receipt without starting an engine.

Ask a compact question with plausible choices from the model library. For
example, “Strata on a 70B model, majority RAM and the 3090” first requires
the exact compatible model/pack: the [Strata model catalog](https://github.com/Niko1221/Strata/blob/main/docs/MODELS.md)
checked on 2026-11-15 does not list a 70B family, while the rig's Llama 3.3
70B experiments use llama.cpp. Do not
switch engines or models silently. Next clarify whether “majority RAM” means
weight/expert residency or KV, and whether the 3090 is the only GPU. If the
user only wants to see whether it loads, run a guarded fit/health smoke after
those choices. If they want a speed claim, also settle the workload and
baseline. Each clarification becomes a case field and appears in the receipt.

The current schema-3 compiler checks experiment kind, load path, case order,
variables and direct-load justification. It does not yet resolve prose,
validate Strata model support, or prove actual tensor residency. Those are
preflight responsibilities of the future Strata adapter and the human intake
step until that adapter exists.

## The load boundary

Normal published-model test:

```text
benchmark case -> gateway Manager fit/admission/claim -> rig plan item
               -> orchestration-owned rig runtime command/readiness/cleanup
               -> ready route -> benchmark requests/measurements
```

Benchmarking must not maintain its own card allocator or duplicate llama.cpp
load flags for this path. Ask the gateway Manager for a canonical model ID,
profile/recipe, context, and optional explicit card constraint when the card
is the experimental variable. Record its fit, actual GPU UUIDs, load receipt,
served route, and cleanup. `capacity_run.py` already uses `rigctl fit`,
`load-model`, and `unload`; Phase 5 campaigns and worker lanes also load
through the Manager. The Manager controls admission; the rig's plan service
and runtime scripts in orchestration execute the physical load. The
orchestration status API consumes prepared *work plans* and is not a second
benchmark load API. Follow the cross-repo communication contract on the Pi
(`~/Desktop/cross repo communication contract.md`) for recipe ownership; its
proposed recipe-to-runtime mapping is still open.

Experimental loader, only when the Manager/orchestration recipe cannot express
the tested behavior (unregistered Strata packs or placements, expert tensor
kernels, PLE row shards, altered engine builds):

```text
benchmark case -> Manager run and claim for selected physical GPUs
               -> benchmarking engine adapter plan/launch/verify/measure/stop
               -> receipt with exact build, inputs, placement, and cleanup
```

Never bypass Manager admission because the loader is unusual. A direct loader
must select cards by the session's physical UUID/PCI bus, verify the effective
CUDA mapping, and leave a terminal receipt on failure. It may manage the
experimental engine itself; it must not write an alternative lease database.
Once a special load mode has passed repeatability and readiness checks, give
it a stable recipe ID and implement the hardware command in orchestration.
Benchmarking keeps the protocol and evidence, while subsequent tests use the
normal managed path.

## Before writing a new runner

1. Write one sentence stating the variable and the measured outcome. Identify
   whether this is a full-model result, a chat-state test, a component proof,
   or a transfer microbenchmark.
2. Choose an existing case type: `model_fit`, `depth_replay`, `paired_replay`,
   `service_replay`, `chat_sequence`, `component_probe`, `transfer_probe`.
   Existing `run_model_loading_sequence.py` runs the ordered session and
   `tier_trace.py` supplies common hardware phase samples.
3. Reuse an adapter if one already plans, starts, verifies, sends requests to,
   and stops that engine. If code must be added, put those engine operations in
   one adapter module, separate from the manifest's prompts, budgets, cards,
   and comparison. A new wrapper is justified for a genuinely new engine or
   transport, not for a new model, card, context, prompt, or resident budget.
4. Define a deterministic fixture or pinned saved chat state, model/pack and
   adapter hashes, engine build, context/KV/MTP settings, output cap, cache
   state, warmups, repetitions, hardware role constraints, and safety gates.
   Put all differing values in the manifest. Give each run and case unique
   output paths; never overwrite an old receipt.
5. State the control and comparison before running. For a card comparison,
   use A/B/A or an alternating order and report drift. For a RAM budget,
   compare independent loads and record physical reads. Check correctness
   separately from speed. A one-expert timing cannot claim full-model gain.

## Parameterized cases today

`scripts/integration/compile_experiment.py` expands schema-3 parameters into
the existing schema-2 sequence format. It substitutes `${variable}` in
commands, environment, GPU lists, and output paths; `{gpu:role}` is left for
the sequence runner's frozen hardware scan. Each case has `id`, `values`, and
optional `stage` overrides. Its `kind` must be one of the case types above;
`baseline` must name an earlier case. Every case declares `load_path` as
`managed` or `experimental`; experimental cases require a reason and selected
card roles for Manager admission. Expansion is deterministic, records the
source SHA-256, rejects missing variables and duplicate IDs, and keeps case
values in the comparison index.

The [Qwen35 replay example](campaigns/examples/qwen35_oneworker_replay.schema3.json)
declares common model/state/KV settings once and varies only the worker role
in 1060 -> 1070 -> 1060 order. It requires the already prepared 200K/250K
state files; preparation remains a separate case. Compile and preview:

```bash
python3 scripts/integration/compile_experiment.py \
  campaigns/examples/qwen35_oneworker_replay.schema3.json \
  --output /tmp/qwen35_oneworker_replay.schema2.json
python3 scripts/integration/run_model_loading_sequence.py \
  /tmp/qwen35_oneworker_replay.schema2.json --run-id qwen35-replay-check --check
```

For a live run, use `rigctl run-start` and a fresh run ID, with a session claim
covering the resolved cards. The generated schema-2 file is the immutable
execution input; keep both source and generated hashes with the result.
`--check` does no model load. The compiler reduces repeated manifests but
does not yet execute that Qwen-specific replay. If a similar new request arrives,
implement the needed adapter then; prior runs do not need to be replayed.

## Adapter contract

Every adapter takes a resolved case file and output directory. It writes a
running checkpoint and terminal receipt atomically, even after a failed plan,
fit, load, request, or cleanup. The required phases are:

```text
preflight -> acquire/admit -> plan -> load -> verify ready and placement
          -> warmup -> measure -> verify correctness -> stop/unload -> release
```

Use the Manager's load/unload for ordinary models. A direct adapter must show
why it needs its own launch and report the actual executable, container/build,
flags, model/pack hashes, GPU UUID/CUDA mapping, and resident tensor map.
Snapshot memory, swap and physical device reads around the measured phase;
time requests with a monotonic clock. Verify actual input/output token counts
and whether the answer passed the declared oracle. Cleanup runs in `finally`;
leaving a service loaded requires an explicit retained-service case and claim.

When a new Strata request needs a direct load, build the shared adapter around
plan, launch, health, request, metrics, and stop. Its case input should select model/pack,
context, KV, resident budget, MTP, GPU role, prompt/sequence, output cap, and
cache policy. If a new expert/PLE request needs code, use a common
container/build launcher with separate expert-invocation, packed-row lookup,
and bus-transfer measurement plugins. Do not merge their result classes.

## Promotion and cleanup

A new adapter needs a deterministic contract test, a no-load plan/preview, one
small rig smoke with a terminal receipt, and a verified unloaded/claimed end
state. Add a repeated control when making a comparative claim. Keep historical
raw receipts, fixtures, and a note that a past test used a retired runner and
results may vary under a new adapter. Retire one-off launchers without
converting or repeating their old cases. Implement reusable code when a new
request actually needs it.
