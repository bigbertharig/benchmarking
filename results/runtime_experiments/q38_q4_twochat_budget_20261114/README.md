# Qwen3.8 Flash-Next Q4 Strata: two 15K chats at 12 versus 16 GiB (2026-11-14)

The guarded [two-chat runner](../../../scripts/integration/run_strata_q4_multichat.py) loaded the same Unsloth UD-Q4_K_XL model and Strata pack on GPU0. Each run reserved two 32,768-token slots, used K8V4 KV and 1,000 filler lines (15,084 occupied prompt tokens) per chat, and disabled MTP and drafting. Chat A and B had distinct private codes, opened sequentially, and both passed recall after B was admitted. The runs used separate loads, first 16 GiB then 12 GiB resident expert budget, and both stopped Strata cleanly. Receipts: [16 GiB](ram16/terminal.json), [12 GiB](ram12/terminal.json).

| Metric | 12 GiB | 16 GiB |
| --- | ---: | ---: |
| Load time | 136.97 s | 138.55 s |
| A first 15K request | 241.05 s | 226.42 s |
| A first cached continuation | 16.05 s | 21.21 s |
| B first 15K request | 221.98 s | 214.97 s |
| A after B continuation | 4.74 s | 11.31 s |
| B after B continuation | 10.68 s | 16.21 s |
| Sum of five requests | 494.50 s | 490.12 s |
| Host MemAvailable after load | 11.87 GiB | 7.36 GiB |
| NVMe reads during A/B first admission | 101.68 / 94.46 GB | 93.55 / 90.22 GB |

The extra 4 GiB shortened the initial prompt requests and reduced NVMe reads, but did not materially shorten this five-request sequence. The short cached continuations are noisy: generated token counts and draft acceptance differed between runs. The earlier Nov 10 [8 GiB INT8 run](../model_loading_sequences/strata-q4-two-32k-16k-20261110/README.md) is a capacity reference, not a matched budget control because KV format changed. The model weights stayed on GPU0 and NVMe/RAM; worker GPUs were idle. These synthetic prompts check admission and code isolation, not realistic long chat quality or steady concurrent decode.
