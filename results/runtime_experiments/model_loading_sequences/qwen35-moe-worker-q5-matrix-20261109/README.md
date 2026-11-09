# Qwen3.6 35B-A3B Q4/Q5/Q8 worker KV comparison (2026-11-09)

Run `qwen35-moe-worker-q5-matrix-20261109` passed all four stages. The Q4_K_XL model weights stayed on RTX 3090 Ti GPU0; one GTX 1060 GPU1 worker held each chat's KV. All cache formats reserved 262,144 tokens and replayed validated independent checkpoints at occupied 16,384/32,768/50,000 tokens. Each stage generated 64 solo worker tokens per depth, with Q4 bracketing the changes.

| K/V cache | 16K tok/s | 32K tok/s | 50K tok/s | Worker allocation |
| --- | ---: | ---: | ---: | ---: |
| Q4_0/Q4_0 before | 35.77 | 23.86 | 17.15 | ~2,037 MiB |
| Q5_0/Q5_0 | **45.61** | **30.31** | **20.80** | ~2,357 MiB |
| Q8_0/Q8_0 reference | 53.51 | 39.05 | 28.85 | ~3,309 MiB |
| Q4_0/Q4_0 after | 36.61 | 23.87 | 17.17 | ~2,037 MiB |

Q5 gained about 1.26x/1.27x/1.21x over the mean Q4 controls, using about 320 MiB more 1060 VRAM. Q8 remained faster at each depth, using about 952 MiB more than Q5. In the separate [mixed Q4/Q8 matrix](../qwen35-moe-worker-kv-format-matrix-20261109/README.md), either mixed format was also faster than Q5 at each depth but used about 312 MiB more. These are short decode windows with synthetic histories. Their result is specific to this runtime's attention implementation and does not establish full-turn latency or quality.

Evidence: `terminal.json`, stage receipts, manifest `campaigns/qwen35_moe_worker_q5_matrix_20261109.json`, and raw logs/GPU samples under `/mnt/shared/experiments/kv-matrix-20261107/qwen35_moe_worker_q5_matrix_20261109_*`.
