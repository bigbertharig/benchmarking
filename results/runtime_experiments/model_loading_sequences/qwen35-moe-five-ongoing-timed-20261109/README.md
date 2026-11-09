# Qwen3.6 35B-A3B five-chat 50K pilot (2026-11-09)

Run `qwen35-moe-five-ongoing-timed-20261109` reached 50K occupied context on five independent GTX 1060 chats, each with 262K Q4 KV capacity, while one MoE weight load stayed on GPU0. All five private-code recalls passed. In the 16-token simultaneous decode window, per-chat speeds were about 12.9-13.8 tok/s, versus about 16.1 tok/s on a solo 1060. The first chat's GPU0 preparation took 43.18 s, and save/restore to its 1060 took 0.96 s; it became usable in 44.43 s. Checkpoints were about 355 MB per chat.

The run was intentionally stopped as it entered 100K preparation to prioritize the matched two-chat baseline. The `failed` terminal status and exit 137 reflect that stop, not a 50K correctness failure. Later depths were not measured in this pilot. See [the completed six-depth two-chat curve](../qwen35-moe-two-curve-20261109/README.md) for 16K-200K data.

Evidence: `terminal.json` and stage JSON in this directory; raw log `/mnt/shared/experiments/kv-matrix-20261107/qwen35_moe_five_ongoing_timed_20261109.log` and its checkpoints.
