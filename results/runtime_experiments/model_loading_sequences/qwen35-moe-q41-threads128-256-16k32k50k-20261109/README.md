# Qwen3.6 native Q4_1 vector kernel: 128 versus 256 threads (2026-11-09)

This test follows the [decode-only trace](../qwen35-moe-q41-decode-trace-16k32k50k-20261109/README.md), which found that the native Q4_1 attention kernel on GPU1 consumed the extra time. We copied the native-Q4_1 source and build into isolated variant directories and changed only the vector kernel's host and device thread counts from 128 to 256. Both paths retained the Q4_1/Q4_1 KV kernel, Qwen3.6-35B-A3B Q4_K_XL model on GPU0, one GPU1 chat, 262,144-token reservation, and the same saved 16K/32K/50K histories. Each point generated 64 tokens.

The guarded A/B/A campaign `qwen35-moe-q41-threads128-256-16k32k50k-20261109` passed. All stages had exit 0, `ok=1`, and no F16-fallback warning. Peak sampled GPU0/GPU1 allocation was unchanged at 21,173/2,197 MiB.

| Native Q4_1 build | 16K tok/s | 32K tok/s | 50K tok/s |
| --- | ---: | ---: | ---: |
| 128 threads before | 37.26 | 24.92 | 17.96 |
| 256 threads | 35.66 | 23.94 | 17.25 |
| 128 threads after | 37.79 | 24.93 | 18.00 |

Against the mean bracketing control, 256 threads slowed worker decode by **5.0%/4.0%/4.1%** at 16K/32K/50K. The controls agree closely at 32K and 50K. At 16K the first-token time varied, but median per-token latency also worsened (about 25.2 ms controls versus 25.8 ms variant). The 256-thread variant remains substantially slower than the previously measured F16 attention fallback with the same Q4_1 cache.

The isolated [256-thread Nsight campaign](../qwen35-moe-q41-threads256-trace-16k32k50k-20261109/README.md) confirmed that the variant changed its attention launch from **1×5×16 grid, 128-thread blocks** to **1×3×16 grid, 256-thread blocks**. Registers per thread barely changed, **255 → 254**; static shared memory rose from 4,352 to 8,448 bytes. Summed GPU1 attention time across 64 generated tokens increased from **972/1,903/2,881 ms** in the prior 128-thread traces to **1,015/2,011/3,042 ms** at 16K/32K/50K. GPU0 graph and GPU1 copy times stayed near their prior values. This variant did not relieve the suspected register pressure and reduced parallel KV partitions, so do not use 256 threads for this Pascal/Q4_1 layout.

**Scope:** This is a result for the Qwen3.6 attention shape (the traced head size is 256), the tested llama.cpp build, CUDA architecture 61, and this 3090/1060 placement. The test method transfers to other models; the thread-count decision and tok/s numbers do not. A different model can change KV heads, layer count, attention window, cache type, and kernel dispatch.

Evidence: [terminal receipt](terminal.json), stage JSON and logs, [campaign manifest](../../../../campaigns/qwen35_moe_q41_threads128_256_16k32k50k_20261109.json), and [isolated build recipe](build_q41_256.sh). Raw logs, GPU samples, and PCIe samples are under `/mnt/shared/experiments/kv-matrix-20261107/qwen35_moe_q41_threads128_256_16k32k50k_20261109_*`.
