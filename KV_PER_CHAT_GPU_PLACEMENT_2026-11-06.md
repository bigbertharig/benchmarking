# One chat cache per 1060: placement feasibility (2026-11-06)

## Goal

Keep one model weight load on the RTX 3090 Ti. Assign each live conversation's
KV cache to one of the five GTX 1060 6 GB cards. The assigned 1060 computes
attention against its own cache and returns only the layer result to the 3090.
This is intended to work for dense and MoE models: expert placement is a
separate policy. The 3090 remains shared computation, so the five lanes do not
behave like five independent model copies.

## Evidence and limits

The prior Qwen3.6 27B Q4_0 run measured 5,908 MiB of KV for a 336,128-token
pool. Linear scaling gives about 3,515 MiB at 200K and 4,395 MiB at 250K per
chat. This is model- and cache-format-specific sizing, not a universal KV rate.
At Q8_0 the 250K cache is too large for a 1060. See the Pi gateway's
`docs/PARALLEL_CONTEXT_EXPERIMENT_2026-11-06.md` for the original runtime
measurements and the earlier layer-split results.

The [capacity probe](scripts/active/kv_cache_residency_probe.py) held one
synthetic cache reservation and one workspace reservation on **each** 1060 at
the same time. Results are in
`results/runtime_experiments/kv_cache_residency_20261106/`.

| Approximate chat cap | Cache per 1060 | Workspace per 1060 | All five fit | Free per 1060 |
| ---: | ---: | ---: | --- | ---: |
| 200K | 3,515 MiB | 1,536 MiB | yes | 944 MiB |
| 250K | 4,395 MiB | 1,024 MiB | yes | 576 MiB |
| 250K | 4,395 MiB | 1,536 MiB | yes | 64 MiB |

The 250K/1,536-MiB case is an allocation edge, not an admissible serving
profile. CUDA contexts and later attention allocations need room. Each process
freed its allocations, and the five 1060s returned to 4 MiB reported use.

The [attention worker probe](scripts/active/kv_attention_worker_probe.cu)
ran one real FP16 softmax attention head over a separate resident token array
on each 1060. A query originated on GPU0, crossed via pinned host memory to
all five workers, and all five outputs returned to GPU0. The final 250K
run gave each 1060 a distinct value (1 through 5), and GPU0 verified the
five results in their respective lanes. The probe reserved the
Q4-sized cache and 1,024 MiB workspace per card, but **only 49/98/122 MiB of
the cache was initialized and read** at 100K/200K/250K: one FP16 head, not a
full model's quantized multilayer KV. It does not prove full-model numerical
correctness or useful token rate.

| Tokens per chat | Five-worker median round trip | Verified |
| ---: | ---: | --- |
| 100K | 1.30 ms | yes |
| 200K | 2.44 ms | yes |
| 250K | 3.05 ms | yes, distinct lane markers |

These are 10 measured iterations after two warmups, one run per point. The
100K and 200K runs used the same marker on all five lanes; the 250K run
used distinct markers, which tests lane assignment. They ran with
the existing 27B chat route resident but idle on GPU0. The old route was not
unloaded. Container output and normalized JSON receipts are preserved. The
earlier `moe_transport_probe_20261106` measured host-staged vector transfers
without attention and reported no GPU0-to-1060 peer access. The current
topology also reports no peer access.

## Runtime change required

The installed llama.cpp layer split places each layer's KV on that layer's
model device, and one layer's cache can hold multiple sequences. Static
`--override-tensor` rules move model tensors, not a particular sequence's
dynamic KV. Strata's Flash-Next `--kv-resident` streams KV through pinned host
RAM; its slots are independent, but it does not assign one slot's KV to each
1060. Neither existing flag implements this topology.

A reusable backend needs an explicit `sequence -> KV device` mapping and
separate per-sequence/per-layer cache buffers. For each attention layer,
GPU0 computes the model projections, sends the current query and new K/V to
the chosen 1060, that GPU appends K/V and computes attention against its local
cache, then returns the attention result to GPU0. Dense or MoE feed-forward
work continues under the model's independent weight/expert placement. A
microbatch must be partitioned by assigned sequence before attention; a
single mixed-sequence attention graph cannot be pinned to one 1060. Hybrid
models also need explicit ownership for any recurrent state.

The first engineering gate was a forked llama.cpp prototype with one weight
copy, two assigned contexts and real token generation. It passed at 4K, then
five contexts passed at 32K cache capacity on dense and MoE models; details
follow below. The next capacity gate is long prompts with measured cache
occupancy, continuations and cross-chat isolation. Allocated Q4 KV at 256K
passed in the paired-worker experiment below.
Compare bytes copied between cards with the theoretical query/new-KV/result
traffic. The previous 1M-token layer-split failure was a 3,929-MiB compute
buffer on a 1060; it does not establish failure for a cache-only worker.

## Reproduction

Run the Python capacity probe on the rig with the installed CUDA 12
`libcudart.so.12`, passing `--cache-mib`, `--workspace-mib` and the card list.
The attention probe compiles with the existing
`nvidia/cuda:12.9.2-devel-ubuntu24.04` image for `sm_61` and `sm_86` and accepts
`TOKENS CACHE_MIB ITERS`. The exact source, binary, raw CUDA output and JSON
results are preserved in the paths above. No llama.cpp image or active model
route was changed during these probes.

## Real-model prototype result (2026-11-06)

The next engineering gate above is now met at short prompts. A private
llama.cpp fork gave each of five `llama_context` objects its own CUDA KV device,
while all contexts shared one model object with weights on GPU0. Its attention
node was assigned to the cache GPU in the graph scheduler. The same mechanism
passed on dense Qwen3 1.7B, MoE GPT-OSS 20B, and the target dense Qwen3.6 27B.
All five chats were resident at 32K capacity and produced distinct correct
first answers. For the 27B run, GPU0 held a 15,346 MiB model buffer and peaked
at 19,019 MiB; each 1060 held 2,048 MiB KV and peaked at 2,208 MiB.

See [the full receipts and private patch](results/runtime_experiments/kv_chat_real_model_20261106/README.md).
The harness decodes chats sequentially and uses a process-global device
selector; it is not a concurrent server. The 32K caches were allocated but
only short prompts were filled. Long-context retrieval,
independent continuation under concurrent scheduling, and exact transfer
accounting remain open. A production path also needs an explicit per-context
device parameter, a scheduler that shares or budgets GPU0 workspace, and a
Manager load contract for one weight GPU plus the chosen cache GPUs. Keep this
as experimental benchmarking evidence until those runtime and Manager pieces
are implemented and validated.

## Paired 1060 workers and staged chat creation (2026-11-07)

The private fork assigns one context's KV-bearing attention layers across a
selected pair of 1060s, keeping one Qwen3.6 27B Q4_0 weight load on GPU0.
It starts chat A on GPUs1+2 with a 256K Q4_0 K/V allocation, decodes it,
adds chat B on GPUs3+4 with another 256K allocation, then adds a 32K chat
on GPU5. Earlier chats continue after each addition. All three short capital
prompts produced their expected first tokens. The final run reported 2,304
MiB KV and about 1,029 MiB compute buffer on each paired 1060; sampled
peaks were 3,412 MiB on GPUs1+2 and 3,408 MiB on GPUs3+4. GPU0's model
buffer was 15,346 MiB and sampled peak was 16,027 MiB.

The first two 27B runs exposed a hybrid-layer indexing error: although two
devices were selected, all KV went to one card in each pair. Those runs still
completed 256K Q4 cache allocations on individual 1060s, with about 5,716
MiB sampled peak. Thus one 6 GB 1060 *can* reserve a 256K Q4 cache for this
model at `n_ubatch=8`, but has little headroom. This does not imply a 256K
FP16 cache fits. The corrected final run counts only KV-bearing layers after
the cache filter and confirms the intended even split.

These are 256K **configured capacities**, with only short prompts and a few
continuation tokens filled. A 256K-token retrieval or near-full occupancy
test remains open. Contexts were created one at a time within the same
process and model object; this prototype does not grow or migrate an existing
context's cache. Its process-global device selector and sequential decode are
not suitable for concurrent serving. Manager integration remains open.

See [patch, logs, GPU samples, and receipts](results/runtime_experiments/kv_pair_dynamic_20261107/README.md).



## Paired-cache decode speed (2026-11-07)

A timed extension of the private harness compared Qwen3.6 27B Q4_K_M dense
with GPT-OSS 20B MXFP4 MoE. One model weight load stayed on GPU0. Two chats
had 256K Q4 K/V capacities split across GPUs1+2 and 3+4, and a 32K chat
used GPU5. After adding all three chats, 64 additional tokens per chat were
timed separately: the dense model gave 33.67, 33.51, and 33.44 tok/s;
the MoE gave 51.90, 50.93, and 51.18 tok/s. The pair means are 33.59 and
51.42 tok/s, respectively. Sequential decoding means these rates are not
concurrent throughput. The comparison uses different models and weight
formats, and histories occupied only a few tokens. A filled 256K history
remains unmeasured. Receipts and timed source are in
`results/runtime_experiments/kv_paired_speed_20261107/`.

## Concurrent local and 1060 chats, GPU0 prefill, and state handoff (2026-11-07)

The private llama.cpp fork now uses a thread-local KV device selector so
independent contexts sharing one model object can decode concurrently. With
Qwen3.6 27B Q4_K_M dense weights on GPU0, one short local chat and five
single-1060 chats each reserved a 256K Q4 cache and generated 64 tokens
concurrently: workers ran at 7.50–7.63 tok/s; aggregate throughput was
45.0 tok/s. GPT-OSS 20B MXFP4 MoE likewise ran one local and five
131K-capacity worker chats: workers 16.67–17.17 tok/s, aggregate 100.0
tok/s. These are short occupied histories despite large allocated capacities.

GPU0 can also serve as a temporary prefill engine without a persistent
local chat. It filled a Qwen27 256K context to 90% (235,929 tokens) in
539 seconds, saved a 4.51 GB state, and freed the temporary context. Five
single-1060 contexts restored copies of that state in 11.05–11.11 seconds
each, then generated concurrently. At 10% occupancy they ran at
6.57–6.70 tok/s each (32.84 tok/s aggregate); at 90% they fell to
1.21–1.26 tok/s each (6.06 tok/s aggregate). The 256K cache fits on each
1060 with Q4 K/V and small microbatch, but near-full decode is slow.

A separate Qwen3 1.7B 32K run prepared five **different** synthetic 10%
histories on GPU0, verified five distinct state fingerprints, restored
them to GPUs1–5, and decoded them concurrently at 252.0 tok/s aggregate.
This demonstrates additive preparation of separate chats. It does not
measure long-context retrieval quality or implement agent messaging.
The 27B distinct-history version prepared five separate 26,214-token
histories in 38.18–38.30 seconds each; all five fingerprints differed,
and restored workers decoded concurrently at 31.94 tok/s aggregate.
The checkpointed 1.7B test also prepared five different 90%-filled 32K
histories in 12.76–12.85 seconds each, wrote and verified five ~952 MB
state files, and restored them to GPUs1–5. Three successive concurrent
continuations gave 104.0, 142.3, and 143.5 tok/s aggregate; the first
included warmup. These state files remain experiment staging artifacts;
their fingerprints are in the receipt, not committed as binary results.

See [the matrix, raw receipts, PCIe samples, and private patch](results/runtime_experiments/kv_local_worker_matrix_20261107/README.md).
The earlier process-global-selector and sequential-decode limitations above
describe the historical prototypes; this experiment replaces those two
mechanisms in the private fork. Manager load profiles and robust serving
remain to be implemented.

## Overnight distinct-chat, hybrid MoE, and RAM-KV campaign (2026-11-07)

The five-case campaign finished with exit 0; all cases passed their explicit
validators. [Receipts, source, and interpretation](results/runtime_experiments/kv_overnight_20261107/README.md)
are archived in the benchmarking repo.

Qwen3.6 27B Q4_K_M used one model load on GPU0. Five **different** chats
were prepared separately, transferred to GPUs1-5, and continued concurrently
at 10%, 50%, and 90% of a 262,144-token context. Each worker had a 4,608 MiB
Q4 GPU KV buffer; at 90%, each held 235,929 occupied tokens. The final
answer contained its own planted code in all 15 worker/depth checks. The
synthetic filler controls depth and does not establish natural-conversation
quality. This case took about 65 minutes including preparation and state I/O.

With Nemotron 3.5 Bolt 74B, the newer b11669 private port placed the model
on GPUs0-3. Two 8K-capacity chats on GPUs4/5 ran concurrently; a third chat
with 131,072 configured capacity was then added across GPUs4+5 and all three
continued concurrently. The 64-token phases delivered 27.16 and 33.23
aggregate tokens/s. The large context had only a short prompt, so occupied
131K operation remains untested. The older fork's tensor-shape load failure
was a version mismatch; the b11669 build loaded the same model successfully.

GPU weights plus host-RAM Q4 KV also worked. Qwen3 1.7B at 32K capacity
measured 51.07 tok/s at 10% occupied and 8.19 at 90%. Llama 3.3 70B Q4
loaded model layers across all six GPUs with an 11,520 MiB CPU KV allocation
for 131,072 configured tokens and decoded a short prompt at 3.75 tok/s. A
separate 8K-capacity synthetic-depth run measured 2.82 tok/s at 10% and
0.85 at 90%. The 70B 128K context was allocated but not filled, and the
raw prompt did not use its instruct template.

These are experiment profiles, not Manager serving profiles. A Manager
handoff needs to encode model-weight placement separately from per-chat KV
placement, configured capacity separately from measured occupied depth, and
the RAM-KV mode before it can select these layouts safely.

## Whole expert tensors with live 1060 chat caches (2026-11-07)

The [matched Nemotron experiment](results/runtime_experiments/kv_expert_chat_20261107/README.md)
combined the prior four-group whole-expert placement with two 8K chats on
GPUs4/5 and an additively created 131K-capacity chat split across them. With
the same five weight cards, the normal layer split delivered 21.21 aggregate
tok/s for two chats and 21.34 for three; whole-expert placement delivered
67.13 and 72.02, respectively (3.16x and 3.37x). A four-weight-card layer
control reached 27.28 and 33.09, so merely adding a card did not cause the
gain. Moving the fourth expert group from GPU4 to GPU5 changed throughput by
only 1-2% in this single pass.

With three synthetic histories at 10% and 90% occupancy (8K on each small
chat, 32K on the paired chat), the same five-card layer control measured
16.40 and 8.61 aggregate tok/s. The expert layout measured 44.55 and 14.52
(2.72x and 1.69x). The gain narrows as attention/cache work grows. The
131K-capacity chat was not filled. In the short-history 131K-capacity case,
peak sampled GPU4 use fell from 5,968 MiB with layer placement to 4,638 MiB
with expert placement, adding about 1.3 GiB of headroom on the shared card.

The PCIe rate samples are archived but not phase-aligned tightly enough to
claim fewer transferred bytes. This is a speed and residency result for a
hybrid MoE model; dense models need a different weight-placement strategy.
It remains a private experiment, not a Manager profile.

## Byte-balanced expert group placement with live chats (2026-11-07)

The [matched whole-expert placement test](results/runtime_experiments/kv_matched_placement_20261107/README.md)
held the Nemotron model, 3090 plus four expert 1060s, two 8K 1060 chats,
optional paired chat, quantization, prompts, and output counts fixed. A
header-only GGUF inventory allowed an interleaved layer assignment with the
same 44 expert tensors and per-card expert bytes within 3.4 MiB of the
existing contiguous assignment. All five measured runs passed first-token,
model-buffer, phase, and occupied-depth checks. A local SATA copy of the
same GGUF avoided repeated shared-storage load stalls; load time is excluded
from the token rates.

In short-history A/B/A order, the two-chat controls measured 64.09 and 61.21
aggregate tok/s, with interleaved at 61.88. With the paired chat added, the
controls measured 71.44 and 71.23, with interleaved at 68.49 (3.98% below
their mean). At 10% and 90% occupied depth, the interleaved run measured
43.55 and 14.45 aggregate tok/s versus 44.32 and 14.54 for contiguous.
Both layouts filled the paired chat to 29,491 tokens in 538.2 seconds.
Graph split counts were the same for both layouts. The 1 Hz PCIe samples
cannot establish exact transferred bytes or explain the small speed gaps.

There is no measured benefit from redistributing whole expert layers among
these four 1060s, so the contiguous layout remains the supported experimental
recipe. A routing-derived hot-expert placement needs expert-granularity
residency and per-token transfer tracing; the current tensor overrides can
only move whole expert tensors. This result should not change a Manager
serving profile yet.
