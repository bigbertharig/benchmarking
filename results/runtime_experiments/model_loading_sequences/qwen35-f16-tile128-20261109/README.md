# Single-1060 F16 attention launch probe (2026-11-09)

This is a **single-chat generation** experiment, using the Qwen3.6-35B-A3B
Q4_K_XL model weights on GPU0 (3090) and one independent F16-KV chat on GPU1
(1060). The chat reserves 262,144 positions, and the same saved 16K, 32K, and
50K occupied states are replayed for 64 generated tokens. Each variant is
bracketed by unchanged-build controls. Raw logs and Nsight reports are under
`/mnt/shared/experiments/kv-matrix-20261107/qwen35_f16_tile{128,64,256}_*`.

| Occupied context | Control before / after | 128-thread tile | Gain vs mean control | 64-thread tile |
| --- | ---: | ---: | ---: | ---: |
| 16K | 68.94 / 68.12 tok/s | **70.47 tok/s** | **+2.8%** | 53.25 tok/s |
| 32K | 60.05 / 60.00 tok/s | **62.52 tok/s** | **+4.1%** | 40.03 tok/s |
| 50K | 49.65 / 49.68 tok/s | **52.64 tok/s** | **+6.0%** | 30.61 tok/s |

At 50K, the baseline F16 attention kernel uses a 32×8 = 256-thread block;
changing the **NVIDIA FP32 fallback** config for head-256, eight columns to
32×4 = 128 threads cut summed GPU1 attention time from **631.9 ms to 558.2
ms** across the traced 64 tokens (11.7%). GPU0 graph time stayed about 369 ms.
GPU1 H→D transfers were about 39.85 MB / 105.8 ms in both traces, and GPU1
D→H transfers were about 10.49 MB / 18.8 ms. These summed CUDA times can
overlap; they are not additive wall-clock components. The trace supports the
interpretation that 1060 attention efficiency, rather than the x1 bus alone,
limits this single-chat path at these depths. Transfers are still material.

The [64-thread follow-up](../qwen35-f16-tile64-20261109/) changed that same
config and made 50K attention time 1,429.9 ms; its 50K decode fell 38.4%
relative to its bracketed controls. The [initial 256-thread attempt](../qwen35-f16-tile256-20261109/)
accidentally edited the AMD RDNA config and left the actual 1060 launch
unchanged. Its no-change result is **not** a valid 256-vs-128 test. The normal
Pascal baseline already uses 256 threads.

The candidate is a model-shape-specific launch choice, not yet a default.
The replay checks that generation completes from the same saved states; it
does not establish response-quality equivalence or behavior on other models,
KV formats, long outputs, or simultaneous chats. Next: validate generation
quality and repeatability, test a 128-thread launch on another head-256/F16
model, and profile a longer single-chat response. Return-state capture remains
a separate follow-up because this run measures generation speed only.

Artifacts: [campaign](../../../../campaigns/qwen35_f16_tile128_20261109.json),
[patch](f16_tile128.patch), [build recipe](build.sh), [terminal receipt](terminal.json).
