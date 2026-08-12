# bench-geoimport

Tests whether a local brain model can prepare reviewable County Map
geometry/admin-spine artifacts before the cloud orchestrator performs QA.

## What It Tests

| Task | What is measured |
|---|---|
| `classification` | Strict admin spine vs sidechain vs blocked policy decision. |
| `prep_plan` | Executable local prep plan: approved acquisition, canonical scripts, isolated outputs, lightweight checks, and handoff. |
| `prep_handoff` | Correctly returns a reviewable candidate or blocks when preparation artifacts/checks are incomplete. |

The suite intentionally does not validate final geometry correctness. That
belongs to deterministic repo QA. This suite checks whether the model chooses
the right lane and refuses unsupported claims.

## Measurements

- strict JSON response;
- required keys present;
- required evidence concepts present, with accepted equivalent wording;
- prohibited completion claims absent from claim fields;
- average and per-case scores;
- non-gating historical reference markers at 0.90 average and 0.60 per case.

Capability scores do not make a benchmark run pass or fail. Only incomplete
execution, request, or parsing failures produce a nonzero suite exit.

Version 2 uses the Canada completion fixture to define which provenance,
counts, exclusions, metadata, and artifacts the prep handoff must expose. It
does not ask the local model to prove the full completion contract. The cloud
orchestrator evaluates candidate QA after this benchmarked stage; the trusted
main machine owns final QA, runtime, release, adoption, and publication gates.

The suite prioritizes operating the pipeline: selecting existing scripts,
planning acquisition/build steps, invoking deterministic validators, producing
artifacts, and responding correctly to script failures. Deep source semantics
remain useful evidence but are not the local-brain benchmark's primary weight.

## Model-Agnostic Contract

The cases, required concepts, enum values, and thresholds are fixed across
models. The harness normalizes harmless formatting differences such as JSON
fences and underscore/hyphen/space separators. It also gives each prompt the
allowed enum values so synonymous labels do not become accidental failures.

Per-model output discipline and inference defaults come from the shared
`model_tuning_profiles.json`. `--inference-config-json` may override
temperature, sampling, token budget, thinking, stop sequences, or JSON grammar
for a controlled run. Campaign manifests continue to own runtime settings such
as context size, GPU placement, and reasoning runtime flags. Model profiles may
not alter case content, required preparation concepts, or score thresholds.

Useful harness arguments:

- `--tuning-profiles`: shared model profile file; defaults to
  `/benchmark-scripts/model_tuning_profiles.json`.
- `--no-model-profile`: controlled suite-default run with no model profile.
- `--inference-config-json`: run-specific inference overrides.
- `--config-id` / `--config-json`: explicit configuration identity/evidence;
  the resolved model profile and inference settings are always recorded.

## Build

```bash
cd /mnt/shared/plans/shoulders/benchmarking/docker/bench-geoimport
docker build -t bench-geoimport .
```

## Smoke Run

```bash
docker run --rm --network host \
  -v /mnt/shared:/mnt/shared \
  -v /mnt/shared/logs/benchmarks/bench-geoimport/history:/results \
  -v /mnt/shared/plans/shoulders/benchmarking:/benchmark-scripts:ro \
  bench-geoimport \
  --model qwen3.6:27b \
  --runtime-base http://localhost:11434 \
  --tasks classification,prep_plan,prep_handoff \
  --limit 1 \
  --run-name qwen36_27b_geoimport_smoke_v1 \
  --run-class smoke
```

## Local Validation

```bash
python3 -m unittest tests.test_geoimport_suite -v
```
