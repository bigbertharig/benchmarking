# Two 256K chat caches and staged addition on Qwen3.6 27B

Run date: 2026-11-07 local. This is a private llama.cpp experiment using one
Qwen3.6 27B Q4_K_M model load on GPU0 (RTX 3090 Ti). Each chat is a separate
`llama_context`, and all contexts share the same `llama_model` object. K and V
are Q4_0. The prototype assigns attention cache layers alternately to the two
GTX 1060s in a pair. The harness creates and decodes chat A before creating
chat B, then creates a GPU5 chat, continuing earlier chats after each addition.

| Run | Pair A GPU1+2 | Pair B GPU3+4 | GPU5 | Outcome |
| --- | --- | --- | --- | --- |
| `smoke_1_7b` | 16K allocation | 16K allocation | 8K | Pass on dense Qwen3 1.7B |
| `qwen27_pair256k` | 256K on GPU2 only | 256K on GPU4 only | 32K | Pass; exposed layer parity error |
| `smoke_1_7b_v2` | 16K allocation | 16K allocation | 8K | Pass after ordinal change |
| `qwen27_pair256k_v2` | 256K on GPU2 only | 256K on GPU4 only | 32K | Pass; exposed hybrid cache filter |
| `qwen27_pair256k_v3` | 256K across GPU1+2 | 256K across GPU3+4 | 32K | Pass; verified both cards in each pair |

In the final run, each paired 1060 held **2,304 MiB of KV** and reserved
**1,029 MiB of compute buffer**. The 1 Hz GPU sample peaked at 3,412 MiB on
GPU1/2 and 3,408 MiB on GPU3/4. The model buffer on GPU0 was 15,346 MiB;
GPU0 sampled peak was 16,027 MiB. All three chats gave the expected first
answer (Paris, Tokyo, Madrid). `PHASE_1_READY`, `PHASE_2_READY`, and
`PHASE_3_READY` in the log mark successful continuation before and after
staged additions. The same model was loaded once; the second and third
contexts were created later in that process.

The two intermediate 27B runs answered the single-card question directly.
Because Qwen3.6's attention cache is only on a filtered subset of its hybrid
layers, the initial parity mapping put each entire 256K cache on one 1060.
Each such card held 4,608 MiB KV, reserved 1,029 MiB compute, and reached a
5,716 MiB sampled peak. It passed with `n_batch=64`, `n_ubatch=8`, but this is
a tight edge on a 6 GB card. The final mapping counts only attention-cache
layers, so both cards of each pair now carry KV and attention work.

All 256K contexts were **allocated but only filled with five prompt tokens and
a few continuation tokens**. This is a real-model allocation and short-decode
proof, not a 256K retrieval or quality result. The GPU sample interval can
miss transient maxima; runtime buffer sizes are copied from the log. The
process-global environment selector is a test shim and is unsafe for parallel
decode threads. The harness adds whole contexts while the process lives; it
does not grow or migrate an already created context's cache. A separate
process would require another model load. Manager has no serving profile for
this topology yet.

`private_llama_kv_pair.patch` is the final private source diff against the
llama.cpp tree vendored under
`/data/bench-staging/strata-v0.2.10/install/third_party/llama.cpp`.
The source remains at `/mnt/shared/experiments/kvchat-20261106/llama.cpp` and
the incremental CUDA build at `/data/bench-staging/kvchat-20261106-build`.
`manifest.json` contains parsed placement, first answers, phases, exits, and
sampled peaks; every raw log and GPU sample is retained here. All rig runs
used Manager reservations. The ordinary `chat-27b` route was restored after
the experiment.
