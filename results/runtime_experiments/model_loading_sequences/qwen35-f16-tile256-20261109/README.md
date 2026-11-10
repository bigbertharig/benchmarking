# F16 tile configuration no-op (2026-11-09)

The first isolated edit targeted an AMD RDNA tile configuration. The 1060
uses NVIDIA's FP32 fallback, so the control and edited builds both launched
the same 32×8 (256-thread) attention kernel and stayed near 69/60/50 tok/s
at 16K/32K/50K. This result must not be read as evidence that changing the
Pascal launch to 256 threads has no effect; 256 is already its baseline.
See the [corrected comparison](../qwen35-f16-tile128-20261109/).
