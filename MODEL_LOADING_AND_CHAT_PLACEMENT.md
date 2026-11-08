# Model loading and chat placement

This is the entry point for experiments that place one shared model and multiple
independent chats across the RTX 3090 Ti, five GTX 1060s, host RAM, and local
storage. The aim is to keep frequently used computation and state on the fastest
practical device while using slower tiers for capacity. A larger configured
context is useful only when occupied-depth recall and speed have been measured.

## Ownership and operating contract

Benchmarking owns measurements, raw receipts, and the passive
[`load_recipes.json`](load_recipes.json) handoff. The Pi gateway's
[`MODEL_LIBRARY_HANDOFF.md`](https://github.com/bigbertharig/llm-gateway/blob/main/docs/MODEL_LIBRARY_HANDOFF.md)
documents import and promotion. Manager owns the lookup from a supported recipe
ID to a known load procedure, resource leases, fit checks, launch, and observed
ready state. The rig executes that procedure. Harnesses and use cases request a
model, context, number of chats, and a preference such as latency or capacity;
they do not select cards, tensor overrides, cache files, or storage paths.

Manager should keep four choices at most for a model: fastest single chat,
balanced concurrent chats, largest validated per-chat context, and largest
validated model fit. A choice is offered only when its complete procedure is
implemented and measured for the requested context and hardware. A request
that does not fit returns a reason; Manager does not silently shrink context or
substitute a slower recipe. The ready response must report actual context,
chat capacity, placement ID, and measured versus estimated performance basis.

The existing registry and importer already pass named model profiles to Manager.
The recipe handoff added here is **passive**: schema v1 permits `research` and
`validated` records, but no `manager_ready` record. Importing a recipe cannot
make a private CUDA fork or a Strata-plus-worker topology runnable. A future
Manager capability must explicitly map the recipe's symbolic `procedure` to
its own vetted launcher before that status can exist.

## Keep model and chat decisions separate

| Component | Access pattern | Placement question |
| --- | --- | --- |
| Dense/attention weights, router, recurrent state | Touched every token or layer | How much can stay on the 3090 without starving active KV and workspace? |
| Routed experts | Sparse by expert but frequent across layers | Which whole tensors or shards repay their 1060/host transfer cost? |
| N-gram/lookup tables | Model-specific access | Can the runtime use a mapped or file-backed tier without exhausting host RAM? |
| Live chat KV and other per-chat state | Grows with occupied history; attention architecture matters | Does it belong on the attention GPU, a dedicated 1060, or host RAM with a hot GPU block cache? |
| Parked chat state | No decode until resumed | Is checkpoint-to-NVMe plus measured restore acceptable? |

Storage-backed **live** KV is a research target. Dense attention can revisit
an entire history on each token; writing a checkpoint to NVMe is a different
operation from serving active KV there. Sparse attention may permit a bounded
GPU hot-block cache over host RAM and, only with measured miss behavior, a
storage backing tier. The m10dis author's reported 262K sparse-KV update is
an external lead, not yet a reproduced rig result or a published Manager
capability. See [m10dis](https://github.com/crgregersen/m10dis) and
[BigMoeOnEdge](https://github.com/Helldez/BigMoeOnEdge) for distinct external
designs: the former distributes expert computation; the latter streams routed
experts from flash behind caches. Neither is our combined runtime.

## What has been measured here

| Layout | Evidence | Current limit |
| --- | --- | --- |
| Qwen3.6 27B weights on GPU0, separate chats' KV and attention on GPUs1-5 | [KV placement](KV_PER_CHAT_GPU_PLACEMENT_2026-11-06.md), [concurrent matrix](results/runtime_experiments/kv_local_worker_matrix_20261107/README.md), [filled-depth campaign](results/runtime_experiments/kv_overnight_20261107/README.md) | Private llama.cpp fork, no Manager serving profile; 27B deep-chat decode slows sharply at 90% occupancy. |
| Nemotron 74B weights and whole experts on GPU0-3, chats on remaining 1060s | [live expert/chat test](results/runtime_experiments/kv_expert_chat_20261107/README.md), [matched placement](results/runtime_experiments/kv_matched_placement_20261107/README.md) | Private fork; the 131K paired chat had short occupied history. Byte-balanced interleaving did not beat contiguous experts. |
| Llama 70B weights across six GPUs, host-RAM KV | [overnight campaign](results/runtime_experiments/kv_overnight_20261107/README.md) | Short 128K-capacity generation and separate 8K depth probe; 128K occupancy and useful serving speed unproved. |
| Qwen3.8 Q2 Strata, GPU/RAM/NVMe | [memory plan](STRATA_MEMORY_TEST_PLAN.md), [matched mixed-card comparison](results/runtime_experiments/strata_q38_mixed_matched_20261106/README.md) | One-card long-context recall and mixed-card short-context tests; no independent per-chat placement or combined Strata-plus-1060 expert workers. |
| Qwen3.8 Q4 | [expert placement plan](EXPERT_TENSOR_PLACEMENT_TEST_PLAN.md) | Four verified shards staged on rig NVMe; runtime pack and full-model run pending. |

Whole-expert placement improved Coder Next and Nemotron decode, while ordinary
layer splits across slow 1060 links often hurt. [Tiered real-expert probes](results/runtime_experiments/q38_tiered_expert_probe_20261106/README.md)
show that row-sharded 1060 compute can avoid a cold NVMe miss but has not beaten
a 3090 RAM upload for one Q2 expert. Do not multiply a one-expert latency into
a full-model tokens/s claim. The rig topology has no direct 3090-to-1060 peer
access in these probes, so account for host-staged transfers and synchronization.

## Experiment to managed recipe

1. **Inventory:** identify exact GGUF bytes, engine build, model components,
   GPU topology, host budget, storage backing, KV format, and workspace per
   device. Distinguish requested capacity from occupied depth.
2. **Measure:** retain cold and warm load, prefill, decode, total request time,
   concurrent aggregate and per-chat rates, physical I/O, memory minima, and
   correctness/recall at realistic depths. Record failed fits and the limiting
   allocation. Use matched model, prompt, context, and output conditions for
   comparisons.
3. **Record:** add a stable ID and receipt links to `load_recipes.json` as
   `research`; change to `validated` only after its stated context, concurrency,
   and correctness claims pass. `procedure` is an identifier, never shell text.
4. **Implement:** Manager and the rig add an explicit capability for the
   procedure, reserve *all* weight and chat devices and host memory, launch one
   shared model, and verify observed buffers, context, and chat admission.
5. **Promote:** only a later schema and Manager implementation may offer a
   managed recipe. Test full request routing, concurrent admission, cancel,
   unload, failure cleanup, and fallback refusal before exposing it to harnesses.

The next capacity gate is Q4 Strata on the staged verified shards, followed by
a matched BigMoeOnEdge control if that engine accepts the same GGUF. The next
multi-chat gate is a managed version of the 27B GPU0/1060 KV layout. Real
routing traces should decide whether expert-granularity 1060 caching repays
transfer cost before building a Strata-plus-worker bridge.
