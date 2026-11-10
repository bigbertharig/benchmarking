# Durable checkpoint guards (2026-11-09)

A fresh process recovered a base-only 100K checkpoint with zero committed
turns and committed turn 1. A copied record with one changed payload byte
was rejected with an explicit checksum error and expected exit 75. The
original checkpoint was untouched. See the [durability result](../qwen35-return-durable-20261109/README.md)
and [parsed receipt](../qwen35-return-durable-20261109/receipt.json).
