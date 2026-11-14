# Qwen3.8 Flash-Next Q4 Strata: fixed 50K, 12 versus 16 GiB (2026-11-14)

The same Unsloth UD-Q4_K_XL model and Strata pack were run on GPU0 with K8V4 KV, 256K reserved context, one 49,694-token prompt, 768 generated tokens, MTP off, and 12 or 16 GiB resident expert budget. Both Manager runs passed. The runs were separate loads, in 16 then 12 GiB order. Raw receipts are in [16 GiB](ram16_a/k8v4_ram16/terminal.json) and [12 GiB](ram12_a/k8v4_a/terminal.json).

| Metric | 12 GiB | 16 GiB |
| --- | ---: | ---: |
| Load time | 117.55 s | 136.34 s |
| Request wall time | 822.16 s | 765.07 s |
| Prompt prefill | 707.36 s, 70.3 tok/s | 653.54 s, 76.0 tok/s |
| 768-token decode | 114.75 s, 6.7 tok/s | 111.49 s, 6.9 tok/s |
| NVMe block reads during request | 350.53 GB | 323.38 GB |
| Host MemAvailable after load | 11.85 GiB | 7.79 GiB |

The 16 GiB request was 6.9% shorter and read 27.15 GB less from NVMe. This repeats the direction of the Nov 11 fixed-50K series (12 GiB: 824.8-833.3 s; 16 GiB: 783.3 s), while leaving less host memory. This is a throughput result for synthetic 50K input, not a 50K recall or quality test. Block counters are device totals; the rig had no other benchmark load. Both runs left a Strata service after completion; it was stopped before the next benchmark.
