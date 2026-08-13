# Creating a Benchmark Suite

All campaign-compatible suites implement `campaign-v1`. The machine-readable
source of truth is `docker/suite_contracts.json`; the only scheduler is
`/mnt/shared/scripts/benchmarks/run_campaign.py`.

## 1. Choose the Contract

Add the suite to `suite_contracts.json` with explicit values for:

- `runtime_mode`: normally `external`; the campaign runner owns model loading.
- `limit_supported`: whether bounded smoke runs accept `--limit N`.
- `task_selector`: `--tasks`, `--tests`, `--cases`, or `null`.
- `profile_policy`: how prompts are selected.
- `hardware_id_required`: whether hardware identity is part of the result.
- `container_gpu_access`: only for suites that inspect GPU telemetry directly.
- `env_file_supported`: only for suites with an explicit optional env file.

Profile policies:

| Policy | Meaning |
| --- | --- |
| `required` | Resolve the model through `scripts/active/model_profiles.py`; require `system_prompt`. |
| `task_prompt_plus_profile` | Combine a frozen task prompt with the resolved model profile. |
| `fixed_evalplus_prompt` | EvalPlus owns the prompt; model profile is not injected. |
| `fixed_case_prompt` | Each frozen case owns its prompt. |
| `fixed_probe_prompt` | The operational probe owns its prompt. |
| `fixed_suite_prompt` | The suite owns one frozen prompt. |

Do not add suite-specific profile matching. Import `resolve_profile()` or invoke
`model_profiles.py`; this is what makes aliases and model-specific settings
behave identically across suites.

## 2. Implement the CLI

Every entrypoint accepts:

```text
--model MODEL
--run-name RUN_NAME
--run-class smoke|provisional|validated|full
--results-dir PATH
```

External-runtime suites also accept `--runtime-base URL`. Add the registered
task selector, `--limit`, `--tuning-profiles`, and `--hardware-id` exactly when
the registry says they are supported. Runner-owned flags must not be placed in
manifest `suite_args`.

The Dockerfile must use a JSON `ENTRYPOINT` and include:

```dockerfile
LABEL daedalmap.benchmark.contract="campaign-v1"
```

## 3. Own Outputs Correctly

Write run artifacts beneath:

```text
/results/<suite>_<model_safe>_<run_name>/
```

At minimum, write a live `status.json`, deterministic task artifacts, and a
final summary or terminal task states. Reusing the same run name must skip only
completed work and rerun failed or interrupted work.

The benchmark source mount is read-only. Canonical result records must use
writable shared paths, either the standard defaults or explicit arguments:

```text
/mnt/shared/plans/shoulders/benchmarking/results/model_benchmark_records.jsonl
/mnt/shared/plans/shoulders/benchmarking/results/MODEL_BENCHMARK_REFERENCE.md
/mnt/shared/plans/shoulders/benchmarking/results/model_library_scoreboard.json
```

Never rely on recorder defaults derived from `/benchmark-scripts`, because that
mount is read-only in campaign containers.

The campaign runner supplies `HOME`, `HF_HOME`, `HF_DATASETS_CACHE`, and
`XDG_CACHE_HOME`. Suites must respect those paths rather than deriving a cache
from `/` or writing dependencies into the source mount.

## 4. Register Methodology

Add an entry to `benchmark_methodologies.json`. Change the methodology version
or comparison group whenever scoring, extraction, case data, prompts, or runtime
semantics change. The harness records observations; it does not impose a pass
threshold or decide whether a model is acceptable.

## 5. Add Documentation

Each `docker/bench-<name>/` directory must contain:

- `README.md`: scope, task IDs, CLI, outputs, and a direct debug command.
- `BENCH_<NAME>_HISTORY.md`: methodology changes and run notes.

Direct `docker run` commands are for suite debugging. Sequential and parallel
production runs both use the campaign runner.

## 6. Validate and Smoke Test

Run from the benchmarking repository:

```bash
python3 scripts/active/validate_suite_contract.py
python3 -m unittest tests.test_model_profiles tests.test_suite_contract
```

Then build and inspect the image on the rig:

```bash
docker build -t bench-<name> docker/bench-<name>
docker image inspect bench-<name> \
  --format '{{ index .Config.Labels "daedalmap.benchmark.contract" }}'
```

Create one campaign manifest containing a bounded suite block. Verify:

1. `--dry-run --verbose` produces the expected Docker command.
2. A real `--limit 1` run records an artifact and exits zero.
3. Reusing `--run-id` resumes without duplicating completed work.
4. Two independent blocks can occupy non-overlapping slots.
5. Two dependent blocks execute in dependency order.

`bench-code` is intentionally all-problem EvalPlus and does not support
`--limit`; validate its command contract separately from bounded suites.
