# 50K extension of 65K-cap two-chat checkpoints

Run `qwen35-moe-two-short-extend-20261109` passed. It hard-linked the prior 16K/32K 65K-cap Q4 KV checkpoints into a new state directory, reused those completed depths, then continued both independent chats to 50K on GPU0 and transferred their states to GPUs1/2. Both private-code recalls passed. This supplies matched 16K/32K/50K checkpoints for the [65K mixed-placement control](../qwen35-moe-mixed-16k32k50k-20261109/README.md). The full-262K comparison used its own validated checkpoint set instead.

Evidence: `terminal.json` and stage JSON here; manifest `campaigns/qwen35_moe_two_short_extend_20261109.json`; raw log and checkpoints under `/mnt/shared/experiments/kv-matrix-20261107/qwen35_moe_two_short_extend_20261109.*`.
