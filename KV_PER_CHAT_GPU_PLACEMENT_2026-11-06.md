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
occupancy, Q4 KV at 200K and 250K, continuations and cross-chat isolation.
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
only short prompts were filled. Long-context retrieval, Q4 KV at 200–250K,
independent continuation under concurrent scheduling, and exact transfer
accounting remain open. A production path also needs an explicit per-context
device parameter, a scheduler that shares or budgets GPU0 workspace, and a
Manager load contract for one weight GPU plus the chosen cache GPUs. Keep this
as experimental benchmarking evidence until those runtime and Manager pieces
are implemented and validated.

