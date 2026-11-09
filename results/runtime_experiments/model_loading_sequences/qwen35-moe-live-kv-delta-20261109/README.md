# Live partial KV handoff, Qwen3.6 hybrid model (2026-11-09)

An isolated llama.cpp fork added a guarded sequence-state flag to export
only full-attention KV cells after the previous occupied position. Its reader
appends those cells to the worker's existing KV instead of replacing the
sequence; the hybrid model's recurrent state is still replaced in full. The
Q4_K_XL model weights stayed on GPU0. GPU0 temporarily restored and extended
one chat; a Q4_1 worker on GPU1 received the partial update, and a matched
control on GPU2 received the full state. Both worker contexts reserved 262K.
The test started from saved 16K, 50K, and 100K states and added 176 tokens
per turn, twice per depth.

| Starting context | Partial bytes | Full bytes after turn | Partial export + apply | Full restore alone | GPU0 sampled peak |
| --- | ---: | ---: | ---: | ---: | ---: |
| 16K | 66.8 MB | 172–173 MB | 0.047–0.048 s | 0.294–0.297 s | 21,697 MiB |
| 50K | 66.8 MB | 388–389 MB | 0.048–0.055 s | 0.848–0.851 s | 21,963 MiB |
| 100K | 66.8 MB | 709–711 MB | 0.048–0.049 s | 1.674–1.684 s | 22,363 MiB |
| 150K | 66.8 MB | 1,031–1,032 MB | 0.049–0.052 s | 2.489–2.503 s | 22,761 MiB |
| 200K | 66.8 MB | 1,352–1,353 MB | 0.049–0.052 s | 3.319–3.338 s | 23,161 MiB |

At **all ten handoffs**, the partial-update worker and full-restore control
produced **byte-identical complete saved states before generation**. Both
passed the long-range code recall after each turn. The second turn starts
from the partial worker's own post-recall state, exercising repeated use.
The partial payload is dominated by the model's roughly 63 MiB recurrent
state; it stays nearly constant for these short increments. The full state
grows with context. The 1 Hz memory peaks can miss short peaks.

This is a real partial GPU update, but the comparison isolates handoff work.
The run prepares each turn once on GPU0 and then executes both handoffs in
sequence. Its GPU0 workspace timer includes the full-control save and
restore, so it is **not** a delta-only end-to-end turn latency. Earlier file
compression patches reduced checkpoint bytes but still required a full GPU
restore; the [file-level probe](../qwen35-moe-file-delta-probe-20261109/README.md)
records why that route was slower. A separate [complete-turn A/B](../qwen35-moe-turn-full-vs-delta-100k200k-20261109/README.md)
now measures request through first token and worker capture at 100K/200K.
Concurrent GPU0 preparation and a second worker's decode remain unmeasured.

The prototype is experimental: the flag encodes a cutoff position, and its
reader assumes the worker already has exactly the matching prior state.
Add validation for model/KV format, position continuity, sequence identity,
and rollback after a failed apply before treating it as a reusable loader.
Then repeat with two distinct chats before scaling to five.

Evidence: [summary receipt](receipt.json), [source patch](live-kv-delta.patch),
[build recipe](build.sh), [16K terminal receipt](../qwen35-moe-live-delta-validated-20261109/terminal.json),
[50K/100K terminal receipt](../qwen35-moe-live-delta-50k100k-20261109/terminal.json),
and [150K/200K terminal receipt](../qwen35-moe-live-delta-150k200k-20261109/terminal.json).
Raw logs and GPU samples are under
`/mnt/shared/experiments/kv-matrix-20261107/qwen35_moe_live_delta_validated_*`.
