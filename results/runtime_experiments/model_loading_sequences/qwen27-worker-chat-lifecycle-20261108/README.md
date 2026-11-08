# Qwen27 worker chat lifecycle on one 1060

2026-11-08. [Campaign](../../../../campaigns/qwen27_worker_chat_lifecycle_20261108.json); [terminal receipt](terminal.json). The run passed in one attempt (22:54:48–22:55:55 UTC, 67 seconds). Raw log: `/mnt/shared/experiments/kv-matrix-20261107/qwen27_worker_chat_lifecycle_20261108.log`.

## Question and setup

Can a 27B model and a continuing main chat stay on GPU0 (3090) while one GPU1 (1060) worker chat is used, released, and replaced by another independent worker without reloading the weights?

The Qwen3.6 27B Q4_K_M weights loaded once from NVMe. The harness held a manager context on GPU0, then opened A (8K cap), B (16K cap), and C (8K cap) sequentially on GPU1. Each worker had two turns and a distinct private four-digit code. The manager answered between worker turns and again after C closed. Occupied depths reached 2,084 for A and C, 4,132 for B, and 3,108 for the manager. Histories used repeated-note filler, and answers were short recall checks.

## Result

| Operation | A | B | C |
| --- | ---: | ---: | ---: |
| Open worker context | 0.141 s | 0.152 s | 0.143 s |
| Close worker context | 0.008 s | 0.009 s | 0.008 s |
| GPU1 while worker live | 261 MiB | 439 MiB | 261 MiB |
| GPU1 after close | 77 MiB | 77 MiB | 77 MiB |
| First turn fill | 1,000 tokens / 6.07 s | 2,024 tokens / 12.48 s | 1,000 tokens / 6.05 s |
| First recall | 0.375 s | 0.384 s | 0.368 s |

GPU1 baseline was 71 MiB. Closing each context returned it to 77 MiB, within 6 MiB of that baseline. A→B and B→C close plus open took 0.161 and 0.152 seconds. The first useful answer also required filling the new chat history: about 6.6 seconds for the 1K workers and 13.0 seconds for the 2K worker, adding open, fill, and recall timings. All six worker recalls and all five manager recalls returned their expected codes. The manager's state survived all three turnovers; no second weight load appears in the log. The ordinary `chat-27b` route was restored after the test.

This establishes serial context reuse with one live model and a continuing main chat in this private llama.cpp harness. The 6 MiB residual is likely CUDA/runtime allocation, but this run does not identify its owner. It does not measure simultaneous generation, full agent prompts, cross-chat state leakage, or a network API's lifecycle overhead. The harness made new empty contexts; it did not save or transfer worker KV snapshots. Future admission tests should verify actual free capacity after many turnovers and explicitly probe for stale state in a new worker.
