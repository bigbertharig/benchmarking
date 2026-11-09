# Qwen3.6 35B-A3B Q4_1 and Q5_1 KV checkpoint preparation (2026-11-09)

Run `qwen35-moe-kv-variant-prep-20261109` passed both sequential stages. For each cache format, the Q4_K_XL model weights stayed on RTX 3090 Ti GPU0, while two independent GTX 1060 chats used that format for both keys and values with a 262,144-token reservation each. Both chats passed private-code recall at occupied 16K, 32K, and 50K. The saved states feed the [matched worker replay](../qwen35-moe-worker-kv-variant-matrix-20261109/README.md).

The Q4_1 cache allocated 1,600 MiB of KV per 1060; Q5_1 allocated 1,920 MiB. Peak sampled worker memory, including other runtime buffers, was 2,197 and 2,517 MiB respectively. The raw logs record incremental GPU0 preparation, state capture and 1060 restore, checkpoint I/O, recall, and short decode windows separately. These passed preparations establish usable independent histories, not a matched speed comparison.

The Q4_1 stage also generated with two chats simultaneously. Worker1/2 reached 54.18/54.29 tok/s at 16K, 33.79/33.59 at 32K, and 22.96/22.86 at 50K, close to the solo worker1 rates of 52.42/34.00/23.79 in this stage. This supports two-worker isolation for Q4_1 in short windows; it does not establish five-worker scaling.

Evidence: `terminal.json` and both stage receipts in this directory; manifest `campaigns/qwen35_moe_kv_variant_prep_20261109.json`; raw logs, GPU samples, and checkpoints under `/mnt/shared/experiments/kv-matrix-20261107/qwen35_moe_two_q4_1_16k32k50k_20261109.*` and the corresponding `q5_1` prefix.
