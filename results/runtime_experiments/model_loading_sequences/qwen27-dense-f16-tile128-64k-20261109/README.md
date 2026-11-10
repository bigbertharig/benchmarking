# Dense 27B versus MoE 35B-A3B on one 1060 chat (2026-11-09)

The comparison replays validated chats at occupied 16K, 32K, and 50K for
64 generated tokens. Both use Q4 model weights on GPU0 (3090), one F16 KV
worker on GPU1 (GTX 1060 6 GB), and the same experimental 128-thread
Pascal/head-256 attention tile. The solo replay has no second chat context.
The reported rate is worker generation only: model load, chat preparation,
snapshot restore, and final state capture are outside the timer.

| Occupied context | Dense Qwen3.6 27B | MoE Qwen3.6 35B-A3B | MoE / dense |
| ---: | ---: | ---: | ---: |
| 16K | 23.20 tok/s | 70.47 tok/s | 3.04x |
| 32K | 18.56 tok/s | 62.52 tok/s | 3.37x |
| 50K | 14.76 tok/s | 52.64 tok/s | 3.57x |

The dense chat reserved **64K**, while the MoE chat reserved **262K**.
The first dense attempt at 262K failed before generation: F16 KV alone
requested 16,384 MiB on a 6 GB 1060. At 64K it allocated 4,096 MiB of
worker KV; the observed worker occupancy was about 4,169 MiB. The MoE
262K F16 reservation uses about 5,120 MiB. Thus the table matches
occupied depth, KV format, GPU placement, generated length, and attention
tile, but **not reserved capacity**. Dense F16 at 262K on one 1060 is
physically unavailable in this build.

The first 64K solo replay stopped at a harness-only guard inherited from
the MoE replay mode (`pair_cap < 210000`). It did not reach generation.
An isolated build changed that one threshold to 50K, leaving kernels and
model placement untouched. Its fresh-process solo replay passed all three
depths. The preparation stage had already passed and saved the 16K, 32K,
and 50K dense states. Its additional two-chat measurements were 19.59/19.29,
16.61/16.50, and 14.08/14.01 tok/s per chat at the respective depths;
they are separate from the solo-only table.

For a different reference, the earlier
[Qwen3.5-4B single-1060 capacity run](../../qwen3_5_4b_capacity_g1_ctx32768_20261025.json)
measured 27.97 tok/s near an empty chat, 23.61 tok/s near 16.7K, and
21.15 tok/s near 30.4K. A
[separate full-1060 4B run](../../../ram_offload_comparison_r3_20261027/terminal.json)
measured 28.4 tok/s on a 1.4K prompt. The MoE split is roughly three
times faster at similar occupied depths, but it uses the 3090 for weights
and model compute. The 4B run keeps its whole model and chat on one 1060;
these figures do not compare equal hardware use or model quality.

The much larger dense active weight path and KV footprint are plausible
sources of its slower rate and steeper curve. This replay does not
isolate their contributions. The follow-up
[dense 50K Nsight trace](../qwen27-dense-f16-trace-50k-20261109/README.md)
measured substantially more GPU0 graph work, GPU1 attention, and link
traffic than the matched MoE trace. A Q4_0 or Q4_1 dense KV run at 262K
is a different capacity/speed trade-off; earlier Q4_0 dense long-context
runs were much slower and should not be compared as if only the model changed.

Evidence: [parsed receipt](receipt.json), [first full-cap campaign](../../../../campaigns/qwen27_dense_f16_tile128_20261109.json),
[64K preparation campaign](../../../../campaigns/qwen27_dense_f16_tile128_64k_20261109.json),
[isolated solo replay campaign](../../../../campaigns/qwen27_dense_f16_tile128_64k_solo_fix_20261109.json),
[one-line replay guard patch](replay_guard.patch), and the
[MoE tile result](../qwen35-f16-tile128-20261109/README.md). Stage and
terminal receipts are in their respective campaign folders. Raw logs and
GPU samples are under `/mnt/shared/experiments/kv-matrix-20261107/`.
