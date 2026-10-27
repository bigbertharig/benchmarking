# Qwen3.5 4B placement speed experiment

Runs `ram-offload-qwen35-r4-20261027` and the strict CPU-only follow-up
`ram-offload-qwen35-cpu-only-20261027` on 2026-10-27, `llama-runtime:b11669`,
Qwen3.5-4B-Q4_K_M from rig NVMe. Context allocation 32,768; batch and
micro-batch 64; four CPU threads; 128 generated tokens on each of two identical
completion requests. Values below are the second request. The model was loaded
separately for each placement with `--load-mode none`. All power caps stayed at
350 W (3090 Ti) and 100 W (each 1060).

| Placement | Model layers on GPU | Load s | Prefill tok/s | Decode tok/s | GPU memory after load |
|---|---:|---:|---:|---:|---:|
| Strict CPU/RAM, no CUDA device visible | 0/33 | 14.60 | 47.4 | 7.44 | unchanged (GPU0 15 MiB) |
| Weights in system RAM; CUDA compute buffer | 0/33 | 6.37 | 243.8 | 7.52 | GPU0 443 MiB |
| 20 layers on one 1060; rest in RAM | 20/33 | 8.33 | 25.1 | 14.21 | GPU1 2,644 MiB |
| Fully on one 1060 | 33/33 | 10.37 | 482.4 | 28.40 | GPU1 3,774 MiB |
| Fully on the 3090 Ti | 33/33 | 2.31 | 3,884.7 | 177.42 | GPU0 4,021 MiB |

The first zero-layer case still allocated a 149 MiB CUDA compute buffer on the
3090. It is a weights-in-RAM result, not a strict no-GPU result. The follow-up
set `CUDA_VISIBLE_DEVICES=-1`; its log reports no CUDA-capable device and its
GPU memory remained at baseline. Its prefill was 47.4 rather than 243.8 tok/s,
while its decode remained about 7.4 tok/s. This shows that zero model layers
offloaded does not, by itself, imply CPU-only prefill in this llama.cpp build.
The partial case logged `offloaded 20/33 layers to GPU`; both full cases logged
`offloaded 33/33`. Baseline GPU memory was 15 MiB on GPU0 and 4 MiB on the
1060s. The partial case's very low prefill may involve CPU/GPU transfers and
synchronization over the 1060's Gen2 x1 link; this experiment does not isolate
which component dominates. Load times are from sequential NVMe loads with
uncontrolled filesystem cache state, so they are not cold-load benchmarks.

The earlier successful run `ram-offload-qwen35-r3-20261027` reproduced the
same broad pattern: prefill/decode 242/7.41, 25/14.11, 484/28.37, and
3,892/177.63 tok/s in the same placement order. Its server logs used lower
verbosity and did not show the offload counts. The two initial launch attempts
failed before sampling because the script used an unsupported `--no-mmap` flag;
the runtime supports `--load-mode none`.
