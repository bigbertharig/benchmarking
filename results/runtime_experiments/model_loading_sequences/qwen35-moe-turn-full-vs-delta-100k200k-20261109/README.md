# Complete-turn full versus partial handoff, 100K/200K (2026-11-09)

The isolated Qwen3.6 hybrid partial-KV fork was compared with the existing
full-state handoff. Model Q4_K_XL weights stayed on GPU0, while one Q4_1 chat
with a 262K reservation lived on GPU1. Each case resumed the same saved
worker state, appended one user turn and 128 filler tokens on a temporary
GPU0 context, handed the updated state to GPU1, generated a recall answer,
and captured the worker state for the next turn. The second turn resumed
from that captured state. Full ran before partial at 100K; partial ran
before full at 200K. All eight recall checks passed.

| Depth and turn | Handoff full → partial | Request to first token full → partial | Complete turn including capture full → partial |
| --- | ---: | ---: | ---: |
| 100K, 1 | 2.06 → 0.052 s | 3.23 → 1.21 s | 5.34 → 3.31 s |
| 100K, 2 | 2.07 → 0.050 s | 3.07 → 1.04 s | 4.85 → 2.83 s |
| 200K, 1 | 4.05 → 0.054 s | 5.86 → 1.81 s | 9.97 → 5.92 s |
| 200K, 2 | 4.08 → 0.052 s | 5.65 → 1.64 s | 9.15 → 5.14 s |

The partial transfer stayed 66.8 MB while full state was 709–711 MB at
100K and 1.35 GB at 200K. GPU0 preparation of the new material was
matched at about 0.2–0.4 s. The full worker capture after its answer cost
1.6–1.9 s at 100K and 3.1–3.7 s at 200K **in both paths**. This is now
the dominant handoff cost for ongoing turns. A future return-path test
should export only the worker's newly generated KV and current recurrent
state into a host checkpoint, while keeping no persistent GPU0 chat mirror.

Timers start after model load and after reading the first saved checkpoint
from disk. They include GPU0 context creation and restore, prefill, handoff,
GPU0 context destruction, worker response, and full worker capture.
The same host and model were used, but these are two-turn samples, not a
statistical speed distribution. The recall check is narrow; the separate
[state-equivalence run](../qwen35-moe-live-kv-delta-20261109/README.md)
verified byte-identical full states after partial and full handoff at five
starting contexts. Neither test measured simultaneous GPU0 preparation
and another worker's generation.

Evidence: [parsed receipt](receipt.json),
[campaign](../../../../campaigns/qwen35_moe_turn_full_delta_100k200k_20261109.json),
[terminal receipt](../qwen35-moe-turn-ab-20261109/terminal.json), stage
receipts there, and raw logs/GPU samples under
`/mnt/shared/experiments/kv-matrix-20261107/qwen35_moe_turn_full_delta_100k200k_20261109_*`.
