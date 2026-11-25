# Standalone products and integration audit

Audited 2026-11-24. Status: **standalone acceptance is proposed; not yet passed**.
This is a source and documentation audit, not an isolated installation test. Existing
integrated test passes do not prove operation without sibling repositories or services.

## Required product boundaries

Each repository must install, document, and test a useful core workflow without any of
the other three repositories, their services, private modules, or checkout layout.
Ordinary third-party runtimes, provider credentials, model files, and hardware remain
valid prerequisites. Optional integrations must declare their capabilities and fail
locally without disabling unrelated core functionality.

| Product | Standalone workflow | Optional integration |
|---|---|---|
| Orchestration | Configure and run a user's local model; inspect, stop, and recover it through its own CLI/API. | Gateway as a controller; Benchmarking evidence import. |
| Gateway | Remote coding and conversations through configured cloud providers, with project/workspace tools. | Orchestration local models; Harness engine or MCP tools; Benchmarking evidence. |
| Harness | Embed or invoke the bounded model/tool loop in another project using an explicit provider and tool policy. | Gateway discovery/admission adapter; Benchmarking model metadata. |
| Benchmarking | Run a selected suite against an explicitly configured supported model/provider and save reproducible evidence. | Gateway/Orchestration managed lifecycle; Harness evaluation. |

The integrated deployment can retain stricter managed admission rules. A standalone
workflow must not silently bypass the controller or leases on an already managed rig.
Benchmarking's canonical registry is the source for its published evidence artifact;
it must not become a mandatory live service or mandatory source for every user model.

## Findings at the audited revisions

1. **Gateway cloud UI depends on Rig Manager.** `src/llm_gateway/app.py:116-145`
   mounts dashboard and cloud routes only when a Manager exists; lines 286-292 apply
   the same gate to conversation routes. `RIG_MANAGER=off` therefore does not provide
   the requested standalone cloud coding product. Separate conversation/provider
   services from optional hardware management, including background tasks and UI state.
2. **Gateway tool launches can require the Harness checkout.**
   `src/llm_gateway/dashboard/dashboard_mcp_servers.py` resolves several scripts beneath
   `HARNESS_TOOLS_DIR` (default `~/llm-harness/tools`) and raises when selected scripts
   are absent. Workspace Git and gateway-reset are examples. Configurable paths help
   deployment but do not establish independent distribution. Gateway needs its own
   core coding capability and explicit optional MCP provider installation/configuration;
   missing optional providers must not break unrelated cloud turns.
3. **Harness's maintained loop requires a Gateway-specific service.**
   `tools/project_agent.py:245-248` unconditionally fetches and checks the ready roster;
   `tools/ready_roster.py:15-26` requires `/v1/rig/ready-roster` version 1. Generic
   inference compatibility alone is insufficient. Introduce an explicit provider/route
   capability boundary and keep the existing ready-only checks in the Gateway adapter.
   Direct providers need explicit model identity, context/output limits, auth, and
   supported capabilities, without fabricated rig readiness or implicit cold loads.
4. **Orchestration has the execution primitives but lacks a supported standalone
   user load workflow.** `shared/workspace/quickstart.md:26-28` directs users to Gateway.
   `shared/scripts/rig/rig.py:824-826` accepts a prepared remote spec; `1441-1448` rejects
   other start modes in favor of Manager loads. This does not prove Gateway is required
   internally: a different controller can supply a spec. Provide a documented local
   profile-to-admission-to-launch path inside Orchestration, preserving locks, guard,
   controller fencing, and leases. Finish moving hardware-fit authority out of Gateway.
5. **Benchmarking has reusable endpoint evaluation plus site-coupled integrations.**
   `scripts/active/run_lm_eval_task.py:128-139` accepts an explicit HTTP(S) endpoint and
   model route, with identity in its own registry. However,
   `scripts/integration/hardware_inventory.py:7` names an Orchestration script directly;
   `scripts/integration/resolve_model.py:18-20,42-46` assumes a shared tree and conditionally
   imports `brain_core`; several launchers invoke sibling checkout scripts. Keep these
   as explicit managed/site adapters and remove private imports/path assumptions from
   supported portable workflows. Do not describe all suites as arbitrary-provider ready.

## Protocol assessment

- **Model artifact: deployed isolation mechanism.** The versioned export, content hash,
  explicit sync, and local projections allow consumers to run without Benchmarking's
  checkout. Unknown versions/bad hashes must continue to preserve the last good snapshot.
- **Inference and ready roster: useful, distinct interfaces.** OpenAI-compatible
  inference is separate from Gateway-specific live readiness. Harness currently binds
  them together; a generic provider adapter must not assume every provider implements
  the rig extension. The ready-roster client already validates version 1 and required fields.
- **MCP: appropriate tool transport; packaging and approval still need work.** A local
  stdio executable is a valid MCP deployment. Requiring a sibling source checkout for
  core behavior is a separate problem. Imported tool-name grants and live schemas exist;
  reviewed normalized schema digests remain proposed in the cross-repo contract.
- **Harness task/event/receipt adapter: proposed substitution boundary.**
  `docs/ENGINE_ADAPTERS.md` describes the launch envelope and conformance milestone.
  The active loop has journaling and receipts, but this audit found no completed generic
  engine adapter/conformance layer. Do not advertise interchangeable engines as proven.
- **Whole-system compatibility: not yet established.** The tested-revision/artifact
  compatibility manifest is explicitly proposed in `CROSS_REPO_CONTRACT.md`. Shared
  `/v1` route prefixes and passing tests at individual HEADs are insufficient evidence.

## Acceptance work, in order

1. Gateway: cloud-only startup and coding workflow with Rig Manager disabled and no
   sibling checkout, SSH target, shared mount, or local model. Exercise authenticated
   conversation, workspace tools, streaming, cancellation, and restart using a fake
   provider first. Missing optional hardware/tool providers must remain localized.
2. Harness: an installable/public entry point with a generic provider adapter and a
   small external example project. Run tool-free and approved-tool tasks against a fake
   endpoint without any `/v1/rig/*` calls; verify identity/limits, denial, cancellation,
   recovery, and truthful receipts. Retain ready-only Gateway adapter conformance tests.
3. Orchestration: documented local profile registration and load/observe/stop lifecycle
   with the other services absent. Test fake hardware admission, competing controllers,
   failure cleanup, and restart before a separate real NVIDIA smoke. Other accelerators
   remain planned until their own implementations and evidence exist.
4. Benchmarking: a standalone suite command against a configured endpoint with a local
   model record and durable result. Validate missing optional telemetry and managed
   adapters explicitly; keep hardware experiments separate from endpoint-only suites.
5. All four: run isolated source/package installations with a fresh HOME and no sibling
   repositories or private mounts. Then test optional pairwise integrations, unknown
   versions, missing capabilities, schema drift, stale snapshots, and interrupted calls.
   Publish producer/consumer fixtures and tested revisions/artifact hashes. Register
   these tests in each repository's existing runner rather than creating parallel suites.

A pass requires the actual product workflow, not just imports, `--help`, or `/health`.
Use deterministic fake providers/hardware for CI; record live integration evidence
separately. Avoid replacing existing protocols or creating a fifth mandatory shared
repository merely to centralize schemas.

## Evidence and limits

Source excerpts above were inspected at these revisions:

- `llm-gateway`: `0a88dee88c92fba2af41b3fd6043bc4566883944`
- `llm-harness`: `398648651e389e08ee9bb7b1eee5086c9f3a2312`
- `benchmarking`: `9606c830df28827acf782b3ce7f25e2c102ddb4b`
- `llm_orchestration`: `347b7271ed8bcf333c00d21cbbf6bdb4092d69fa`

No runtime code or deployed service was changed during this audit. Standalone tests
were not run; all acceptance items above remain open.
