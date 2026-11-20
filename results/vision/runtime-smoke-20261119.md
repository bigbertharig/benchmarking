# Vision runtime smoke — 2026-11-19

## Qwen3.5-9B Q3_K_M

Files:

- language GGUF: 4,673,643,744 bytes;
- F16 vision projector: 918,165,952 bytes;
- combined disk payload: 5,591,809,696 bytes (5.21 GiB).

Runtime: llama.cpp `b11669-620d2225c`, context 8,192 on the RTX 3090 Ti
and GTX 1070, context 4,096 on the GTX 1060, reasoning budget zero.

The smoke image was Step3-VL's benchmark-results chart. The model correctly
answered: “This is a grouped bar chart comparing the accuracy percentages of
various vision-language models across six different benchmarks.”

| Card | Context | Observed VRAM | Cold request | Decode | Result |
| --- | ---: | ---: | ---: | ---: | --- |
| RTX 3090 Ti 24 GB | 8,192 | 6,143 MiB after image request | ~4.7 s | 109.3 tok/s | pass |
| GTX 1070 8 GB | 8,192 | 5,880 MiB observed after request | 35.4 s | 21.6 tok/s | pass |
| GTX 1060 6 GB | 4,096 | 5,766 MiB observed during request | 51.3 s | 16.1 tok/s | pass, only ~378 MiB free |

The 1060 result proves that the existing Q3 checkpoint can process a large
image on one 6 GB card, but the margin and 4K context are too narrow to call it
a safe deployment without a broader image-size sweep. The 1070 is the practical
one-card baseline. The first request includes image encoding; a repeated cached
request completed in roughly two seconds on both Pascal cards and is not a fair
cold-image latency measurement.

## Gemma 4 12B Q4_K_M

The language model and Q8 projector were present, but the vision runtime did
not reach ready state. Gemma requires at least 161,280 image pixels while the
gateway profile's micro-batch of 64 capped the runtime at 147,456 pixels.
Passing `--ubatch-size 512` as an extra argument did not override the profile's
later runtime setting. This is an integration/profile issue, not a quality
score. A benchmark profile with a vision-safe micro-batch is required before
testing Gemma.
