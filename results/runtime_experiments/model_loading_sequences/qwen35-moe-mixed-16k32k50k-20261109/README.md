# Qwen3.6 35B-A3B mixed chat placement, 65K control (2026-11-09)

Manager run `qwen35-moe-mixed-16k32k50k-20261109` passed an A/B/A comparison at occupied 16K, 32K, and 50K with two Q4 KV contexts reserving 65,536 tokens each. A kept both chats on 1060 GPUs1/2. B moved the main chat KV to GPU0 and left the worker on GPU1. All MoE weights stayed on GPU0. Each stage restored the same saved checkpoints and generated 64 tokens per chat in solo and simultaneous windows.

| Occupied depth | Baseline worker range, before/after tok/s | Mixed main / worker tok/s |
| ---: | ---: | ---: |
| 16,384 | 37.26-37.44 | 118.81 / 36.67 |
| 32,768 | 22.98-23.42 | 111.95 / 23.58 |
| 50,000 | 16.87-16.88 | 101.45 / 16.98 |

Peak mixed-stage GPU0/1 memory was 21,743/569 MiB. This small-reservation control confirms the GPU0 main is much faster while the 1060 worker remains near its baseline. The [full-262K repeat](../qwen35-moe-mixed-maxctx-16k32k50k-20261109/README.md) is the capacity-relevant result. Saved histories came from the passed [50K checkpoint extension](../qwen35-moe-two-short-extend-20261109/README.md).

Evidence: `terminal.json` and stage JSON in this directory; manifest `campaigns/qwen35_moe_mixed_16k32k50k_20261109.json`; raw logs and GPU/PCIe samples under `/mnt/shared/experiments/kv-matrix-20261107/qwen35_moe_mixed_16k32k50k_20261109_*`.
