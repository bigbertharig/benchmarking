# Dense 27B 50K single-worker decode trace (2026-11-09)

This Nsight Systems run replays the validated 50K Qwen3.6 27B Q4_K_M chat
with F16 KV on GPU1 (GTX 1060), weights on GPU0 (3090), a 64K context
reservation, and the 128-thread Pascal head-256 attention tile. CUDA capture
covers only 64 generation tokens. It completed at 14.37 tok/s under tracing;
the untraced solo replay was 14.76 tok/s. The matched
[MoE trace](../qwen35-f16-tile128-20261109/README.md) uses the same tile,
F16 worker, 50K occupied depth, and 64 generated tokens, but a 262K
reservation and different model weights.

| Captured activity across 64 tokens | Dense 27B | MoE 35B-A3B | Dense / MoE |
| --- | ---: | ---: | ---: |
| GPU0 graph execution, summed | 1,323.8 ms | 369.1 ms | 3.59x |
| GPU1 attention tile kernels, summed | 2,472.5 ms | 558.2 ms | 4.43x |
| GPU1 total kernels, summed | 2,488.4 ms | 568.5 ms | 4.38x |
| GPU1 host-to-device copies | 89.3 MB / 237.4 ms | 39.8 MB / 105.7 ms | 2.24x time |
| GPU1 device-to-host copies | 25.2 MB / 50.3 ms | 10.5 MB / 18.8 ms | 2.68x time |

At this depth, the dense worker's flash-attention tile takes almost all of
its GPU1 kernel time. The 3090 graph is also substantially longer. The
x1 transfer lane carries more bytes, but its measured copy time is far
smaller than GPU1 attention and GPU0 graph time. The CUDA activities can
overlap; these summed values **must not be added** to estimate turn latency
or interpreted as exclusive shares. The trace supports optimizing dense
attention and model compute before focusing only on the link. It does not
prove which change will improve wall time without a matched A/B run.

This also explains why the MoE's 52.6 tok/s at 50K is not simply a lucky
transfer result: both its model work and worker attention are much smaller.
The two models differ in active weights and KV geometry. The experiment
does not isolate which model property causes each difference, and it does
not establish answer-quality equivalence.

The practical next speed probes are a dense attention kernel variant at
50K, then a matched model-compute/transfer intervention if attention gains
alone plateau. Retain the 16K/32K/50K replay as the scorecard, and include
state-handoff time separately from raw generation. The earlier
[dense/MoE speed comparison](../qwen27-dense-f16-tile128-64k-20261109/README.md)
records capacity and speed limits.

Evidence: [parsed device summary](trace_summary.json),
[campaign](../../../../campaigns/qwen27_dense_f16_trace_50k_20261109.json),
[trace runner](../../../../scripts/integration/run_qwen27_dense_f16_decode_trace.sh),
[stage receipt](trace_dense_50k.json), and [terminal receipt](terminal.json).
Raw `.nsys-rep`, exported SQLite, and log are under
`/mnt/shared/experiments/kv-matrix-20261107/qwen27_dense_f16_tile128_trace_50k_20261109*`.
