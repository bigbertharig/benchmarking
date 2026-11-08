# Model loading and chat placement

This is the entry point for open-ended experiments with model components and
independent chats across the RTX 3090 Ti, five GTX 1060s, host RAM, and local
storage. The broad goal is to load larger models and make them useful at better
speeds. We are exploring placements, chat behavior, tensor layouts, caching,
and runtime designs; no single layout or Manager procedure is the target yet.
The order of experiments can change when a result suggests a better question.

## The big picture

There are two linked goals. The systems goal is to use the rig's separate 3090
VRAM, 1060 VRAM, host RAM, and NVMe tiers to run larger models at useful speed.
Strata demonstrates a software-managed GPU/RAM/storage hierarchy, and
BigMoeOnEdge and m10dis supply ideas for caching, streaming, and placing routed
experts. This is not a true unified memory pool: each tier has its own capacity,
access cost, and supported runtime operations. The installed Strata path has
run Qwen3.8 with GPU0, RAM, and NVMe; using the 1060s as dedicated expert
workers in that engine would require a separate compatible bridge or engine
change. The [expert placement plan](EXPERT_TENSOR_PLACEMENT_TEST_PLAN.md)
tracks that unbuilt combined path.

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
| Qwen3.6 27B weights on GPU0, chats' KV on 1060s and/or RAM | [KV placement](KV_PER_CHAT_GPU_PLACEMENT_2026-11-06.md), [filled-depth campaign](results/runtime_experiments/kv_overnight_20261107/README.md), [27B RAM-KV smoke](results/runtime_experiments/qwen27_ram_kv_20261108/README.md), [mixed-tier chats](results/runtime_experiments/qwen27_mixed_ram_gpu_20261108/README.md) | Private llama.cpp fork; five distinct 1060 chats reached 90% of 256K and passed recall. Separate short-history GPU1 + RAM + GPU2 chats now coexist and decode on one weight load. Deep mixed-tier recall remains open. |
| Nemotron 74B weights and whole experts on GPU0-3, chats on remaining 1060s | [live expert/chat test](results/runtime_experiments/kv_expert_chat_20261107/README.md), [matched placement](results/runtime_experiments/kv_matched_placement_20261107/README.md) | Private fork; the 131K paired chat had short occupied history. Byte-balanced interleaving did not beat contiguous experts. |
| Llama 70B weights across six GPUs, host-RAM KV | [overnight campaign](results/runtime_experiments/kv_overnight_20261107/README.md) | Short 128K-capacity generation and separate 8K depth probe; 128K occupancy and useful serving speed unproved. |
| Qwen3.8 Q2 Strata, GPU/RAM/NVMe | [memory plan](STRATA_MEMORY_TEST_PLAN.md), [three-chat gate](results/runtime_experiments/model_loading_sequences/strata-q2-three-chat-20261108/q2_three_chat_detail/terminal.json) | Logical separation: one loaded model served three distinct short chats at a common 8K configured limit. No mixed-size or occupied-depth multi-chat result, independent KV placement, or combined 1060 expert workers. |
| Qwen3.8 Q4 | [expert placement plan](EXPERT_TENSOR_PLACEMENT_TEST_PLAN.md), [32K baseline](results/runtime_experiments/model_loading_sequences/q4-32k-baseline-20261108/q4_32k_detail/terminal.json), [two-chat probe](results/runtime_experiments/model_loading_sequences/strata-q4-two-chat-20261108/q4_two_chat_detail/terminal.json) | Strata 3090/RAM/NVMe served two interleaved chats at 1,044 and 2,964 prompt tokens on one 8K-capacity load. Slots were reserved at launch; deeper occupancy, third chat, and separate KV tiers are open. |
| Qwen3.8 on BigMoe | [same-file Q4 smoke](results/runtime_experiments/model_loading_sequences/bigmoe-q4-compat-20261108/bigmoe_q4_detail/terminal.json), [Q2 warm session](results/runtime_experiments/model_loading_sequences/bigmoe-q2-session-20261108/bigmoe_q2_session_detail/terminal.json) | Q4 32K CPU/flash correctness passed. One Q2 CLI session served five correct turns; clearing KV reset live context but retained a warming expert cache. Concurrent independent live KV remains untested. |

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

## Candidate experiments

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
refuses an offline/no-lease run. Host `MemAvailable` must remain above 4 GiB.
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
