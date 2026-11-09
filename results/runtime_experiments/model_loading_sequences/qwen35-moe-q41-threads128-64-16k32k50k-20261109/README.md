# Qwen3.6 native Q4_1 vector kernel: 128 versus 64 threads (2026-11-09)

The user requested the opposite launch-shape probe after [256 threads](../qwen35-moe-q41-threads128-256-16k32k50k-20261109/README.md) regressed. We copied the existing 128-thread native-Q4_1 source and build into isolated variant directories and changed only the vector kernel's host and device thread counts to 64. Model weights stayed on GPU0 (RTX 3090 Ti), one Q4_1/Q4_1 KV chat stayed on GPU1 (GTX 1060), reservation stayed at 262,144 tokens, and each stage restored the same validated 16K/32K/50K states and generated 64 tokens. The guarded A/B/A campaign passed with exit 0, `ok=1`, and no F16-fallback warning in every stage.

| Native Q4_1 build | 16K tok/s | 32K tok/s | 50K tok/s |
| --- | ---: | ---: | ---: |
| 128 threads before | 37.54 | 24.92 | 18.00 |
| 64 threads | 37.21 | 24.90 | 18.02 |
| 128 threads after | 37.72 | 24.92 | 17.99 |

The 64-thread run is **effectively tied** at 32K and 50K. At 16K its 64-token tok/s is about 1.1% below the mean controls because its first token took 144 ms rather than about 118 ms; median later-token latency was slightly better at 24.99 ms versus about 25.12 ms. This does not establish a useful speed gain. Peak sampled GPU0/GPU1 allocations remained 21,173/2,197 MiB.

The [64-thread decode traces](../qwen35-moe-q41-threads64-trace-16k32k50k-20261109/README.md) found the same 1×5×16 attention grid as 128 threads, with 64 rather than 128 threads per block. Registers per thread changed only **255 → 254**, static shared memory halved **4,352 → 2,304 bytes**, and attention kernel time across 64 generated tokens was **961/1,904/2,877 ms** at 16K/32K/50K versus **972/1,903/2,881 ms** for 128 threads. GPU0 graph time and GPU1 copy time were essentially unchanged. Halving threads did not remove the native kernel's bottleneck. The 64-, 128-, and 256-thread native kernels all remain slower than the F16 attention fallback for this Q4_1 chat layout.

**Transfer limit:** The launch-shape outcome belongs to this llama.cpp vector kernel, Qwen3.6 head size 256, Pascal 1060, and the measured context depths. Other models may dispatch a different kernel or use a different head size or attention scheme. The matched A/B/A and per-GPU trace method is reusable.

Evidence: [terminal receipt](terminal.json), stage JSON and logs, [campaign manifest](../../../../campaigns/qwen35_moe_q41_threads128_64_16k32k50k_20261109.json), and [isolated build recipe](build_q41_64.sh). Raw logs, GPU samples, and PCIe samples are under `/mnt/shared/experiments/kv-matrix-20261107/qwen35_moe_q41_threads128_64_16k32k50k_20261109_*`.
