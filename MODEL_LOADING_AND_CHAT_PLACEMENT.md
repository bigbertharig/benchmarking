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
| Qwen3.8 Q2 Strata, GPU/RAM/NVMe | [memory plan](STRATA_MEMORY_TEST_PLAN.md), [matched mixed-card comparison](results/runtime_experiments/strata_q38_mixed_matched_20261106/README.md) | One-card long-context recall and mixed-card short-context tests; no independent per-chat placement or combined Strata-plus-1060 expert workers. |
| Qwen3.8 Q4 | [expert placement plan](EXPERT_TENSOR_PLACEMENT_TEST_PLAN.md), [8K smoke](results/runtime_experiments/model_loading_sequences/model-loading-q4-smoke-20261108/q4_smoke_detail/terminal.json) | Four verified NVMe shards; Strata 8K 3090/RAM/NVMe load and one correct request passed. Matched 32K throughput and multi-chat tests pending. |

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

## Next test queue

Run these as separate managed benchmark runs with fresh terminal receipts and
the existing rig lease, guard, and cleanup path. Keep load-to-ready, prefill,
decode, and total wall time separate. For chat tests report both configured
capacity and occupied tokens, per-chat latency, aggregate throughput, recall,
GPU/host allocation, and physical storage reads. A failed fit with its exact
limiting allocation is a result.

1. **Qwen3.8 Q4 capacity gate (first).** Follow
   [the Q4 execution plan](EXPERT_TENSOR_PLACEMENT_TEST_PLAN.md#resume-here-q4-strata-and-expert-placement):
   reuse the verified four-shard receipt if file metadata is unchanged and check free NVMe space, build the small Strata runtime
   pack without an `experts.bin` duplicate, run the non-allocating plan, then
   attempt a guarded 3090 + 8 GiB resident-expert + NVMe load. Begin at 8K
   for a functional request; move to matched 32K short and depth prompts only
   after the first fit. Record whether the 26 GB decimal new-host-allocation
   ceiling and 4 GiB `MemAvailable` floor hold throughout. This answers whether
   the staged 111.3 GB Q4 actually runs on this rig before optimizing it.
2. **Same-file BigMoeOnEdge control.** Start with a read-only plan and a Q2
   compatibility smoke, then test the *same verified Q4 shards* and 32K
   requests used in test 1 if its model/loader supports them. Compare one cold
   request, two warm repeats, and a distinct-prompt request; use identical
   output caps and record GPU cache hits, RAM, physical NVMe reads, and answer
   correctness. A plan refusal or unsupported Qwen3.8 layout is a compatibility
   result. Do not compare its published speeds from other machines with ours.
3. **One Qwen3.8 model, several chats.** On the already working Q2 Strata
   placement, test one, two, then three independent 8K chats on one load.
   Measure correct first turns, separate continuations, prefix retention,
   aggregate versus per-chat tokens/s, and whether the engine actually runs
   them concurrently. Repeat at 32K only if the small gate passes. This tells
   us whether a large model can share one weight load before adding custom KV
   placement. Later repeat with Q4 only if test 1 fits and resources allow it.
4. **Matched 27B chat-state crossover.** Keep the Qwen3.6 27B weights on the
   3090 and compare local Q4 KV, one 1060 per chat, paired 1060s, and host-RAM
   Q4 KV. Begin with identical distinct histories at a common 32K configured
   capacity and 10%, 50%, and 90% occupied depth. Test one chat on every
   fitting layout; then five concurrent chats on layouts with capacity for
   five, and two paired chats on GPUs1-4. Run a separate 256K capacity/depth
   comparison only on layouts that fit it safely. Include GPU0 prefill and
   state-transfer time alongside continuation speed. This identifies where
   each state tier becomes too slow, rather than selecting from configured
   context size alone. Any host-RAM 27B variant requires a new validated run;
   existing 1.7B/70B RAM results are not its baseline.
5. **Expert hotness and link-cost replay.** Capture real routed expert IDs for
   Nemotron and Qwen3.8, then replay fixed 3090, 1060, RAM, and NVMe budgets.
   Compare contiguous whole tensors, hot whole tensors, and a hypothetical
   finer-grained cache using measured 1060 transport and storage-miss costs.
   Implement a new expert-worker bridge only if the replay predicts a gain and
   a full-model test can verify it. Keep live NVMe-backed KV as a later sparse
   attention experiment after a RAM-backed hot-block cache has passed.

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
The next stages check free space, build the small Q4 Strata pack without
`experts.bin`, and request a non-allocating Strata plan. The guarded 8K smoke
is ready and passed once. BigMoeOnEdge,
multi-chat Strata, matched 27B KV, and expert replay each name their missing
runner or input in the manifest; these are queued questions, not runnable
measurements yet. A new manifest revision needs a fresh run ID so a changed
procedure cannot silently reuse old receipts.

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

The next run uses [the short followup campaign](campaigns/q4_32k_sequence.json)
so it checks the existing shard receipt, then leases GPU0 for a 32K capacity
load without repeating pack creation or the 8K smoke. Its fixed requests are
one short first turn, two same-prompt repeats, and one retrieval prompt with a
target at 80% of the input records. The generated prompt and per-request
timing, answer, host/GPU memory and block-I/O snapshots are saved for a later
same-file loader comparison. The depth prompt occupies less than 32K; this
stage tests 32K configured capacity and modest occupied depth, not a full
32K attention stress test.
