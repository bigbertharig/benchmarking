# Model loading and chat placement

This is the entry point for open-ended experiments with model components and
independent chats across the RTX 3090 Ti, five GTX 1060s, host RAM, and local
storage. The broad goal is to load larger models and make them useful at better
speeds. We are exploring placements, chat behavior, tensor layouts, caching,
and runtime designs; no single layout or Manager procedure is the target yet.
The order of experiments can change when a result suggests a better question.

For common GPU/RAM/NVMe traces and back-to-back case scheduling, see
[Tier diagnostics and test series](TIER_DIAGNOSTICS_AND_TEST_SERIES.md).

For exact settings to reload the current Nemo two-chat and Qwen 35B five-chat baselines, see [MoE chat baseline reloads](MOE_CHAT_BASELINE_RELOAD_2026-11-09.md).

## Current speed results (2026-11-09)

For a model on GPU0 and one F16 chat on GPU1, the
[matched 16K/32K/50K replay](results/runtime_experiments/model_loading_sequences/qwen27-dense-f16-tile128-64k-20261109/README.md)
measured **70.5/62.5/52.6 tok/s** for Qwen3.6 35B-A3B MoE versus
**23.2/18.6/14.8 tok/s** for Qwen3.6 dense 27B. Both use the 128-thread
Pascal attention tile and 64-token solo windows. Dense F16 fits only a 64K
reservation on one 1060; MoE F16 fits 262K. An entire Qwen3.5 4B on one
1060 previously measured about 23.6 tok/s near 16.7K and 21.2 near 30.4K.
That 4B comparison uses different model-compute hardware.

The [50K dense/MoE Nsight trace](results/runtime_experiments/model_loading_sequences/qwen27-dense-f16-trace-50k-20261109/README.md)
found 2,473 versus 558 ms summed 1060 attention time, 1,324 versus 369 ms
summed GPU0 graph time, and 89 versus 40 MB copied into the 1060 across
64 generated tokens. The activities overlap; these are diagnostic totals,
not additive wall time. Attention and model compute both deserve targeted
speed tests. The [single-worker return-delta result](results/runtime_experiments/model_loading_sequences/qwen35-return-delta-20261109/README.md)
addresses post-response state capture, and the
[durable checkpoint result](results/runtime_experiments/model_loading_sequences/qwen35-return-durable-20261109/README.md)
addresses process restart recovery. Neither raises raw generation tok/s.

## The big picture

There are two linked goals. The systems goal is to use the rig's separate 3090
VRAM, 1060 VRAM, host RAM, and NVMe tiers to run larger models at useful speed.
Strata demonstrates a software-managed GPU/RAM/storage hierarchy, and
BigMoeOnEdge and m10dis supply ideas for caching, streaming, and placing routed
experts. This is not a true unified memory pool: each tier has its own capacity,
access cost, and supported runtime operations. The installed Strata path has
run Qwen3.8 with GPU0, RAM, and NVMe. Strata also documents a helper-GPU
path for routed expert decode, but 1060 helpers remain untested on this rig.
The [expert placement plan](EXPERT_TENSOR_PLACEMENT_TEST_PLAN.md) tracks
that next placement experiment.

The practical goal is to keep a capable model resident as a main brain and
admit more work without repeatedly loading its weights. A helper can be a new,
independent chat on that same model, gaining the same weights and quantization
as the main chat, or a separately loaded smaller model with its own speed and
quality tradeoff. Shared weights do not guarantee equal per-chat speed: KV
placement, occupied history, concurrent attention, and contention with the
main chat all matter. Different model families and quants also need quality
checks before calling one configuration smarter than another.

We are still learning what fits, how independent chats behave, and where time
and bytes move. After that, optimize promising placements and compare them on
realistic workloads. Only then choose a small number of useful load styles for
Manager and harnesses. The current passive recipe handoff records evidence; it
does not commit us to a serving policy.

## Questions to explore

Try different ways to place weights, dense layers, experts, lookup tables,
workspace, and chat state across the available tiers. For a shared model load,
open chats A, B, C, and later chats with different histories and sizes, then
continue earlier chats. Test whether the runtime can add chats without moving
or reloading model buffers, and whether it can change chat capacity at runtime.
These are useful probes, not required steps for every placement experiment.

Measure enough to understand what happened: actual buffer residence where it
can be observed, GPU/host/storage use, configured and occupied context,
correctness, load time, prefill, decode, and physical I/O. A failed fit or a
slow layout can be informative. Pursue a promising speed or tensor-placement
idea when the evidence points to it; there is no requirement to finish every
capacity case first. Test parked-chat restore separately from live KV access.

Keep claims precise. One loaded engine serving several sessions demonstrates
logical separation of model and chat. Physical separation requires evidence
that chat state lives on a different GPU, in RAM, or in storage while model
placement stays fixed. A configured context is distinct from occupied depth;
prefix reuse is distinct from durable session state. The Q2 Strata results
establish useful logical separation, with physical state location still open.

## Research now, orchestration later

Benchmarking owns experiments, scripts, observations, and raw receipts. The
existing [`load_recipes.json`](load_recipes.json) handoff preserves information
for possible later use by the Pi gateway, whose
[`MODEL_LIBRARY_HANDOFF.md`](https://github.com/bigbertharig/llm-gateway/blob/main/docs/MODEL_LIBRARY_HANDOFF.md)
describes import. It is passive research metadata, not a requirement to turn
each promising idea into a Manager procedure. The current Manager is useful
for rig leases, safe launches, and restoring normal service while experiments
remain free to use private forks, direct launchers, and unusual hardware
layouts. Once the useful patterns are clearer, we can decide which ones are
worth generalizing and exposing to harnesses.

## Keep model and chat decisions separate

| Component | Access pattern | Placement question |
| --- | --- | --- |
| Dense/attention weights, router, recurrent state | Touched every token or layer | How much can stay on the 3090 without starving active KV and workspace? |
| Routed experts | Sparse by expert but frequent across layers | Which whole tensors or shards repay their 1060/host transfer cost? |
| N-gram/lookup tables | Model-specific access | Can the runtime use a mapped or file-backed tier without exhausting host RAM? |
| Live chat KV and other per-chat state | Grows with occupied history; attention architecture matters | Does it belong on the attention GPU, a dedicated 1060, or host RAM with a hot GPU block cache? |
| Parked chat state | No decode until resumed | Is checkpoint-to-NVMe plus measured restore acceptable? |

### Baseline: model work, chat work, and preparation

For the current Qwen3.6-35B-A3B Q4_K_XL experiments, use **one model load
with weights on GPU0 and independent chats with resident KV on separate
1060s** as the placement baseline. Keep GPU0 free of a resident chat. The
working two-chat reference has GPU1 for main-chat KV and GPU2 for
secondary-chat KV, both reserving 262,144 positions. The labels main and
secondary describe use, not a different priority or model. This baseline
specifies *where* work runs; a speed comparison must also hold the model
file/build, KV format, occupied depth, reservation, prompt, answer length,
and active-chat count fixed. Record model cold load separately from chat
admission and steady generation.

| Work | Needs to be fast when | Current placement rule and measurement |
| --- | --- | --- |
| Model weights and repeated layer computation | Every prompt and generated token | Keep dense weights, router, and hot experts on GPU0 while they fit; measure GPU0 compute and any expert misses per token before moving weights. An inactive or rarely selected expert may be worth a slower tier only if measured transfer and cache behavior repay the space. |
| Chat preparation | A new chat is admitted or existing history grows | Choose a temporary workspace by **time to a usable, correct chat**, including prefill, capture, handoff, and restore. GPU0 may use its own VRAM, a dedicated 1060, or RAM depending on headroom and contention. The 100K → 150K one-chat helper result is 422.5 s with GPU0+GPU1, versus about 594 s with GPU0+RAM and 749.2 s with direct 1060 fill; these paths differ in temporary cap and batch size. |
| Live chat KV and attention | Every generated token, increasingly with occupied history | Keep the active KV beside the attention work on its assigned 1060. Avoid moving the full growing history every token. Compare per-chat tok/s, first-token delay, and interference with other chats at fixed depth; test compact KV only against matched F16 controls. |
| Chat handoff or parked state | At admission, turn boundaries, or resume | Move a completed state in infrequent, measured transfers; use a validated delta when available. NVMe checkpoints are useful for parking and replay, but are not evidence that dense attention can efficiently read live KV from storage. |

This is a tiered placement rule, not a fixed ranking that always chooses
GPU0, then 1060, then RAM, then NVMe. Capacity, access pattern, supported
kernels, and transfer frequency determine the fastest *whole workflow*.
The x1 1060 link can make repeated cross-device traffic expensive; the
recent GPU0+GPU1 admission win does not prove x1 bandwidth exceeds RAM
bandwidth. We should minimize repeated transfers of weights, activations,
and KV, while allowing a bounded state handoff when it saves more prefill
time than it costs.

The existing [Q4 two-chat curve](results/runtime_experiments/model_loading_sequences/qwen35-moe-two-curve-20261109/README.md)
measured GPU0 preparation followed by independent GPU1/GPU2 chats, not
GPU0+RAM preparation. The [Q4_1 two-chat replay](results/runtime_experiments/model_loading_sequences/qwen35-moe-q41-main-secondary-16k32k50k-20261109/README.md)
did the same at 16K/32K/50K. F16 workers reached about 68/60/50 tok/s
solo and 64/57–58/49–50 tok/s each with two active chats at those depths;
this is the current short-depth F16 **decode reference**, not a matched
GPU0+RAM versus GPU0+1060 admission comparison. The
[150K admission test](results/runtime_experiments/model_loading_sequences/qwen35-admission-paths-20261109/README.md)
compared one-chat preparation paths and five direct fills. It did not
measure two sequential helper admissions or a new helper admission during
another chat's generation.

Five-way *admission* overlapped well: five direct 100K → 150K fills took
866.4 s versus 749.2 s for one. Five-way *decode* has a separate cost:
at 16K, a F16 worker fell from 76.5 tok/s solo to about 40 tok/s with
five active; at 100K, from 33 to about 27. These are distinct workloads
and neither number predicts whole-turn latency by itself.

The [matched two-chat F16 comparison](results/runtime_experiments/model_loading_sequences/qwen35-two-admission-small-20261109/README.md)
ran direct worker filling, GPU0+RAM preparation, and GPU0+dedicated-GPU1
preparation for two final 1060 chats at 16K/32K/50K. All arms passed
private-code recall. Both chats were ready in 134.5/195.9/270.8 seconds
on the direct path, 88.5/136.3/194.4 seconds with RAM preparation, and
95.7/136.8/175.8 seconds with the GPU1 helper. These measured stage
intervals include a solo main-chat generation window between admissions.
RAM won 16K readiness, RAM and helper were effectively tied at 32K, and
helper won 50K readiness. During the early 50K secondary admission,
the main chat ran at 45.9 tok/s with RAM preparation but only 30.6 tok/s
with the helper, versus about 49.8 tok/s solo. The helper leaves four
1060 worker slots; RAM leaves five. Preparation placement therefore needs
an admission-time **and** active-chat-interference budget. Next repeat
the 50K helper overlap with a longer, full-admission generation trace and
GPU0/GPU1/x1 utilization before treating the 50K readiness win as useful
for a busy main chat. Keep this follow-up at 16K/32K/50K.

### Prepare on fast hardware, then place on a slower tier

The 3090 can act as a temporary preparation engine: create a chat history or
other reusable state there, then move its finished representation to the card,
RAM, or storage tier where it will live. Keep preparation, serialization,
transfer, restore, and first generation step as separate measurements. A
handoff wins on admission only when fast preparation plus moving the result is
shorter than preparing it at the destination. Measure subsequent decode too:
the move does not make a slow destination fast during generation.

The KV-state path has now passed for one deep chat and for two different 100K
chats on one 1060. Other candidates are prepared prompt prefixes,
packed or quantized weights, expert tensors, and sparse-attention hot blocks.
Each needs a compatible representation at the destination and enough space for
any temporary staging copy. Check whether preparing one new artifact disturbs
chats already resident there. Do not assume that a model tensor or a live KV
cache can be moved as cheaply as a completed chat checkpoint.

Storage-backed **live** KV is a research target. Dense attention can revisit
an entire history on each token; writing a checkpoint to NVMe is a different
operation from serving active KV there. Sparse attention may permit a bounded
GPU hot-block cache over host RAM and, only with measured miss behavior, a
storage backing tier. The m10dis author's reported 262K sparse-KV update is
an external lead, not yet a reproduced rig result. See
[m10dis](https://github.com/crgregersen/m10dis) and
[BigMoeOnEdge](https://github.com/Helldez/BigMoeOnEdge) for distinct external
designs: the former distributes expert computation; the latter streams routed
experts from flash behind caches. Neither is our combined runtime.

## Upstream projects to check before a new campaign

| Project | Repository and useful entry points | What to watch for |
| --- | --- | --- |
| [m10dis](https://github.com/crgregersen/m10dis) | [Results](https://github.com/crgregersen/m10dis/blob/main/docs/RESULTS.md), [architecture](https://github.com/crgregersen/m10dis/blob/main/docs/ARCHITECTURE.md) | A committed 262K sparse-KV implementation and receipts: occupied depth, GPU hot-buffer size, RAM use, hit/miss rate, MTP settings, and decode rate. Its PCIe peer/multicast path differs from our host-staged 1060 links. |
| [BigMoeOnEdge](https://github.com/Helldez/BigMoeOnEdge) | [Planner](https://github.com/Helldez/BigMoeOnEdge/blob/main/docs/hardware-planning.md), [streaming](https://github.com/Helldez/BigMoeOnEdge/blob/main/docs/moe-streaming.md), [model compatibility](https://github.com/Helldez/BigMoeOnEdge/blob/main/docs/which-models-stream.md) | Same-GGUF Qwen3.8 compatibility, GPU expert-cache behavior, physical reads on cold and diverse prompts, multi-chat serving, and how its planner accounts for the n-gram table. |
| [Strata](https://github.com/Niko1221/Strata) | [Q4 setup](https://github.com/Niko1221/Strata/blob/main/docs/UNSLOTH_Q4.md), [engine details](https://github.com/Niko1221/Strata/blob/main/docs/DETAILS.md), [supported models](https://github.com/Niko1221/Strata/blob/main/docs/MODELS.md) | Q4 pack and low-RAM requirements, 1060-compatible builds, concurrent chat/KV support, and changes to the resident expert and storage tiers. |

Pin the exact upstream revision and engine build in every local receipt. A new
README claim or Reddit post is a lead until its code, conditions, and result
are available; do not merge numbers from different quants, contexts, drafts,
or hardware into one comparison. Checking these links is part of each new
campaign preflight, not an automatic change to our test conclusions.

## What has been measured here

| Layout | Evidence | Current limit |
| --- | --- | --- |
| Qwen3.6 27B weights on GPU0, chats' KV on 1060s and/or RAM | [KV placement](KV_PER_CHAT_GPU_PLACEMENT_2026-11-06.md), [filled-depth campaign](results/runtime_experiments/kv_overnight_20261107/README.md), [alternating chats](results/runtime_experiments/model_loading_sequences/qwen27-alternating-tiers-20261108/README.md), [mixed-tier chats](results/runtime_experiments/qwen27_mixed_ram_gpu_20261108/README.md) | Private llama.cpp fork; new chats were added without a second weight load. Five distinct 1060 chats reached 90% of 256K and passed recall; GPU1, RAM, and GPU2 chats also coexisted and decoded. Deep mixed-tier recall and practical admission speed remain open. |
| Nemotron 74B whole experts on GPU0-4, chat-only GPU5; also a GPU0-3 layer split with chats isolated on GPU4/5 | [live expert/chat test](results/runtime_experiments/kv_expert_chat_20261107/README.md), [matched placement](results/runtime_experiments/kv_matched_placement_20261107/README.md), [two isolated 32K chats](results/runtime_experiments/model_loading_sequences/nemotron-two-isolated-chat-depth-20261108/README.md) | Private fork; two GPU4/GPU5 chats each reserved 262K and reached 32K occupied history on one GPU0-3 weight load, decoding concurrently at about 11 tok/s each. The prior 131K paired chat was only shallowly occupied. Larger occupied depths, retrieval quality, and ongoing chat migration remain open. |
| Llama 70B weights across six GPUs, host-RAM KV | [overnight campaign](results/runtime_experiments/kv_overnight_20261107/README.md) | Short 128K-capacity generation and separate 8K depth probe; 128K occupancy and useful serving speed unproved. |
| Qwen3.8 Q2 Strata, GPU/RAM/NVMe | [memory plan](STRATA_MEMORY_TEST_PLAN.md), [three-chat gate](results/runtime_experiments/model_loading_sequences/strata-q2-three-chat-20261108/q2_three_chat_detail/terminal.json) | Logical separation: one loaded model served three distinct short chats at a common 8K configured limit. No mixed-size or occupied-depth multi-chat result, independent KV placement, or combined 1060 expert workers. |
| Qwen3.8 Q4, 3090/RAM/NVMe | [expert placement plan](EXPERT_TENSOR_PLACEMENT_TEST_PLAN.md), [32K single chat](results/runtime_experiments/model_loading_sequences/q4-32k-baseline-20261108/q4_32k_detail/terminal.json), [two 32K slots at 15K](results/runtime_experiments/model_loading_sequences/strata-q4-two-32k-16k-20261110/README.md) | One 125B-class weight load served two independent, interleaved chats at 15,084 occupied tokens each, with 32K reserved per slot. Each first deep turn read about 100 GB from NVMe and took about four minutes; warm continuations were much quicker. Slots were reserved at launch and physical KV tier is unproven. |
| Qwen3.8 on BigMoe | [same-file Q4 smoke](results/runtime_experiments/model_loading_sequences/bigmoe-q4-compat-20261108/bigmoe_q4_detail/terminal.json), [Q2 warm session](results/runtime_experiments/model_loading_sequences/bigmoe-q2-session-20261108/bigmoe_q2_session_detail/terminal.json) | Q4 32K CPU/flash correctness passed. One Q2 CLI session served five correct turns; clearing KV reset live context but retained a warming expert cache. Concurrent independent live KV remains untested. |

The [Nemotron five-card expert / one-card chat follow-up](results/runtime_experiments/nemo_single_chat_20261109/README.md) keeps weights on GPU0-4 and one 262K-capacity chat on GPU5. At 16K/32K/50K occupied history, F16 KV improved solo decode from 32.10/27.15/22.56 to 38.05/34.40/32.50 tok/s versus Q4_0, at the cost of 2,048 versus 576 MiB GPU5 KV allocation. Preparing 16K/50K F16 histories on GPU0 then handing off to GPU5 took 34.89/107.40 seconds plus 0.38/1.07 seconds restore, compared with 115.36/411.31 seconds cumulative direct GPU5 fill. A 250K occupied F16 preparation and GPU5 handoff also passed: GPU0 peaked at 23,169/24,564 MiB, preparation took 559.66 seconds, restore took 5.24 seconds, and GPU5 decoded at 18.14 tok/s. This is synthetic-history, single-chat evidence; a matched layer-split control, long output, quality checks, and GPU0 contention remain to be measured.

The [reversed Nemotron placement](results/runtime_experiments/nemo_chat3090_20261109/README.md) put a 262K-capacity F16 main chat on GPU0 and tested expert tensors on four versus five 1060s. Four expert cards decoded at 44.58/44.21/43.86 tok/s at 16K/32K/50K occupied history, about 14% faster than five expert cards. Keeping the four-card map and adding a GPU5 worker produced two concurrent 50K chats at 33.93 and 27.61 tok/s; both first answers were correct and GPU0 peaked at 23,373 MiB. This proves two admitted F16 chats at 50K synthetic depth, not two 250K occupied chats or deep retrieval.

**Additive chat admission is established in the private llama.cpp fork.** With
weights held once, the 27B tests opened distinct chats on separate 1060s, a
shared 1060, paired 1060s, and RAM at different configured and occupied sizes.
The Nemotron tests added a third chat while two were already active. This is
the ability to add independent contexts, not a guarantee that every new chat
fits or responds quickly. Removing and replacing chats across all tiers has
only been checked for three sequential 27B workers on one 1060.

Whole-expert placement improved Coder Next and Nemotron decode, while ordinary
layer splits across slow 1060 links often hurt. [Tiered real-expert probes](results/runtime_experiments/q38_tiered_expert_probe_20261106/README.md)
show that row-sharded 1060 compute can avoid a cold NVMe miss but has not beaten
a 3090 RAM upload for one Q2 expert. Do not multiply a one-expert latency into
a full-model tokens/s claim. The rig topology has no direct 3090-to-1060 peer
access in these probes, so account for host-staged transfers and synchronization.

## Working method

Keep an exact engine revision, model bytes, settings, topology, and resource
snapshot with each run. Record cold and warm load, prefill, decode, I/O,
memory, and correctness when relevant to the question. Use matched conditions
when comparing two layouts; use small probes when exploring a new mechanism.
Record surprising failures and dead ends as well as successes. A result may
lead to another placement test, a tensor experiment, a speed experiment, or a
different model family. Add research notes to the passive handoff when useful;
Manager integration is a separate future choice.

## Workloads to anchor the next comparisons

Use the same evolving conversation and output requests when comparing memory
placements of one model. Record each turn's occupied context, added prompt
tokens, prefill time, first-token delay, per-chat decode rate, correctness,
and physical GPU/RAM/storage use. Include ordinary back-and-forth turns and a
few long additions; report a speed curve, not one short-prompt number or a
10%/90% pair alone. Separate the cost of preparing and transferring a chat
from its later generation speed.

Then compare three practical schedules under a fixed hardware budget: main
brain alone; main brain plus a same-model worker chat; and main brain plus a
separately loaded small worker model. Measure main-chat latency while helpers
work, each helper's useful output, total task completion time, cold admission
time, and the memory/IO left for the next helper. A new chat has no second
weight load, but may still slow the main chat; a small model has a load cost
but may finish its part faster.

Use the best plausible large-brain candidates, not parameter count alone.
The 74B-total/9B-active Nemotron MoE has a 32K short-probe result around
24 tok/s on GPU0-3; dense Llama 70B was much slower in its measured six-card
layout. Qwen3.8 Q2/Q4 Strata can reach the RAM/storage tiers, but its cold
reads, context depth, and independent-chat behavior need the same workload
measurements. For a promising oversized candidate, compare placements on the
same model bytes and conversation trace, with expert-route hit/miss rates and
physical reads, before attributing a gain to a particular tier.

## Suggested next tests

This is a menu of capability questions, not a required sequence. Favor a small
test that exposes a new operation or a surprising boundary before tuning its
speed. Keep the weight load, chat state, and actual buffer locations separate
in every receipt.

1. **Worker chat lifecycle on one 1060 (first pass complete).** Keep a 27B
   model and main chat on GPU0. Open worker A on GPU1, use it for multiple
   turns, close it, and open worker B with a different code and context
   capacity on the same card.
   Repeat once more. Time context creation, cleanup, and the next worker's
   first useful answer; verify GPU1 memory is reclaimed, the main chat
   continues correctly, and the model weights load once.
   This tests serial reuse, not simultaneous serving. The
   [A → B → C lifecycle run](results/runtime_experiments/model_loading_sequences/qwen27-worker-chat-lifecycle-20261108/README.md)
   passed with one weight load, correct recalls, 0.15–0.16 second context
   turnover, and GPU1 returning within 6 MiB of its baseline after each close.
   Follow with many turnovers and an explicit test that B cannot see A's state.
2. **Nemotron model across cards, worker on the spare 1060.** The 74B MoE
   baseline already placed weights on GPU0-4 and a chat on GPU5. Two 8K chats
   and an added 131K-capacity paired chat worked; a separate 32K paired chat
   reached 29,491 occupied tokens. The model advertises 262K context and Q4
   KV allocated 288 MiB for a 131K paired context. A new
   [GPU0-3 weight, GPU4/GPU5 isolated-chat run](results/runtime_experiments/model_loading_sequences/nemotron-two-isolated-chat-depth-20261108/README.md)
   admitted two 262K-capacity chats and filled both to 32K; per-chat decode
   was 12.6, 12.1, and 11.0 tok/s at 8K, 16K, and 32K occupied depth.
   Next test 128K and the largest safe occupied depth with retrieval checks.
   In the GPU0-4 expert layout, keep a main chat's KV on GPU0 (also compare
   GPU4) and add an independent GPU5 worker. Measure matched per-chat speed
   and main-chat delay, then close and replace the worker without reloading
   weights. The exact 13.6 versus 33.6 tok/s short-history comparison changes
   weight placement as well as card count; a controlled placement sweep is
   needed to attribute its speed difference.
3. **27B per-chat speed and admission optimization.** The GPU0-weight,
   1060-chat layout has strong capacity and correctness evidence, but a new
   chat's history fill and deep generation are slow on a 1060. Measure
   conversation turns at matched occupied depths with one worker, multiple
   workers, and a GPU0-KV control. Separate context creation, direct 1060
   prefill, GPU0 preparation plus KV transfer, first answer, and steady decode.
   Do not extrapolate the 1K worker fill linearly: two directly filled 100K
   GPU1 chats each took about half an hour as attention cost grew with depth.
   Test whether GPU0 preparation delays the continuing main chat. The
   [two-100K handoff](results/runtime_experiments/model_loading_sequences/qwen27-two-100k-handoff-20261108/README.md)
   cut admission sharply, while the
   [matched 102K comparison](results/runtime_experiments/model_loading_sequences/qwen27-matched-100k-kv-placement-20261108/README.md)
   measured 26.73 tok/s on GPU0 KV versus 3.66 tok/s on GPU1 KV; use those as
   controls before trying placement or transfer optimizations.
4. **Removal across tiers.** Adding independent chats is established. With
   one model load, remove and replace chats of different context caps on
   separate 1060s, a shared 1060, a pair, and RAM. Check whether releasing
   one chat makes capacity available for another without moving the weights
   or invalidating surviving chats; probe explicitly for stale state.
5. **Move, park, and revive a chat.** Prepare on GPU0, restore on a 1060 or in
   RAM, park to NVMe, and revive on a different tier. Measure transfer and
   first answer separately; check whether it is a compatible live state or a
   prefix that must be recomputed. Test a main chat continuing during worker
   preparation, because temporary GPU0 memory and compute may interfere.
   The [27B ongoing-turn handoff](results/runtime_experiments/model_loading_sequences/qwen27-ongoing-turn-handoff-20261108/README.md)
   passed three GPU1 → GPU0 → GPU1 trips: each roughly 4K-token new turn was
   prepared on GPU0 and answered correctly on GPU1. Complete turn time was
   4.46–4.71× faster than direct GPU1 prefill at 8K–16K occupied depth,
   including both state transfers. Next test a continuing main chat during
   worker preparation, deeper and varied histories, and the full recurrent
   state path for Nemotron. Compare against direct GPU5 prefill there.
6. **Strata shared-brain lifecycle.** With a viable Q2/Q4 load, test whether
   independent chats can open, close, and restart without reloading model
   state. Record each chat's physical state tier and main-chat responsiveness.
   This has different runtime semantics from the private llama.cpp fork.
7. **Placement and caching.** Use real expert-route traces to compare whole
   experts, selected hot experts, and row shards on 1060s against RAM and
   storage misses. The installed CUDA 12 engine exposes native helper-cache flags for Pascal;
   verify a real 1060 load and measured helper work before claiming a gain.
8. **Conversation speed curves.** Once the lifecycle and tier operations are
   mapped, run back-and-forth transcripts that grow through several occupied
   depths. Report per-turn speed ranges for each working layout, including
   how concurrent worker chats affect the main chat.

9. **F16 chat admission and contention.** The
   [matched 35B admission comparison](results/runtime_experiments/model_loading_sequences/qwen35-admission-paths-20261109/README.md)
   extended saved 100K chats to 150K with GPU0 model weights and F16 worker
   KV. One direct 1060 fill took 749.2 seconds; five simultaneous direct
   fills took 866.4 seconds until all were ready, with recall correct for
   every chat. Thus the five fills did not serialize on GPU0, although the
   first five-way chat was slower than one solo fill. A dedicated GPU1
   preparation helper made one GPU2 chat usable in 422.5 seconds after
   source restore, leaving four worker slots on GPUs2–5. Four sequential
   helper admissions and interference with active workers were not measured.
   RAM-backed preparation took about 594 seconds per sequential chat in the
   earlier partial run. These are workflow comparisons with different
   temporary KV reservations and batch sizes, not raw memory-bandwidth
   measurements.

   Next, test compact Q4_1 preparation KV on GPU0 and handoff to F16 worker
   KV at up to 150K, measuring GPU0 peak VRAM and first useful token. Probe
   the dedicated helper while an existing worker generates, and measure
   time until each chat is ready and all four are ready. With identical
   occupied histories, trace GPU0 compute, x1 links, and 1060 attention in
   matched solo and five-chat 1,000-token decode windows. At 16K the
   previous five-chat rates fell from 76.5 solo to about 40 tok/s per chat;
   at 100K, from 33 solo to about 27. The new 150K comparison tested
   admission and short recall, not sustained answer generation.

10. **Two deep Nemo chats on the faster placement.** Reload the saved
    [four-expert-card, GPU0-main/GPU5-worker baseline](MOE_CHAT_BASELINE_RELOAD_2026-11-09.md).
    Both chats reserve 262K, but simultaneous occupancy is proven only through
    50K. Increase both histories in bounded steps, recording GPU0 peak memory,
    first-token correctness, each chat's decode, and whether admitting the
    worker disrupts the main chat. A solo 250K GPU5 chat does not establish a
    two-chat 250K fit; stop at the first reproducible capacity boundary.
11. **Separate lookup-table traffic from expert traffic.** Use the Qwen3.8
    UD-Q4 model already on NVMe. At a fixed 16K or 32K context, compare a
    cold request, a repeated request, and a different request while logging
    physical reads and the model's table/expert access counters where the
    engine exposes them. This tests whether the n-gram table or expert misses
    dominate our storage tier. Only then try a different table format or
    cache policy if the current runtime supports one; keep model weights
    fixed and check quality as well as bytes and latency.
12. **Layer-aware expert-cache placement.** From our existing Qwen3.8
    routing traces, rank hot experts separately for early, middle, and late
    layers on one prompt set, then check hit coverage on held-out prompts.
    Compare equal-byte hot sets against uniform per-layer budgets and record
    misses and estimated RAM/NVMe traffic. Test a real placement only if
    held-out coverage predicts a material benefit. This applies the
    Reddit post's lesson that layers may differ in value without requiring
    its unpublished mixed-precision pack; [the precision branch](EXPERT_TENSOR_PLACEMENT_TEST_PLAN.md#research-lead-per-layer-precision-and-n-gram-table-2026-11-10)
    remains a later quality experiment.
13. **Strata-slim VRAM-reclamation controls.** If we revisit Strata on the
    rig, pin the [reviewed fork and optional patches](MOE_CHAT_BASELINE_RELOAD_2026-11-09.md#strata-slim-idea-to-revisit),
    then compare the same pack and workload with each capacity patch enabled
    individually. Measure actual VRAM reclaimed, expert-cache hit rate,
    file-tier reads, and complete-turn speed. Confirm that a build supports
    the 3090 and 1060 architectures before using it for a mixed-card test.

14. **Cache-budget crossover on the existing Qwen3.8 load.** Hold model,
    prompt, occupied context, KV, and engine fixed while varying a safe
    expert-resident budget around the current 8 GiB setting. Record cache
    hit rate, NVMe read bytes, prefill, steady decode, first-token time,
    GPU0 headroom, and host `MemAvailable`. This tests the transferable
    question from the 5090 discussion: how much speed does one more GiB of
    hot experts buy on *our* RAM and NVMe path? Use the rig's established
    memory guard and stop when added residency displaces useful workspace.

15. **Qwen3.8 Q4 model and chat tier matrix.** The existing Q4 results
    establish GPU0-only 8K and 32K configured loads, with at most about 15K
    occupied tokens in the two-slot run. They do not establish a matched
    one-chat 16K/32K/50K speed curve. The
    [four-case 64K campaign](campaigns/strata_q4_onechat_tier_overnight_20261110.json)
    keeps one slot, INT8 KV, an 8 GiB expert RAM budget, a 1,024-token
    prefill setting, and the same additive conversation. Compare GPU0 only,
    GPU0+one 1060 layer split, all six GPUs, and all six with KV streamed
    from RAM above a 32K resident window. Record actual stage/layer order,
    per-card cache capacity, occupied prompt tokens, prompt and decode tok/s,
    physical NVMe reads, memory, and whether all four placements fit.
    The n-gram table stays file-backed with opportunistic OS page caching.
    Strata's layer split duplicates stage KV on its cards; it does not give
    a dedicated 1060-only chat. Test that layout with a compatible runtime
    separately. Park/revive on NVMe is a different operation from live NVMe KV.

## Model and engine follow-ups

These are promising directions, not a fixed order or a checklist to finish
before trying a new idea. Use the existing rig lease, guard, cleanup, and
terminal receipts for runs that occupy hardware. Pick the next probe by what
the latest result can answer most clearly.

1. **27B model weights with chat state elsewhere.** The private fork places
   Qwen3.6 27B weights on GPU0. The exact A → B → A → C → A sequence now passed
   with three separate 1060 KV chats, two pairs plus a single 1060, and three
   RAM KV chats, with occupied positions up to 8.2K and final B/C recall.
   RAM KV gave faster repeated-note prefill in this layout. A later varied-note
   run also passed three concurrent chats at 16.4K/6.2K/10.3K occupied
   positions. Next vary per-chat context caps and test longer generated turns;
   the earlier five-worker 256K depth run need not be repeated.
2. **Strata chat capacity and KV behavior.** The Q2 run served three chats at
   about 1K, 3K, and 5.8K occupied prompt tokens on one load. Try a larger
   context and more interleaving, and inspect whether its conversation cache
   keeps each chat's state or just reuses a resent prefix. The installed
   0.1.56 engine served a 42K Q2 prompt with RAM-backed KV streaming and
   reused its prefix on a follow-up. KV growth remains separate and untested;
   the installed Q2 pack's 32 GiB expert file exceeds this host's safe RAM
   capacity for that mode.
   Repeat useful long-context findings on Q4, whose single-chat 32K load and
   two-chat 8K load have both passed.
3. **BigMoe warm model, multiple conversations.** Q2 and same-file Q4
   CPU/flash correctness passed. A Q2 session now shows that continuing the
   current chat retains context, while `clear_kv` resets it and keeps the
   expert cache warm. The HTTP server's A → B → A → A probe showed that
   switching back to A reprocessed its prefix, while immediately continuing
   A reused the current KV. A later 1.5K-token-per-chat switch reproduced that
   cost: reopening A prefetched 1,488 tokens in 132 seconds. Explore explicit
   chat-state save/restore, then try GPU prefill, cache budget, and dense-weight policy where
   they change the result.
4. **Expert and tensor placement.** Compare whole experts on 1060s with
   row-sharded experts on a small real Qwen3.8 slice, including transfer and
   synchronization costs. A routed layer-0 expert passed the real Q2 kernel
   comparison, but a single expert covered only 2.19% of held-out routes.
   The Q2 routing trace now ranks hot experts with a
   later-token check; use it to test a 16/32/64-expert-per-layer cache on new
   prompts. A gain in a slice is a lead for a full-model run, not a presumed
   full-model speedup.
5. **Larger and stranger layouts.** Revisit 70B and Nemotron 74B with the chat
   tiers above; then test a 120B-class model spanning GPU, RAM, and NVMe.
   Compare live KV in RAM with a parked chat restored from storage. Push fit
   limits, but also record whether the result remains usable.

## Reusable experimental sequence

Last night's [KV campaign](results/runtime_experiments/kv_overnight_20261107/README.md)
ran serialized cases in one Manager job, kept per-case receipts, and reused
validated cases after an interruption. The reusable version is
[`campaigns/model_loading_sequence.json`](campaigns/model_loading_sequence.json)
with [`scripts/integration/run_model_loading_sequence.py`](scripts/integration/run_model_loading_sequence.py).
The manifest serializes runs whose commands are ready and marks unbuilt ideas
as blocked. Its stage order is operational bookkeeping, not the research
priority or an obligation to implement every entry.
It is for experimental engines outside the standard registry-backed suite
runner described in [CAMPAIGN_RUNNER.md](docker/CAMPAIGN_RUNNER.md). Each stage
has an explicit command, timeout, expected outputs, and optional GPU set. A
GPU stage requires a Manager benchmark lease and renews it; the sequence
refuses an offline/no-lease run. A benchmark session can reserve its entire
planned GPU set before its first stage with `--session-gpus`, including cards
that are idle while a model loads. The persistent Manager claim has an owner
and purpose visible to other sessions, is passed to each lease request, and
survives stage boundaries and the end of the run. Use `--claim NAME` to reuse
an existing persistent claim. Combine `--claim NAME --session-gpus 0,1,2`
to extend that claim to additional cards before the next stage; Manager
refuses a shrink or a claim owned by someone else. A stage marked `freeze: true` leaves its runtime
loaded and releases its temporary lease only after the persistent claim is
verified; `reuse_loaded: true` runs against an already loaded service under
that claim without attempting a second GPU lease. The command must explicitly
support `--reuse-loaded`. Older scripts that stop their own service must be
updated before marking their stage frozen. End the session with `rigctl unclaim
NAME` only after its loaded runtimes are stopped or another owner takes over.
Host `MemAvailable` must remain above 4 GiB.
The runner writes a log and atomic JSON receipt for every attempted stage,
plus a terminal summary under
`results/runtime_experiments/model_loading_sequences/<run-id>/`. Reusing the
same run ID skips a passed stage only while its expected artifacts still exist
and the manifest hash matches. It stops at a failure or a declared blocked
stage, so a partial queue cannot be reported as a successful experiment.

Dry run from the rig (read-only):

```bash
cd /mnt/shared/plans/shoulders/benchmarking
python3 scripts/integration/run_model_loading_sequence.py \
  campaigns/model_loading_sequence.json --run-id q4-sequence-20261108 --check
```

When the remaining stages have validated commands, launch the rig-side runner
through `rigctl run-start` on the Pi with the same run ID for recovery:

```bash
python3 ~/llm-gateway/tools/rigctl.py run-start \
  --run model-loading-YYYYMMDD --cwd /mnt/shared/plans/shoulders/benchmarking \
  -- python3 scripts/integration/run_model_loading_sequence.py \
  campaigns/model_loading_sequence.json --run-id model-loading-YYYYMMDD
```

For a new multi-card session, reserve all anticipated cards up front:

```bash
python3 ~/llm-gateway/tools/rigctl.py run-start --run model-loading-YYYYMMDD --cwd /mnt/shared/plans/shoulders/benchmarking -- python3 scripts/integration/run_model_loading_sequence.py campaigns/model_loading_sequence.json --run-id model-loading-YYYYMMDD --session-gpus 0,1,2,3,4,5 --session-purpose "model loading and chat placement"
```

The claim name is the run ID. The terminal receipt records its card set; a
rerun verifies the same claim rather than creating another. When a model is
already frozen, use its existing claim instead. The current 125B-class Qwen3.8
Q4 Strata load uses `qwen38-q4-frozen` across GPUs 0?5. GPU0 holds the
healthy 32K two-slot Strata service; the five 1060s are idle but reserved for
follow-up benchmarks. The claim was extended through Manager on 2026-11-10
and persists after the current run. The loaded Qwen model was not unloaded
by the runner or gateway changes.

The first stage now reuses the full SHA-256 receipt when each shard still has
the verified size, digest in the manifest, and unchanged modification/change
timestamps. The full read is needed only after a shard or its metadata changes.
The preparation, guarded Q4 8K smoke, and Q4 32K single-chat baseline have
passed. The manifest lists the missing incremental-chat runners in
capacity-first order after those completed stages. Its blocked entries are
queued questions, not runnable measurements. A new manifest revision needs a
fresh run ID so a changed procedure cannot silently reuse old receipts.

The first managed run, `model-loading-q4-prep-20261108`, finished the shard
verification, pack build and plan stages. Its
[terminal receipt](results/runtime_experiments/model_loading_sequences/model-loading-q4-prep-20261108/terminal.json)
records `blocked` at the 8K smoke gate. The Manager marked the job failed
because the sequence deliberately exits nonzero at a blocked stage; the three
preparation stages themselves passed. Use
[`watch_model_loading_sequence.py`](scripts/integration/watch_model_loading_sequence.py)
to receive one event for each completed stage and a terminal event from
filesystem notifications:

```bash
python3 scripts/integration/watch_model_loading_sequence.py model-loading-q4-prep-20261108
```

The [first read-only Q4 plan](results/runtime_experiments/q4_plan_20261108.json)
on 2026-11-08 found the four local model shards and no model download
requirement with vision off, but reported the engine missing because the
command omitted `STRATA_COMPONENTS_DIR`. The
[corrected plan](results/runtime_experiments/q4_plan_components_20261108.json)
uses the installed components and reports `engine_usable=true` with no
download. Both plans warn that normal sizing does not fit this host; exit 0
means a plan was produced, not that the model fits or answered a request.
The first pack build succeeded at 1.4 GiB with no `experts.bin`. The 8K launch
showed that the installed Strata launcher uses
`runtime/strata-ud-q4_k_xl/packs/unsloth-ud-q4_k_xl/`; the campaign now targets
that exact path. The earlier `packs/ud-q4_k_xl/` remains on disk as a redundant
pack until it is separately reviewed for cleanup.

The [managed 8K smoke](results/runtime_experiments/model_loading_sequences/model-loading-q4-smoke-20261108/terminal.json)
passed all four stages on 2026-11-08. Strata loaded the 111.3 GB Q4 bundle
using GPU0 (23,567 MiB loaded), an 8 GiB resident expert budget, host RAM, and
NVMe. Available host memory dropped by 13.22 GB decimal at the sampled loaded
point and stayed above 16.5 million KiB during the stage, within the 26 GB
ceiling and 4 GiB floor. One 68-token prompt returned `ORCHID` correctly;
its 42 generated tokens decoded at 4.6 tok/s and 68 prompt tokens processed
at 10.7 tok/s. Launch took 599 seconds, including startup and pack setup.
These are one short smoke request, not a steady-state speed or 32K result.
Strata stopped cleanly and the ordinary GPU0 chat service was restored.

The completed followup used [the short campaign](campaigns/q4_32k_sequence.json)
so it checks the existing shard receipt, then leases GPU0 for a 32K capacity
load without repeating pack creation or the 8K smoke. Its fixed requests are
one short first turn, two same-prompt repeats, and one retrieval prompt with a
target at 80% of the input records. The generated prompt and per-request
timing, answer, host/GPU memory and block-I/O snapshots are saved for a later
same-file loader comparison. The depth prompt occupies less than 32K; this
stage tests 32K configured capacity and modest occupied depth, not a full
32K attention stress test.

The [32K baseline receipt](results/runtime_experiments/model_loading_sequences/q4-32k-baseline-20261108/q4_32k_detail/terminal.json)
passed on 2026-11-08. The reused pack cut launch time to 131 seconds. GPU0
used 23,561 MiB when loaded; sampled host `MemAvailable` stayed above
15,917,564 KiB. The model answered all four requests correctly:

| Request | Prompt tokens | Output tokens | Wall time | Prefill tok/s | Decode tok/s | NVMe read |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| First short | 68 | 42 | 21.4 s | 5.7 | 4.4 | 7.91 GB |
| Repeat 1 | 68 (63 cached) | 42 | 2.6 s | 22.9 for 5 new tokens | 18.0 | 0.46 GB |
| Repeat 2 | 68 (63 cached) | 42 | 2.4 s | 22.2 for 5 new tokens | 19.7 | 0.52 GB |
| Retrieval at 80% of 640 records | 11,597 | 87 | 235.3 s | 54.1 | 4.1 | 99.86 GB |

The block counters include any device activity during each request; no other
rig workload was scheduled. Strata's [engine log](results/runtime_experiments/model_loading_sequences/q4-32k-baseline-20261108/q4_32k_detail/engine.log)
attributes about 99.9 GB of physical reads to the depth request. Its warning
reported only 457 MiB VRAM free at one short request start. A 768 MiB VRAM
reserve or lower batch/context is the next headroom control. The speed gap
between first and repeated short prompts includes KV reuse, warmed experts and
page cache; this run does not isolate their individual contributions.

BigMoeOnEdge v0.40.1 (`930b2c9`) was staged from its published Linux CLI and
CUDA packs, each checked against its release SHA-256. Its
[Q4 read-only plan](results/runtime_experiments/bigmoe_q4_plan_20261108/terminal.json)
accepted the exact Q4 shard set and identified 512 experts with top-10 routing
across 48 blocks. With the storage read probe disabled, it proposed host decode,
CUDA0 prefill, and a 21,443 MiB expert RAM cache. This is a capacity and
compatibility plan, not an inference result. The first correctness run uses
[a bounded 8 GiB cache on the existing Q2 model](campaigns/bigmoe_q2_smoke_sequence.json)
before attempting same-file Q4; it monitors host memory and saves output and
device-read receipts. The planner reported CUDA1-5 probes ending with signal 6,
while their Vulkan probes succeeded; a later multi-card BigMoe trial must
investigate that backend behavior separately.

The [Q2 compatibility smoke](results/runtime_experiments/model_loading_sequences/bigmoe-q2-compat-fixed-20261108/bigmoe_q2_detail/terminal.json)
passed on the second receipt: BigMoe loaded Qwen3.8 Q2 with an 8 GiB expert
cache and returned `ORCHID`. Model load took 169 seconds; the 28-token prompt
prefilled at 1.7 tok/s and the three-token answer decoded at 1.49 tok/s on
CPU. The CLI reported 532 MiB streamed for those three output tokens and a
17.3% expert-cache hit rate. This short output is a compatibility check only.
The [first attempt](results/runtime_experiments/model_loading_sequences/bigmoe-q2-compat-20261108/bigmoe_q2_detail/terminal.json)
had the same correct model output and exit 0, but the validator misread the
CLI's echoed prompt and trailing metrics; the parser was corrected before the
passed repeat. The ordinary GPU0 chat route remained loaded throughout.

The [same-file Q4 BigMoe smoke](results/runtime_experiments/model_loading_sequences/bigmoe-q4-compat-20261108/bigmoe_q4_detail/terminal.json)
also passed at 32K configured context. With an 8 GiB expert RAM cache and CPU
decode, model load took 275 seconds, 28 prompt tokens prefetched at 0.8 tok/s,
and a correct three-token answer decoded at about 0.43 tok/s. BigMoe reported
2,492 MiB of expert reads during those three output tokens, a 10.1% cache hit
rate, and 2,690 evictions. Whole-run NVMe counters increased by 138.69 GB;
this includes model loading and request activity. `MemAvailable` stayed above
13,470,284 KiB, and GPU0 remained with the ordinary chat model. This proves
same-file compatibility under a safe CPU/flash placement. It does not compare
BigMoe's GPU path with Strata's 3090 path. A later speed-comparison run could
give BigMoe CUDA0 prefill and separate first/warm requests; the current
priority is its ability to admit independent chats on one model load. The long
11.6K-token Strata depth prompt would be excessively slow under this CPU-only
prefill setting.

The [Q2 Strata two-chat gate](results/runtime_experiments/model_loading_sequences/strata-q2-two-chat-20261108/q2_two_chat_detail/terminal.json)
passed with one model load, two 8K configured slots, and a 768 MiB VRAM
reserve. Chat A returned `ORCHID` and chat B returned `LANTERN`; after both
first turns, their continuations ran concurrently and each repeated its own
word. Both continuations reported 60 cached prompt tokens, so the intervening
chat did not evict their short prefixes. Concurrent wall time was 2.79 seconds
for 97 generated tokens across the two chats, about 34.8 aggregate tok/s for
that pair. Loaded GPU0 use was 23,399 MiB, and sampled `MemAvailable` stayed
above 16,974,800 KiB. The histories were short (91 prompt tokens each); this
establishes separate short-chat correctness and overlap, not 8K occupancy or
multi-chat behavior at depth. Three slots were tested next.

The [three-chat Q2 gate](results/runtime_experiments/model_loading_sequences/strata-q2-three-chat-20261108/q2_three_chat_detail/terminal.json)
then passed with the same model, 8K configured context per slot, 8 GiB resident
experts, and 768 MiB VRAM reserve. `ORCHID`, `LANTERN`, and `SAPPHIRE` each
survived a distinct first turn and concurrent continuation; all three
continuations reported 60 cached prompt tokens. The concurrent turn took
3.60 seconds for 160 generated tokens in total, about 44.4 aggregate tok/s,
versus 2.79 seconds and 34.8 aggregate tok/s for two chats. Loaded GPU0 use
was again 23,399 MiB; sampled host `MemAvailable` stayed above 16,615,704 KiB.
This is one short-history run per slot count. Occupied 8K histories, 32K
capacity, mixed chat sizes, and physical chat-state placement remain untested.

The [incremental Q2 capacity probe](results/runtime_experiments/model_loading_sequences/strata-q2-capacity-20261108/q2_capacity_detail/terminal.json)
then passed with one Strata Q2 model load and three slots reserved at launch.
Chat A opened with 1,044 prompt tokens, B with 2,964, and C with 5,844. After
each admission, every open chat correctly recalled its distinct private code
word. The final continuations reported 1,072, 2,992, and 5,839 cached prompt
tokens respectively. GPU0 use was 23,399 MiB just after load and 23,555 MiB
after each admission; sampled host `MemAvailable` was 17,002,072 KiB after C.
The model stopped cleanly. This demonstrates correctness and prefix reuse at
three different occupied sizes on one model load. Each API request resent its
chat history, the slots were reserved before the first chat, and this receipt
does not locate the underlying KV buffers. Dynamic slot allocation, separate
chat-state tiers, an occupied 8K limit, 32K slots, and an N+1 fit boundary
remain open.

The [Q4 Strata two-chat probe](results/runtime_experiments/model_loading_sequences/strata-q4-two-chat-20261108/q4_two_chat_detail/terminal.json)
passed with one Q4 model load, two 8K configured slots, and distinct chats at
1,044 and 2,964 prompt tokens. Both chats recalled their own code word after
interleaving. Their final continuations reported 1,072 and 2,959 cached
prompt tokens. GPU0 use was 23,437 MiB after load, 23,577 MiB after A, and
23,601 MiB after B. The launch took 134 seconds and stopped cleanly. The
requests resent full histories and slots were reserved at launch, so this is a
two-chat fit and prefix-reuse result; it does not establish dynamic chat
allocation or physical KV separation.

The [deeper Q4 two-chat run](results/runtime_experiments/model_loading_sequences/strata-q4-two-32k-16k-20261110/README.md)
passed with two 32K slots and 15,084 prompt tokens per chat. A and B recalled
their own codes after interleaving. The first deep turns took 246.5 and
236.0 seconds, with about 105 and 101 GB NVMe reads during admission;
later continuations took 5.5-16.1 seconds with cached prefixes. GPU0 used
23,603 MiB and the 1060s were idle. This establishes deeper logical chat
separation, not physical KV placement or a stable long-form decode rate.

The [BigMoe Q2 warm-session probe](results/runtime_experiments/model_loading_sequences/bigmoe-q2-session-20261108/bigmoe_q2_session_detail/terminal.json)
passed five turns on one model load (169 seconds). A first turn and its
continuation returned `ORCHID`; a new chat and its continuation returned
`LANTERN`; reopening A returned `ORCHID`. `n_past` grew from 26 to 52 within
each chat and reset to 26 after `clear_kv`. The cumulative expert-cache hit
figure rose from 17.8% to 72.8% across turns, while each turn's `read_mib`
remained nonzero. This supports a warm model/expert cache with one live CLI
conversation at a time. It does not show simultaneous independent live KV or
cheap restoration of a parked chat.

The [dense 70B two-RAM-chat probe](results/runtime_experiments/model_loading_sequences/llama70-two-ram-chats-20261108/terminal.json)
passed on one Llama 3.3 70B Q4_K_M weight load across GPUs 0-5. Model buffers
were 19,060 MiB on GPU0, 4,317 MiB on each GPU1-3, 4,033 MiB on GPU4, and
3,935 MiB on GPU5. Chat A had an 8K cap and 720 MiB CPU KV; chat B had a 32K
cap and 2,880 MiB CPU KV. Both admitted and decoded together, 16 tokens each
in 4.57 seconds (7.00 aggregate tok/s). These were short prompts and outputs;
the result proves separate chat-state allocation and concurrent decode on one
large-model load, not long-history recall. The source GGUF was on shared storage
for this run, so its 17m53s stage wall time is not an NVMe load benchmark.
The [NVMe-path repeat](results/runtime_experiments/model_loading_sequences/llama70-nvme-two-ram-chats-direct-20261108/terminal.json)
passed with the same GGUF, GPU split, and chat settings in 3m29s stage wall
time, versus 17m53s for the shared-path run. Concurrent decode was similar:
7.12 versus 7.00 aggregate tok/s. This is a strong load-path signal, not a
controlled cold-load ratio: the NVMe file was copied immediately beforehand,
page cache was not cleared, and both stage times include context setup and
inference. The new file fully loaded and produced both chats; transfer finished
successfully and the copy has the expected 42,520,398,816-byte size.

The [BigMoe Q2 route trace](results/runtime_experiments/model_loading_sequences/bigmoe-q2-route-trace-20261108/bigmoe_q2_route_trace_detail/README.md)
recorded 30,720 decode routes over 64 output steps and 48 layers from one
NVMe-backed Qwen3.8 Q2 prompt. Ranking each layer's experts by the first 32
steps and evaluating the next 32, top 16/32/64 experts per layer covered
46.5%/60.1%/76.0% of later routes, at estimated expert-weight budgets of
1.06/2.12/4.25 GB. Top 128 covered 84.1% at 8.49 GB. This is one nearby-token
holdout and does not measure cache hits or speed. It suggests testing compact
per-layer expert sets before a larger hot-expert placement.

The [27B alternating-chat placement run](results/runtime_experiments/model_loading_sequences/qwen27-alternating-tiers-20261108/README.md)
passed the exact A → B → A → C → A sequence, plus final B/C recall, on one
NVMe-backed Qwen3.6 27B weight load per layout. Three separate 1060 KV chats,
two paired-1060 chats plus one single-1060 chat, and three RAM KV chats all
retained distinct code words. Final occupied positions were A 8,228, B 3,144,
and C 6,216 under 16K caps. The logs show 288 MiB per single-GPU or RAM KV
chat, or 144 MiB on each card of a paired chat. With this repeated-note filler,
aggregate prefill was about 148 tok/s for either 1060 layout and 292 tok/s for
RAM KV. No second model load occurred when a chat was added. This is a
correctness and placement result with artificial histories and brief answers;
real mixed-content histories and concurrent longer decode remain to test.

The [Strata Q2 RAM-KV streaming probe](results/runtime_experiments/model_loading_sequences/strata-q2-ram-kv-stream-20261108/q2_ram_kv_stream_detail/README.md)
passed with engine 0.1.56, 64K context, and a live `--kv-resident 32768`
setting. One 42,084-token prompt recalled its code correctly beyond the VRAM
resident window. A follow-up resent the history, recalled correctly, and
reported 42,079 cached tokens with only 38 new prompt tokens processed.
GPU0 use rose from 23,459 MiB after load to 23,607 MiB after the long prompt.
This verifies the installed feature path and long-prefix reuse for one chat;
the receipt does not isolate physical RAM KV bytes or prove multiple long
conversations. KV growth remains a separate, untested mode with different
requirements.

The [BigMoe Q2 HTTP server switch probe](results/runtime_experiments/model_loading_sequences/bigmoe-q2-server-switch-20261108/bigmoe_q2_server_switch_detail/README.md)
passed A → B → A → A with correct separate code words on one CPU/flash model
load while GPU0's ordinary chat route remained loaded. The server's per-turn
`n_prompt` values were 23, 23, 48, and 22: reopening A after B reprocessed
A's full 48-token history, while immediately continuing A processed only a
22-token suffix. The expert cache stayed warm (cumulative hit rate 17.8% to
68.0%). This indicates one live KV stream across the HTTP requests and
recomputation on chat switching, rather than simultaneous resident A/B KV.
The prompts were short; larger histories or explicit KV state save/restore
would reveal the switching cost more clearly.

The [deeper concurrent-chat and route-selected expert campaign](results/runtime_experiments/model_loading_sequences/overnight-loading-probes-20261108/README.md)
ran on 2026-11-08. Four runnable stages passed. Qwen3.6 27B held one weight
load per layout while three chats grew to 16,408/6,168/10,264 occupied
positions and all correctly recalled their distinct codes after concurrent
timing. The timed loop's first step replayed the 24-token opening prompt,
followed by 31 single-token generation steps. The 29.38 versus 12.76
aggregate steps/s for separate 1060 versus RAM KV is mixed prompt/decode work,
not a clean generation comparison. This differs from the earlier repeated-note
prefill ordering; the subsequent large-chat latency campaign corrects the
setup and measures each chat separately at matched depths.

With 70 distinct notes per BigMoe chat, reopening A after B prefetched 1,488
tokens in 131.6 seconds, almost the same work as the first A request's 1,463
tokens in 130.4 seconds. Immediate continuation of A needed only 22 new
prompt tokens. A route-selected real Q2 expert had correct GPU0, RAM-upload,
NVMe, and two-1060 row-shard results; its single-expert held-out coverage was
only 2.19%, so the multi-expert cache budget remains the useful next routing
question. Strata KV growth was capacity blocked before launch: the installed
32 GiB `experts.bin` cannot be fully resident within the rig's 4 GiB RAM floor
and 26 GB allocation ceiling. The ordinary chat service was restored.

The [two-100K same-1060 test](results/runtime_experiments/model_loading_sequences/qwen27-large-chat-latency-v2-20261108/README.md)
then put two independent 102,423-occupied chat contexts on GPU1 while the 27B
weights remained on GPU0. Each chat reserved 2,016 MiB of KV; GPU1 total use
was about 5,037 MiB. Both codes were recalled correctly after concurrent
generation. A alone decoded at 3.62 tok/s with 273 ms median token latency;
with both chats active, A and B each decoded at about 1.53 tok/s and 650 ms
median token latency. This is a clean 16-token window per chat, unlike the
earlier mixed prompt/decode timing. It proves two 100K chats fit and remain
independent on one 6 GB 1060, while the per-chat rate roughly halves when they
generate at the same time. The setup of each deep chat took about half an hour.
Treat this as a capacity proof: about 1.53 tok/s per chat under concurrent
generation is poor for ordinary use. Preparing each chat directly on GPU1 also
made admission expensive. The matched [GPU0 preparation and GPU1 handoff run](results/runtime_experiments/model_loading_sequences/qwen27-two-100k-handoff-20261108/README.md)
prepared the same two distinct 102K histories in 180.67 and 180.83 seconds,
saved each 2.05 GB state in 1.02 seconds, and restored each on GPU1 in 4.79
and 4.81 seconds. Both private-code recalls passed. Solo generation remained
3.66 tok/s and concurrent generation was 1.46 tok/s per chat. Thus admission
became much faster, while deep generation remained slow. Earlier GPU0
preparation filled one 235K Qwen27 context in 539 seconds and restored it on
a 1060 in about 11 seconds; the five-distinct-chat run also passed. The
general design question is which reusable chat or model artifacts can be
constructed on fast devices and moved to a slower residency tier. Transfer is
useful when saved preparation time exceeds transfer cost and the destination's
decode rate still meets the use case.

A separate [235K per-chat latency run](results/runtime_experiments/model_loading_sequences/qwen27-one-235k-chat-latency-20261108/README.md)
was stopped after 65,536 occupied positions in 906.52 seconds of direct GPU1
fill to free the rig for the handoff test. It has no 235K decode result.

The [matched 102K placement comparison](results/runtime_experiments/model_loading_sequences/qwen27-matched-100k-kv-placement-20261108/README.md)
prepared one chat on GPU0 and restored the same snapshot sequentially to
GPU0, GPU1, GPUs1+2, then GPU0 again. With Qwen27 weights on GPU0, 64 clean
generation steps measured 26.73, 3.66, 3.65, and 27.32 tok/s respectively.
All four private-code recalls passed. The pair allocated 1,008 MiB KV on
each 1060 versus 2,016 MiB on one card. At this occupied depth, using one or
two 1060s for attention was about 7.4 times slower than local 3090 KV;
splitting across two 1060s did not improve generation in this run. This is
one synthetic-history pass, so it does not yet isolate attention compute,
memory access, host-staged PCIe transfers, and graph synchronization.

The [worker chat lifecycle run](results/runtime_experiments/model_loading_sequences/qwen27-worker-chat-lifecycle-20261108/README.md)
kept the same 27B weights and a continuing manager chat on GPU0 while three
worker chats opened and closed sequentially on GPU1. Each worker had a
different private code and two successful recall turns; the manager recalled
its own code throughout. Worker context creation took 0.141–0.152 seconds,
cleanup 0.008–0.009 seconds, and close-plus-next-open 0.152–0.161 seconds.
GPU1 returned from 261 or 439 MiB while a worker was live to 77 MiB after
each close, versus 71 MiB before the first worker. This establishes a clean
serial context lifecycle in the private llama.cpp harness. The first useful
answer still paid for the new chat's 1K or 2K history fill; repeated worker
turnover, explicit stale-state exclusion, and API-level overhead remain open.

The [ongoing-turn GPU1 → GPU0 → GPU1 test](results/runtime_experiments/model_loading_sequences/qwen27-ongoing-turn-handoff-20261108/README.md)
began from one 4K Qwen27 chat state cloned onto two GPU1 contexts. Across
three matched new turns of roughly 4K tokens each, direct GPU1 ingestion plus
answer took 30.61, 34.60, and 38.61 seconds. Saving the live GPU1 state,
preparing on GPU0, returning the updated state to GPU1, and answering there
took 6.87, 7.52, and 8.19 seconds, including both transfers. All six GPU1
private-code answers were correct. This proves repeated migration for the
private 27B path at 8K–16K occupied depth; main-chat interference, long
histories for that direct comparison, and Nemotron recurrent-state compatibility remain unmeasured.

The [five-chat 50K-200K continuation run](results/runtime_experiments/model_loading_sequences/qwen27-five-ongoing-depths-20261108/README.md)
kept Qwen3.6 27B Q4 weights on GPU0 and five independent 262K-cap Q4 KV chats
on GPUs1-5. Each chat received four continuing synthetic turns, with each
new batch prepared on GPU0 and returned to its 1060. All 20 private-code
recalls passed. A [one-context replay](results/runtime_experiments/model_loading_sequences/qwen27-one-checkpoint-solo-20261108/README.md)
restored the same worker1 states with GPUs2-5 unused. At 50K/100K/150K/200K
occupied positions, true solo medians were 6.74/3.75/2.57/1.98 tok/s. With
five chats actively generating, each chat ran at 5.25-5.38/2.90-3.11/
2.05-2.12/1.55-1.65 tok/s respectively. Four parked chats changed the
worker1 solo rate only about 1-3%; active generation reduced worker1 to
78-83% of true solo. The stronger speed effect was growing context. Each
additional 50K tokens took about 75/99/123/146 seconds to prepare on GPU0
at the successive depths, before transfer and checkpoint I/O. This establishes
the five-chat capacity and per-chat generation tradeoff for this private
llama.cpp path. It does not measure a main chat responding while GPU0 is
preparing a new worker turn or natural long-conversation retrieval quality.

## Five isolated agents: keeping GPU0 available

The [64-token startup-overlap run](results/runtime_experiments/model_loading_sequences/qwen27-main-gpu0-five-agents-20261109/README.md)
replayed the same 50K/100K/150K/200K Qwen27 checkpoints with a main Q4 KV
chat on GPU0 and five independent Q4 KV agent chats, one per 1060. Main-only
decode was 32.36/26.87/22.92/19.86 tok/s; during the first few seconds of
six-way activity it was 24.93/20.63/19.41/17.28 tok/s. The agents ran at
4.84–4.92/2.85–2.96/2.00–2.06/1.53–1.62 tok/s, but the main finished
long before the agents, so those windows do not measure sustained overlap.

The [matched sustained-overlap run](results/runtime_experiments/model_loading_sequences/qwen27-main-gpu0-sustained-five-20261109/README.md)
compares five agents alone with the same five agents plus a continuously
generating main chat. The five-agent-only condition is the immediate target
layout: GPU0 holds the model and performs shared model work, while GPUs1–5
each hold one independent chat state. The experiment separates the model's
capacity benefit from the speed cost of a competing main turn. The working
speed target is **30 tok/s per agent with five active chats** at 50K, 100K,
150K, and 200K occupied context; current dense-model rates are far lower.
Five-agent-only rates were 5.31–5.47/2.98–3.10/2.05–2.14/1.56–1.61 tok/s;
with the main generating they were 2.86–2.95/2.21–2.22/1.65–1.72/
1.34–1.37 tok/s. Main-only rates were 33.84/27.37/23.02/19.69 tok/s,
versus 23.71/21.30/19.07/16.92 with agents. At deeper depths the main
finishes before all agent tokens, so the measured wall-time penalty is partly
diluted by the remaining agent-only period. Reserving GPU0 for shared model
work helps five agents, but growing context is still the dominant loss.
The 262K context caps are allocated, while correctness and decode have been
measured through 200K occupied depth, not 250K.

The [Qwen3.6 35B-A3B Q4 two-chat six-depth baseline](results/runtime_experiments/model_loading_sequences/qwen35-moe-two-curve-20261109/README.md)
kept one NVMe-backed model load on GPU0 and independent 262K-cap Q4 KV chats
on GPUs1 and 2. At occupied 16K/32K/50K/100K/150K/200K, concurrent per-chat
decode was about 38.4/23.6/17.0/9.3/6.4/4.9 tok/s. Solo worker1 was
37.2/23.3/16.9/9.3/6.4/4.9 tok/s. Both chats passed private-code recall at
every depth. Each incremental chat preparation took 14-79 seconds to become
usable, of which 0.35-3.64 seconds was GPU0 state capture and 1060 restore;
the rest was mostly GPU0 context preparation. These are 64-token decode
windows with synthetic histories, not whole-turn agent throughput. The full
six-point MoE curve now anchors 16K/32K placement experiments and longer-chat
estimates; changes to placement still need matched measurements.

An earlier five-chat 50K MoE pilot had independent private-code recall on all
five 1060s and about 12.9-13.8 tok/s per active chat in a 16-token window.
It was intentionally stopped before the deeper points when the test priority
shifted to the matched two-chat curve. Its failed terminal status records the
stop, not a 50K capability failure; it does not establish five-chat speed
through 200K.

The [16K/32K placement sweep](results/runtime_experiments/model_loading_sequences/qwen35-moe-placement-16k32k-20261109/README.md)
found no meaningful decode gain from moving block 0 experts to GPU1. Both KVs
on GPU0 were 2.2x-3.1x faster per chat but consume scarce GPU0 memory. This
reference suggests the 1060-side chat path, especially growing full-attention
KV access, is the immediate decode limit in this layout. It does not prove
which transfer or kernel dominates. Next probes should profile 1060 attention,
state transfer, and PCIe traffic before moving more experts. A five-chat MoE
capacity/speed test remains separate from this two-chat baseline. The 1060
links are x1 Gen2 during active transfer; that observation alone does not
identify the bottleneck.

The immediate optimization target is **per-chat decode for KV on a 1060**,
with GPU0 holding the model and doing as much useful shared work as possible.
The [mixed GPU0-main/1060-worker A/B/A](results/runtime_experiments/model_loading_sequences/qwen35-moe-mixed-maxctx-16k32k50k-20261109/README.md)
passed with both chats reserving 262K: the GPU0 main reached about
118/111/101 tok/s at occupied 16K/32K/50K, while its simultaneous 1060
worker stayed at about 37/24/17 tok/s, close to the two-1060 baselines. This
is a capacity and interference reference, not a worker speed optimization.
The small 65K-reservation control had essentially the same decode rates;
the full reservation added about 1.47 GiB per chat card. Place a chat on GPU0
only if the chosen model and worker optimization still leave useful headroom.

The first [one-1060 attention-weight placement probe](results/runtime_experiments/model_loading_sequences/qwen35-moe-worker-attn3-16k32k50k-20261109/README.md)
kept the 262K KV reservation and moved just 27.63 MiB of block 3 attention
weights from GPU0 to GPU1. The worker slowed 3.8%/2.4%/1.8% at
16K/32K/50K against surrounding baselines. That negative result argues
against moving more attention weights blindly. GPU1 was busy while sampled
PCIe traffic during decode was modest, but one-second counters cannot isolate
kernel, memory, or transfer time. Next measure the 1060 attention/KV path more
directly, then test a specific KV format, kernel, or hot-state change with
the same saved histories and A/B/A controls.

### Placement ideas to measure on this rig

For the current experimental sequence, do not automatically restore `chat-27b`
after a benchmark. Leave the model or service currently loaded until the next
test needs the cards. The custom placement runner owns its model in an
experiment container, so its load ends when that run exits; a separate idle
MoE server can be loaded between runs but is not the same resident instance.
The next custom run may unload that server to claim GPU0, and it should not
revert to 27B afterward.

[m10dis architecture](https://github.com/crgregersen/m10dis/blob/main/docs/ARCHITECTURE.md)
keeps attention, routing, and live KV on its fast RTX while distributing
resident expert row slices across many slower M10 GPUs. Its
[transport](https://github.com/crgregersen/m10dis/blob/main/docs/TRANSPORT.md)
uses a PCIe switch, peer mappings, multicast, and persistent workers. Our
five 1060s have x1 links and do not have that transport, so a row-sharded
expert test here must measure crossings and reductions rather than assume
the published timing transfers. The useful general rule is to distinguish
attention and dense per-token work from sparsely selected expert work.

[BigMoeOnEdge's hardware planner](https://github.com/Helldez/BigMoeOnEdge/blob/main/docs/hardware-planning.md)
keeps tensors that fit on an accelerator resident there, then plans the
experts left on the host or storage. Its
[measured-planning notes](https://github.com/Helldez/BigMoeOnEdge/blob/main/docs/measured-planning.md)
emphasize real-model, matched A/B timings, route traces, and accounting for
context and compute buffers before giving memory to a cache. Those are
directly useful here. For the 35B-A3B five-chat speed baseline, keep all
weights on GPU0 while they fit. Later compare a routing-trace-selected cold
expert set on 1060/RAM against that baseline, including both token time and
chat setup/transfer time. A test that sends every token through all five
1060s would exercise a different tradeoff and needs its own measured budget.

The m10dis [host KV tier](https://github.com/crgregersen/m10dis/blob/main/docs/KV_TIER.md)
relies on Qwen3.8's sparse QSA selecting roughly 2K tokens from a much larger
history. It is an idea source for sparse-attention models, not evidence that
Qwen3.6's full attention can skip most KV reads without a model or algorithm
change.

### Current 1060 worker speed probes

The model's Q4_K_XL weight quantization is fixed in these comparisons. Q4_0,
Q5_0, and Q8_0 below refer instead to each chat's attention key/value (KV)
cache format. The runtime can choose K and V types separately per chat. With
the same model, saved history, 262K reserved capacity, and one GPU1 worker,
the [KV format matrix](results/runtime_experiments/model_loading_sequences/qwen35-moe-worker-kv-format-matrix-20261109/README.md)
found Q4/Q4 at about 36/24/17 tok/s, either mixed Q8/Q4 or Q4/Q8 at about
49/34/24 tok/s, and Q8/Q8 at about 53/39/29 tok/s for occupied 16K/32K/50K.
Worker allocation rose from about 2,037 to 2,669 to 3,309 MiB. The higher
precision cache being faster is an observed property of this attention path,
not a claim that quantization generally makes execution slower. The separate
[Q5 KV comparison](results/runtime_experiments/model_loading_sequences/qwen35-moe-worker-q5-matrix-20261109/README.md)
placed Q5/Q5 between Q4/Q4 and mixed Q4/Q8: about 46/30/21 tok/s at the
same depths, using about 2,357 MiB per worker. The separate
[Q4_1/Q5_1 variant matrix](results/runtime_experiments/model_loading_sequences/qwen35-moe-worker-kv-variant-matrix-20261109/README.md)
found Q4_1/Q4_1 at about 50/35/24 tok/s using about 2,197 MiB per worker,
less than Q5_0, while Q5_1/Q5_1 was slower at about 45/30/21 tok/s using
about 2,517 MiB.
Q4_1 is the current best measured middle tradeoff; full Q8 remains fastest.
The separate
[Q8 extension](results/runtime_experiments/model_loading_sequences/qwen35-moe-two-q8-curve-extend-20261109/README.md)
showed about 15.3 tok/s per simultaneous chat at 100K versus Q4's 9.3, then
was intentionally stopped before a complete 150K result.

The [Q4_1 main/secondary replay](results/runtime_experiments/model_loading_sequences/qwen35-moe-q41-main-secondary-16k32k50k-20261109/README.md)
confirmed one GPU0 model load with independent 262K-reserved Q4_1 KV chats
on GPUs1 and 2. At occupied 16K/32K/50K, main-alone decode was about
50/35/24 tok/s; with both active, main was 54/34/23 and secondary was
52/33/23. In the preceding checkpoint preparation, GPU0 built each chat's
history and handed its state to the 1060: the capture/restore portion took
about 0.4/0.7/1.1 s by depth, while usable setup took roughly 14-25 s.
Smaller KV state therefore reduces worker memory and handoff bytes, but does
not directly speed GPU0 prefill. This replay does not yet cover alternating
conversation turns.

A [Q4_1 CUDA fusion A/B/A](results/runtime_experiments/model_loading_sequences/qwen35-moe-worker-q41-fusion-16k32k50k-20261109/README.md)
held the worker cache and histories fixed while disabling runtime operation
fusion. Worker speed fell about 8.5%/5.5%/2.7% at occupied 16K/32K/50K,
with close default runs before and after. Some fused work in the model-plus-
worker path therefore matters, particularly at short history; the smaller
effect at 50K is consistent with growing attention/KV work on GPU1. This is
an inference from the matched speed trend, not a GPU or kernel attribution.
The next local knob to
probe is worker decode microbatch configuration, while keeping the same
Q4_1 checkpoints and full worker reservation. The resulting
[microbatch sweep](results/runtime_experiments/model_loading_sequences/qwen35-moe-worker-q41-ubatch-16k32k50k-20261109/README.md)
found all tested worker `n_ubatch` values (1, 8, 32, 64) within roughly 3%
at these depths, so this is not yet a useful single-token decode knob. The
small 32K/50K advantage for `n_ubatch=1` needs a repeat before adoption.

The [CUDA graph optimization A/B/A](results/runtime_experiments/model_loading_sequences/qwen35-moe-worker-q41-graph-opt-16k32k50k-20261109/README.md)
changed Q4_1 worker decode by less than 1% at 16K/32K/50K. This is not a
useful tuning knob in the current layout. CUDA graphs are disabled on Pascal
1060s by this backend, limiting the meaning of the GPU0 option for worker
attention. The next worthwhile speed work should measure the 1060 attention
and KV kernels more directly and test an explicit change to that path, while
keeping end-to-end chat preparation and transfer time visible.

The [native Q4_1 attention-kernel A/B/A](results/runtime_experiments/model_loading_sequences/qwen35-moe-q41-native-16k32k50k-20261109/README.md)
tested a specific backend build change. The earlier build omitted the Q4_1
FlashAttention vector template and logged an F16 attention fallback. Adding
`q4_1-q4_1` removed that warning but **slowed** one 1060 worker from roughly
49.5/34.4/24.2 to 36.0/24.8/17.9 tok/s at occupied 16K/32K/50K, with
the same 262K reservation and saved histories. GPU1 peak memory stayed at
2,197 MiB. The surrounding original-build controls closely agreed. Keep
Q4_1 as a compact worker KV format, but do not enable its native vector
kernel on Pascal based on this result. The next attention experiment should
trace GPU1 decode kernels and stalls before changing kernel parallelism.

The [decode-only Nsight traces](results/runtime_experiments/model_loading_sequences/qwen35-moe-q41-decode-trace-16k32k50k-20261109/README.md)
locate the native Q4_1 regression on GPU1. Across 64 tokens, its vector
attention kernel costs 679/1,241/1,710 ms more than the fallback F16 kernel
at 16K/32K/50K; removing Q4_1 dequant saves only 241/477/729 ms. The net
GPU1 kernel increase closely tracks the end-to-end slowdown. GPU0 graph time
stays about 371 ms, and GPU1 host-to-device copy time stays about
96/101/106 ms, in each paired run. The native attention instance uses
255 registers per thread versus 220 for F16, with the same 128-thread block.
The next controlled probe is a Pascal native-kernel launch-shape variant,
starting with 256 threads and measuring kernel time, register use, and
generation speed at the same three depths. A separate hot-F16-KV-cache idea
could remove the fallback's recurrent conversion cost while retaining compact
Q4_1 backing; that needs a distinct memory and setup-time budget.

The [256-thread native Q4_1 A/B/A](results/runtime_experiments/model_loading_sequences/qwen35-moe-q41-threads128-256-16k32k50k-20261109/README.md)
slowed worker decode about 5.0%/4.0%/4.1% at 16K/32K/50K. Its
[traces](results/runtime_experiments/model_loading_sequences/qwen35-moe-q41-threads256-trace-16k32k50k-20261109/README.md)
showed nearly unchanged register use (255 to 254 per thread), fewer KV
partitions (grid Y 5 to 3), and more attention-kernel time. The opposite
[64-thread A/B/A](results/runtime_experiments/model_loading_sequences/qwen35-moe-q41-threads128-64-16k32k50k-20261109/README.md)
was effectively tied with 128 threads at 32K/50K and about 1% slower in
64-token throughput at 16K because its first token was slower. Its
[traces](results/runtime_experiments/model_loading_sequences/qwen35-moe-q41-threads64-trace-16k32k50k-20261109/README.md)
kept five KV partitions and nearly the same register use and attention time.
Thus 64/128/256-thread launch shape is not a useful speed lever for this
native Q4_1 kernel on the 1060. The F16 attention fallback remains the
fastest tested Q4_1 path. The next promising idea is a separately budgeted
F16 hot KV window with compact Q4_1 backing, since repeated dequantization
costs 241/477/729 ms per 64 tokens at 16K/32K/50K in the fallback traces.

### Which findings transfer to other models

The experimental method transfers: separate weight placement from each chat's
KV placement, measure setup/transfer and per-chat decode separately, and use
saved-history A/B/A controls plus device-specific traces before changing a
kernel. The hardware-tier constraint also transfers on this rig: a 1060's
x1 link and 6 GiB VRAM limit the amount and frequency of data it can receive.

Capacity and speed must be measured for each model and attention family.
Number of layers, KV heads, head size, context scheme, and cache format change
KV bytes and attention work per token. Dense, sliding-window, and sparse
attention need different placement and growth assumptions. MoE routing and
expert caching affect the weight path but do not by themselves make a long
chat's KV cheap. The exact Q4_1 fallback advantage, register counts, thread
choice, and tok/s above are specific to this Qwen3.6 build, Pascal CUDA
kernel, and tested context depths; they are not universal loader settings.
Before applying a speed rule elsewhere, replay the same short depth curve on
at least one different dense and one different MoE model, recording the
selected kernel, KV footprint, occupied context, GPU topology, and setup time.

Near-term tests stay at occupied **16K, 32K, and 50K** on a 262K-cap worker.
Use 100K only when a short result merits a targeted slope check. Do not run
every format or placement through 150K/200K yet. Measure each change against
matched saved histories and bracketing controls; preserve preparation,
capture/restore, memory, correctness, and decode evidence separately. Focus
on per-chat 1060 speed before scaling promising changes to two and five
workers. These are experiments, not a fixed Manager load recipe.

### Research leads for 1060 chat speed (2026-11-09)

1. **Pascal vector versus tile attention, at occupied 16K/32K/50K with a
   262K reservation (first pass complete).** Current llama.cpp dispatch sends
   single-token quantized KV to the vector kernel, while its generic tile
   kernel can share KV reads across grouped query heads after expanding the
   quantized cache to F16 scratch. Force tile only for this Q4_1/Q4_1,
   256-wide-head worker case. First gate on GPU1 memory at full reservation;
   then compare saved-history vector/tile/vector runs with kernel traces,
   correctness, setup/transfer, and per-chat decode. A pending upstream
   [Q8_0 tile PR](https://github.com/ggml-org/llama.cpp/pull/30792) reports
   gains on ROCm hardware; those gains are not evidence for Pascal Q4_1.
   [Current dispatch](https://github.com/ggml-org/llama.cpp/blob/master/ggml/src/ggml-cuda/fattn.cu)
   is the implementation reference.
2. **Fused GQA tile with native quantized reads.** If tile helps but F16
   scratch costs too much time or VRAM, study the same upstream Q8_0 PR's
   register dequantization and the [experimental GQA decode kernel](https://github.com/LL4nc33/llama-tq/blob/turboquant/docs/turboquant.md)
   for a Q4_1-capable Pascal prototype. Account for dequantization and
   grouped-head reuse together. Measure quality and total per-chat latency,
   not just kernel time; do not assume the prototype can use tensor cores.
3. **Query-selected KV pages at longer contexts.** [Quest](https://proceedings.mlr.press/v235/tang24l.html)
   suggests selecting important pages per query to reduce full-attention
   reads. This changes which history is attended to, so compare long-range
   recall and output quality with exact attention before treating speed as a
   win. [HiSparse](https://github.com/sgl-project/sglang/blob/main/docs/docs/advanced_features/hisparse_guide.mdx)
   currently needs models with native sparse attention; its exact host-backed
   behavior does not directly apply to Qwen3.6 full-attention layers.
4. **Shared-prefix admission for independent chats.** For workers with the
   same system/task prefix, reuse prepared KV and branch independent chat
   tails. Measure bytes and time saved at spawn and verify isolation after
   divergence. [SGLang's session-aware radix cache](https://github.com/sgl-project/sglang/blob/main/docs/docs/advanced_features/session_radix_cache.mdx)
   is a reference for retaining reusable prefixes under memory pressure;
   it does not by itself improve a worker's steady decode speed.

For this model, the [published configuration](https://huggingface.co/Qwen/Qwen3.6-35B-A3B/blob/main/config.json)
has 40 layers with full attention every fourth layer, 256-wide heads, and
16 query heads sharing two KV heads. Treat its recurrent state and growing
full-attention KV separately when deciding what to optimize or move.

The [first Q4_1 vector/tile/vector A/B/A](results/runtime_experiments/model_loading_sequences/qwen35-moe-q41-vector-tile-16k32k50k-20261109/README.md)
passed at all three depths with the full 262K reservation. Generic tile
attention raised the one-worker rate from mean vector controls of roughly
50.8/35.0/24.1 to 53.5/40.9/31.5 tok/s at 16K/32K/50K, while GPU1 peak
memory stayed near 2.2 GiB. Decode traces show tile attention itself fell
from 293/661/1,171 to 217/422/633 ms across 64 tokens; recurring Q4_1
dequantization remained about 242/477/723 ms. This makes the fused-read
candidate concrete, but output-quality equivalence and wider-model transfer
are still open tests. The result applies to this Pascal Q4_1/head-256/GQA
path; it is not a general speed rule for all chats.

The [Q8 tile A/B/A](results/runtime_experiments/model_loading_sequences/qwen35-moe-q8-vector-tile-16k32k50k-20261109/README.md)
did not reproduce the Q4_1 improvement: 50.9/38.0/29.0 tok/s versus
surrounding Q8 vector controls around 53.7/38.8/28.7. The tile choice is
specific to KV format, head shape, and hardware. The
[F16 KV ceiling](results/runtime_experiments/model_loading_sequences/qwen35-moe-f16-ceiling-16k32k50k-20261109/README.md)
reached 68.3/59.9/49.7 tok/s at occupied 16K/32K/50K on one 1060 with a
262K reservation, but allocated 5,120 MiB of KV on that card. Two separate
F16 1060 chats also passed recall and ran near the same per-chat rate in
their preparation run. These results sharpen the next trade-off: remove
Q4_1's repeated conversion while retaining much of its smaller KV footprint
and transfer cost. They do not establish quality equivalence between KV
formats or deep-context speed.

The [single-1060 F16 attention launch probe](results/runtime_experiments/model_loading_sequences/qwen35-f16-tile128-20261109/README.md)
replayed the same 16K/32K/50K saved chats through unchanged–variant–unchanged
builds. On this Qwen3.6 head-256, F16-KV, Pascal path, changing the tile from
256 to 128 threads raised solo decode from bracketed controls near
68.5/60.0/49.7 to 70.5/62.5/52.6 tok/s. At 50K the 1060 attention kernel
fell 11.7% in summed time, while measured transfer time and GPU0 work stayed
flat. A 64-thread tile was substantially slower. This suggests 1060 attention
efficiency is a single-chat limit, alongside transfer cost. Keep 128 threads
as an isolated candidate pending response-quality and wider-model checks;
the return-state capture path remains a separate optimization experiment.
The [matched dense 27B replay](results/runtime_experiments/model_loading_sequences/qwen27-dense-f16-tile128-64k-20261109/README.md)
then used the same GPU0-weight/GPU1-F16-chat layout, occupied depths, and
128-thread tile. It reached 23.2/18.6/14.8 tok/s at 16K/32K/50K versus
70.5/62.5/52.6 for the MoE. The dense F16 262K reservation requested
16 GiB on a 6 GB 1060 and failed before generation; the successful dense
run reserved 64K. This limits the capacity match but makes the MoE speed
advantage at equal occupied depths clear. The subsequent
[50K Nsight trace](results/runtime_experiments/model_loading_sequences/qwen27-dense-f16-trace-50k-20261109/README.md)
found both substantially longer dense GPU0 model work and 1060 attention,
with more link traffic as well. A Qwen3.5-4B model fully on one 1060
measured about 23.6 tok/s near 16.7K and 21.2 near 30.4K; that
comparison uses different hardware for model compute.

The [Q4_1 tile 50K–200K curve](results/runtime_experiments/model_loading_sequences/qwen35-moe-q41-tile-curve-50k100k150k200k-20261109/README.md)
passed independent recall for two 1060 chats at every stage. Solo decode fell
from 30.74 to 18.22, 13.04, and 10.13 tok/s; two simultaneous chats stayed
near those per-chat rates, ending at 10.11/10.03 tok/s at 200K. Preparation
already appends new tokens instead of recomputing earlier tokens, but each
stage still restores and saves a complete growing state. The save/restore
handoff grew from about 1 to 4 seconds between 50K and 200K; this timing is
not a pure transfer measurement. GPU0 holds weights and a temporary one-chat
preparation workspace, while each worker's chat state stays on its 1060.

### Suggested next test: transient GPU0 append and delta handoff

Keep the model weights on GPU0 and authoritative independent chats on their
1060s. For a new turn, use GPU0 only as a temporary preparation workspace,
then release it; do not retain GPU0 mirrors of all worker chats. Compare the
current full-state restore/append/save/handoff with a format-aware delta
handoff that copies only new KV and required recurrent state. Include a
pinned-RAM checkpoint source if needed to avoid reading the full prior state
over a 1060 x1 link. Start with one worker, then two and five after correctness
and GPU0 headroom are measured. Record GPU0 high-water memory and occupancy
time, bytes across each link, state restore/capture time, first-token and
end-to-end turn latency, per-chat tok/s, and recall/isolation across repeated
turns. Test both short and long increments at 16K/32K/50K first, then a long
context point. Recurrent state cannot be treated as an append-only KV file;
define and validate a compatible delta format before optimizing transfer.

The [serialized-state delta probe](results/runtime_experiments/model_loading_sequences/qwen35-moe-file-delta-probe-20261109/README.md)
found exact `zstd --patch-from` payloads at 41–56% of full state size for
16K→32K, 32K→50K, and 50K→100K. Both worker chats reconstructed byte for
byte, but encode/decode alone cost 1.3–6.5 seconds and the public state API
still restores the full GPU state. It is not a turn-speed win or a true
incremental handoff. The next test must update new KV pages and recurrent
state in place on the 1060, while GPU0 uses a temporary one-chat workspace.
The long run sampled GPU0 at 21,319 MiB with weights alone and up to 23,075
MiB during preparation. Measure its exact per-turn occupancy and concurrent
decode interference in the partial-update prototype.

The [live partial-KV handoff](results/runtime_experiments/model_loading_sequences/qwen35-moe-live-kv-delta-20261109/README.md)
supersedes the file-level delta candidate: for this Qwen3.6 hybrid model, an
isolated fork exported new full-attention KV cells and replaced the recurrent
state on the 1060. Across two short turns starting at 16K, 50K, 100K, 150K,
and 200K,
the partial worker and a full-restore control had byte-identical states and
both passed recall. The partial payload was about 66.8 MB per turn while
full state grew from 172 MB to 1.35 GB; export plus apply took roughly 0.05 s,
against full restore alone of 0.29–3.34 s. GPU0 peaked at 23,161 MiB in 1 Hz
samples at 200K. This is a handoff result, not
yet a complete request-to-first-token measurement. Next measure a delta-only
turn and GPU0 workspace occupancy, verify rollback/position guards, test
interference while another worker decodes, then test two distinct chats before
trying five.

The [complete-turn A/B](results/runtime_experiments/model_loading_sequences/qwen35-moe-turn-full-vs-delta-100k200k-20261109/README.md)
includes GPU0 restore and preparation, 1060 handoff, recall response, and
worker-state capture over two turns. At 100K, full handoff took
5.34/4.85 s per turn versus 3.31/2.83 s with partial KV. At 200K, it took
9.97/9.15 s versus 5.92/5.14 s. Request-to-first-token fell from roughly
3.2 to 1.1 s at 100K and from 5.8 to 1.7 s at 200K. Full capture of the
worker's post-response state remains 1.6–1.9 s at 100K and 3.1–3.7 s at
200K. The [single-1060 return-state delta](results/runtime_experiments/model_loading_sequences/qwen35-return-delta-20261109/README.md)
now exports the worker's new KV and recurrent state to a host checkpoint
without a resident GPU0 mirror. At 100K/200K its ~66 MB return took about
0.036 s versus 1.56–1.87/3.10–3.71 s for full worker capture. Complete
two-turn latency fell to 1.49/1.29 s at 100K and 2.25/2.07 s at 200K;
request-to-first-token and raw decode speed were essentially unchanged.
Two-turn and 20-turn final states reconstructed byte for byte. The host
update chain grows with turns: at 200K, temporary GPU0 rebuild rose from
0.35 to 0.67 s over 20 turns. Compaction after turn 10 cost 1.44 s and
saved about 0.61 s net through turn 20; it should be deferred when no
further turns are expected. The next capability tests are distinct workers
and concurrent generation before five workers. The
[durable single-chat return checkpoint](results/runtime_experiments/model_loading_sequences/qwen35-return-durable-20261109/README.md)
adds an atomic base-plus-turn journal and exact recovery after a fresh
inference process loads the model. It ignores incomplete writes and rejects
corrupt records. At 100K, persisting each ~133 MB turn record took about
0.52 s on rig NVMe versus 2.01–2.02 s on shared storage; complete measured
turns on NVMe took 1.99–2.05 s. This is a one-worker process-restart
prototype; atomic on-disk compaction, crash-time answer delivery, and
power-loss recovery remain untested. The gateway dashboard's saved-chat
list currently reopens a SQLite transcript and resends up to 16 recent
messages; it does not restore this exact KV checkpoint. Its
`docs/DASHBOARD.md` now names the future conversation-ID/model/turn binding.
Keep runtime checkpoint integration separate from the current speed tests.

The [resident mirror experiment](results/runtime_experiments/model_loading_sequences/qwen35-moe-resident-mirror-20261109/README.md)
kept matched GPU0 and 1060 chat copies, exchanging only new KV and recurrent
state in both directions. Two independent 50K or 100K chats passed alternating
turns; one 200K chat passed even with a full 262K GPU0 reservation. At 100K,
the two-mirror turn range was 1.03–1.27 s and sampled GPU0 peak was 23,411
MiB. At 200K, the full-cap single mirror took 1.66–1.92 s per turn. Every
post-turn state matched byte for byte, and both private-code recalls passed.
This is a deliberately memory-heavy speed mode, not evidence that five GPU0
mirrors fit. The smaller-model and matched non-mirror control probes can test
the capacity/latency trade further; concurrent worker interference remains open.

The [smaller 27B mirrored-chat probe](results/runtime_experiments/model_loading_sequences/qwen27-resident-mirror-20261109/README.md)
passed two independent 50K and 100K chats on separate 1060s, with GPU0
copies and exact post-turn state agreement. At 50K, turns took 2.15–2.54 s
and GPU0 peaked at 19,307 MiB; at 100K, turns took
3.42–3.57 s and GPU0 peaked at 21,423 MiB.
The 27B model leaves more mirror capacity on GPU0 than the 35B MoE, but its
dense worker turns are slower at these depths. The follow-up below tests the
mirror count; a matched no-mirror control and simultaneous generation remain
open.


A [four-mirror 27B follow-up](results/runtime_experiments/model_loading_sequences/qwen27-resident-mirror-20261109/README.md#four-50k-mirrors-and-a-five-mirror-limit)
then kept four 50K GPU0 mirrors and one 262K-reserved worker chat on each
of four 1060s. All eight alternating turns passed recall and exact state comparison; GPU0
sampled peak was 22,949 MiB and per-chat turns took 2.15–2.54 s.
The fifth GPU0 mirror failed during a 266 MiB CUDA allocation after four
contexts had initialized. This establishes four-chat capacity at a 65K GPU0
mirror cap, not at full 262K reservations or with simultaneous generation.
