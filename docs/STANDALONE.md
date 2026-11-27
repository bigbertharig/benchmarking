# Standalone Benchmarking

Endpoint evaluation does not require a runtime manager, model-library import or Gateway.
Run `python scripts/active/run_endpoint_suite.py --config endpoint.json --dataset cases.json
--out results/new-receipt.json` from this checkout. Existing receipt paths are refused.

```json
{"schema":"benchmark-endpoint/1","endpoint":"http://localhost:8000/v1",
 "model":{"id":"my-model","route":"served-route","revision":"my-weight-revision"},
 "max_tokens":256,"timeout_seconds":60,"api_key_env":"BENCHMARK_API_KEY"}
```

```json
{"schema":"benchmark-exact-match/1","id":"arithmetic-v1",
 "cases":[{"id":"two-plus-two","prompt":"What is 2+2? Reply with a digit.","expected":"4"}]}
```

The runner records a validated schema-v3 measurement, local model provenance, configuration
and dataset hashes, per-case output/usage/latency and timestamps. Missing hardware telemetry
is explicitly `not_collected_endpoint_only`; it is never replaced with zero. This exact-match
suite is a smoke comparison, not certification of model quality. Other evaluation suites and
optional framework requirements remain in their existing runners. `run_lm_eval_task.py` now
uses its own interpreter by default and writes to `BENCHMARK_OUTPUT_DIR` or local results.

## Optional managed runtime

Set `BENCHMARK_ORCHESTRATION_COMMAND` to an installed command's JSON argv (default `["rig"]`).
`BENCHMARK_CONTROLLER` names an already claimed runtime controller. `managed_lease.py` calls
`rig-lifecycle/1`; the `harness_lease.sh` wrapper remains for existing lane callers and can be
removed once those callers switch to the Python entry point. Unreachable or refusing runtime,
renewal and release failures are errors. There is no automatic no-lease mode.

`local_runtime.py register --profile ID --spec FILE`, `load --profile ID --gpus 0`, and
`stop --profile ID` consume the public lifecycle API. Registration is explicit and immutable.
`p45.sh` uses this boundary and stops only its own profile; it no longer deletes every runtime
container. `run_mode_smoke_stage.sh run MODEL PROFILE_JSON PORT TAG` takes an explicit local
profile JSON and checks the admitted port. Generic container teardown is no longer supported.

## Comparison campaigns

`scripts/experiments/runtime_campaign.py --config FILE --out NEW_DIRECTORY` measures explicit
profile/placement variants through the public lifecycle API. Its configuration schema is
`benchmark-runtime-campaign/1`: `controller`, optional `runtime_command`, and `cases` with
`id`, `profile_id`, `spec`, `gpu_ids`, `endpoint` (ending in `/v1`), `prompt`, optional `repeats`,
`workers`, `max_tokens`, `generation`, and single-GPU `power_watts`.
Each case loads, measures and stops its own profile. Explicit power experiments are scoped to
an owned lease and restored by Orchestration. Receipts retain operation evidence and failure
progress. Managed campaigns consume Orchestration's versioned hardware guard through Gateway,
hold new work on stale or missing telemetry, abort after three missed samples, and stop on a fresh owner-reported
critical level. The separate runtime comparison runner still does not claim
historical stress-driver thermal aborts or continuous power sampling; those require
site acceptance before live use.

Former hardcoded hardware experiment source is preserved byte-for-byte with hashes under
`archive/experiment_sources_20261124`; it is retired executable code, not new measurement
provenance. Gateway retains its historical network fault/recovery driver. Search comparisons
now live in `scripts/experiments/search_provider_benchmark.py` and `search_provider_concurrency.py`.
DuckDuckGo uses the installed `rig_search.duckduckgo` API; SearXNG uses its HTTP API. No private
Orchestration search module is imported.

Validation: use registered native suites. `evaluation_suites` exercises an isolated copy with
fresh HOME, a real fake-provider HTTP call and a model absent from the registry. `campaigns`
checks cleanup and failure receipts; `capacity` checks strict owner inspection consumption.


An interrupted power campaign leaves a durable `receipt.json` with original request IDs.
Run `python scripts/experiments/recover_runtime_campaign.py --receipt PATH` after the
runner has stopped. Recovery restores its owned power session before stopping its model,
records a separate `recovery.json`, and refuses to replay an unresolved cleanup request.
Check the returned power limit and idle runtime before starting new work.


November 25 live acceptance: the portable campaign ran five Ministral 3B endpoint
requests with GPU 0 at 300 W, then restored the configured 350 W cap and stopped its
model. An injected endpoint failure also restored and stopped. A separate run was
stopped after `power.set`; `recover_runtime_campaign.py` restored 350 W from the
recorded session ID, stopped the loaded profile and wrote `recovery.json`. The rig
returned to idle without leases. The registered campaigns suite passed 53 tests and
10 subtests after the recovery command was added.

Portable managed campaigns can run from an extracted package without a Benchmarking checkout. Their ledger and generated views live beside the campaign terminal receipt under the shared campaign history. See [campaign runner](../docker/CAMPAIGN_RUNNER.md) for build, install, verification, and rig-control requirements. The [live acceptance receipt](../results/campaign_acceptance/portable_package_resume_20261127.json) covers a stopped and recovered package run against a clean source-tree control.
