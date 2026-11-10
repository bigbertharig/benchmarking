# Twenty-turn return checkpoint compaction (2026-11-09)

At 200K occupied context, one Q4_1 1060 worker completed 20 turns with
recall success and a byte-identical final reconstructed state in both runs.
The no-compaction run retained 40 host updates and its temporary GPU0
rebuild rose from 0.35 to 0.67 s. The compaction run replaced its host base
after turns 10 and 20, resetting the next rebuild to 0.31 s after turn 10.

Turns 11–20 saved 2.04 s with compaction; the turn-10 compaction cost 1.44 s,
leaving about 0.61 s net through turn 20. The final turn-20 compaction cost
1.37 s and only benefits a future turn. See the [full return-path result](../qwen35-return-delta-20261109/README.md)
and its [parsed receipt](../qwen35-return-delta-20261109/receipt.json).
