# Qwen3.6 27B deep per-chat latency — 2026-11-08

Manager run: `qwen27-large-chat-latency-v2-20261108`.

This campaign keeps Qwen3.6 27B Q4 weights on GPU0 and tests independent KV contexts on GTX 1060 cards. It is a capacity and per-chat latency experiment. The ordinary `chat-27b` route is unloaded for the run and should be restored after the terminal receipt.

1. Start two new independent chats with 114,688-token capacity each on GPU1. Grow each to 102,400 occupied tokens using distinct note text. Time A alone, then A and B concurrently, and verify both private-code recalls. Sample GPU memory and PCIe activity through the existing matrix wrapper.
2. Build five fresh 235,929-token chat histories, one on each 1060 under a 256K cap. Time 16 **single-token generation steps per chat** with one, three, and five active chats. Record each chat's first-step, median, p95, total seconds, and tokens/s; verify five private-code recalls after timing. Progress is logged every 8K occupied positions.

The first attempt, `qwen27-large-chat-latency-20261108`, stopped before measurement when the prior 256K snapshot failed to restore: the current runtime reported incompatible key rotation (`2 instead of 256`). Its header and content fingerprint parsed, but its KV layout is incompatible with the present context. The v2 run does not reuse that snapshot; it creates fresh state with the current runtime. The first attempt's terminal receipt remains separate.

The earlier `qwen27_varied_single_20261108` throughput measurement included a replayed 24-token opening prompt in the first of 32 timed steps. Its independence and recall result remains valid, but its 29.38 tok/s figure is a mixed prompt/decode timing, not a clean generation rate. This campaign decodes that pending token outside the timed window and reports per-chat generation latency.

The 256K histories use varied note lines recycled to reach the target depth, so results measure context-length and placement behavior rather than natural conversation quality. The two 100K chats use the same method. One run per layout is exploratory evidence.

Receipts: `terminal.json` and per-stage JSON files here; raw `.log`, `.exit`, GPU memory and PCIe samples under `/mnt/shared/experiments/kv-matrix-20261107/`.
