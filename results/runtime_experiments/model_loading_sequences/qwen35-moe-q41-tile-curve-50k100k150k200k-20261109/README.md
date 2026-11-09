# Qwen3.6 Q4_1 tile worker curve, 50K–200K (2026-11-09)

Qwen3.6-35B-A3B Q4_K_XL weights stayed on the RTX 3090 (GPU0). Two
independent chats kept Q4_1 KV on GTX 1060 GPU1 and GPU2, with a 262,144-token
reservation for each. A transient GPU0 context restored each worker's prior
state, appended the next messages and filler, saved the grown state, and
restored it on its 1060. Each chat passed its own long-range recall check at
50K, 100K, 150K, and 200K occupied tokens. The test generated 64 tokens per
chat, first solo on GPU1 and then concurrently on GPU1/GPU2, at each depth.

| Occupied depth | Solo tok/s | Two chats, tok/s each | Prepare next stage, seconds per chat | GPU0 save → 1060 restore, seconds per chat | Worker state size |
| --- | ---: | ---: | ---: | ---: | ---: |
| 50K | 30.74 | 30.80 / 30.44 | 51.85–52.03 | 1.06 | 370 MiB |
| 100K | 18.22 | 18.30 / 18.12 | 67.24–70.32 | 2.04–2.05 | 676 MiB |
| 150K | 13.04 | 12.75 / 12.75 | 80.12–86.23 | 3.03–3.05 | 982 MiB |
| 200K | 10.13 | 10.11 / 10.03 | 93.43–102.27 | 4.03–4.05 | about 1.3 GiB |

The concurrent per-chat decode rate stayed close to solo at every depth.
Absolute tok/s still falls as context grows; the earlier Q4_1 tile gain is a
*relative* gain against vector attention, not faster absolute decode at long
context. Preparation is incremental in token computation: it appends only
new material to the restored prior state. It still reads, saves, and restores
the full growing checkpoint every stage. The handoff timer includes state
serialization and worker restore, so it is not a pure PCIe bandwidth measure.
Worker state size and handoff time both grow with occupied context. The
GPU0 workspace is transient, not a resident mirror of both chats.

Peak sampled GPU memory: GPU0 23,075 MiB, GPU1 2,193 MiB, GPU2
2,193 MiB. The samples can miss short allocation peaks. This run does not
establish five-worker scaling, quality equivalence, or repeated live turn
latency; the recall probes cover only two independent markers. We should
measure an appended-KV-only handoff next, while tracking GPU0 high-water
memory, its occupancy time, worker isolation, transfer bytes, and full
per-turn latency. Delta state transfer requires an explicit compatible format
for recurrent state and KV; a simple file append is not sufficient.

Evidence: [terminal receipt](terminal.json), [campaign](../../../../campaigns/qwen35_moe_q41_tile_curve_50k100k150k200k_20261109.json),
stage receipts in this directory, and raw logs, GPU samples, and states under
`/mnt/shared/experiments/kv-matrix-20261107/qwen35_moe_q41_tile_curve_50k100k150k200k_20261109*`.
