# Model loading and chat placement

This is the entry point for proof-of-concept experiments that place one shared
model and multiple independent chats across the RTX 3090 Ti, five GTX 1060s,
host RAM, and local storage. The current question is **what fits**: hold the
model placement fixed, then admit additional chats of increasing size without
reloading or moving the model. Record throughput as a diagnostic, but do not
select or optimize layouts by speed in this phase. A configured context is a
capacity claim; occupied history, correct continuation, and actual state
residence must be demonstrated separately.

## Current proof-of-concept gate

For each layout, load the model once and record the weight, expert, and shared
workspace tiers. Open chat A, then add B, C, and later chats while A remains
available. Give each chat a distinct marker and history, continue earlier chats
after each admission, and verify that neither their history nor their state
leaks between chats. Grow occupied history in steps and report the requested
and observed capacity **for each chat**, not just a server-wide context limit.
Where the engine only supports one context size for all slots, record that
limitation instead of claiming mixed-size chats.

At each admission, record where the new chat's live KV and other per-chat state
actually reside, GPU/host memory and storage use, whether model buffers moved
or reloaded, and the first failed admission with its allocation reason. Test
parking and restoring a chat separately from live chat placement. The useful
result is a layout and a reproducible capacity boundary: one model load plus N
independent chats at stated occupied sizes. Correctness and fit are gates;
prefill, decode, and I/O timings remain in receipts for later optimization.

One loaded engine serving several sessions proves **logical separation** of
model and chat. **Physical separation** requires evidence that chat state
lives on a different GPU, in RAM, or in storage while model placement stays
fixed. The Q2 Strata three-chat result proves the former for short histories;
it does not yet prove the latter.

## Ownership and operating contract

Benchmarking owns measurements, raw receipts, and the passive
[`load_recipes.json`](load_recipes.json) handoff. The Pi gateway's
[`MODEL_LIBRARY_HANDOFF.md`](https://github.com/bigbertharig/llm-gateway/blob/main/docs/MODEL_LIBRARY_HANDOFF.md)
documents import and promotion. Manager owns the lookup from a supported recipe
ID to a known load procedure, resource leases, fit checks, launch, and observed
ready state. The rig executes that procedure. Harnesses and use cases request a
model, then open or add chats with stated capacity needs; they do not select
cards, tensor overrides, cache files, or storage paths. Manager applies a
known model procedure and admits chats within its measured resource envelope.

Manager should keep a small lookup of validated model load procedures and their
chat admission envelopes. During this proof-of-concept phase, a choice is
offered only when its complete procedure is implemented and its claimed model
fit, chat count, per-chat context, and correctness have been demonstrated. A
request that does not fit returns a reason; Manager does not silently shrink
context or substitute a different recipe. The ready response must report the
model placement ID, actual per-chat capacity and placement, and whether each
claim is measured or estimated.

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
campaign preflight, not an automatic update to a Manager recipe.

## What has been measured here

| Layout | Evidence | Current limit |
| --- | --- | --- |
| Qwen3.6 27B weights on GPU0, separate chats' KV and attention on GPUs1-5 | [KV placement](KV_PER_CHAT_GPU_PLACEMENT_2026-11-06.md), [concurrent matrix](results/runtime_experiments/kv_local_worker_matrix_20261107/README.md), [filled-depth campaign](results/runtime_experiments/kv_overnight_20261107/README.md) | Private llama.cpp fork, no Manager serving profile; 27B deep-chat decode slows sharply at 90% occupancy. |
| Nemotron 74B weights and whole experts on GPU0-3, chats on remaining 1060s | [live expert/chat test](results/runtime_experiments/kv_expert_chat_20261107/README.md), [matched placement](results/runtime_experiments/kv_matched_placement_20261107/README.md) | Private fork; the 131K paired chat had short occupied history. Byte-balanced interleaving did not beat contiguous experts. |
| Llama 70B weights across six GPUs, host-RAM KV | [overnight campaign](results/runtime_experiments/kv_overnight_20261107/README.md) | Short 128K-capacity generation and separate 8K depth probe; 128K occupancy and useful serving speed unproved. |
| Qwen3.8 Q2 Strata, GPU/RAM/NVMe | [memory plan](STRATA_MEMORY_TEST_PLAN.md), [three-chat gate](results/runtime_experiments/model_loading_sequences/strata-q2-three-chat-20261108/q2_three_chat_detail/terminal.json) | Logical separation: one loaded model served three distinct short chats at a common 8K configured limit. No mixed-size or occupied-depth multi-chat result, independent KV placement, or combined 1060 expert workers. |
| Qwen3.8 Q4 | [expert placement plan](EXPERT_TENSOR_PLACEMENT_TEST_PLAN.md), [32K baseline](results/runtime_experiments/model_loading_sequences/q4-32k-baseline-20261108/q4_32k_detail/terminal.json) | Strata 3090/RAM/NVMe answered all four 32K-capacity requests; repeat runs, full-depth occupancy, and multi-chat tests pending. |
| Qwen3.8 Q4 on BigMoe | [same-file smoke](results/runtime_experiments/model_loading_sequences/bigmoe-q4-compat-20261108/bigmoe_q4_detail/terminal.json) | 32K capacity CPU/flash correctness passed; GPU placement and matched throughput remain untested. |

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

The next gate is incremental chat admission on a fixed model load, first in the
already working Q2 Strata layout and then in the 27B GPU0/1060 KV layout to
prove physical separation. Q4 Strata and larger model layouts follow as fit
experiments. Matched throughput comparisons, expert-hotness replay, and a
Strata-plus-worker bridge are later optimization work.

## Next test queue

Run each case with a fresh terminal receipt and the existing rig lease, guard,
and cleanup path. Report one model load identity; model and chat buffer
residence before and after each admission; configured and occupied tokens per
chat; correct continuation of every earlier chat; memory and storage use; and
the first failed fit with its exact allocation reason. Retain timing and I/O
observations without using them to choose the next layout.

1. **Q2 Strata incremental chats.** Reuse the working GPU/RAM/NVMe model
   placement. The short-history one-, two-, and three-chat 8K gates have
   passed. Grow A's history, add B, continue A, grow B, add C, and continue A
   and B. Try 8K and 32K configured limits; test different per-chat limits if
   the runtime supports them. Record the number of occupied tokens at every
   step and the first fit failure. Determine whether the runtime allocates
   chat KV separately or reserves a common per-slot pool at launch.
2. **27B model on GPU0, chats on 1060s or RAM.** Hold the existing private-fork
   model load fixed. Admit one chat on a 1060, then another on a different 1060,
   then additional chats until a fit limit; continue all earlier chats after
   each addition. Repeat with paired 1060s and host-RAM KV where supported.
   Start at a modest occupied history, then grow selected chats toward their
   configured limits. This is the clearest near-term proof of physical model
   and chat separation. Do not infer the 27B host-RAM result from other models.
3. **Q4 Strata incremental chats.** The staged Q4 model already passed its
   32K-capacity single-chat baseline. Attempt a second and third chat on the
   same load within the established host and GPU guards. Vary occupied size,
   check whether model buffers stay resident, and record any admission limit.
4. **Larger model fit.** Revisit the 70B six-GPU/RAM-KV and Nemotron 74B
   expert/chat-split layouts with the same incremental admission method. Then
   try a 120B Strata-like weight hierarchy only after its single-chat fit and
   chat-state mechanism are explicit. A storage-backed parked chat is a
   separate proof from storage-backed live KV.
5. **BigMoeOnEdge chat capacity.** Q2 and same-file Q4 CPU/flash correctness
   already passed. Investigate whether its server can retain one model load
   while adding independent chats, and where it allocates each chat's state.
   Run an admission test only if the server exposes a repeatable way to verify
   those conditions. Matched GPU throughput, expert-hotness replay, and new
   cache algorithms remain later work.

## Reusable experimental sequence

Last night's [KV campaign](results/runtime_experiments/kv_overnight_20261107/README.md)
ran serialized cases in one Manager job, kept per-case receipts, and reused
validated cases after an interruption. The reusable version is
[`campaigns/model_loading_sequence.json`](campaigns/model_loading_sequence.json)
with [`scripts/integration/run_model_loading_sequence.py`](scripts/integration/run_model_loading_sequence.py).
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
