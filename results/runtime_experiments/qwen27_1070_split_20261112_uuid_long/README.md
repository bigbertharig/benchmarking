# 3090 Ti / 1070 / 1060 split comparison (2026-11-12)

Qwen3.6-27B Q4_K_M from rig NVMe, llama-runtime:b11669, 32K context cap, one 13,002-token occupied prompt, 128 generated tokens, temperature 0, batch 64, two repeats per placement. The same model, request and runtime flags were used for all three. Tensor splits: 8,2 for two cards and 8,1,1 for three. All 65/65 layers were GPU offloaded. The managed series is `results/runtime_experiments/model_loading_sequences/qwen27-1070-split-20261112-v3/comparison.json`.

| Placement (host IDs) | Model buffers (MiB) | Prefill, repeat 1 / 2 tok/s | Decode, repeat 1 / 2 tok/s |
| --- | --- | ---: | ---: |
| 3090 Ti + 1060 (0,3) | 11,538 + 3,807 | 401.44 / 400.55 | 17.24 / 17.24 |
| 3090 Ti + 1070 (0,2) | 11,538 + 3,807 | 503.15 / 500.78 | 20.88 / 20.81 |
| 3090 Ti + 1070 + 1060 (0,2,3) | 11,538 + 1,629 + 2,178 | 474.10 / 477.91 | 18.41 / 18.59 |

At this depth the 1070 two-card split is about 25% faster in prefill and 21% faster in decode than the 1060 two-card split. Adding the 1060 to the 1070 split reduced decode by about 11% and prefill by about 5%, though the three-card run remained faster than 3090+1060. These are two warm repeats of one workload, not a general speed claim. The larger 1070 also offers 2 GiB more VRAM; this comparison did not push that capacity advantage. Load times (14.4 s each) were warm-cache loads and are not cold-load evidence.

## Placement verification and invalid pilot

The corrected runner selected GPUs by their hardware UUIDs in Docker and failed if any requested GPU gained under 512 MiB or an unrequested GPU gained over 256 MiB. Host VRAM increases were 13,688/4,334 MiB for GPU 0/3, 13,688/4,356 MiB for GPU 0/2, and 13,688/1,912/2,558 MiB for GPU 0/2/3. The logs name the 1070 at PCI 0D:00.0 and show the model buffers above. The final three-card container was left loaded under the benchmark claim.

The earlier `qwen27_1070_split_20261112` pilot is **invalid as a 1070 comparison**. It used Docker `--gpus all` and a host-index `CUDA_VISIBLE_DEVICES` mask. CUDA ordinal order differed from the host's `nvidia-smi` indices: the supposed 1070 leg actually loaded GPU 1, a 1060, while GPU 2 was idle. Its receipts are retained to document the placement bug and must not enter speed summaries. The first managed attempt also failed before any model load because the sequence runner did not quote a claim note over SSH; the runner is fixed.
