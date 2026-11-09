# Qwen3.6 35B-A3B two-chat short probe (2026-11-09)

Run `qwen35-moe-two-short-20261109` passed 16K and 32K occupied contexts with one model load on GPU0 and separate Q4 KV chats on GPUs1 and 2. This probe reserved 65,536 tokens per worker, so use the [fixed-262K six-depth run](../qwen35-moe-two-curve-20261109/README.md) for the matched full curve. Each chat passed its private-code recall. Solo worker1 measured 37.13/23.41 tok/s at 16K/32K; two active chats measured about 38.3/23.6 tok/s per chat. GPU0-prepared chat state became usable on a 1060 in about 14 seconds at 16K and another 15-17 seconds at 32K. The GPU0-to-1060 save/restore portion was about 0.35/0.64 seconds.

Evidence: `terminal.json` and stage JSON in this directory; manifest `campaigns/qwen35_moe_two_short_20261109.json`; raw log and checkpoints under `/mnt/shared/experiments/kv-matrix-20261107/qwen35_moe_two_short_20261109.*`.
