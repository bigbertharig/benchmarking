# Qwen3.6 35B-A3B Q5 KV checkpoint preparation (2026-11-09)

Run `qwen35-moe-two-q5-16k32k50k-20261109` passed at occupied 16K, 32K, and 50K. All model weights stayed on RTX 3090 Ti GPU0; two independent GTX 1060 chats used `q5_0` for both KV keys and values and each reserved 262,144 tokens. Private-code recall passed for both chats at all depths. The checkpoints feed the [matched Q4/Q5/Q8 worker replay](../qwen35-moe-worker-q5-matrix-20261109/README.md).

Each 1060 allocated about 2,357 MiB, compared with about 2,037 MiB for Q4 KV, 2,669 MiB for mixed Q4/Q8, and 3,309 MiB for Q8 KV at the same reservation. The raw log records preparation, state capture/restore, checkpoint I/O, and 64-token decode windows separately. This preparation receipt establishes correct independent histories; the matched replay is the speed comparison.

Evidence: `terminal.json` and stage receipt in this directory; manifest `campaigns/qwen35_moe_two_q5_16k32k50k_20261109.json`; raw log, GPU samples, and checkpoints under `/mnt/shared/experiments/kv-matrix-20261107/qwen35_moe_two_q5_16k32k50k_20261109.*`.
