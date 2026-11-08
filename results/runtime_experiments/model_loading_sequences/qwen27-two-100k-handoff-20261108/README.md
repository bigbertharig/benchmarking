# Qwen3.6 27B, prepare two 100K chats on GPU0 and hand off to GPU1

Manager run: `qwen27-two-100k-handoff-20261108`, finished 2026-11-08T22:15:33Z with exit 0. The normal `chat-27b` route was restored on GPU0 at 22:15:49Z.

The same Qwen3.6 27B Q4 weights loaded once on GPU0. Each of two different chats used a 114,688-token configured context and reached 102,423 occupied positions on GPU0. The harness saved each live state to host memory, freed its temporary GPU0 context, created an independent GPU1 context, and restored the state. Chat A remained resident on GPU1 while chat B was prepared on GPU0. After transfer, the harness timed 16 clean generation steps for A alone, then 16 for both concurrently, and checked separate private-code recall. No old snapshot was reused; preparation and restore used the same b11669 private runtime build.

| Measure | Chat A | Chat B |
| --- | ---: | ---: |
| GPU0 preparation to 102,423 occupied positions | 180.665 s | 180.834 s |
| Save 2,047,213,666-byte state to host memory | 1.019 s | 1.019 s |
| Restore state on GPU1 | 4.789 s | 4.814 s |
| Solo GPU1 generation, 16 tokens | 3.662 tok/s | not measured |
| Concurrent GPU1 generation, 16 tokens each | 1.455 tok/s | 1.455 tok/s |
| Private-code recall after generation | passed | passed |

The matched direct-GPU1 preparation run took about half an hour per 100K chat and measured 3.62 tok/s solo and 1.53 tok/s per chat concurrently. GPU0 preparation plus state handoff cut chat setup from roughly half an hour to about three minutes per chat in these exploratory runs. It did not improve deep GPU1 generation: per-chat rates stayed near the direct-preparation result. The 16-token generation windows are short, and synthetic repeated notes do not establish natural-conversation quality.

This supports a conditional preparation rule: build reusable state on the fastest suitable device, then transfer it to its residency tier when preparation plus transfer beats preparation there. Time the destination's generation separately before choosing a serving layout. Next candidates include prepared prompt prefixes, compatible packed weights, expert tensors, and sparse-attention hot blocks; each needs its own transfer and correctness test.

The terminal and stage receipts are in this directory. Raw log, start/finish/exit markers, GPU samples, and PCIe samples are under `/mnt/shared/experiments/kv-matrix-20261107/` with the `qwen27_two_100k_handoff_20261108` prefix. The [source mode](../../../../scripts/active/llama_simple_chat_latency.cpp) is `two_100k_handoff_one_1060`, launched by the [campaign manifest](../../../../campaigns/qwen27_two_100k_handoff_20261108.json).
