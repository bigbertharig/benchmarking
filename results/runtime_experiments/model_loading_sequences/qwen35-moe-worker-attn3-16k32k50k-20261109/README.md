# Qwen3.6 35B-A3B one-worker attention placement (2026-11-09)

Manager run `qwen35-moe-worker-attn3-16k32k50k-20261109` passed an A/B/A comparison with one Q4 KV chat on GTX 1060 GPU1, reserving the full 262,144-token context. The same validated saved history was restored at occupied 16,384, 32,768, and 50,000 tokens. Each stage generated a 64-token solo worker window. Baselines kept all MoE weights on RTX 3090 Ti GPU0. The middle stage placed `^blk[.]3[.]attn_.*weight$` on GPU1; runtime load logging confirmed 27.63 MiB of model buffer on CUDA1 and 20,737.16 MiB on CUDA0.

| Occupied depth | Baseline before tok/s | Block 3 attention weights on GPU1 tok/s | Baseline after tok/s |
| ---: | ---: | ---: | ---: |
| 16,384 | 36.36 | 35.12 | 36.64 |
| 32,768 | 23.87 | 23.29 | 23.88 |
| 50,000 | 17.17 | 16.87 | 17.17 |

The override **slowed** the worker about 3.8%, 2.4%, and 1.8% against the mean of the surrounding baselines. This is a small, consistent negative result for one attention block. It does not establish that every attention layer should stay on GPU0, nor identify the exact cost of crossing the x1 link; the one-second PCIe counters and GPU utilization samples are coarse. It does show that moving a small block of attention weights to the 1060 is not an immediate speed improvement for this worker layout.

The larger goal remains improving decode for chats whose KV is on 1060s. The [mixed GPU0-main/1060-worker result](../qwen35-moe-mixed-maxctx-16k32k50k-20261109/README.md) is a capacity and interference reference: a fast GPU0 main chat barely changed the 1060 worker speed, but accelerating that GPU0 chat is not the optimization target. Next useful probes are attention kernel timing and memory-traffic profiling on one 1060 worker, then a matched A/B of any concrete kernel, KV format, or hot-state placement change. Full-attention KV access grows with occupied context, so a model-specific sparse or selective-KV idea needs a correctness gate as well as speed measurement.

Evidence: `terminal.json` and stage receipts in this directory; manifest `campaigns/qwen35_moe_worker_attn3_16k32k50k_20261109.json`; raw logs and GPU/PCIe samples under `/mnt/shared/experiments/kv-matrix-20261107/qwen35_moe_worker_attn3_16k32k50k_20261109_*`. Source checkpoints are from the passed [six-depth curve](../qwen35-moe-two-curve-20261109/README.md), where private-code recall passed at each tested depth.
