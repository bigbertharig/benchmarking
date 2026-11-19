# Benchmark Suite Audit - August 2026

## Evidence Policy

Existing scores, graphs, Markdown history, raw outputs, and schema-v2/legacy
ledger rows remain valid historical evidence. New methodology versions do not
delete or rewrite them. The primary scoreboard remains available for graph
continuity, while `results/model_methodology_history.json` separates evidence
by comparison group.

Direct score comparison is valid only inside one `comparison_group`. A harness
implementation change increments methodology version. A dataset, prompt,
extraction, grading, or score-definition change that breaks comparability also
creates a new comparison group.

## Suite Decisions

| Suite | Decision | Method | Audit result |
|---|---|---|---|
| `bench-pipeline` | Keep and update | `bench-pipeline/local-custom` 2.0.0 | Core workload cases remain useful. Added schema-v3 methodology recording, controlled inference profiles, failure retention, and recorder preflight. Rig image is stale and must be rebuilt. |
| `bench-agent` | Keep | `bench-agent/executable-tools` 1.0.0 | Covers planning versus execution, arguments, observations, recovery, multi-tool work, no-tool decisions, malformed calls, and MCP mutations. Needs first real-model rig evidence. |
| `bench-code` | Keep and update | `bench-code/evalplus` 2.0.0 | HumanEval+/MBPP+ remain the stable code baseline. Added run class, sample counts, failure rows, deterministic dependency versions, and nonzero exit on partial generation/evaluation. Future coding-agent work belongs in agent/terminal suites rather than changing these scores. |
| `bench-reasoning` | Keep and update | `bench-reasoning/lm-eval-normalized` 2.0.0 | Registered strict/flexible GSM8K and DROP EM/F1 outputs. Records raw and normalized GSM8K scores, estimated extractor failures, sample counts, and task failures. Existing extractor-patched results remain historical and are not relabeled. |
| `bench-knowledge` | Keep optional and update | `bench-knowledge/lm-eval-gguf` 2.0.0 | Still useful for ad-hoc broad knowledge checks, but not a primary operational routing signal. Added explicit methodology, deterministic dependency versions, strict recorder handling, and failure rows. |
| `bench-daedalmap` | Keep and update | `bench-daedalmap/chat-isolation` 2.0.0 | Domain-specific JSON, type routing, grounding, hallucination, and optional bucket checks remain valuable. Added method/config identity, sample counts per metric, failure rows, and registered dynamic result families. |
| `bench-dataimport` | Keep | `bench-dataimport/capability` 1.0.0 | Covers converter generation/execution, reference metadata, aggregation, and schema diagnosis without external downloads. Needs first real-model rig evidence. |
| `bench-routing` | Keep | `bench-routing/cost-awareness` 1.0.0 | Covers cheapest-sufficient tier selection and human escalation. Tier costs are heuristic; measured model cost remains in Pareto/runtime outputs. Needs first real-model rig evidence. |
| `bench-runtime` | Add | `bench-runtime/operational` 1.0.0 | Fills the upgrade-plan gap for stability, TTFT, throughput, controlled context growth, VRAM, GPU-seconds, and energy. It supplements rather than replaces historical `context_window_benchmark.py` reports. |

## Catalog-Only External Tests

BFCL, LiveCodeBench, SWE-bench Verified, Terminal-Bench, LongBench, RULER, and
other catalog entries are candidates, not maintained local Docker suites.
Workload-specific executable agent tests remain the primary orchestration
signal. Add an external harness only when its setup is pinned, locally staged,
and its result semantics map cleanly into a versioned comparison group.

## Rig Snapshot

Audit host: `bryan-GPU-Rig` (`10.0.0.3`), Docker 28.2.2.

At audit time the rig had older images for code, reasoning, knowledge,
pipeline, and DaedalMap. Agent, data-import, routing, and runtime images were
not present. Image age does not invalidate stored results; it means new runs
must wait for controlled rebuild and smoke validation.

Agent, routing, and runtime images were subsequently built with
`--network=none`. Isolated `--no-record` checks against the live
Qwen3.6-27B endpoint completed without harness failures: all four runtime
signals had full request success, both sampled routing cases scored 1.0, and
both sampled agent cases executed but averaged 0.1875 task score. These are
harness checks, not model evidence, and were not added to the ledger.

GPU telemetry remains unverified. GPUs 1-3 reported device-handle errors and
the NVIDIA container prestart hook failed NVML initialization even when GPU 0
was requested. Endpoint-only measurements remain available; VRAM, energy, and
GPU-seconds require the rig's NVIDIA runtime state to be repaired first.

## Required Validation Sequence

1. Run local unit and mock-endpoint tests.
2. Build images on the rig with pinned dependencies and no benchmark execution.
3. Run `smoke` cases into isolated temporary ledger/output paths.
4. Inspect schema-v3 methodology and failure fields.
5. Run provisional campaigns against selected models.
6. Promote evidence to `validated` or `full` only at the declared sample size.
