# Qwen3.6 Q4_1 native attention kernel: matched A/B/A (2026-11-09)

The existing benchmark build compiled FlashAttention vector kernels for F16, BF16, Q4_0 and Q8_0 KV, but omitted Q4_1. Its runtime log said Q4_1 attention converted K/V values to F16 inside the attention path. We built the same source with one added `GGML_CUDA_FA_QUANTS` entry, `q4_1-q4_1`, for CUDA architectures 61 and 86. This tested the native Q4_1 vector kernel without changing the model, saved histories, or chat capacity.

The guarded `qwen35-moe-q41-native-16k32k50k-20261109` campaign passed all three stages: original build, native-kernel build, original build. Each stage loaded Qwen3.6-35B-A3B Q4_K_XL weights on GPU0 and one Q4_1/Q4_1 KV worker on GPU1, restored the same validated 16K/32K/50K checkpoints, reserved 262,144 tokens, and generated 64 tokens at each depth. All stage exits were zero and each generation reported `ok=1`. The fallback warning appeared in both original-build controls and disappeared in the native stage.

| Build | 16K tok/s | 32K tok/s | 50K tok/s | Peak GPU0 / GPU1 MiB |
| --- | ---: | ---: | ---: | ---: |
| Original before | 49.31 | 34.19 | 24.22 | 21,173 / 2,197 |
| Native Q4_1 kernel | 36.03 | 24.81 | 17.87 | 21,173 / 2,197 |
| Original after | 49.65 | 34.67 | 24.11 | 21,173 / 2,197 |

Native Q4_1 was **27.2%, 27.9%, and 26.1% slower** than the mean of surrounding controls at 16K, 32K, and 50K. Median per-token latency increased from approximately 18.6/28.8/41.2 ms in the controls to 25.6/40.1/55.8 ms. Restore times remained 0.29/0.56/0.84 s; this compile-time change did not reduce KV state bytes or worker memory. The two original-build controls agree closely, supporting a real performance difference in this layout. These are 64-token runs and do not establish exact output equivalence; `ok=1` means generation completed its existing check.

**Interpretation:** Retain the compact Q4_1 KV cache but leave the F16 attention fallback in place on the GTX 1060 for now. Avoid assuming that a native quantized kernel is faster simply because it removes a conversion. The next focused probe is an isolated GPU1 decode trace to separate vector-attention kernel time, memory reads, and GPU0/model or PCIe stalls. A kernel-level adjustment would then be tested against these saved-history controls. m10dis's parallelism lesson and BigMoeOnEdge's real-model A/B discipline motivated this measured comparison; neither repo predicts the Q4_1 kernel speed on our Pascal/x1 topology.

Evidence: [terminal receipt](terminal.json), stage JSON and logs in this directory, [manifest](../../../../campaigns/qwen35_moe_q41_native_16k32k50k_20261109.json), raw logs and GPU/PCIe samples under `/mnt/shared/experiments/kv-matrix-20261107/qwen35_moe_q41_native_16k32k50k_20261109_*`, and isolated build log `/data/bench-staging/build_q41_native.log`. The original build is `/data/bench-staging/kvchat-b11669-build`; the variant is `/data/bench-staging/kvchat-q41-native-build`.
