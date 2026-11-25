# GPU Rig cross-repo contract

Wire schemas remain version 1. Ownership decision updated 2026-11-24. This document defines two kinds of shared information: **published knowledge** (model and tool catalogs) and **live state** (admission, loaded routes, execution, diagnostics). A catalog entry never implies that a model is loaded or that a tool server is running. This document owns cross-repository responsibilities. Product guides describe active behavior; the [cleanup plan](REPOSITORY_CLEANUP_PLAN.md) tracks implementation against these decisions.

## Product ownership decision

The four repositories are independently usable products with optional integrations.
Each owns its state and operations. Gateway coordinates the connected installation;
other products also accept direct clients. These are implementation rules. The
standalone workflows and interfaces labelled **Planned** below have not passed acceptance.

| Product | Owns | Standalone acceptance workflow (Planned) |
|---|---|---|
| Gateway | Dashboard, conversations, authenticated remote access, cloud accounts and credentialed connectors, connection configuration, operator approvals, work requests and model assignment. | Cloud coding and conversations with configured workspace tools, without a local rig or sibling checkout. |
| Harness | Agent loop, model-facing tool schemas and implementations, validation and bounded execution, workspace/file/Git tools, retrieval, context/compaction, delegation, execution journals and terminal receipts. | Use its library/CLI in another project with an explicit provider and tool policy; expose its tools independently through MCP. |
| Orchestration | Model installation/path configuration, local executable profiles, hardware discovery, physical fit/admission, placement, leases/reservations, runtime lifecycle, telemetry and recovery. | Register, load, observe and stop a user's local model through its own CLI/API without Gateway or Benchmarking. |
| Benchmarking | Evaluation tasks/datasets, experiment definitions, scoring, model/runtime/tool/harness comparisons, reproducible measurements, results and published evidence. | Run a supported suite against an explicitly configured endpoint/provider and save evidence without the other services. |

### Authority and state

- A model-facing tool belongs in Harness; the controlled operation belongs to its service.
  A model-load tool calls Orchestration, and a conversation-reset tool calls Gateway.
  Tool wrappers do not edit another product's database, state files, or private modules.
- Gateway owns conversation history and operator approval records. Harness owns run journals,
  context state and tool-execution receipts. Orchestration owns leases and observed runtime
  state. Benchmarking owns measurement records. References and events cross boundaries;
  mutable databases and filesystem layouts do not.
- Gateway authenticates users, grants capabilities and records approvals in its deployment.
  Harness validates the exact call and enforces the effective grant; the owning service
  authorizes the operation again. Approval binding and uncertain-write reconciliation
  remain required even when a transport retries. Some of these checks are still Planned.
- Account credentials remain with the configured connector/provider, outside model-visible
  inputs. Gateway owns cloud accounts in the connected installation. Standalone Harness
  callers configure their own provider/connector and permission authority without Gateway.
- Networking in Gateway means public ingress, authentication, routing and connection
  management. Tool/provider clients may communicate directly through their configured
  interfaces; Gateway is not a mandatory relay for every network operation.
- Each product keeps its own unit, contract and integration tests. Benchmarking owns
  comparative evaluations and experiment evidence. Harness keeps deterministic tool/engine
  conformance fixtures and development regressions. Historical trials remain attributable.

### Measured knowledge and executable configuration

Benchmarking is authoritative for its published model identities, measured configurations,
recommended generation settings and evidence. Orchestration is authoritative for executable
runtime configuration on a particular installation. Its standalone workflow must accept a
local model that has no Benchmarking record. A Benchmarking import is an optional source
of defaults/evidence; local configuration must preserve source identity and record explicit
changes separately from the immutable imported snapshot. Local changes do not rewrite
published evidence or promote a model to a reviewed Gateway offer.

In the active integrated path, Benchmarking supplies startup sampling settings, Gateway
passes the selected profile, and Orchestration applies it. Harness inherits those settings
and supplies its task output budget. The planned standalone path uses explicit local
runtime/provider configuration and records its provenance. Harness and Gateway must not
silently invent model-specific sampler overrides. Evaluation runs record requested and,
where observable, effective settings and the exact environment.

## Published artifacts and live interfaces

| Owner | Publishes | Consumers |
|---|---|---|
| Benchmarking | `model_library_export.json`, schema `gpu-rig-model-library/1` | Optional import by Gateway, Orchestration and Harness |
| Harness | `tools/dashboard_tool_catalog.json`, schema version 1, generated from `tools/tool_registry.json`; reviewed MCP tool interfaces | Gateway, Benchmarking and external tool clients |
| Gateway | OpenAI-compatible inference/model discovery; active `/v1/manager`, `/v1/rig/status` and `/v1/rig/ready-roster`; authenticated account/conversation operations | Dashboard, Harness, Benchmarking and other clients |
| Orchestration | Rig inventory/observation, physical admission, leases/claims and runtime lifecycle through its CLI; normalized direct-client service contract is Planned | Gateway, Benchmarking, local users and other authorized controllers |

Orchestration does not import the tool catalog. Gateway and Benchmarking hold local tool
snapshots. Discovery does not grant permission. Active catalogs grant reviewed names and
live MCP supplies argument schemas; normalized reviewed schema digests and mismatch
handling are Planned. A catalog entry never establishes live availability.

### Gateway and Harness interfaces (Planned)

1. **Run interface, owned by Harness:** an embedding caller or Gateway submits an objective,
   explicit provider/model capabilities, workspace/artifact references, grants and budgets.
   Stable run/attempt/request IDs identify submission, additional input, cancellation and
   reconnect/resume. Harness returns ordered events and one terminal receipt per attempt.
   Gateway persists its conversation projection; it does not write Harness journal internals.
2. **Inference interface:** Harness selects a configured provider adapter. Gateway inference
   is one adapter; direct providers do not need `/v1/rig/*`. The Gateway adapter preserves
   versioned ready-roster validation and ready-only calls. Model identity, context/output
   limits and supported features must be explicit; unknown capabilities are not fabricated.
3. **Tool interface:** Harness tools use MCP independently of the agent engine. Gateway or
   an external coding engine can invoke approved tools without adopting the Harness loop.
   Installed packages or configured services provide tools; sibling source paths are not
   the installation contract. A missing optional provider disables that capability only.

The detailed run/engine semantics belong in Harness's
[engine contract](https://github.com/bigbertharig/llm-harness/blob/main/docs/ENGINE_ADAPTERS.md).
The implementation must freeze schemas, capability negotiation, transport/authentication,
error and retry semantics, and producer/consumer fixtures before calling these interfaces
Active. This documentation does not allocate new HTTP endpoints or claim wire compatibility.

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

## Active integrated model request and observation

1. A client names a canonical model ID or task capability and requirements such as context and chat count. Gateway resolves a reviewed profile and asks Manager for fit/admission using its imported catalog **and current rig observation**.
2. In the current implementation, Gateway's Manager selects a reviewed profile and coordinates the load, while the rig-side Orchestration layer enforces hardware admission, reservations, and runtime constraints. Gateway still contains some placement and lease policy during the migration. The rig executes the admitted command and readiness check. Gateway's old plan-start/resume routes and Orchestration's paired `submit_prepared` action have been retired; new work must use direct requests, not shared plan files as a command channel.
3. Gateway publishes a route only when the rig reports a matching ready profile, served context, and port. `/v1/rig/ready-roster` lists those routes. `/v1/rig/status` and `/v1/manager/status` describe current rig and admission state. `/v1/models` is an OpenAI-compatible **offer list** and may include cold profiles. Clients must not interpret it as the loaded roster.
4. Requests to `/v1/chat/completions` or `/v1/responses` name the selected route. `X-Require-Ready: true` asks gateway to refuse a cold route rather than preparing it. Benchmark and harness receipts should record canonical model ID, route ID, profile/recipe, served context, catalog hash and relevant tool-catalog hash. Route ID is an endpoint identity; it is not a replacement canonical model ID.

The rig's observation and hardware-action queue are authoritative for live loads,
claims and heartbeats. Gateway projects that state for its dashboard and rig-info tools.
The old brain/worker engine, shared task queues and private batch API are **Retired**
and removed; their former status/diagnostics routes are not a current service contract.
The planned standalone client path retains the same admission and controller fencing.

## OpenAI compatibility boundary

Keep the client-facing `GET /v1/models`, Chat Completions and Responses shapes where supported. [OpenAI's model-list object](https://developers.openai.com/api/reference/resources/models/methods/list) identifies a callable model with fields such as `id`, `object`, `created`, and `owned_by`; it does not define rig placement, tested context by recipe, catalog provenance, lease/claim state, or benchmark evidence. Do not overload its `id` to carry that internal contract. Use canonical IDs in the GPU Rig artifact, route IDs at inference, and explicit `/v1/manager` and `/v1/rig` APIs for local hardware semantics.

MCP is the portable protocol for tool discovery and calls. Harness's registry is the ownership/approval record; gateway's imported projection is the grant; live MCP `tools/list` supplies the JSON argument schema. [OpenAI Responses](https://developers.openai.com/api/reference/resources/responses/methods/create) can declare function or MCP tools, but that request-time declaration is not a cross-repo source of truth for tool ownership or approval. External services are discovered and enabled deliberately; they do not become dashboard tools merely because `tools/list` returns them.

For sharing outside the rig, offer the OpenAI-compatible inference facade and MCP servers first. Publish the versioned GPU Rig model artifact only to consumers that need planning or reproducible model metadata, with a stable schema and its own compatibility policy. Never expose local GGUF paths, rig credentials or hardware-control endpoints as if they were required by an OpenAI-compatible client.

## Portability and replaceable implementations

The four repositories are product boundaries, not deployment topology. They may run on one host or
several hosts and communicate through versioned artifacts, requests, events, and receipts. They must
not import another repository's private Python modules or require another repository's checkout at
runtime. Site addresses, mount roots, credentials, model paths, and service identities are private
configuration. A portable installation supplies those values and remeasures its own hardware; it does
not edit a published contract to describe one machine.

The extension boundaries below are decisions; backend and generic engine extraction remain Planned:

| Replaceable part | Stable consumer boundary | Authority that cannot move with the replacement |
|---|---|---|
| Accelerator/runtime implementation | Orchestration inventory, capability, admission, lifecycle, observation, and receipt contract | Orchestration remains final authority for physical admission and observed state. |
| Harness engine | Caller task envelope, configured provider and grants in; ordered Harness events and terminal receipt out | Gateway grants and operator policy, plus Harness tool validation and approval checks, cannot be expanded by an engine. |
| Inference runtime | Reviewed Orchestration runtime adapter and explicit local profile; optional Benchmarking evidence | A runtime cannot self-publish a model offer or bypass admission. |
| Tool provider | MCP plus a reviewed, digest-bound Harness catalog entry | Discovery does not grant permission; Gateway policy and Harness execution checks still apply. |

Orchestration is NVIDIA/CUDA-focused today. AMD/ROCm and Apple Silicon/Metal integrations are planned.
The expansion path keeps one Orchestration control plane with versioned backend adapters, allowing each
backend to represent its own memory and topology model through normalized capabilities and lifecycle
outcomes. An adapter may become an external package later if its release, licensing, dependencies, or
maintainership require that split.

Portable benchmark records and recipes identify the hardware/runtime backend and measured environment.
Gateway requests capabilities and desired outcomes rather than selecting cards through a vendor API.
Harness remains accelerator neutral. Its active Gateway adapter consumes a ready route;
the planned direct-provider adapter accepts explicit provider capabilities. The project-owned
Harness is the default engine. Additional engines require the planned conformance boundary.

## Change rules

- Additive fields within version 1 may be ignored by consumers. Changing the meaning or type of an existing field requires a new major schema. Importers fail closed on unknown major versions and preserve their last good local snapshot.
- A model-status or role change is a deliberate benchmarking publish and consumer sync; observed load success alone does not promote a candidate.
- A new executable recipe requires Orchestration implementation and its admission path. The active integrated client is Gateway Manager. A research recipe in the artifact remains passive.
- A new production tool starts in harness registry, passes its review/tests, enters the generated enabled catalog, and is explicitly synced into gateway and benchmarking. Test fixtures and external observations stay out of the enabled projection until promoted.
- Keep receipts and old result context, but retire old one-off runners. If a new adapter replaces a historical procedure, note that the old test used another runner and results may vary.

## Implementation status and compatibility work

Use these labels when a cross-repository claim affects an operator or consumer:

- **Active** (also called deployed) means the behavior is present in the published artifact or live interface and has a maintained verification path.
- **Experimental** means an implementation and evidence exist, but it is not a supported default.
- **Planned** means an accepted direction or acceptance requirement awaits implementation.
- **Proposed** means an option still awaits a decision.
- **Retired** means the path is historical or compatibility-only and must not be selected for new work.

The hash-verified model-library export, explicit consumer sync, local projections, and separation between cold offers and the ready roster are **Active**. Candidate models, research recipes, and individually labelled trial runtimes remain **experimental** or passive evidence; their presence in an artifact does not promote them.

The following reliability work is **Planned** and is not part of version 1 of this contract:

1. Use one Benchmarking evidence selector for the scoreboard and model-library export. Each selected summary should identify the chosen measurement record, methodology version, and configuration hash so consumers can explain the selection.
2. Publish a compatibility manifest containing the four repository revisions tested together plus the model-library and reviewed tool-catalog hashes. The manifest should distinguish a visible mismatch that still permits offline planning from one that blocks live execution. Until that policy and its tests land, the individual schema and hash checks above remain authoritative; no compatible four-repository set should be inferred from repository HEADs alone.
3. Publish normalized reviewed tool-schema digests from Harness and have Gateway disable only the mismatched tool. Live schema discovery and name-based grants do not by themselves establish reviewed schema compatibility.

Evidence-selection changes must preserve historical measurement records. Compatibility work must add a versioned fixture and consumer test before this section can label it Active.

## Standalone product acceptance

Each product must support its own core workflow without the other repositories or
services. Optional integration is not a prerequisite for standalone use. This is an
acceptance requirement, not a claim about the current implementation. The
[2026-11-24 isolation audit](reports/STANDALONE_ISOLATION_AUDIT_2026-11-24.md) records
current blockers, exact audited revisions, and the required independent-install tests.

Implementation follows the [repository cleanup plan](REPOSITORY_CLEANUP_PLAN.md).
The historical audit records the pre-cleanup code; this contract records the accepted division.
