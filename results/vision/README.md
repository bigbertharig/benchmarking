# Local vision screen, November 20, 2026

This is a frozen, synthetic 24-image local screen with four cases each for
OCR, documents, charts, GUI reading, absence/abstention, and spatial/counting.
It is a pipeline and candidate screen, not an official score for any public
vision benchmark. The suite and `SHA256SUMS` are in
[`suites/vision/understanding/local-v1`](../../suites/vision/understanding/local-v1).
All runs used temperature 0, a 256-token response cap, one image per request,
an 8K runtime context, and the same runner and answer key.

| Checkpoint and card | Exact matches | Valid JSON schema | Median request | Idle GPU memory |
| --- | ---: | ---: | ---: | ---: |
| Qwen3.5 9B Q3_K_M, GTX 1070 | 19/24 | 23/24 | 7.34 s | 5,592 MiB |
| Qwen3.5 9B Q4_K_M, RTX 3090 Ti | 18/24 | 22/24 | 1.18 s | 6,571 MiB |
| Gemma 4 12B Q6_K_L, RTX 3090 Ti | 24/24 | 24/24 | 0.92 s | 11,101 MiB |

The speed figures are on different GPUs for Qwen Q3 and Q4, so they do not
isolate the effect of quantization. Each exact-match score is one run on a
small local suite. Both Qwen runs missed all four OCR cases; Gemma got all
four. Qwen Q4 answered chart-01 as `4` rather than the keyed `Q4`/`Quarter 4`,
and both Qwen runs described the absent serial number instead of using the
keyed word `unavailable`. The raw replies are preserved in the result files;
the frozen scorer was not changed after seeing them.

The first Qwen Q4 load read the model and projector over the shared mount and
hit the runtime's 900-second readiness limit. After both files were staged to
the local model hotset, it loaded successfully. Gemma Q6 staging took 1,089 s
for the weights and 19 s for the projector from the shared archive; the local
load succeeded with batch size 512. These are storage-staging observations,
not inference latency. The staged Qwen Q4 files were removed after its tests;
the Gemma Q6 local copy remains for follow-up loads. The source archives remain
on shared storage.

Step3-VL-10B BF16 is downloaded but did not join this quick GGUF screen. Its
local model card requires a Transformers or vLLM BF16 runtime, which is not
installed on the rig. It has no score in this table.

The case receipts are in the sibling `local-full24-*` folders. Gemma's
`run_context.json` records the suite hash and completion; the Qwen results
were produced before that per-case durability improvement. The earlier Qwen
Q3 six-case receipt and runtime notes are preserved here as a baseline.
