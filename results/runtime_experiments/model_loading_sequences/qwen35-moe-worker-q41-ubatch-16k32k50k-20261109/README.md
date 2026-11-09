# Qwen3.6 Q4_1 worker: decode microbatch sweep (2026-11-09)

Run `qwen35-moe-worker-q41-ubatch-16k32k50k-20261109` passed all five stages. The Q4_K_XL model weights remained on GPU0; one GPU1 worker held Q4_1 K/V with a 262,144-token reservation. The same validated checkpoints were replayed at occupied 16K/32K/50K, with 64 solo decode tokens per depth. Only the worker context's `n_ubatch` changed; `n_batch` stayed 64 and generation still requested one token per decode. The default 8 was measured before and after. Each stage also saved once-per-second GPU utilization, memory utilization, clocks, power, and PCIe link state.

| Worker `n_ubatch` | 16K tok/s | 32K tok/s | 50K tok/s |
| ---: | ---: | ---: | ---: |
| 8 before | 50.78 | 34.94 | 24.32 |
| 1 | 50.77 | 35.59 | 24.81 |
| 32 | 51.04 | 34.78 | 24.61 |
| 64 | 51.12 | 34.93 | 24.18 |
| 8 after | 50.69 | 35.10 | 24.09 |

The rates are close. `n_ubatch=1` was about 1.6% faster at 32K and 2.5% at 50K than the mean default controls, with no 16K benefit. These small, unreplicated differences do not justify changing the default yet. Since generation is one token at a time, this setting mostly changes graph reservation and scheduling capacity rather than the actual decode batch. This result does not test multi-token speculative decoding or prefill throughput.

Evidence: `terminal.json`, stage receipts, manifest `campaigns/qwen35_moe_worker_q41_ubatch_16k32k50k_20261109.json`, and raw logs and GPU/PCIe samples under `/mnt/shared/experiments/kv-matrix-20261107/qwen35_moe_worker_q41_ubatch_16k32k50k_20261109_*`.
