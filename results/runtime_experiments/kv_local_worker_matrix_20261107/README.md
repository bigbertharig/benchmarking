# Concurrent local and 1060 chat matrix (2026-11-07)

This is a private llama.cpp experiment. One model object and its weights reside
on GPU0 (RTX 3090). Each chat has its own `llama_context`; Q4_0 K/V and
attention are placed on one or two GTX 1060s, or locally on GPU0. Contexts
can be created after the model is loaded. A thread-local selector lets the
contexts decode concurrently. `five_migrate_depth` uses GPU0 as a temporary
prefill engine, snapshots the state, destroys the temporary context, restores
five copies of the same snapshot onto separate 1060 contexts, then decodes
all five together. This checks residency and independent context state after
the fork; it does not test five different long conversations.
`five_distinct_prefill` instead prepares five different 10%-filled histories
on GPU0 in succession, logs full-state fingerprints, restores each to its
own 1060, and decodes them together.
It does not keep a main GPU0 chat resident.

All five 1060s are on PCIe x1 links. The harness uses synthetic repeated-token
histories at 10% and 90% of configured capacity, then measures 32-token
continuations. Short-history matrix runs use 64-token continuations. The
short-history prompts verify first-token capitals and continuation success, but these are
not long-context retrieval accuracy tests. Aggregate throughput is total
generated tokens divided by the slowest concurrent wall time; individual
rates are reported in the raw logs. Q4 K/V and small `n_ubatch` are essential
to fit the 256K Qwen27 cache on a single 6 GB card.

## Short-history capacity and concurrency

| Model | Layout | Configured capacities | Concurrent aggregate | Worker rate | Local rate |
| --- | --- | --- | ---: | ---: | ---: |
| Qwen3 1.7B Q4_K_M dense | GPU0 local + 2 pairs + GPU5 | 32K each | 309.1 tok/s | 77–82 tok/s | 195 tok/s |
| Qwen3.6 27B Q4_K_M dense | GPU0 local + 2 pairs + GPU5 | local/pairs 256K; GPU5 32K | 44.4 tok/s | 11.1–11.2 tok/s | 12.1 tok/s |
| GPT-OSS 20B MXFP4 MoE | GPU0 local + 2 pairs + GPU5 | 131K each | 105.1 tok/s | 26.3–26.7 tok/s | 125.9 tok/s |
| Qwen3.6 27B Q4_K_M dense | GPU0 local + five single 1060s | 256K each | 45.0 tok/s | 7.50–7.63 tok/s | 25.98 tok/s |
| GPT-OSS 20B MXFP4 MoE | GPU0 local + five single 1060s | 131K each | 100.0 tok/s | 16.67–17.17 tok/s | 127.14 tok/s |

The local and worker rates above are each thread's rate over its own decode
interval. They do not sum to aggregate throughput when threads finish at
different times. Sequential matrix baselines gave Qwen27 local 41.4 tok/s,
pairs 32.3–32.4, GPU5 32.5; GPT-OSS local 147.6, pairs 48.8–49.2, GPU5
49.1. These runs establish capacity and independent continuation, not
near-full latency.

## Filled histories and GPU0 prefill

Direct worker-side 90% prefill on Qwen3 1.7B took roughly four minutes per
32K worker. GPU0 prefill and state restore shortened the prefill phase
substantially, while preserving concurrent decode behavior. With two pairs,
GPU5, and a local chat, direct 10%/90% aggregate was 210.1/104.2 tok/s;
GPU0-prefilled aggregate was 226.4/113.8 tok/s. The five-single-worker
GPU0-prefilled run had no persistent local chat and reached 245.7/118.1
tok/s at 10%/90%.

The distinct-history 1.7B run used five different capital prompts. Its
five 10%-filled snapshots had distinct fingerprints, restored onto GPUs1–5,
and decoded concurrently at 252.0 tok/s aggregate. GPU0 filled each 3,276
token synthetic history in about 1.05–1.08 seconds. This proves separate
cache preparation and handoff, but the histories are synthetic and the
experiment does not exchange messages between workers.
The corresponding 27B run prepared five different 26,214-token histories
sequentially on GPU0 in 38.18–38.30 seconds each. The five fingerprints
were distinct; restored workers decoded together at 31.94 tok/s aggregate.
The checkpointed 1.7B run prepared five different 90%-filled 32K histories
in 12.76–12.85 seconds each, wrote and verified five ~952 MB state files,
and restored them to GPUs1–5. Three consecutive concurrent 32-token
continuations gave 104.0, 142.3, and 143.5 tok/s aggregate; the first
included warmup. These state files are staging artifacts outside the
benchmark repo, not committed result data. Their fingerprints and read
receipts are preserved in the log.

For Qwen27, a temporary GPU0 context reached 90% of 256K in about nine
minutes. Its 90% snapshot was about 4.51 GB and restored to paired 1060
contexts in about 11 seconds each. With two 256K pairs, a 32K GPU5 chat,
and a short local chat, worker rates fell to 1.45–1.64 tok/s at 90% and
aggregate was 5.80 tok/s. With **five single-card 256K chats and no local
chat**, all workers restored the same 90% snapshot and decoded concurrently
at 1.21–1.26 tok/s each, 6.06 tok/s aggregate. At 10% they ran at
6.57–6.70 tok/s each, 32.84 tok/s aggregate. The five 90% restores took
11.05–11.11 seconds each after the 9-minute GPU0 prefill. This is a
capacity proof; such a deep history is not yet practical for interactive
agents on these cards.

## PCIe and interpretation

`*.pcie.txt` contains sampled `nvidia-smi dmon -s t` PCIe Rx/Tx rates for
the later runs. In the six-chat short-history Qwen27 run, sampled 1060 Rx
was about 24–33 MB/s and Tx about 10–13 MB/s; GPU0 Rx about 103 MB/s and
Tx about 187 MB/s. The x1 links were below their nominal capacity in this
sample. This does not establish whether PCIe, GPU0 scheduling, or attention
dominates deep histories; transfer volume and timings need a matched
profiling run. The short-history six-chat Qwen27 run put GPU0 near its
24 GB limit and each 1060 near 5.7 GB.

## Artifacts and limits

`manifest.json` indexes every run, its exit status, timing lines, state
snapshot/restore events, and sampled peak memory. Each run has `.log`,
`.gpu.csv`, `.start`, `.finish`, and `.exit` receipts. Later runs also have
`.pcie.txt`. `private_llama_local_worker_parallel.patch` and `final_simple.cpp`
preserve the private runtime change and harness; the helper scripts show the
incremental edits. The patch is for this experiment and is not a Manager
load contract or production API. Real agent message exchange, retrieval
quality, robust scheduling, and Manager profile conversion remain open.
