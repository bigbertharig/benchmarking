# Qwen3.6 27B deep per-chat latency — 2026-11-08

Manager run: `qwen27-large-chat-latency-20261108`.

This campaign keeps Qwen3.6 27B Q4 weights on GPU0 and tests independent KV contexts on GTX 1060 cards. It is a capacity and per-chat latency experiment. The ordinary `chat-27b` route is unloaded for the run and should be restored after the terminal receipt.

1. Restore the five previously validated 90%-of-256K chat snapshots, one onto each 1060. Each saved context has 235,929 occupied tokens. Time 16 **single-token generation steps per chat** with one, three, and five active chats. Record each chat's first-step, median, p95, total seconds, and tokens/s; verify five private-code recalls after timing. Existing snapshot files stay outside Git and have their embedded fingerprints checked on read.
2. Start two new independent chats with 114,688-token capacity each on GPU1. Grow each to 102,400 occupied tokens using distinct note text. Time A alone, then A and B concurrently, and verify both private-code recalls. Sample GPU memory and PCIe activity through the existing matrix wrapper.

The earlier `qwen27_varied_single_20261108` throughput measurement included a replayed 24-token opening prompt in the first of 32 timed steps. Its independence and recall result remains valid, but its 29.38 tok/s figure is a mixed prompt/decode timing, not a clean generation rate. This campaign decodes that pending token outside the timed window and reports per-chat generation latency.

The existing 256K snapshots were created with synthetic repeated field-note blocks, so results measure context-length and placement behavior rather than natural conversation quality. The two 100K chats also use varied note lines recycled to reach the target depth. One run per layout is exploratory evidence.

Receipts: `terminal.json` and per-stage JSON files here; raw `.log`, `.exit`, GPU memory and PCIe samples under `/mnt/shared/experiments/kv-matrix-20261107/`.
