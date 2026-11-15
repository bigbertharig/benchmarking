# Experiment runner inventory

Status: historical question map, 2026-11-15. This is an internal benchmarking inventory,
not a cross-repo tool catalog. The [runner guide](TEST_RUNNER_GUIDE.md) owns the
procedure; [repeatable experiments](REPEATABLE_RIG_EXPERIMENTS.md) owns the
case and measurement contract. Historical receipts stay with their original
script names; replacement summaries note that results may vary.

## Scope and count

From `git log --since=2026-11-01 --diff-filter=A --name-only --pretty=format: -- scripts`,
90 script files were added. Forty-three are `run_*.py` or `run_*.sh` entry
points: 15 Strata, 8 expert/PLE/transport, 16 Qwen/BigMoe chat or traces, and
4 other. This is a filename-based count of new entry points, not a claim that
all 43 implement the same job. Build scripts, CUDA kernels, analysis scripts,
and older runners are outside this count. The inventory below names all 43.

## Strata: 15 entry points

| Historical entry points | Pattern to use if a similar new request arrives | Repeated process |
|---|---|---|
| `run_strata_qwen36_probe.py`, `run_strata_qwen36_sweep.py`, `run_strata_qwen38_probe.py`, `run_strata_qwen38_sweep.py`, `run_strata_qwen38_placement.py`, `run_strata_qwen38_mixed_campaign.py` | Strata service adapter + `service_replay`/placement manifests | pack preflight, plan, load, health, resident budget, request, memory/I/O, stop |
| `run_strata_q4_smoke.py`, `run_strata_q4_32k.py`, `run_strata_q2_capacity.py` | Strata service adapter + `model_fit`/capacity manifests | candidate load, fit and first-answer checks |
| `run_strata_q4_fixed50k_speed.py`, `run_strata_q4_depth_curve.py`, `run_strata_q4_mtp_direct.py` | Strata service adapter + `service_replay`/`depth_replay` manifests | fixed prompt/depth, KV/MTP/budget controls, timing and block counters |
| `run_strata_q2_multichat.py`, `run_strata_q4_multichat.py`, `run_strata_q2_kv_stream.py` | Strata service adapter + `chat_sequence` manifests | independent chat admission, continuation, state isolation and cleanup |

The adapter must accept model, pack, engine build, GPU role, context, KV,
resident budget, MTP/drafting, fixture or saved state, output cap, and cache
policy. A different value goes in a manifest; a different Strata engine API
may justify a new adapter. Do not merge fixed-prompt throughput, multi-chat
isolation, and context-depth results into one comparison class.

## Expert, PLE, transport: 8 entry points

These eight launchers, plus `run_q38_tiered_one_worker.py` in the shared/other
section, were retired after their experiments. The tables map their questions
to a future case shape; see [EXPERT_TENSOR_RUNNER_GUIDE.md](EXPERT_TENSOR_RUNNER_GUIDE.md).

| Historical entry points | Pattern to use if a similar new request arrives | Keep distinct measurement |
|---|---|---|
| `run_q38_expert_card_probe.sh`, `run_route_selected_expert_placement.py`, `run_q38_tiered_expert_probe.sh`, `run_coder_next_expert_sweep.py` | CUDA component adapter + `component_probe` manifests | real expert extraction, resident/RAM/NVMe and worker-card invocation, numerical parity |
| `run_ple_shard_probe.sh` | CUDA component adapter + PLE shard plugin | packed-row fit and exact-byte lookup |
| `run_ple_bus_probe.sh`, `run_moe_transport_probe.sh` | transfer adapter + `transfer_probe` manifests | synchronized PCIe/NVMe/host-transfer timings with cold/warm policy |
| `run_q38_ple_model_smoke.py` | full-model experimental recipe smoke | model answer parity, real load time and end-to-end timing; never infer speed from row probe |

The tensor format and kernel can require a plugin, but the container/GPU UUID
mapping, build pin, sample hashing, correctness check, timing repetitions,
hardware snapshots, and terminal receipt should be shared. A successful
component probe does not promote a full-model recipe.

## Qwen and BigMoe chat/trace: 16 entry points

| Current entry points | Internal destination | Repeated process |
|---|---|---|
| `run_qwen27_chat_latency.sh` | saved-chat replay adapter + `paired_replay`/`depth_replay` manifests | pinned state, model/KV, host and worker roles, output cap |
| `run_qwen27_split_trace.sh`, `run_qwen35_pair_trace.sh`, `run_qwen27_dense_f16_decode_trace.sh`, `run_qwen35_durable_nvme.sh`, `run_qwen35_durable_reject.sh`, `run_qwen35_f16_decode_trace.sh`, `run_qwen35_decode_trace.sh`, `run_qwen35_nvprof_trace.sh` | replay adapter with explicit trace/storage modes | same hardware/session identity, Nsight or durable-NVMe capture and raw artifacts |
| `run_bigmoe_q2_long_switch.py`, `run_bigmoe_q2_server_switch.py`, `run_bigmoe_q2_route_trace.py`, `run_bigmoe_q2_session.py` | saved-chat/route scenario plugins | switch sequence, independent holdout trace, request timing and correctness |
| `run_bigmoe_q2_smoke.py`, `run_bigmoe_q4_smoke.py` | `model_fit`/smoke manifests using a managed load when supported | model readiness, one answer and cleanup |
| `run_qwen38_allcard_llama.py` | Manager-backed `model_fit`/`depth_replay` when its placement is supported; otherwise explicit experimental recipe | all-card placement, actual layer split, depth and recall |

Trace modes remain evidence artifacts, not separate benchmark result classes.
Manager-backed loads should replace direct llama.cpp launch code when the
orchestration rig layer can express the tested placement and engine.

## Shared or other: 4 entry points

| Current entry point | Internal role |
|---|---|
| `run_model_loading_sequence.py` | Keep as the managed session executor; typed cases compile into it. |
| `run_cuda_link_probe.py` | Keep as a transfer primitive called by a `transfer_probe` case. |
| `run_mode_smoke_stage.sh` | Keep only while its general rig-mode smoke is used; do not copy it for model variants. |
| `run_q38_tiered_one_worker.py` | Historical one-worker control; create a new component case only if a new question needs it. |

## Forward rule

This inventory records the questions old scripts answered. It is not a list
of cases to convert or rerun. Retire one-off launchers when their execution
is finished; keep receipts and useful fixtures. When a similar **new** request
arrives, resolve it with the runner guide, reuse the managed load path where
possible, and build only the adapter or case needed now. Note in new result
summaries that an older test used a retired script and results may vary. The
compiler and A/B/A example are available; no Strata adapter is required until
a new Strata test needs one.
