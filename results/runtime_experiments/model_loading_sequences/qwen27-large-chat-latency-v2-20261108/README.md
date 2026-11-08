# Qwen3.6 27B deep per-chat latency — 2026-11-08

Manager run: `qwen27-large-chat-latency-v2-20261108`.

This campaign keeps Qwen3.6 27B Q4 weights on GPU0 and tests independent KV contexts on GTX 1060 cards. It is a capacity and per-chat latency experiment. The ordinary `chat-27b` route is unloaded for the run and should be restored after the terminal receipt.

1. Start two new independent chats with 114,688-token capacity each on GPU1. Grow each to 102,400 occupied tokens using distinct note text. Time A alone, then A and B concurrently, and verify both private-code recalls. Sample GPU memory and PCIe activity through the existing matrix wrapper.
2. Build five fresh 235,929-token chat histories, one on each 1060 under a 256K cap. Time 16 **single-token generation steps per chat** with one, three, and five active chats. Record each chat's first-step, median, p95, total seconds, and tokens/s; verify five private-code recalls after timing. Progress is logged every 8K occupied positions.

The first attempt, `qwen27-large-chat-latency-20261108`, stopped before measurement when the prior 256K snapshot failed to restore: the current runtime reported incompatible key rotation (`2 instead of 256`). Its header and content fingerprint parsed, but its KV layout is incompatible with the present context. The v2 run does not reuse that snapshot; it creates fresh state with the current runtime. The first attempt's terminal receipt remains separate.

The earlier `qwen27_varied_single_20261108` throughput measurement included a replayed 24-token opening prompt in the first of 32 timed steps. Its independence and recall result remains valid, but its 29.38 tok/s figure is a mixed prompt/decode timing, not a clean generation rate. This campaign decodes that pending token outside the timed window and reports per-chat generation latency.

The 256K histories use varied note lines recycled to reach the target depth, so results measure context-length and placement behavior rather than natural conversation quality. The two 100K chats use the same method. One run per layout is exploratory evidence.

Receipts: `terminal.json` and per-stage JSON files here; raw `.log`, `.exit`, GPU memory and PCIe samples under `/mnt/shared/experiments/kv-matrix-20261107/`.

## Two 100K chats on one 1060: passed

Both chats reached 102,423 occupied tokens under separate 114,688-token context caps. Each reserved a 2,016 MiB KV buffer on GPU1; total GPU1 use was about 5,037 MiB. A's 16 clean generation steps alone took 4.424 seconds: 3.62 tok/s, 273 ms median and 325 ms p95. With both generating concurrently, A took 10.418 seconds (1.536 tok/s; 650 ms median) and B took 10.437 seconds (1.533 tok/s; 650 ms median). Both independently recalled their original four-digit codes after the timed run. This proves simultaneous fit and correctness at roughly 100K occupied tokens each on one 1060, with approximately half the solo per-chat rate under concurrent generation. One 16-token run per case is exploratory; initialization of each long history took about half an hour.

Operational interpretation: two 100K chats on one 6 GB 1060 are a capacity proof, not an attractive concurrent serving layout at the measured 1.53 tok/s per chat. The direct-on-1060 history fill was a slow-path control. The matched [GPU0 preparation and GPU1 handoff run](../qwen27-two-100k-handoff-20261108/README.md) prepared each history in about three minutes and transferred its fresh state in seconds; generation on GPU1 remained slow. Prior saved states cannot be reused with the current runtime because its KV layout changed.

## Five 235K chats: stopped after startup rate check

The fresh-state stage started and logged occupied-position progress every 8K. GPU1 showed about 5,729 MiB used for its single 256K-capacity context. Its first 8K, 16K, and 24K checkpoints took 56, 128, and 216 seconds; the increasingly long 8K blocks projected that filling five 235K chats would exceed the three-hour stage limit. Manager stopped this stage before a deep-chat timing result. The Manager stop left its Docker child running; that exact container was identified and stopped separately. The [focused one-chat run](../qwen27-one-235k-chat-latency-20261108/README.md) was also stopped during direct GPU1 fill to free the rig for the handoff comparison; it produced no 235K decode result. The two 100K stage above had already passed and was preserved.
