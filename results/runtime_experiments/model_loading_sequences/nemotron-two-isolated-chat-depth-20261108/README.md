# Nemotron: two isolated 1060 chats beyond 8K

2026-11-08. [Campaign](../../../../campaigns/nemotron_two_isolated_chat_depth_20261108.json); [terminal receipt](terminal.json). The run passed in one attempt (23:19:29–23:34:27 UTC). Raw log: `/mnt/shared/experiments/kv-matrix-20261107/nemotron_two_isolated_chat_depth_20261108.log`.

## Question and layout

Can one Nemotron 3.5 Bolt 74B UD-Q3_K_XL weight load on GPU0–3 serve two independent, larger-than-8K chats, with no model weights on GPU4 or GPU5? How does per-chat decode change as both histories grow?

The private b11669 llama.cpp fork used the established four-device layer split `56,16,9,8`. It opened a Japan-prompt chat on GPU4 and a Germany-prompt chat on GPU5. Both contexts reserved 262,144 positions, the GGUF's native context limit, and Q4 KV. Their first tokens were `Tokyo` and `Berlin`. Each GPU4/GPU5 KV buffer was 576 MiB; each chat also allocated 107.05 MiB recurrent state on GPU0. The harness filled repeated synthetic tokens sequentially on each card and timed 64 concurrent generation steps per chat after both reached each depth.

## Results

| Occupied depth before timing | GPU4 main chat | GPU5 worker chat | Notes |
| --- | ---: | ---: | --- |
| 8,192 | 12.56 tok/s | 12.57 tok/s | Both filled in about 79 s each |
| 16,384 | 12.08 tok/s | 12.10 tok/s | Added history took about 85 s on each card |
| 32,768 | 11.01 tok/s | 11.02 tok/s | Added 16K history took 191.0 and 189.8 s |

Two 262K-capacity contexts were admitted, and both were filled and decoded at 32,768 occupied positions. Per-chat decode decreased gradually across the three depths, with only about a 12% reduction from 8K to 32K in this short window. Sequential direct-on-1060 fill cost about 79 + 85 + 190 seconds per chat through 32K, excluding model load and 64-token decode windows. GPU0, GPU1–3, GPU4, and GPU5 held distinct model, weight, and chat allocations; the ordinary `chat-27b` route was restored after the run.

This does not establish 262K *occupied* history, long-context retrieval, realistic multi-turn conversation, or a 3090-prefill handoff for Nemotron. It is 64-token synthetic continuation after repeated-token fill. The layer split is the known two-dedicated-chat-card tradeoff. The faster whole-expert placement uses GPU4 for model weights, so the earlier 13.6 versus 33.6 tok/s short-history comparison changes placement as well as card count; it cannot isolate the effect of adding one model card.
