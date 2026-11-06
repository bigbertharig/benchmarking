# Qwen3.8 Q2 expert sharding across VRAM, RAM, and NVMe — 2026-11-06

This is a standalone engineering prototype combining **within-expert row sharding** with **tiered expert storage**. It computes one real Qwen3.8 Q2_0 expert, rather than moving a dummy vector. It does not modify Strata, llama.cpp, orchestration, model loads, or the serving route.

## Setup and correctness

- Existing model only: `Qwen3.8-Flash-Next-GSQ-RCO-Q2_0` on the rig. The extractor samples **layer 0, routed expert 0** from the first local GGUF shard. No model was downloaded.
- The sample contains gate, up, and down Q2_0 matrices: hidden width 2,560; intermediate width 640; **1,382,400 packed bytes per expert**. The five-worker layout gives each GTX 1060 128 intermediate rows; the two-worker layout gives each 320. Both are aligned to Q2_0's 64-element blocks. Down-projection blocks are sliced by intermediate row, and each worker returns a 2,560-element partial output.
- GPU 0 is an RTX 3090 Ti; workers are GTX 1060 6GB cards. Worker requests and partial returns use pinned host memory and CPU reduction because GPU 0 has no peer access to the 1060s.
- Every case computes gate, SiLU, up, and down projections from the **real packed model weights**. An independent NumPy CPU Q2_0 decode and matrix calculation supplies the reference. All 24 reported cases passed with maximum absolute error below 1.2e-8.
- CUDA 12.9.2 image, `sm_61` + `sm_86`, 20 warmups and 100 timed calls per case, two fresh-container runs per worker layout. The sample files and CPU reference remain under `/data/bench-staging/` and are **excluded from Git**. Only code, timing JSONL, and this report are committed.
- `gpu0` is packed weights resident on the 3090. `gpu0_ram` uploads the same packed weights from pinned RAM for every call. `gpu0_nvme` directly reads them from `/dev/nvme0n1p1` using `O_DIRECT`, then uploads them. `resident`, `ram`, and `nvme` do the analogous work on row-sharded 1060 workers; the worker modes also include GPU0↔host transport and CPU partial reduction.

## Results

Two-run means for the existing two- and five-worker cases; the new one-worker measurement is one 100-call run. Latency per expert call, microseconds:

| Weight source and compute | 3090 | Two 1060 shards | Five 1060 shards |
| --- | ---: | ---: | ---: |
| Packed weights resident in VRAM | **159.6** | 309.8 | 284.8 |
| Packed weights uploaded from pinned RAM per call | **277.8** | 2,032.4 | 997.3 |
| Packed weights read with direct NVMe I/O per call | **3,610.2** | 6,239.8* | 4,263.2 |

A one-1060-shard extension used the same verified full expert and independent CPU reference, with 20 warmups and 100 timed calls. All six modes passed (maximum absolute error 1.19e-8). One worker measured **338.3 µs** with its weights in 1060 VRAM, **3,786.1 µs** when uploading from RAM each call, and **7,175.8 µs** with direct NVMe reads each call. The corresponding five-worker values above were 284.8, 997.3, and 4,263.2 µs. Adding workers helped this one-expert microkernel most when weights had to be moved, but it cost extra GPUs; none of these numbers is a full-model throughput prediction. Runner: [run_q38_tiered_one_worker.py](../../../scripts/active/run_q38_tiered_one_worker.py). Receipt: [one_worker_20261106.json](one_worker_20261106.json).

**Placement rule for future planners:** if the full requested model and context fit entirely in GPUs, prefer the fewest measured-fast cards that fit. If any model data must spill to RAM, compare an expanded GPU placement that uses the available VRAM *before* accepting a smaller GPU set plus RAM. Only after useful GPU and RAM capacity is assigned should a compatible storage tier be considered. The existing one-card Strata manager policy and one-card llama RAM path do not yet implement this general mixed-tier search.

\*The two-worker NVMe mean includes one timed outlier; its two per-run medians were about 5,324 and 5,333 µs. Two-worker resident timing also varied between runs (291 and 328 µs means). The five-worker and 3090 runs were more consistent. See `summary.json` and the four JSONL receipts for individual run means, medians, p95, error, and requested direct-read bytes.

On this one-expert path, **five 1060s with the expert already resident (284.8 µs) were essentially tied with uploading the expert from RAM to the 3090 (277.8 µs)**. Keeping a cold expert on 1060s could be valuable when it replaces an NVMe miss or frees scarce RAM; this probe does not show a speed win over the 3090's RAM path. Re-reading a cold expert from NVMe each call was milliseconds on both layouts; the resident 1060 path was about 15× faster than the five-worker direct-read path, but real routing and cache hit rates determine whether that matters to a full request.

The existing [256K Strata launch](../strata_q38_ctx256k_g0_20261103/terminal.json) reported 31.6 GiB of experts: 15.3 GiB in 3090 VRAM, 8.0 GiB in RAM, and 8.4 GiB assigned to the file tier. In a hypothetical dedicated expert-only worker implementation, moving that 8.4 GiB file allocation across five 1060s would average about **1.7 GiB per card**; moving all 16.4 GiB outside the 3090 would average about **3.3 GiB per card**. Those figures omit worker buffers, fragmentation, and all other model state. They are capacity sketches, not tested full-model placements.

## Reproduce on this rig

1. Prepare the sample with [prepare_q38_tiered_expert_sample.py](../../../scripts/active/prepare_q38_tiered_expert_sample.py), pointing `--gguf` to the existing local Q2_0 GGUF, `--gguf-py` to a llama.cpp `gguf-py` checkout, and `--output` to a directory **outside Git**. Use `--workers 5` or `--workers 2`.
2. Bind the benchmarking repo read-only as `/bench`, the sample directory as `/sample`, and run [run_q38_tiered_expert_probe.sh](../../../scripts/active/run_q38_tiered_expert_probe.sh) inside `nvidia/cuda:12.9.2-devel-ubuntu24.04` with `--gpus all`. Set `WORKERS=2` for the two-card matrix. The script compiles [q38_tiered_expert_probe.cu](../../../scripts/active/q38_tiered_expert_probe.cu) and saves timestamped JSONL under the sample directory.

## Limits and next gate

This is **one expert in one layer**, without the router, other experts, context management, KV, n-gram lookup, prefill batching, caching policy, or model serving. Its simple Q2_0 GEMV kernels are correct against the CPU reference but not optimized. `O_DIRECT` bypasses the host page cache; repeated reads of the same small sample may still benefit from drive-internal caching. These timings must not be multiplied by 10 experts × 48 layers to predict tokens per second.

The next test should replay a **real routing trace** with fixed 3090, 1060, RAM, and NVMe budgets. Count misses and bytes by tier, and measure full request latency against Strata's existing 3090-only baseline. Admit an expert to 1060 VRAM only when its expected avoided NVMe cost exceeds the worker transport and compute cost. Current Strata multi-GPU mode is a layer split with dense/KV state on every card, and the installed CUDA 13 engine lacks `sm_61`; integrating these dedicated expert workers would require engine work, not a placement flag.