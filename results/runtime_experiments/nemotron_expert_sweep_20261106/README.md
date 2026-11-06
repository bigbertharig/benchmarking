# Nemotron 3.5 Bolt 32K expert placement sweep — 2026-11-06

The same installed NVIDIA-Nemotron-3.5-Bolt-74B-A9B-UD-Q3_K_XL.gguf was used in every row with llama-runtime:b11669, context 32,768, batch 64, one slot, reasoning off, temperature 0, seed 42, and cache_prompt false. The fixed-length timing probe used ignore_eos true and generated 1,024 tokens after 2,417- and 28,767-token prompts. The practical LRU-cache prompt used normal chat completion. No timing request was truncated.

The GGUF header contains 88 layers, 40 routed-expert layers, about 29.86 GiB of up/down expert weights, and about 6.48 GiB of other weights. The experimental launcher assigns contiguous expert-layer groups measured from GGUF tensor byte counts. Four used 1060s held about 3.8–4.1 GiB expert weights each; five held a fifth 4.1 GiB group. Attention, state-space, shared experts, and KV remained on the 3090. The fifth 1060 was free in the four-1060 layout.

| Layout | GPUs used | 2.4K wall s | 28.8K prefill tok/s | 28.8K decode tok/s | 28.8K wall s | Practical wall s |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Published layer split | 3090 + five 1060s | 64.2 | 214.8 | 17.0 | 194.2 | 39.1 |
| Published layer split | 3090 + four 1060s | 58.0 | 246.3 | 19.0 | 170.8 | 35.7 |
| Expert tensor split | 3090 + five 1060s | 39.9 | 180.2 | 37.7 | 186.9 | 19.9 |
| Expert tensor split | 3090 + four 1060s | 34.9 | 215.3 | 42.4 | 157.8 | 17.2 |
| Expert tensor split, fresh repeat | 3090 + four 1060s | 34.3 | 214.2 | 42.4 | 158.5 | 17.4 |

The four-1060 expert placement is best in this sweep. Compared with the standard placement on the same five GPUs, it raised long-prompt decode 2.24x, reduced the full 28.8K/1,024-token request by 7.6%, and roughly halved the practical response time. A fresh load repeated the long-prompt decode at 42.38 versus 42.43 tokens/s and wall time at 158.5 versus 157.8 seconds. The load used 21,243 MiB on the 3090 and 3,978–4,296 MiB on each participating 1060, leaving more than 1.8 GiB per 1060 and about 3.3 GiB on the 3090.

This is whole expert-tensor placement by layer, not m10dis-style within-expert sharding. It uses existing llama override-tensor support and the normal orchestration runtime lifecycle. It is not yet a gateway or manager recipe. The practical outputs were statically parsed: all contained syntactically valid Python with LRUCache and three named test methods. Generated code was not executed in this pass, so this is not a correctness score. The automatic approval review rejected an attempted execution of unreviewed model-generated code because it could have arbitrary local side effects; a separately approved sandbox would be needed for that check. Full quality suites, concurrent requests, and longer contexts remain open.
