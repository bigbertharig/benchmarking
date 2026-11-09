# Qwen3.6 F16 worker KV speed ceiling (2026-11-09)

The Q4_1 tile trace still spent 242/477/723 ms per 64 generated tokens on
repeated Q4_1-to-F16 conversion. This test uses F16 K and V directly to
measure a conversion-free worker ceiling. Model Q4_K_XL weights stayed on
GPU0; each independent chat's F16 KV was on a separate GTX 1060. The
262,144-token reservation allocated **5,120 MiB of KV per 1060** and fit.
The 3090 prepared matched 16K/32K/50K histories, transferred them to the
workers, and both workers passed recall checks. A later single-worker replay
restored those states and generated 64 tokens per depth; both stages passed.

| Occupied depth | One 1060 replay, tok/s | Two active 1060s, tok/s each | Q4_1 tile control, tok/s |
| --- | ---: | ---: | ---: |
| 16K | 68.28 | about 64 | 53.52 |
| 32K | 59.91 | about 57–58 | 40.91 |
| 50K | 49.65 | about 49–50 | 31.52 |

Peak sampled GPU1 memory in replay was 5,201 MiB. The 50K state file was
about 1.09 GB and took 2.63 seconds to restore; Q4_1 worker state and
transfer are much smaller. The speed result establishes room for a fused
Q4_1 read, but F16's memory and transfer cost make it a different trade-off.
The fully occupied 262K case was not measured. The two-worker preparation
run includes recall checks; the replay stage checks successful generation,
not numerical equivalence against Q4_1.

Evidence: [terminal receipt](terminal.json),
[campaign](../../../../campaigns/qwen35_moe_f16_ceiling_16k32k50k_20261109.json),
stage receipts, and raw logs/states/GPU samples under
`/mnt/shared/experiments/kv-matrix-20261107/qwen35_moe_{two_f16,f16_ceiling}_16k32k50k_20261109*`.
