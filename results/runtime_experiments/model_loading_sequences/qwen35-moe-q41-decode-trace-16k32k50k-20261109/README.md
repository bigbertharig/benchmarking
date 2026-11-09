# Qwen3.6 Q4_1 worker decode traces (2026-11-09)

Six Nsight Systems captures bracketed only the 64-token `moe_one_replay` generation after restoring validated chat state. The Qwen3.6-35B-A3B Q4_K_XL model weights remained on GPU0 (RTX 3090 Ti), with one Q4_1/Q4_1 KV chat on GPU1 (GTX 1060), a 262,144-token reservation, and occupied histories of 16K, 32K, or 50K. Each depth paired the ordinary build's F16 attention fallback with a build containing the native Q4_1 FlashAttention vector kernel. All six stages and generation checks passed. The [previous matched A/B/A](../qwen35-moe-q41-native-16k32k50k-20261109/README.md) established that the native build is slower without profiling.

| Depth | Path | Decode tok/s under profiler | GPU1 attention kernel | GPU1 Q4_1 dequant | GPU1 all kernels | GPU0 graph execution | GPU1 host→device copies |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 16K | F16 fallback | 48.73 | 293 ms | 241 ms | 549 ms | 372 ms | 96 ms |
| 16K | Native Q4_1 | 35.86 | 972 ms | 0 | 987 ms | 367 ms | 96 ms |
| 32K | F16 fallback | 33.33 | 661 ms | 477 ms | 1,153 ms | 371 ms | 101 ms |
| 32K | Native Q4_1 | 23.83 | 1,903 ms | 0 | 1,917 ms | 372 ms | 101 ms |
| 50K | F16 fallback | 23.77 | 1,171 ms | 729 ms | 1,914 ms | 371 ms | 107 ms |
| 50K | Native Q4_1 | 17.35 | 2,881 ms | 0 | 2,895 ms | 371 ms | 106 ms |

Times are **sums of event durations across 64 generated tokens**, not exclusive wall-clock time; GPU work and copies can overlap. The GPU0 CUDA kernel table excludes work inside its captured CUDA graphs, so the graph column is the more useful GPU0 activity measure here. The GPU1 host-to-device records were 36.6/38.7/40.9 MB across 64 tokens at 16K/32K/50K; their duration and the 10.5 MB of GPU1 device-to-host copies were essentially identical between builds. These events do not account for all possible host or bus stalls, but they do not explain the native-kernel regression.

The native vector kernel costs **679/1,241/1,710 ms more** than the fallback F16 vector kernel. Removing the separate Q4_1 dequant kernels saves **241/477/729 ms**, leaving a net GPU1 kernel increase of about **438/765/982 ms**. The observed generation wall time increases by about **471/766/997 ms**, closely tracking that kernel increase. The attention kernel uses the same 1×5×16 grid and 128-thread blocks in both builds, but the native Q4_1 instance reports **255 registers per thread** versus **220** for the F16 instance. This points to work inside the quantized attention kernel, possibly including register pressure; these traces do not measure spills, bandwidth, or achieved occupancy directly.

**Next focused test:** vary the native vector kernel's thread/block shape for Pascal, beginning with 256 threads while holding the 16K/32K/50K replay fixed. Measure register count and kernel time as well as end-to-end tok/s, and retain fallback controls. A separate, more involved idea is to keep a dequantized F16 hot KV window on GPU1 while Q4_1 remains the compact backing store; the fallback traces show a substantial recurring conversion cost, especially at 50K. Do not attribute the current slowdown to the 3090 or PCIe link based on these paired traces.

The first Nsight attempt captured a raw `.qdstrm` but could not import it because the CUDA image lacked `libdw.so.1` and `libelf.so.1`; the runner now mounts those rig libraries read-only and produces `.nsys-rep`, SQLite, and kernel-summary files. The initial failed terminal receipt is preserved as `terminal_first_attempt_failed.json`. A legacy `nvprof` pilot failed before the model ran because it does not support the 3090's compute capability; its separate receipt is retained as tooling evidence.

Evidence: [terminal receipt](terminal.json), [compact metric summary](trace_summary.json), [manifest](../../../../campaigns/qwen35_moe_q41_decode_trace_16k32k50k_20261109.json), [decode-marker source transform](add_decode_trace.py), and [summarizer](summarize_decode_traces.py). Raw per-stage `.nsys-rep`, `.sqlite`, `.kernels.csv`, and logs reside under `/mnt/shared/experiments/kv-matrix-20261107/qwen35_moe_q41_decode_trace_16k32k50k_20261109_*`.
