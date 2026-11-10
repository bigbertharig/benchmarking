# Nemotron chat on 3090, experts on 1060s (2026-11-09)

Same Nemotron 3.5 Bolt 74B-A9B UD-Q3_K_XL GGUF, private b11669 runtime, F16 K/V, greedy sampling, 262,144 reserved context positions per chat, and 128 generated tokens per timed phase. Histories were filled with repeated synthetic tokens. All 89 layers were GPU offloaded; the loader also reported a 544 MiB CPU-mapped model buffer. The main prompt was the capital of Germany, and the worker prompt was the capital of Japan. Their first answers were Berlin and Tokyo.

The [five-card tensor map](nemo_experts_12345.tsv) adds six expert layers (50, 52, 54, 56, 59, 61) to GPU5, totaling 4,173.8 MiB, without changing the [four-card map](../kv_expert_chat_20261107/nemo_experts_1234.tsv) on GPUs1-4. The map was checked against the saved GGUF header inventory for overlapping tensor names and per-card bytes. The added single_local0_depth and dual_local0_worker5_depth modes are in the [probe source](../nemo_single_chat_20261109/nemo_single.cpp). [Build](build.sh) and [run](run_reversed.sh) scripts reproduce the five-card solo test; [four-card control](run_local4.sh), [dual build](build_dual.sh), and [dual run](run_dual.sh) scripts reproduce the others. All three runs exited 0. Compressed raw logs, 1 Hz GPU samples, and terminal receipts are stored here.

## Solo 3090 chat: four versus five expert 1060s

| Occupied history | Five expert cards | Four expert cards | Four-card gain |
| --- | ---: | ---: | ---: |
| Short (133 tokens) | 40.60 tok/s | 45.91 tok/s | 13.1% |
| 16,384 | 38.99 | 44.58 | 14.3% |
| 32,768 | 38.72 | 44.21 | 14.2% |
| 50,000 | 38.43 | 43.86 | 14.1% |

Peak sampled GPU0 memory fell from 23,153 MiB with four expert cards to 18,981 MiB with five; GPU5 used 4,255 MiB for the fifth expert group. The extra weight card freed GPU0 memory but slowed this single chat about 14% at all tested depths. The four-card fill phases to 16K/32K/50K took 84.09/84.64/89.19 seconds; the five-card phases took 100.79/101.81/107.26 seconds. One pass per layout supports the placement result, not a precise attribution to a specific kernel or bus transfer.

## Main chat on 3090 plus worker on GPU5

With the four-card expert map, one F16 chat ran on GPU0 and another on GPU5. Both reserved 262K positions and were filled sequentially to the same occupied depth before each concurrent timing window.

| Occupied history per chat | GPU0 main | GPU5 worker | Aggregate |
| --- | ---: | ---: | ---: |
| Short (133 tokens) | 35.85 tok/s | 33.54 tok/s | 67.08 tok/s |
| 16,384 | 34.92 | 30.88 | 61.77 |
| 32,768 | 34.66 | 29.02 | 58.03 |
| 50,000 | 33.93 | 27.61 | 55.21 |

At 50K, the main fell from 43.86 solo to 33.93 tok/s (22.6%) during concurrent generation. The worker fell from the prior 32.50 solo to 27.61 (15.0%); that earlier worker used the same model/map/context/KV but a different short capital prompt. Dual-run peak sampled memory was 23,373 MiB on GPU0 and 2,133 MiB on GPU5, leaving 1,191 MiB nominal GPU0 headroom. Both chats were admitted without reloading the weights. Direct sequential fill phases through 50K summed to about 258 seconds on GPU0 and 417 seconds on GPU5, excluding model load and timed generation windows.

This proves two F16 chats at 50K synthetic occupied history, not two 250K occupied chats or deep retrieval quality. The short generation windows do not establish realistic multi-turn speed. A [separate test](../nemo_single_chat_20261109/README.md) prepared and handed off one 250K GPU5 chat with no simultaneous GPU0 chat. Further tests should check deep retrieval, longer outputs, and whether GPU0 can prepare a worker while its own chat is resident.
