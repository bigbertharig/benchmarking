# GPU Rig cross-repo contract

Version 1, 2026-11-15. This document defines two kinds of shared information: **published knowledge** (model and tool catalogs) and **live state** (admission, loaded routes, execution, diagnostics). A catalog entry never implies that a model is loaded or that a tool server is running.

## Ownership and handoff

| Owner | Publishes | Consumers |
|---|---|---|
| Benchmarking | `model_library_export.json`, schema `gpu-rig-model-library/1` | Gateway, orchestration, harness |
| Harness | `tools/dashboard_tool_catalog.json`, schema version 1, generated from `tools/tool_registry.json` | Gateway, benchmarking |
| Gateway | OpenAI-compatible inference and model discovery; `/v1/manager` admission; `/v1/rig/status` and `/v1/rig/ready-roster` | Dashboard, harness, benchmarking, other clients |
| Orchestration | Rig scan, physical admission, leases/claims, runtime execution and observation; private legacy batch status, diagnostics and activity API | Gateway, benchmarking and harness through Gateway |

Orchestration does not import the tool catalog. Gateway and benchmarking hold their own hash-pinned tool snapshots. Tool names in an inventory are *candidates* until the harness export enables them. A live MCP `tools/list` supplies schemas at use time; if it conflicts with the approved gateway snapshot, the tool is unavailable.

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

`registry.models` is the single model list. It supplies canonical IDs, aliases, candidate/active/archive status, source and size, and named profile definitions. All backend consumers receive active and candidate entries. Active status permits routine dashboard offers and automatic assignment; candidates remain available for explicit tests. `resolved_profiles[model_id][profile]` contains the merged load settings so consumers need no benchmarking Python. `tuning_profiles` and `resolved_tuning_profiles` carry the generated prompt and inference profiles, including resolved aliases, for benchmark suites. `roles`, `load_recipes`, and `subagent_catalog` reference model IDs from the registry; they are role and service settings, not competing model lists. A research recipe ID is **not** an executable rig command until orchestration implements it. `summary` is a compact benchmark-owned display projection, not the evidence source. Receipts remain in benchmarking.

Consumers verify `schema` and `source_sha256`, validate the fields they use, and atomically write their own local projection. The hash is over `json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)` encoded as UTF-8, where `payload` omits only `source_sha256`. Importers reject unknown schema versions or a wrong hash. A source hash identifies an exact knowledge snapshot, including changes to summaries or resolved profiles. There is no time-based automatic promotion or implicit runtime dependency on the benchmarking directory.

| Consumer command | Local projection | Runtime use |
|---|---|---|
| Gateway: `.venv/bin/python tools/sync_model_library.py --dry-run`, `--check`, or no flag to sync | `model_catalog.json`, `remote_profiles.json`, both with `source_sha256` | Manager resolves catalog models and publishes reviewed offers. |
| Orchestration: `python3 shared/scripts/sync_model_library.py what-new\|check\|sync` | `shared/agents/model_library.json`, `model_tuning_profiles.json`, `models.catalog.json`, `model_access.json` | Hardware runtime and campaign runner use imported model knowledge. |
| Harness: `python3 tools/sync_model_library.py what-new\|check\|sync` | `tools/model_catalog.json` with IDs, roles, profile context and capability hints | Planning only; live inference still requires a gateway ready route. |

These are explicit sync steps. Each repo keeps a hash-verified local snapshot so it can deploy and run without a live Benchmarking checkout; the copies are projections of one published source, not independent model authorities. After Benchmarking changes model knowledge, regenerate the artifact, inspect each consumer's change report, then sync. A consumer reports an unknown model, unsupported recipe, or stale snapshot instead of guessing another model or launch command.

## Live model request and observation

1. A client names a canonical model ID or task capability and requirements such as context and chat count. Gateway resolves a reviewed profile and asks Manager for fit/admission using its imported catalog **and current rig observation**.
2. In the current implementation, Gateway's Manager selects a reviewed profile and coordinates the load, while the rig-side Orchestration layer enforces hardware admission, reservations, and runtime constraints. Gateway still contains some placement and lease policy during the migration. The rig executes the admitted command and readiness check. Gateway's old plan-start/resume routes and Orchestration's paired `submit_prepared` action have been retired; new work must use direct requests, not shared plan files as a command channel.
3. Gateway publishes a route only when the rig reports a matching ready profile, served context, and port. `/v1/rig/ready-roster` lists those routes. `/v1/rig/status` and `/v1/manager/status` describe current rig and admission state. `/v1/models` is an OpenAI-compatible **offer list** and may include cold profiles. Clients must not interpret it as the loaded roster.
4. Requests to `/v1/chat/completions` or `/v1/responses` name the selected route. `X-Require-Ready: true` asks gateway to refuse a cold route rather than preparing it. Benchmark and harness receipts should record canonical model ID, route ID, profile/recipe, served context, catalog hash and relevant tool-catalog hash. Route ID is an endpoint identity; it is not a replacement canonical model ID.

The rig's observation/plan is authoritative for live loads, claims and heartbeats. Orchestration's Unix-socket `/v1/orchestration/status`, `/diagnostics`, and `/activity` endpoints are authoritative for brain and batch state. Gateway exposes those readings to the dashboard and harness rig-info tools. A completed batch keeps a bounded last-day index; its full historical evidence belongs in the owning repo.

## OpenAI compatibility boundary

Keep the client-facing `GET /v1/models`, Chat Completions and Responses shapes where supported. [OpenAI's model-list object](https://developers.openai.com/api/reference/resources/models/methods/list) identifies a callable model with fields such as `id`, `object`, `created`, and `owned_by`; it does not define rig placement, tested context by recipe, catalog provenance, lease/claim state, or benchmark evidence. Do not overload its `id` to carry that internal contract. Use canonical IDs in the GPU Rig artifact, route IDs at inference, and explicit `/v1/manager` and `/v1/rig` APIs for local hardware semantics.

MCP is the portable protocol for tool discovery and calls. Harness's registry is the ownership/approval record; gateway's imported projection is the grant; live MCP `tools/list` supplies the JSON argument schema. [OpenAI Responses](https://developers.openai.com/api/reference/resources/responses/methods/create) can declare function or MCP tools, but that request-time declaration is not a cross-repo source of truth for tool ownership or approval. External services are discovered and enabled deliberately; they do not become dashboard tools merely because `tools/list` returns them.

For sharing outside the rig, offer the OpenAI-compatible inference facade and MCP servers first. Publish the versioned GPU Rig model artifact only to consumers that need planning or reproducible model metadata, with a stable schema and its own compatibility policy. Never expose local GGUF paths, rig credentials or hardware-control endpoints as if they were required by an OpenAI-compatible client.

## Change rules

- Additive fields within version 1 may be ignored by consumers. Changing the meaning or type of an existing field requires a new major schema. Importers fail closed on unknown major versions and preserve their last good local snapshot.
- A model-status or role change is a deliberate benchmarking publish and consumer sync; observed load success alone does not promote a candidate.
- A new executable recipe requires orchestration implementation and a Manager admission path. A research recipe in the artifact remains passive.
- A new production tool starts in harness registry, passes its review/tests, enters the generated enabled catalog, and is explicitly synced into gateway and benchmarking. Test fixtures and external observations stay out of the enabled projection until promoted.
- Keep receipts and old result context, but retire old one-off runners. If a new adapter replaces a historical procedure, note that the old test used another runner and results may vary.
