# Qwen3.6 Q8_0 vector versus forced tile attention (2026-11-09)

An isolated source change forced generic tile attention for Q8_0/Q8_0,
head-size-256 GQA on Pascal. The Q4_1 tile result motivated this test, but
the Q8 path already has a native vector kernel. The model weights stayed on
GPU0, one Q8 worker KV on GPU1. The saved 16K/32K/50K Q8 states, 262,144-token
reservation, and 64 generated tokens were matched in a vector/tile/vector
A/B/A sequence. All stages passed with `ok=1`.

| Path | 16K tok/s | 32K tok/s | 50K tok/s |
| --- | ---: | ---: | ---: |
| Q8 vector before | 53.33 | 38.80 | 28.62 |
| Q8 tile | 50.87 | 38.02 | 29.00 |
| Q8 vector after | 54.03 | 38.87 | 28.84 |

Forced tile was slower at 16K, roughly tied at 32K, and only about 1% faster
at 50K. It is **not a useful Q8 speed change** on this worker. This also
shows that the Q4_1 tile gain does not transfer automatically to all KV
types. Q8 worker KV allocation remained 2,720 MiB; peak sampled GPU1
memory was near 3.3 GiB. This test measured decode, not answer quality or
numerical equivalence.

Evidence: [terminal receipt](terminal.json), [build recipe](build_q8_tile.sh),
[campaign](../../../../campaigns/qwen35_moe_q8_vector_tile_16k32k50k_20261109.json),
stage receipts, and raw logs/GPU samples under
`/mnt/shared/experiments/kv-matrix-20261107/qwen35_moe_q8_vector_tile_16k32k50k_20261109_*`.
