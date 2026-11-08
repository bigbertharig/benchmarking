# Qwen27 ongoing-turn GPU1 → GPU0 → GPU1 handoff

2026-11-08. [Campaign](../../../../campaigns/qwen27_ongoing_turn_handoff_20261108.json); [terminal receipt](terminal.json). Manager run `qwen27-ongoing-turn-handoff-20261108` passed in one attempt, 23:43:53–23:46:13 UTC. Raw log: `/mnt/shared/experiments/kv-matrix-20261107/qwen27_ongoing_turn_handoff_20261108.log`. The ordinary `chat-27b` route was restored at 23:46:31 UTC.

## Question and method

Does preparing *each new turn* on GPU0 and returning an updated live chat state to GPU1 beat ingesting that turn directly on GPU1, after counting both directions of state transfer?

The same Qwen3.6 27B Q4 weights loaded once on GPU0. A 4K occupied seed chat was built on GPU0, answered its private-code question correctly, and was copied into two separate GPU1 contexts with 32K caps. The direct branch appended each new user message and about 4K synthetic note tokens on GPU1. The round-trip branch saved its live GPU1 state, restored it into a reusable GPU0 preparation context, appended the same message and notes there, saved the updated state, restored it on GPU1, and answered there. The branches alternated execution order across three turns. Each answer recalled the same private code correctly. Timings include state save/restore, new-turn prefill, and the answer prompt; context creation and the common seed are outside per-turn timings.

## Results

| Occupied target | Direct GPU1 complete turn | GPU0 round trip complete turn | Speedup |
| ---: | ---: | ---: | ---: |
| 8,192 | 30.614 s | 6.871 s | 4.46× |
| 12,288 | 34.596 s | 7.518 s | 4.60× |
| 16,384 | 38.608 s | 8.193 s | 4.71× |

All six GPU1 answers and the seed answer passed private-code recall. The two branches ended at the same 16,420 occupied positions. The full round-trip state grew from 233 MB before the first turn to 384 MB before the third; the resulting state after the third turn was 459 MB. Four save/restore calls per round trip took approximately 0.89, 1.35, and 1.79 seconds combined at the three depths. The GPU0 preparation work remained faster enough to win after those copies. Answer time on GPU1 was similar between branches, roughly 0.49–0.63 seconds, so the gain is in new-turn admission, not 1060 generation.

This verifies repeated live-state migration for this private llama.cpp 27B path, over three synthetic 4K additions and short recall answers. It does not establish a long natural conversation, many concurrent workers, main-chat responsiveness during GPU0 preparation, deeper transfer break-even, or Nemotron recurrent-state compatibility. The state moved through host memory. Each GPU1 generation step still uses the model on GPU0, so round-trip prefill does not remove model-to-chat communication during generation. A larger, varied-message test should measure transfer bytes and main-chat latency alongside per-chat speed.
