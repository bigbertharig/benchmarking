# Repeatable rig experiments

Status: design and first compiler, 2026-11-15. Owner: benchmarking. The gateway
Manager owns admission, claims, and load requests; orchestration's rig plan and
runtime scripts execute ordinary model loads. This repo owns protocols, case
expansion, measurement, and conclusions. For a load that has no supported
orchestration recipe, a benchmark adapter may launch the experimental engine
under a Manager run and claim. Do not create another GPU allocator. See the
[test runner guide](TEST_RUNNER_GUIDE.md) for the creation workflow.
The [runner inventory](EXPERIMENT_RUNNER_INVENTORY.md) maps the recent entry
points to internal adapters. Cross-repo tool exposure is deliberately deferred.

## What the recent runs actually measured

| Experiment | Recent example | Repeatable case type | Evidence it can support |
|---|---|---|---|
| Full-model fit and load | `run_model_context_bounds.py`, Nemotron all-card | `model_fit` | Load success, actual placement, load time, memory headroom |
| Occupied context and recall | Nemotron 16K/32K and 200K/250K | `depth_replay` | Prefill, first-token and decode rate at actual token depth; planted-code recall |
| Paired card placement | Qwen35 1060 -> 1070 -> 1060 at 200K/250K | `paired_replay` | A/B/A worker difference with control drift, same saved chats and output cap |
| Resident expert budget | Qwen3.8 Strata 12/16 GiB fixed 50K | `service_replay` | End-to-end request time, physical reads, memory for a fixed prompt |
| Multi-chat state | Qwen3.8 Strata 12/16 GiB two-chat | `chat_sequence` | Admission, isolation, interleaved continuation and total sequence time |
| Expert and lookup tensor | Qwen3.8 routed expert, PLE shard | `component_probe` | Numerical correctness, fit, per-mode latency; not model speed |
| PCIe/NVMe transfer | PLE bus v4 | `transfer_probe` | Link and transfer cost under explicit cold/warm and synchronization policy |

The Phase 5 suite campaign runner remains for model-quality task collections. The
existing `scripts/integration/run_model_loading_sequence.py` is the execution
backbone for rig experiments: schema 2 cases, hardware roles and UUID freeze,
Manager claims/leases, host-memory gates, timeouts, stage logs, and atomic
receipts. It currently runs arbitrary commands; the case types above should
compile to those stages and share the same session contract. Specialized
scripts become engine/probe adapters, not independent campaign schedulers.

## Declarative experiment definition

One manifest should specify four independent things:

1. **Subject:** canonical model ID or component artifact, content hashes,
   engine/build, quantization, context and KV format.
2. **Placement:** hardware roles with capability/topology constraints, load
   profile, worker roles, resident budget and storage tier. Resolve to physical
   GPU UUID and PCI bus once per session; record actual loaded placement.
3. **Scenario:** saved prompt/chat-state hash or deterministic generator and
   seed, occupied token targets, output cap, cache policy, warmups, repetitions,
   correctness oracle, and ordered chat requests.
4. **Analysis:** measurement class, primary metric, matched controls, A/B/A or
   alternating order, acceptable control drift, and comparison group.

For example, the Qwen35 run is one `paired_replay` at two depths with placements
`worker=pascal6,pascal8,pascal6`. The model, saved histories, Q4_1 KV, 262144
reservation, 256-token output cap and 3090 model role are declared once. The
compiler emits preparation and three schema 2 stages per depth, preserving the
explicit order and giving each stage a unique result directory. The existing
manifest repeats those settings in three command arrays.

The Qwen3.8 budget run is a `service_replay` matrix over 12/16 GiB. Its
protocol fixes the same model/pack, K8V4, 256K reservation, 49,694-token
prompt, 768-token cap, MTP off, independent loads, and physical block counter
capture. The `chat_sequence` case uses its own two-chat admission/isolation
oracle and must not be summarized as the same workload as fixed 50K.

## Shared execution contract

The next adapter layer should write a fully resolved `case.json` before
admission. The session runner continues to write `manifest.json`,
`session_hardware.json`, per-stage logs/receipts, and `terminal.json`. Each
adapter writes a versioned `measurement.json` with these common fields:

- `run_id`, `case_id`, case type, protocol version, model/artifact identity and
  hashes, engine build and exact effective settings;
- hardware UUID/PCI bus, requested and actual placement, Manager claim/load
  IDs, load/readiness time, and cleanup result;
- prompt/state hash, actual input/output tokens, cache/cold-warm state,
  correctness outcome, and raw response/log paths;
- monotonic load, prefill, first-token, decode and full-request durations when
  applicable, with explicit missing/not-applicable values;
- sampled GPU/host memory, power and temperature, process I/O plus physical
  NVMe/SATA counters, swap, and start/last-progress/finish timestamps;
- terminal status, exit code, failure phase and artifact paths even after a
  failed fit or interrupted run.

The adapter must preflight model and pack completeness, free GPU/host budgets,
Manager availability and any required saved state before launch. It must
confirm the served engine's model/settings and physical GPU mapping after load,
then stop its own service and release its Manager resources in `finally`.
Resume is valid only when manifest, protocol, adapter/build, model and scenario
hashes match; a changed input starts a new run ID. Log unattended pauses as
inactive wall time rather than compute time.

## Comparison rules

Calculate a comparability key from measurement class, model and engine build,
quantization, prompt/state hash, actual occupied tokens (or declared tolerance),
context/KV, output cap, MTP/drafting, cache policy, and run settings. Refuse an
automatic speed ratio across unequal keys unless the manifest explicitly names
the varied dimension. Store the key and the unequal fields in `comparison.json`.

For A/B/A, compare B with the interpolated A controls and show both A values,
drift, individual rates, and uncertainty from repetitions. For budget sweeps,
alternate order across repetitions where safe. Report prefill, decode, total
time and physical reads separately. Never promote a component probe or a
synthetic recall pass into a full-model quality or speed claim.

## Implementation order

1. The first `compile_experiment.py` expands parameterized, typed cases into
   the existing schema 2 sequence. It validates ordered baselines, values and
   the source hash; `run_model_loading_sequence.py --check` resolves hardware
   roles without loading. Continue with receipt hash pinning and comparison
   calculations. Retain raw command stages for targeted one-off work.
2. Extract shared engine adapters: Manager/llama.cpp load and request;
   Strata plan, launch, health, request, stop; CUDA component container. Move
   pinned paths, GPU0, ports and constants out of specialized scripts and into
   resolved case inputs. Use one measurement writer and one cleanup path.
3. Retire completed one-off launchers without converting their historical
   cases. Keep receipts and useful fixtures as evidence. When a similar new
   request arrives, build its case and any missing adapter then; note that old
   results used a retired runner and may vary.
4. Before a new adapter's first live use, run a small controlled smoke and
   verify cleanup. Run repeated A/B/A or budget controls when the new question
   calls for a comparison. Publish only comparable results in the runtime
   reference; retain failed-fit receipts.

The outcome is one session scheduler, one case/measurement contract, and a
small set of adapters. New card/model/Strata experiments become manifest edits
with explicit controls rather than copies of an experiment script.
