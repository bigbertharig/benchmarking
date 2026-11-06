# Qwen3.8 Q2_0 mixed-tier Strata comparison (2026-11-06 UTC)

All four matched cases passed. Source is the same pinned, SHA-256-verified Qwen3.8-Flash-Next GSQ-RCO Q2_0 GGUF and prepared expert pack already used on the rig. Strata control 0.1.56 and CUDA 12 engine 0.1.56 were used throughout these four cases, because GTX 1060 (sm_61) needs the CUDA 12 build. This uses Strata's **layer split** across cards, with VRAM expert caches, a pinned RAM expert budget and an NVMe-backed file tier. It is not the m10dis within-expert sharding prototype.

Conditions: 8,192 context, int8 KV, one request at a time, drafting/MTP/vision off, temperature zero, identical 1,483-token prompt and 128/128/512 output caps. Expert-file pages were advised for eviction before each launch. Request 1 is cold (no prompt tokens cached); requests 2 and 3 report 1,478 cached prompt tokens. Effective tok/s below is generated tokens divided by total request wall time, not engine-only decode throughput. One run per placement; treat close rates as exploratory.

| Placement | Expert VRAM cache | Pinned expert RAM | File tier | Load to ready | Cold request (128 tokens) | Warm request (512 tokens) | Physical NVMe reads, cold / warm 512 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 3090 only, CUDA 12 | 18.6 GiB | 0.1 GiB | 12.9 GiB | 71.8 s | 21.90 s | **80.3 tok/s** (6.38 s) | 8.16 / 0.69 GiB |
| 3090 + one 1060 | 20.7 GiB | 0.1 GiB | 10.8 GiB | 97.3 s | 35.59 s | 68.5 tok/s (7.47 s) | 12.15 / 0.21 GiB |
| 3090 + five 1060s | 29.1 GiB | 0.1 GiB | 2.5 GiB | 202.8 s | 36.61 s | 38.0 tok/s (13.49 s) | 7.65 / 0.04 GiB |
| 3090 + five 1060s | 29.1 GiB | 8.0 GiB | 0.0 GiB | 227.6 s | 27.88 s | 37.7 tok/s (13.57 s) | 2.48 / 0.02 GiB |

The 3090-only CUDA 13 historical baseline at the same 0.1 GiB RAM budget was 70.9 effective tok/s on its warm 512-token request, with 12.9 GiB file tier and 1.09 GiB physical NVMe reads. Its different engine build and date mean it is a historical check, not the primary GPU-count control. Receipt: `../strata_q38_nvme0p1_matched_20261103/terminal.json`.

At this small-context workload, extra 1060s reduced physical NVMe reads but slowed end-to-end inference. Strata assigned early layer ranges to the 1060s and the final range plus head to the 3090; with six cards it made five inter-card handoffs. The 8 GiB RAM budget improved the cold request but did not improve warm output speed; about 0.72 GiB of swap-free capacity changed during that load, while `MemAvailable` remained 14.5 GiB. Do not conclude that extra GPUs are always slower for larger quants or long prompts from this one Q2 workload.

The Q4 follow-up is a separate fit experiment. Official Strata docs specify a 111.3 GB, four-shard UD-Q4_K_XL file with 71.7 GiB of experts and warn this 32 GB RAM rig does not fit the normal setup. The pinned download is staged on the 4 TB drive at `/mnt/shared/models/qwen3.8-flash-next-ud-q4_k_xl`; `download_terminal.json` there is the authority for completion and SHA-256 verification. The rig NVMe had 69 GiB free at download start, so do not claim a rig-NVMe Q4 benchmark until the verified files are safely staged there or explicitly label a shared-drive run.

Receipts: each sibling `strata_q38_mixed_matched_20261106_<case>/terminal.json` contains usage, wall time, GPU memory, host memory, per-process read bytes and host NVMe counters. `engine.log` records the actual cache split and layer assignment. The campaign's `terminal.json` lists all four completed cases. The original exploratory mixed-card starts, including one CUDA 13 sm_61 failure, are kept separately and excluded from this matched table.
