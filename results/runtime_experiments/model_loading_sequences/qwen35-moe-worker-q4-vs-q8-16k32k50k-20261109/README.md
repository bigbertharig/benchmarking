# Qwen3.6 35B-A3B 1060 worker: Q4 versus Q8 KV (2026-11-09)

Manager run `qwen35-moe-worker-q4-vs-q8-16k32k50k-20261109` passed a Q4/Q8/Q4 A/B/A comparison. All model weights stayed on RTX 3090 Ti GPU0. One GTX 1060 GPU1 worker held a Q4 or Q8 key/value cache with a fixed 262,144-token reservation, restoring independently validated checkpoints at occupied 16,384, 32,768, and 50,000 tokens. Each stage generated 64 solo worker tokens. The Q8 checkpoints were built separately and passed private-code recall for both chats at each depth; Q4 checkpoints came from the passed six-depth baseline.

| Occupied depth | Q4 before tok/s | Q8 tok/s | Q4 after tok/s | Q8 gain versus mean Q4 |
| ---: | ---: | ---: | ---: | ---: |
| 16,384 | 36.01 | **53.58** | 36.54 | **1.48x** |
| 32,768 | 23.80 | **38.75** | 23.85 | **1.63x** |
| 50,000 | 17.13 | **28.71** | 17.16 | **1.67x** |

The repeated Q4 values were close, so the Q8 gain is much larger than short-run drift. Q8 KV costs about 1,272 MiB more per 1060 at the fixed reservation (about 3,309 MiB versus 2,037 MiB) and takes roughly 1.8x as long for GPU0 state save/1060 restore at these depths. All weights remained on GPU0. Q8 has a favorable decode tradeoff for one 1060 worker; the result does not establish five-worker speed or a full conversation-turn latency. A [separate extension](../qwen35-moe-two-q8-curve-extend-20261109/README.md) measured 100K, then was intentionally stopped. The 64-token windows and synthetic histories are controlled decode probes, not a quality evaluation.

Evidence: `terminal.json` and stage receipts in this directory; manifest `campaigns/qwen35_moe_worker_q4_vs_q8_16k32k50k_20261109.json`; raw logs and GPU/PCIe samples under `/mnt/shared/experiments/kv-matrix-20261107/qwen35_moe_worker_q4_vs_q8_16k32k50k_20261109_*`.
