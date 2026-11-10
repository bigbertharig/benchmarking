# Single-1060 return-state delta (2026-11-09)

The Qwen3.6-35B-A3B Q4_K_XL weights stayed on GPU0 (3090). One Q4_1-KV
chat with a 262K reservation stayed on GPU1 (1060). Each turn used a
temporary GPU0 workspace to append a user message and 128 filler tokens,
sent the partial outbound state to the worker, generated a short recall
answer, and then made the worker state ready for the next turn. Starting
states came from the validated 50K/100K/200K curve. All turns passed the
private-code recall check.

The new return path exports only the worker's newly decoded KV and its
current recurrent state into host RAM. The host checkpoint is the original
full snapshot plus ordered outbound and return updates. On the next turn,
GPU0 restores that base, applies the updates, prepares new input, and
releases the workspace. There is no resident GPU0 chat mirror. A full
worker save was performed **after** each timed sequence solely to compare
the reconstructed state byte for byte. The final states matched at 50K,
100K, and 200K.

| Starting context | Full worker capture in controls | Return update | Complete turn 1, control → delta | Complete turn 2, control → delta |
| --- | ---: | ---: | ---: | ---: |
| 50K | 0.93 s in final verification | 66.1 MB, 0.036 s | no matched control → 1.12 s | no matched control → 0.91 s |
| 100K | 1.56–1.87 s | 66.1 MB, 0.036 s | 3.31–3.33 → **1.49 s** | 2.82–2.84 → **1.29 s** |
| 200K | 3.10–3.71 s | 66.1 MB, 0.037 s | 5.91–5.92 → **2.25 s** | 5.13 → **2.07 s** |

The 100K and 200K controls used the same isolated build and bracketed the
delta run. At 200K, the full saved worker state was about 1.35 GB. The
request-to-first-token timing remained essentially the same: about 0.53 s
at 100K and 0.95 s at 200K. This change improves **readiness for the next
turn**, not raw generated tok/s or first-token latency. The return update
is around 66 MB even for a short response because it includes the hybrid
model's recurrent state.

## Checkpoint growth and compaction

A [ten-turn 200K run](../qwen35-return-chain10-v2-20261109/terminal.json)
passed every recall and the final exact-state check. The unbounded chain
then ran for 20 turns: two ~66 MB updates were retained per turn, so its
update payload reached about 2.66 GB plus the 1.35 GB base snapshot.
Temporary GPU0 reconstruction grew from 0.35 s on turn 1 to 0.67 s on
turn 20; return export stayed near 0.037 s.

The [matched 20-turn compaction test](../qwen35-return-compact20-20261109/terminal.json)
saved a new full base from a temporary GPU0 workspace after turns 10 and
20, then discarded prior updates. The first compaction took 1.44 s and
reduced turn-11 rebuild from 0.51 s without compaction to 0.31 s. Across
turns 11–20 it saved 2.04 s of turn time, or about **0.61 s net** through
turn 20 after paying for compaction at turn 10. Compaction at turn 20 took
another 1.37 s and provided no benefit inside this 20-turn run; it only
prepares for a later turn. Both 20-turn final states matched byte for byte.
Compaction should therefore be deferred until more turns are expected or
the GPU0 workspace is idle. It occupies GPU0 temporarily and does not
increase worker generation speed.

This is an in-memory proof of concept. The partial-state format needs
model/KV-format, sequence, position, and rollback validation; the host
checkpoint chain needs atomic persistence and recovery before relying on
it across process restarts. The timings cover one worker and short recall
answers. Concurrent workers and longer answers remain separate tests.

Evidence: [parsed receipt](receipt.json), [return patch](return_delta.patch),
[build recipe](build.sh), [two-turn campaign](../../../../campaigns/qwen35_return_delta_20261109.json),
[20-turn campaign](../../../../campaigns/qwen35_return_compact20_20261109.json),
and [20-turn compaction patch](../qwen35-return-compact20-20261109/compact20.patch).
Raw logs and GPU samples are under
`/mnt/shared/experiments/kv-matrix-20261107/qwen35_return_*_20261109*`.
