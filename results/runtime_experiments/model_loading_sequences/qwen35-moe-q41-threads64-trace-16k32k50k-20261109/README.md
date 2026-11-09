# 64-thread Q4_1 attention traces (2026-11-09)

Three guarded Nsight captures bracketed 64 generated worker tokens after restoring the validated 16K/32K/50K Q4_1 states. The model weights were on GPU0 and one chat's KV was on GPU1. All stages passed. The matched unprofiled comparison is [here](../qwen35-moe-q41-threads128-64-16k32k50k-20261109/README.md); the [earlier 128-thread](../qwen35-moe-q41-decode-trace-16k32k50k-20261109/README.md) and [256-thread](../qwen35-moe-q41-threads256-trace-16k32k50k-20261109/README.md) traces provide controls for launch shape.

| Occupied context | 64-thread attention time, 64 tokens | 128-thread attention time, 64 tokens | GPU0 graph (64) | GPU1 H→D copies (64) |
| --- | ---: | ---: | ---: | ---: |
| 16K | 961 ms | 972 ms | 366 ms | 95 ms |
| 32K | 1,904 ms | 1,903 ms | 372 ms | 101 ms |
| 50K | 2,877 ms | 2,881 ms | 372 ms | 106 ms |

The 64-thread kernel reports a 1×5×16 grid, 32×2 blocks, 254 registers per thread, and 2,304 bytes of static shared memory. The 128-thread kernel uses the same grid, 32×4 blocks, 255 registers per thread, and 4,352 bytes of static shared memory. Each capture contains 640 attention kernel instances. Thus smaller blocks did not meaningfully change register pressure or sustained kernel time. The 256-thread variant instead reduced the grid's KV partition dimension from five to three and ran slower. Kernel and copy totals are sums of potentially overlapping events, not additive wall time.

Evidence: [terminal receipt](terminal.json), [manifest](../../../../campaigns/qwen35_moe_q41_threads64_trace_16k32k50k_20261109.json), stage JSON and logs. Raw `.nsys-rep`, SQLite, kernel summaries, and generation logs are under `/mnt/shared/experiments/kv-matrix-20261107/qwen35_moe_q41_threads64_trace_16k32k50k_20261109_*`.
