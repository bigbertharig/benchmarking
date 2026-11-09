# Qwen3.6 35B-A3B mixed KV checkpoint preparation (2026-11-09)

This run passed at occupied 16K, 32K, and 50K with the model on GPU0 and independent chats on GPUs1 and 2. Each chat reserved 262,144 tokens. Private-code recall passed for both chats at every depth. The saved states feed the [one-worker KV matrix](../qwen35-moe-worker-kv-format-matrix-20261109/README.md). A mixed Q4/Q8 cache allocated about 2,669 MiB per worker, between Q4/Q4 (~2,037 MiB) and Q8/Q8 (~3,309 MiB).

The per-depth state-save/restore and preparation timings are in the raw log. This receipt establishes correct staged histories for the format comparison, not a full-turn speed claim.

Evidence: `terminal.json`, stage receipt, the matching manifest under `campaigns/`, and raw log/GPU samples under `/mnt/shared/experiments/kv-matrix-20261107/` with the same run name.
