# Matched 102K chat placement: 3090, one 1060, and a 1060 pair

Manager run: `qwen27-matched-100k-kv-placement-20261108`, passed with exit 0 on 2026-11-08. The normal `chat-27b` route was restored afterward.

Qwen3.6 27B Q4_K_M weights loaded once on GPU0. A synthetic chat with a private four-digit code reached 102,423 occupied positions under a 114,688-token configured context. GPU0 prepared it once in 180.760 seconds and saved a 2,047,213,666-byte state to host memory. The harness then restored this exact state into fresh contexts on GPU0, GPU1, GPUs1+2, and GPU0 again, one at a time. Each placement decoded one pending token outside the timed window, generated 64 tokens, and passed private-code recall. The final GPU0 repeat checks drift across the measurement order.

| KV and attention placement | Physical Q4 KV allocation | Restore | 64-token generation | Median/token | Recall |
| --- | ---: | ---: | ---: | ---: | --- |
| GPU0, first | GPU0, 2,016 MiB | 0.267 s | **26.732 tok/s** | 37.459 ms | passed |
| GPU1 | GPU1, 2,016 MiB | 4.789 s | **3.663 tok/s** | 272.933 ms | passed |
| GPUs1+2 | 1,008 MiB per card | 4.792 s | **3.653 tok/s** | 273.664 ms | passed |
| GPU0, repeat | GPU0, 2,016 MiB | 0.263 s | **27.317 tok/s** | 36.368 ms | passed |

The 1060 placements delivered about 13.5% of the 3090-local rate at the same occupied history, or roughly **7.4 times longer per token**. Splitting the cache across two 1060s did not improve the generation rate in this run. The paired placement physically split KV, but it also introduces graph and transfer work; this result alone does not isolate the bottleneck. One 64-token sample per placement and synthetic repeated-note history limit generalization to natural conversations. The A/B/C/A order bounds major drift but does not replace repeated randomized trials.

The preparation and restore timings are separate from generation. They confirm that GPU0 prefill plus handoff is the faster admission path established by the prior two-chat test, while live long-context generation remains substantially faster when KV stays on GPU0. The matched comparison supports investigating attention device time, host-staged PCIe transfer, and graph synchronization with phase-aligned profiling before designing a faster split runtime.

Receipts: `terminal.json`, stage JSON, and manifest here. Raw log, `.start`, `.finish`, `.exit`, GPU memory, and PCIe samples are under `/mnt/shared/experiments/kv-matrix-20261107/` with prefix `qwen27_matched_100k_kv_placement_20261108`. Source: [matched mode](../../../../scripts/active/llama_simple_chat_latency.cpp) and [campaign manifest](../../../../campaigns/qwen27_matched_100k_kv_placement_20261108.json).
