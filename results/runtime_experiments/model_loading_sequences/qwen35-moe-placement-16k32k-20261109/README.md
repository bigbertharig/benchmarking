# Qwen3.6 35B-A3B short placement sweep (2026-11-09)

Manager run `qwen35-moe-placement-16k32k-20261109` passed all four stages: all weights GPU0 with separate KV on GPUs1/2; Qwen block 0 expert tensors moved to GPU1; baseline repeated; both KVs on GPU0. Each stage restored the same 16K and 32K independent chat checkpoints and generated 64 tokens per chat, solo and concurrently. The target model is the NVMe Qwen3.6 35B-A3B Q4_K_XL GGUF.

| Placement | 16K two active, worker1 / worker2 tok/s | 32K two active, worker1 / worker2 tok/s |
| --- | ---: | ---: |
| GPU0 weights, KV GPUs1/2 | 38.08 / 37.17 | 23.39 / 23.08 |
| Block 0 experts on GPU1, KV GPUs1/2 | 38.26 / 37.74 | 23.62 / 23.44 |
| GPU0 weights, KV GPUs1/2 (repeat) | 38.06 / 37.50 | 23.63 / 23.45 |
| GPU0 weights and both KVs | 85.74 / 82.51 | 75.02 / 72.58 |

Moving one block's experts to GPU1 had no meaningful speed advantage over the repeated baseline in these short windows. Keeping KV on GPU0 was about 2.2x faster at 16K and 3.1x at 32K per chat, but it spends GPU0 memory that this layout reserves for weights and preparation. This is a placement reference, not a capacity-equivalent alternative. Stage-one model load took 54.94 s cold; later warm stages took about 4.4–4.5 s, so load latency must not be compared without cache state.

Evidence: `terminal.json` and stage receipts in this directory; manifest `campaigns/qwen35_moe_placement_16k32k_20261109.json`; raw `qwen35_moe_two_replay_*_20261109*.log` under `/mnt/shared/experiments/kv-matrix-20261107/`. The 16K/32K two-1060 values agree with the independent [full six-depth baseline](../qwen35-moe-two-curve-20261109/README.md), which uses a fixed 262K worker reservation and newly prepared checkpoints. The sweep restored 65K-cap saved checkpoints, so its KV reservation differs from the full baseline.
