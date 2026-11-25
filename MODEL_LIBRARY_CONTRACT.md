# Model-library artifact contract

Benchmarking publishes `model_library_export.json` for optional consumer import.
This document owns the artifact format, provenance and compatibility rules. It is not
a requirement to install Benchmarking to run a local model or an external provider.
Benchmarking's registry is authoritative for its evidence; consumers own their executable
configuration and keep explicit local changes separate from imported measurements.

## Model knowledge artifact

Benchmarking runs `python3 scripts/active/export_model_library.py sync`. The exporter validates its own registry and writes one atomic JSON file. The top level contains:

```json
{
  "schema": "gpu-rig-model-library/1",
  "source_sha256": "sha256 of canonical JSON for all other top-level fields",
  "registry": {"schema": "model-registry/1", "models": {}},
  "roles": {"schema": "model-roles/1", "roles": {}},
  "load_recipes": {"schema_version": 1, "recipes": {}},
  "models_catalog": {"schema_version": 1, "models": []},
  "subagent_catalog": {"schema_version": 1, "candidates": {}},
  "tuning_profiles": {"models": {}},
  "resolved_profiles": {},
  "resolved_tuning_profiles": {},
  "summary": {"key_tests": [], "models": [], "roles": {}}
}
```

`registry.models` is the single model list within this published artifact. It supplies canonical IDs, aliases, candidate/active/archive status, source and size, and named profile definitions. All backend consumers receive active and candidate entries. Active status permits routine dashboard offers and automatic assignment; candidates remain available for explicit tests. `resolved_profiles[model_id][profile]` contains the merged load settings so consumers need no benchmarking Python. `tuning_profiles` and `resolved_tuning_profiles` carry the generated prompt and inference profiles, including resolved aliases, for benchmark suites. `roles`, `load_recipes`, and `subagent_catalog` reference model IDs from the registry; they are role and service settings, not competing model lists. A research recipe ID is **not** an executable rig command until orchestration implements it. `summary` is a compact benchmark-owned display projection, not the evidence source. Receipts remain in benchmarking.

Consumers verify `schema` and `source_sha256`, validate the fields they use, and atomically write their own local projection. The hash is over `json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)` encoded as UTF-8, where `payload` omits only `source_sha256`. Importers reject unknown schema versions or a wrong hash. A source hash identifies an exact knowledge snapshot, including changes to summaries or resolved profiles. There is no time-based automatic promotion or implicit runtime dependency on the benchmarking directory.

| Consumer command | Local projection | Runtime use |
|---|---|---|
| Gateway: `.venv/bin/python tools/sync_model_library.py --dry-run`, `--check`, or no flag to sync | `model_catalog.json`, `remote_profiles.json`, both with `source_sha256` | Manager resolves catalog models and publishes reviewed offers. |
| Orchestration: `python3 shared/scripts/sync_model_library.py what-new\|check\|sync` | `shared/model_library/model_library.json`, `model_tuning_profiles.json`, `models.catalog.json`, `model_access.json` | Hardware runtime and campaign runner use imported model knowledge. |
| Harness: `python3 tools/sync_model_library.py what-new\|check\|sync` | `tools/model_catalog.json` with IDs, roles, profile context and capability hints | Planning only; the active project-agent path requires a Gateway ready route. Direct-provider support is Planned. |

These are explicit sync steps. Each repo keeps a hash-verified local snapshot so it can deploy and run without a live Benchmarking checkout; the copies are projections of one published source, not independent model authorities. After Benchmarking changes model knowledge, regenerate the artifact, inspect each consumer's change report, then sync. A consumer reports an unknown model, unsupported recipe, or stale snapshot instead of guessing another model or launch command.

## Compatibility rules

Additive version 1 fields may be ignored by consumers. A change to an existing field's
meaning/type requires a new major schema. Importers reject unknown versions and wrong
hashes and preserve the last valid local snapshot. A model-status or role change is a
Benchmarking publish followed by explicit consumer sync; a successful local load does
not promote evidence or a reviewed offer. Research recipes remain passive until their
runtime owner implements and admits them. Preserve historical measurements and identify
the selected measurement, methodology and configuration in exported evidence.

The model export and local projections are Active. Unified evidence selection, reviewed
tool-schema digests and integrated release compatibility records remain Planned.
Benchmarking correctness tests belong in this repository; comparative evaluations also
record provider/runtime identity, settings, test revision and durable results.
