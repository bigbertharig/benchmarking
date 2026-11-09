# Smaller 27B model with two resident chat mirrors (2026-11-09)

Qwen3.6 27B Q4_K_M weights stayed on the 3090. Two independent Q4_0 chat
states were mirrored on GPU0 and GTX 1060 workers 1 and 2. The workers each
reserved 262,144 positions; GPU0 mirrors reserved only enough for the current
test depth plus growth. Each chat started from its existing validated saved
state, took two alternating turns, and recalled its private code. The same
experimental partial-KV/recurrent-state update flowed GPU0→worker and
worker→GPU0. Full serialized states matched byte for byte after each turn.

| Occupied depth | GPU0 mirror cap | Sampled GPU0 peak | Worker first token after handoff | Complete turn |
| ---: | ---: | ---: | ---: | ---: |
| 50,000 | 65536 | 19,307 MiB | 0.99–1.02 s | 2.15–2.54 s |
| 100,000 | 114688 | 21,423 MiB | 1.68–1.71 s | 3.42–3.57 s |

The timers include GPU0 preparation, both partial state updates, and the
worker response. State serialization for correctness checks ran after the
timer. Initial model load, checkpoint restore, and source file reads are
excluded. The two chats alternated; concurrent generation was not tested.
The 1 Hz GPU samples can miss brief peaks. The 27B dense model sends a
roughly 158–159 MB partial update per direction, more than double this
experiment's 35B MoE payload; the 1060's dense-model attention/decode is
also slower. So smaller weights buy GPU0 capacity, but do not automatically
make each chat faster. Compare with the [35B mirrored result](../qwen35-moe-resident-mirror-20261109/README.md)
at matched 50K and 100K depth. The two models and KV formats differ, so the
speed difference is descriptive, not an isolated model-size effect.

This prototype lacks source-state identity and rollback guards. The
four/five-chat capacity probe below measures the small-cap mirror boundary;
compare with an unmirrored 27B turn and test whether concurrent GPU0
preparation slows another worker.

Evidence: [50K campaign](../../../../campaigns/qwen27_mirror_50k_20261109.json),
[100K campaign](../../../../campaigns/qwen27_mirror_100k_20261109.json),
[50K terminal receipt](../qwen27-mirror-50k-20261109/terminal.json),
[100K terminal receipt](../qwen27-mirror-100k-20261109/terminal.json),
and [prototype source patch](../qwen35-moe-live-kv-delta-20261109/live-kv-delta.patch).
Raw logs and GPU samples are under `/mnt/shared/experiments/kv-matrix-20261107/`.

## Four 50K mirrors and a five-mirror limit

A follow-up run loaded four saved 50K chats and their 1060 workers at
once. Each 1060 still reserved 262K; GPU0 mirrors reserved 65,536 positions.
All four private-code recalls and all eight post-turn byte-for-byte state
comparisons passed. GPU0 peaked at 22,949 MiB in 1 Hz samples. Per-chat
complete-turn time across the alternating sequence was 2.15–2.54 s;
worker first-token time after handoff was 0.98–1.08 s.
These are sequential turns with four chats resident, not four simultaneous
generations. Each 1060 sampled peak remained about 5,717
MiB, leaving little worker-card headroom. A 50K GPU0 mirror cap gives room
to grow only to 65K. A fifth same-cap mirror failed during context creation:
after four mirrors initialized, GPU0 could not allocate an additional 266 MiB
compute buffer. The failed run generated no turns. Reserving 262K on all
GPU0 mirrors is untested.

Evidence: [four-chat campaign](../../../../campaigns/qwen27_mirror_50k_four_20261109.json),
[four-chat terminal receipt](../qwen27-mirror-50k-four-20261109/terminal.json),
[four-chat summary receipt](four_receipt.json),
[five-chat campaign](../../../../campaigns/qwen27_mirror_50k_five_20261109.json),
and [failed five-chat terminal receipt](../qwen27-mirror-50k-five-20261109/terminal.json).
