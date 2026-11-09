# Qwen3.6 35B-A3B Q8 KV extension, intentionally stopped (2026-11-09)

Run `qwen35-moe-two-q8-curve-extend-20261109` reused validated 16K/32K/50K Q8 checkpoints and measured a valid 100K point with two active independent GTX 1060 chats. Both Q8 K and V caches reserved 262,144 tokens, and all weights stayed on GPU0. At 100K occupied context, solo worker1 was **15.98 tok/s** and simultaneous workers1/2 were **15.27/15.25 tok/s**, versus Q4 simultaneous **9.37/9.30 tok/s** in the earlier matched six-depth run. The ~1.64x Q8 advantage therefore persisted at 100K in this setup.

The sequence was stopped by Manager at 03:49:55 UTC after the 100K result because the experiment priority shifted back to short 16K/32K/50K placement and format probes. A 150K preparation had begun but was incomplete; do not treat it as a result. Manager's stopped status and the sequence's failed terminal receipt describe this intentional interruption, not a model failure. We are not routinely extending new candidates through 150K/200K.

Evidence: `terminal.json`, stage receipt, manifest `campaigns/qwen35_moe_two_q8_curve_extend_20261109.json`, and raw log/GPU samples under `/mnt/shared/experiments/kv-matrix-20261107/qwen35_moe_two_q8_curve_extend_20261109.*`.
