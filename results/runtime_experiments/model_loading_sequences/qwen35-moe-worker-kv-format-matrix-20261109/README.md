# Qwen3.6 35B-A3B worker KV format matrix (2026-11-09)

Run `qwen35-moe-worker-kv-format-matrix-20261109` passed all five stages. One GTX 1060 GPU1 worker held each independent chat, while the 35B-A3B Q4 XL model stayed on RTX 3090 Ti GPU0. All formats reserved 262,144 tokens, replayed validated checkpoints at occupied 16,384/32,768/50,000 tokens, and generated 64 solo worker tokens per depth. Q4 stages bracketed the format changes.

| K/V format | 16K tok/s | 32K tok/s | 50K tok/s | Worker GPU1 allocation |
| --- | ---: | ---: | ---: | ---: |
| Q4/Q4 before | 35.77 | 23.86 | 17.14 | ~2,037 MiB |
| Q8/Q4 | 48.99 | 34.15 | 23.81 | ~2,669 MiB |
| Q4/Q8 | 48.76 | 34.27 | 23.86 | ~2,669 MiB |
| Q8/Q8 | **53.44** | **38.83** | **28.71** | ~3,309 MiB |
| Q4/Q4 after | 36.32 | 23.82 | 17.15 | ~2,037 MiB |

Either mixed format gives a substantial gain over Q4 while using about 640 MiB less worker VRAM than full Q8. Key-only and value-only Q8 were nearly identical in this run. Full Q8 was fastest at all depths, with a 1.49x/1.63x/1.67x gain over the surrounding Q4 mean. This measures decode only; checkpoint build, state capture, and restore have separate costs. The 64-token windows and synthetic histories do not establish full-turn throughput or long-context quality.

Evidence: `terminal.json`, stage receipts, manifest `campaigns/qwen35_moe_worker_kv_format_matrix_20261109.json`, and raw logs/GPU samples under `/mnt/shared/experiments/kv-matrix-20261107/qwen35_moe_worker_kv_format_matrix_20261109_*`.
