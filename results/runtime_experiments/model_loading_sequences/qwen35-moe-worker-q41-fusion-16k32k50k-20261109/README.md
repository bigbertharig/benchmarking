# Qwen3.6 Q4_1 worker: CUDA fusion A/B/A (2026-11-09)

Run `qwen35-moe-worker-q41-fusion-16k32k50k-20261109` passed three sequential stages with the model weights on GPU0, one Q4_1 K/V worker on GPU1, fixed 262,144-token reservation, and the same validated saved histories. Each stage replayed occupied 16K/32K/50K and generated 64 solo worker tokens. The middle stage set `GGML_CUDA_DISABLE_FUSION=1`; the surrounding stages used the default fusion setting. The wrapper also sampled GPU utilization, memory utilization, SM clocks, power, and PCIe link state once per second, plus its existing PCIe traffic sample.

| CUDA fusion | 16K tok/s | 32K tok/s | 50K tok/s |
| --- | ---: | ---: | ---: |
| Default before | 50.81 | 35.10 | 24.33 |
| Disabled | 46.53 | 33.12 | 23.67 |
| Default after | 50.91 | 35.02 | 24.31 |

Disabling fusion slowed the worker about 8.5%/5.5%/2.7% against the mean controls. The default stages agree closely. This shows that eligible fused operations in the model-plus-worker decode path matter, especially at shorter occupied context. The shrinking difference is consistent with growing 1060 attention/KV cost taking a larger share, but this experiment does not identify which GPU or kernels changed enough to explain the result. The CUDA source already disables one quantized matrix-vector fusion path on Pascal GPUs; the flag affects other eligible fusions as well. One-second hardware samples are too coarse to assign per-token stalls to GPU0, GPU1, or PCIe.

Evidence: `terminal.json`, stage receipts, manifest `campaigns/qwen35_moe_worker_q41_fusion_16k32k50k_20261109.json`, and raw logs, `gpu_detail.csv`, `gpu.csv`, and `pcie.txt` files under `/mnt/shared/experiments/kv-matrix-20261107/qwen35_moe_worker_q41_fusion_16k32k50k_20261109_*`.
