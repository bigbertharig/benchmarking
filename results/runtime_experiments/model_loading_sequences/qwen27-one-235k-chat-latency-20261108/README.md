# Qwen3.6 27B, one 235K chat on a 1060 — 2026-11-08

Manager run: `qwen27-one-235k-chat-latency-20261108`.

The previous [two-100K campaign](../qwen27-large-chat-latency-v2-20261108/README.md) proved that two 102,423-occupied chats fit on one 1060 and reported per-chat generation latency. Its five-deep-chat follow-up was stopped after a progress-based ETA showed it would exceed the three-hour stage limit. This run narrows the deep question to one full 235,929-token chat on GPU1, with Qwen3.6 27B Q4 weights on GPU0.

The harness creates a fresh 262,144-capacity context, fills it with a private code and varied recycled field-note lines, and logs progress every 8K occupied positions. After reaching 235,929 positions, it decodes the pending prompt token outside the timed window, measures 16 individual generation steps (first, median, p95, tokens/s), and checks code recall. GPU memory and PCIe samples are written by the shared matrix wrapper. The 4 GiB host-memory floor and 26 GB host-allocation ceiling apply throughout.

The synthetic history measures context-length and placement behavior. One 16-token window is not a general quality or throughput claim. The normal `chat-27b` profile must be restored after the terminal receipt.

## Outcome

This direct-on-1060 fill was deliberately stopped at 2026-11-08T22:04:59Z to free GPUs0-1 for the matched GPU0-preparation and GPU1-handoff experiment. The log reached 65,536 occupied positions in 906.52 seconds of fill time. It never reached 235,929 positions, so it produced no 235K decode or recall result. The Manager terminal receipt records a stopped/failed stage; its Docker child was separately identified and stopped because Manager stopping alone left that child running. The ordinary chat route was not restored between these two experiments and must be restored after the handoff campaign.
