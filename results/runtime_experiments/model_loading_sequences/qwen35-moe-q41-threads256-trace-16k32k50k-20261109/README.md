# 256-thread Q4_1 attention traces (2026-11-09)

Three guarded Nsight captures bracketed 64 generated worker tokens after restoring the same validated 16K/32K/50K Q4_1 chat states. They use the isolated 256-thread native Q4_1 build, Qwen3.6-35B-A3B weights on GPU0, and the worker KV on GPU1. All stages passed. The matched unprofiled result is [here](../qwen35-moe-q41-threads128-256-16k32k50k-20261109/README.md); the earlier 128-thread capture is [here](../qwen35-moe-q41-decode-trace-16k32k50k-20261109/README.md).

| Occupied context | 128-thread attention kernel, 64 tokens | 256-thread attention kernel, 64 tokens | GPU0 graph (256) | GPU1 H→D copies (256) |
| --- | ---: | ---: | ---: | ---: |
| 16K | 972 ms | 1,015 ms | 368 ms | 95 ms |
| 32K | 1,903 ms | 2,011 ms | 372 ms | 101 ms |
| 50K | 2,881 ms | 3,042 ms | 371 ms | 106 ms |

The 128-thread kernel launched 1×5×16 blocks of 128 threads, reported 255 registers per thread and 4,352 static shared-memory bytes. The 256-thread kernel launched 1×3×16 blocks of 256 threads, reported 254 registers per thread and 8,448 static shared-memory bytes. Each trace observed 640 attention kernel instances. The new shape does not materially reduce register use and takes 43/109/161 ms longer in attention across 64 tokens. GPU0 graph execution and GPU1 host-to-device copy time are essentially unchanged. These are event-duration sums, so overlapping work must not be added to infer wall time.

The 16K profiled tok/s is noisy and nearly equal between variants, while the unprofiled bracketing test and 32K/50K traces consistently favor 128 threads. Keep the 128-thread native build only as an experimental control; the F16 attention fallback remains faster than either native shape on this GTX 1060.

Evidence: [terminal receipt](terminal.json), [manifest](../../../../campaigns/qwen35_moe_q41_threads256_trace_16k32k50k_20261109.json), stage JSON and logs. Raw `.nsys-rep`, SQLite, kernel summaries, and generation logs are under `/mnt/shared/experiments/kv-matrix-20261107/qwen35_moe_q41_threads256_trace_16k32k50k_20261109_*`.
