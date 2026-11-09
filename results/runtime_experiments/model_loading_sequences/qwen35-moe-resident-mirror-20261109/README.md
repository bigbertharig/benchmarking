# Resident GPU0/1060 chat mirrors (2026-11-09)

The model weights stayed on RTX 3090 GPU0. Each chat had a Q4_1 KV copy on
GPU0 and an independent GTX 1060 worker copy with 262,144 reserved positions.
GPU0 appended the next user turn and 128 note tokens, sent only new KV cells
plus the required recurrent state to the worker, and the worker returned its
new KV plus recurrent state after the recall reply. Two chats took alternating
turns in the 50K and 100K runs. The 200K runs used one chat. One run reserved
the full 262,144 positions on GPU0 as well as the worker.

| Case | Chats | GPU0 mirror cap | Sampled GPU0 peak | Worker first token after handoff | Complete turn |
| --- | ---: | ---: | ---: | ---: | ---: |
| 35B two mirrors, 50K | 2 | 65536 | 22,611 MiB | 0.33–0.38 s | 0.72–1.00 s |
| 35B two mirrors, 100K | 2 | 114688 | 23,411 MiB | 0.52–0.57 s | 1.03–1.27 s |
| 35B one mirror, 200K | 1 | 212992 | 23,045 MiB | 0.92–0.95 s | 1.66–1.89 s |
| 35B one mirror, 200K/full 262K reservation | 1 | 262144 | 23,443 MiB | 0.92–0.98 s | 1.66–1.92 s |

Every worker recalled its own four-digit code and its complete serialized
state matched its GPU0 mirror byte for byte after both turns. The outbound
partial update was about 66.8 MB and the return about 66.1 MB per turn. Each
direction took roughly 0.05 seconds in the process timer. The complete-turn
timer includes GPU0 preparation, both state updates, and the worker response;
state saves used for validation ran *after* that timer. It excludes initial
model load, initial checkpoint restore, and source file reads. The two-chat
test alternated turns; it did not generate concurrently. GPU memory samples
were taken around 1 Hz and may miss shorter peaks.

The two-chat 100K case used nearly the 3090's 24 GiB, so there is little
room for another mirror or a large GPU0 main chat with this 35B quant. The
full-reservation 200K case confirms one mirror works at the 262K cap; it does
not establish that two full-cap mirrors fit. This is a capacity-for-latency
trade: the prior [single-worker full/delta comparison](../qwen35-moe-turn-full-vs-delta-100k200k-20261109/README.md)
still paid a complete worker-state capture after every response. The resident
mirror eliminates that timed full capture, but keeps a second GPU chat copy.

The partial-state format is experimental. It assumes a matching source state
and has no transaction rollback or sequence/model identity check. Benchmark
the same mechanism with a smaller model, then test concurrent worker decode
and whether 3090 mirror preparation interferes with it. Use per-chat latency
and GPU0 headroom as well as throughput; do not infer five mirrors from these
one- and two-chat runs.

Evidence: [two-chat campaign](../../../../campaigns/qwen35_moe_mirror_50k100k200k_20261109.json),
[full-reservation campaign](../../../../campaigns/qwen35_moe_mirror_200k_full262k_20261109.json),
[two-chat terminal receipt](../qwen35-moe-mirror-20261109/terminal.json),
[full-reservation terminal receipt](../qwen35-moe-mirror-full262k-20261109/terminal.json),
and [source patch](../qwen35-moe-live-kv-delta-20261109/live-kv-delta.patch).
Raw logs and GPU samples are under `/mnt/shared/experiments/kv-matrix-20261107/`.
