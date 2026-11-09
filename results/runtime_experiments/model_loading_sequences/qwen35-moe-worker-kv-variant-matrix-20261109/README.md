# Qwen3.6 35B-A3B Q4_1 and Q5_1 worker KV comparison (2026-11-09)

Run `qwen35-moe-worker-kv-variant-matrix-20261109` passed all five stages. The model's Q4_K_XL weights stayed on RTX 3090 Ti GPU0. One GTX 1060 GPU1 worker held each chat's keys and values in the listed cache format with a fixed 262,144-token reservation. Every stage replayed a validated checkpoint at occupied 16,384/32,768/50,000 tokens and generated 64 solo worker tokens per depth. Q4_0 stages bracketed the changes.

| K/V cache | 16K tok/s | 32K tok/s | 50K tok/s | Approx. worker allocation |
| --- | ---: | ---: | ---: | ---: |
| Q4_0/Q4_0 before | 36.28 | 23.86 | 17.14 | 2,037 MiB |
| Q4_1/Q4_1 | **50.10** | **34.76** | **24.26** | 2,197 MiB |
| Q5_1/Q5_1 | 45.25 | 30.04 | 20.78 | 2,517 MiB |
| Q8_0/Q8_0 reference | 53.49 | 38.79 | 28.73 | 3,309 MiB |
| Q4_0/Q4_0 after | 36.23 | 23.86 | 17.17 | 2,037 MiB |

Q4_1 gained about 1.38x/1.46x/1.41x over the mean Q4_0 controls with about 160 MiB more 1060 memory. It was faster than Q5_0 (45.61/30.31/20.80 tok/s in a separate matched run) while using about 160 MiB less worker memory, and it was slightly faster than either mixed Q4_0/Q8_0 option (about 49/34/24 tok/s) while using about 472 MiB less. Q5_1 was slower than Q4_1 despite using more memory. Full Q8 remained fastest. These are runtime-specific 64-token decode probes, not full-turn latency or a quality comparison.

Evidence: `terminal.json`, stage receipts, manifest `campaigns/qwen35_moe_worker_kv_variant_matrix_20261109.json`, and raw logs/GPU samples under `/mnt/shared/experiments/kv-matrix-20261107/qwen35_moe_worker_kv_variant_matrix_20261109_*`.
