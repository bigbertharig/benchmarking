# Repository cleanup implementation plan

Decision accepted 2026-11-24. Status: **Planned**. No runtime migration is completed by
this documentation pass. The [cross-repo contract](CROSS_REPO_CONTRACT.md) owns the
responsibility rules; this plan owns the migration sequence and completion evidence.
The [source audit](reports/STANDALONE_ISOLATION_AUDIT_2026-11-24.md) pins the inspected code.

## Comparison with the previous documents

| Previous documentation | Clarification now accepted |
|---|---|
| Gateway owns work/policy; Orchestration owns hardware; Harness owns tools; Benchmarking owns evidence. | Retained. Add explicit standalone workflows, state ownership and optional direct clients. |
| Gateway is the controller; Harness receives only Gateway-ready routes. | That describes the active integrated deployment. Gateway is optional for standalone Orchestration and Harness. |
| Benchmarking owns the single model list and profiles. | Its authority covers its evidence artifact. Orchestration also needs explicit user-owned executable profiles, with separate provenance. |
| Harness owns harness comparisons and shared comparison runners. | Benchmarking owns reusable comparative evaluations. Harness keeps contract/conformance tests and development regressions; historical receipts remain intact. |
| Generic engine adapters are described as available. | The engine/run boundary is accepted but Planned; active journals and MCP adapters do not establish full substitution conformance. |
| Legacy brain/worker and private batch routes appear in architecture pages. | They were removed. The remaining rig plan queue contains hardware actions only. |
| Tools are launched from another repository's source paths. | Source paths describe deployment debt. Tools are distributed through packages or configured MCP services; operations remain with their state owner. |

## Rules for every migration

- Classify code by the operation and state it owns, not its current directory or filename.
  Separate a measurement driver from the hardware operation it invokes.
- Use public versioned contracts or deliberately installed packages. No sibling private
  imports, shared mutable stores, fixed home directories or hidden SSH-host assumptions.
- Keep model-facing tools and shared execution behavior in Harness. A service still owns
  its authenticated operation and durable operation receipt. Generic host command access
  is not a substitute for a product lifecycle API in maintained integrations.
- Gateway manages connections and approvals for its users; standalone callers supply their
  own explicit provider, connection configuration and permission authority.
- Preserve measured evidence, source revisions and configuration provenance. Do not relabel
  an old measurement as if it ran through the replacement implementation.
- Inventory callers, tests, deployment units and docs before moving a script. Migrate them
  in one coherent change; retain a compatibility wrapper only for an identified consumer
  with an explicit removal condition. Default to one maintained implementation.
- No general-purpose script enters a catch-all tools folder without an owning module,
  supported entry point, documented inputs/effects and registered deterministic tests.
- Each repo keeps its native test runner and its own correctness tests. Update owning
  status docs with receipts in the same pass. No implicit live provider spend or hardware
  mutation is part of documentation/CI checks.

## Phase 1: Benchmarking and Orchestration

| Work | Owner | Completion evidence |
|---|---|---|
| Define direct lifecycle/observation requests, version/capability/refusal shapes and controller ownership using existing rig primitives. | Orchestration | Fake-hardware fixtures for admission, competing controllers, leases, cancellation/failure cleanup and restart; no Gateway imports or calls. |
| Add local model/profile registration and load/observe/stop workflow. Keep imported evidence immutable and explicit local configuration separate. | Orchestration | Fresh installation exercises a model absent from the Benchmarking registry; documented example and deterministic lifecycle tests, followed by a separately recorded NVIDIA smoke. |
| Separate endpoint-only evaluation from managed hardware adapters. | Benchmarking | Supported suite runs against a fake configured provider with a local model record, no other services, and a complete result receipt; missing telemetry is explicit. |
| Replace `scripts/integration/hardware_inventory.py`'s direct `hw_power.py` invocation and `resolve_model.py`'s shared-tree/private `brain_core` dependency. Audit `harness_lease.sh`, `p45.sh`, `run_mode_smoke_stage.sh` and related launchers. | Benchmarking consumes Orchestration's supported operations | No private import or sibling executable requirement in migrated workflows; managed mode retains admission, power checks and lease cleanup. Standalone mode is explicit, never an automatic no-lease fallback on a managed rig. |
| Move reusable experiment drivers out of Gateway and Orchestration. | Benchmarking | Migrated callers, named tests, docs and evidence paths; hardware effects use Orchestration operations. |

Initial experiment inventory: Gateway's `tools/power_cap_sweep.py`, `pcie_split_test.py`,
`split_sweep.py`, `rig_stress.py`, `dual_rig_bench.sh` and `multi_rig_tests.py` require
classification. Move measurement campaigns to Benchmarking; keep Gateway transport/auth
regressions with Gateway. Orchestration's `shared/scripts/rig/experiments/` sweeps belong
with experiment evidence; runtime build/health/admission smoke tests stay in Orchestration.

## Phase 2: Harness and Gateway

| Work | Owner | Completion evidence |
|---|---|---|
| Package the reusable tools/engine behind public entry points; separate MCP adapters, provider adapters, fixtures and research. | Harness | External example project installs and runs tools/engine without a Gateway checkout or rig API. Existing broker/permission regressions still pass. |
| Add direct-provider execution and preserve the Gateway ready-only adapter. | Harness | Explicit identity/context/output capabilities; no `/v1/rig/*` calls for direct providers; tested denial, cancellation, recovery and truthful terminal receipts. |
| Freeze task/event/receipt submission, additional-input, cancel and resume semantics with producer/consumer fixtures. | Harness owns run contract; Gateway owns integration | Duplicate request, sequence gap, reconnect, version mismatch and uncertain-write cases pass; no shared mutable state or credentials in model inputs. |
| Separate cloud dashboard/conversations from Rig Manager; configure tool providers through supported installations. | Gateway | Cloud-only startup, authenticated coding, streaming, tools, cancellation and restart with fake provider and no sibling checkout, SSH target or model library requirement. Missing optional providers affect only their capability. |
| Replace tools that read/write Gateway state files with authenticated owner operations. | Gateway operation; Harness wrapper | Conversation-reset and account operations preserve permission/idempotency semantics; tools contain no private Gateway store knowledge. |
| Move reusable comparison campaigns such as `tools/search_provider_benchmark.py` and search concurrency evaluation. | Benchmarking | Portable runner uses public tool interfaces; Harness keeps reusable search implementation and deterministic fixtures. Preserve existing Harness research receipts. |

Gateway owns provider login/account/session transport; Harness owns common model/tool loop
behavior. External coding engines can consume Harness MCP tools without using our engine.
Review duplicate loops in Gateway adapters against this rule; do not force provider-native
session semantics into a generic loop without conformance evidence.

## Phase 3: isolation and optional integration acceptance

1. Test each product in an isolated install with fresh HOME/config and no sibling source
   trees, mounted private data, or other product services. Install only its declared
   dependencies. Exercise the product workflow, not just imports, `--help` or `/health`.
2. Test optional producer/consumer pairs with frozen versioned fixtures: inference,
   MCP discovery/grants, run events/receipts, lifecycle/admission and model artifacts.
   Unknown versions, missing capabilities, schema drift, stale snapshots and interrupted
   requests have explicit outcomes. Preserve the last valid imported snapshot on failure.
3. Publish tested revisions and artifact hashes for each integration. A four-product
   compatibility record describes the integrated deployment; it never becomes a prerequisite
   for using one product alone.
4. Mark a phase Active only with runner commands, revisions, results, durable receipts and
   updated product quickstarts. Paid provider trials and real hardware runs are separate
   evidence from deterministic contract checks.

The next implementation starts with Phase 1. Existing production paths remain documented
until their replacements pass acceptance; these decisions do not authorize skipping admission
or changing protected permission configuration.
