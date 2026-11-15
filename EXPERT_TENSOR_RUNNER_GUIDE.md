# Expert tensor placement runner guide

Use this guide when a **new** request asks where routed experts or the PLE/n-gram table should live, whether worker GPUs help, or what transfer tier costs. [TEST_RUNNER_GUIDE.md](TEST_RUNNER_GUIDE.md) owns the common case lifecycle. [EXPERT_TENSOR_PLACEMENT_TEST_PLAN.md](EXPERT_TENSOR_PLACEMENT_TEST_PLAN.md) retains dated experiment results and receipts. The old one-off launchers are retired; their results are evidence, not cases to convert or rerun.

## Turn a request into a test

| Example request | Case and endpoint | Choice to resolve |
|---|---|---|
| “Can this expert run on a 1060?” | `component_probe`: extracted real tensor, numerical parity, resident invocation latency | Model/quant, layer/expert, physical card, kernel/build |
| “1060 or 1070 for experts?” | Paired component probe with the same bytes and bracketing card order | Resident compute, RAM upload, or direct NVMe read? |
| “Can the small cards hold the experts?” | Capacity/placement screen, then real shard read and parity | Whole experts, within-expert shards, or hot cache? Which layer set and reserve? |
| “How much faster if we move experts to GPUs?” | Full-model A/B after component gate; answer parity, latency, physical I/O | Existing engine feature or an experimental bridge; model, context, chat state and baseline |
| “Can the PLE table live on the helper cards?” | PLE exact-row capacity and lookup, then full-model integration gate | Packed format, row count, card map, whether a supported runtime hook exists |
| “Is the PCIe link the bottleneck?” | `transfer_probe`: synchronized bytes, link width/speed and latency | Bulk expert bytes or tiny PLE row returns; cold or warm storage |
| “RAM or NVMe for hot experts?” | Tiered same-tensor probe and/or full-model cache-budget sweep | Resident bytes, hit set, route distribution, page-cache policy and physical-read endpoint |
| “Do these placement gains survive long chats?” | Full-model `chat_sequence`/`depth_replay` under matched placement | Occupied depth versus context cap, KV, slots, visible-answer oracle |
| “Can we combine Strata with PLE sharding?” | Compatibility/bridge gate, then full-model A/B | Current Strata binary has no PLE plugin hook; specify the new integration before claiming a Strata result |

If “test expert placement” leaves the endpoint open, start with an inventory and bounded correctness/capacity probe. Ask for the model/quant and placement mechanism if several are plausible. A one-expert latency, exact-row lookup, or PCIe copy is a component result; none predicts whole-model tokens/s by multiplication.

## Four separate mechanisms

1. **Whole-expert override:** a compatible llama.cpp recipe places entire named expert tensors on selected GPUs. Confirm the runtime log's actual placement. This is not a Strata expert cache.
2. **Native Strata helper cache:** a CUDA12 helper can cache selected routed experts for decode while GPU0 owns dense layers and KV. Measure useful entries and per-layer wait. It is not a layer split, PLE placement, or row sharding; CUDA13 on this rig does not execute GTX 1060 kernels directly.
3. **Within-expert shard worker:** an experimental kernel shards one routed expert across devices. Exact numerical parity and real route selection are prerequisites. Compare its transfer plus compute cost with a whole-expert control before integrating a model.
4. **PLE row shard:** a deterministic `(first_row, row_count, device)` map places packed lookup rows on cards. Exact-byte lookup establishes table fit. A patched llama.cpp bridge passed one same-model answer check; the installed Strata binary has no plugin hook for it. Keep this result class separate from routed experts.

## Resolved case and proof ladder

Record: question, proof class (`capacity`, `component_correctness`, `component_timing`, `transfer`, `full_model`), model/quant/pack and hashes, chosen tensor names or row ranges, extraction method and reference hash, runtime/kernel/container build, physical GPU UUID/PCI bus and link state, placement mechanism, bytes requested and observed per tier, host/VRAM reserve, context cap and occupied tokens where applicable, fixture and oracle, output cap, cache policy, warmup, repetitions, timeout, Manager claim and cleanup. For full-model comparisons also pin engine, KV, draft mode, card roles and baseline. Record physical NVMe reads, page-cache state, PCIe bytes where measurable, host `MemAvailable`, swap, load/startup, prefill, decode and total request times. A failed fit or numerical mismatch gets a terminal receipt.

Progress through the evidence needed for the question: read-only model/tensor inventory and capacity screen; extracted-tensor hash and reference; numerical parity across requested tiers/cards; repeated component timing with synchronized transfers; full-model integration and answer parity on the *same model bytes*; then an alternating A/B/A speed or quality comparison if that is the claim. Skip stages only when an existing receipt covers the same tensor format, kernel and placement. Do not redo Q2's entire card matrix for a new Q4 question unless the changed quant/kernel makes that control non-comparable.

Use gateway Manager and orchestration for ordinary supported model loads. Experimental kernels or PLE bridges run in benchmarking under a Manager run/claim for exactly the selected physical GPUs. The direct adapter owns its build pin, container launch, plan, placement verification, measurements and stop; it creates no second lease system. Keep reusable CUDA sources (`ple_shard_probe.cu`, `ple_shard_store.cu`, `ple_bus_probe.cu`), bridge/build code and historical campaign fixtures as inputs for a future case. A new request may justify a small component or transfer adapter; no adapter is required merely to preserve an old script.

## How to read the existing evidence

- The [Nov 13 card probe](results/runtime_experiments/q38_expert_card_20261113/README.md) compared one *Q2* resident expert on 3090+1060 and 3090+1070. Its 1070 invocation mean was 4.9% lower than bracketing 1060 controls; RAM upload and direct NVMe modes measured different costs. This does not establish a Q4 full-model speedup.
- The [Nov 13 PLE shard probe](results/runtime_experiments/q38_ple_shard_20261113/README.md) placed the 28.8 GB packed Q4 table across a 1070 and four 1060s and matched 513 sampled rows. The [patched-model smoke](results/runtime_experiments/q38_ple_model_smoke_20261113/README.md) produced identical text for file-backed and GPU-backed lookup, with 0.85 versus 0.88 tokens/s in one 16-token request and longer startup for the GPU path. It is a capacity/correctness result, not a speed claim.
- The [Nov 13 bus probe](results/runtime_experiments/q38_ple_bus_probe_20261113/README.md) measured Gen2 x1 helper links and small PLE row returns. Do not use bulk-transfer limits to explain complete request time without routed-expert byte traces.

Historical campaign JSON may still name a retired launcher. Treat those files as provenance and fixture examples. For a similar new request, write a fresh typed case against the current adapter, then note that the earlier test used a retired runner and results may vary. Preserve its raw receipt; do not restore the old entry point for compatibility.
