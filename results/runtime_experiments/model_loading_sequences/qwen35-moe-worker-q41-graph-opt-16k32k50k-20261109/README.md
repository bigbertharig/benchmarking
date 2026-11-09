# Qwen3.6 Q4_1 worker: CUDA graph optimization A/B/A (2026-11-09)

Run `qwen35-moe-worker-q41-graph-opt-16k32k50k-20261109` passed all three stages. The Q4_K_XL model weights stayed on GPU0 and one GPU1 worker held Q4_1 K/V with a 262,144-token reservation. The same validated 16K/32K/50K checkpoints were replayed for 64 solo tokens per depth. The middle stage set `GGML_CUDA_GRAPH_OPT=1`; surrounding stages used the default. The installed build has `GGML_CUDA_GRAPHS=ON`, though this experiment did not record a per-kernel graph trace. Detailed one-second GPU and PCIe samples were also saved.

| Graph option | 16K tok/s | 32K tok/s | 50K tok/s |
| --- | ---: | ---: | ---: |
| Default before | 50.68 | 34.87 | 24.37 |
| `GGML_CUDA_GRAPH_OPT=1` | 50.83 | 34.81 | 24.22 |
| Default after | 50.88 | 35.03 | 24.41 |

The option changed measured speed by less than 1% at every depth, within ordinary run variation. It is not a useful speed lever in this configuration. The installed CUDA backend disables CUDA graphs on pre-Volta GPUs such as the GTX 1060, so this option is relevant chiefly to eligible GPU0 graph work; the result should not be taken as a test of 1060 attention graph optimization.

Evidence: `terminal.json`, stage receipts, manifest `campaigns/qwen35_moe_worker_q41_graph_opt_16k32k50k_20261109.json`, and raw logs and GPU/PCIe samples under `/mnt/shared/experiments/kv-matrix-20261107/qwen35_moe_worker_q41_graph_opt_16k32k50k_20261109_*`.
