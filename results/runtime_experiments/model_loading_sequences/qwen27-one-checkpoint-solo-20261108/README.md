# Qwen27 true one-chat replay at four depths

2026-11-09. [Campaign](../../../../campaigns/qwen27_one_checkpoint_solo_20261108.json); [terminal receipt](terminal.json); [restoration receipt](restoration.json). Manager run `qwen27-one-checkpoint-solo-20261108` passed, 01:00:53–01:04:53 UTC. The ordinary chat route was restored by 01:05:39 UTC. Raw log: `/mnt/shared/experiments/kv-matrix-20261107/qwen27_one_checkpoint_solo_20261108.log`.

This replay complements the [five-chat depth run](../qwen27-five-ongoing-depths-20261108/README.md). It loaded the same Qwen3.6 27B Q4 weights on GPU0 and only one 262K-cap Q4 KV context on GPU1. GPUs2–5 had no chat contexts. For each 50K, 100K, 150K, and 200K depth, it restored the exact validated worker1 checkpoint from the five-chat run and measured three 16-token generation windows, restoring the same state before each repetition. No prompt preparation was repeated.

| Occupied depth | Solo repetitions, tok/s | Median, tok/s | Five-chat run with four idle chats, tok/s |
| ---: | ---: | ---: | ---: |
| 50,000 | 6.38, 6.74, 6.74 | 6.74 | 6.54 |
| 100,000 | 3.73, 3.75, 3.75 | 3.75 | 3.65 |
| 150,000 | 2.55, 2.57, 2.57 | 2.57 | 2.53 |
| 200,000 | 1.97, 1.98, 1.98 | 1.98 | 1.96 |

The parked-agent baseline is within about 1–3% of the one-context median at each depth. In this setup, the substantial change in per-chat speed comes when the other chats generate concurrently, not from their idle KV allocations on different 1060s. The windows are short and synthetic; the first 50K isolated repetition was slower than the two subsequent repetitions, consistent with a warmup effect. This run does not measure a main chat responding while GPU0 prepares a new worker turn.
