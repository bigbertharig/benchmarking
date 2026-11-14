# Nemotron all-card 16K/32K depth (2026-11-14)

Matched continuation of [200K/250K](NEMOTRON_ALLCARD_200K250K_20261114.md). The same Nemotron-3.5-Bolt-74B-A9B UD-Q3_K_XL model ran on the six-card mixed rig: one 3090 Ti, four 1060 6GB cards, and one 1070 8GB. GPU order was 0-5, layer split 46,8,16,7,8,4, all 89 layers offloaded, 262,144 context capacity, 64 microbatch, 160 forced output tokens per probe, and prompt cache disabled. The exact receipt is [nemotron_allcard_16k32k_20261114.json](nemotron_allcard_16k32k_20261114.json). The run exited successfully; both planted-code recalls passed.

| Actual prompt depth | Prefill | Time to first token | Decode |
| ---: | ---: | ---: | ---: |
| 15,915 tokens | 179.16 tok/s | 88.8 s | 19.39 tok/s |
| 32,407 tokens | 188.65 tok/s | 171.8 s | 18.13 tok/s |
| 200,543 tokens (prior run) | 136.42 tok/s | 1,470.0 s | 10.04 tok/s |
| 249,889 tokens (prior run) | 124.14 tok/s | 2,013.0 s | 8.79 tok/s |

The short-prompt decode was 20.95 tok/s, compared with 20.82 tok/s in the prior deep run; load time was 193.8 s versus 200.0 s. At about 16K and 32K, decode is 2.21x and 2.06x the 250K result. The 16K-to-32K decline is 6.5%.

These all-card measurements are different from the earlier dedicated-worker-chat layout, where weights were on GPU0-4 and GPU5 held its own F16 KV/chat. That layout reached 38.05 tok/s at 16,384 and 34.40 tok/s at 32,768. The two layouts answer different questions: all-card weight-split speed versus a dedicated chat card with fewer cards carrying weights. All depths here use synthetic repeated-token history and planted-code recall, not realistic dialogue.
