# Qwen 35B long-context KV decode: GTX 1060 versus GTX 1070

Run date: 2026-11-12 (Denver). The four-stage campaign completed at 2026-11-13T02:53:41Z; the second-1060 cross-check completed at 03:01:26Z. All measured stages exited 0.

## Setup and identity

- Qwen3.6 35B A3B Q4_K_XL weights were loaded on the RTX 3090 Ti. Each worker held an independent Q4_1 KV cache on a Pascal card. This measures **worker decode with the 3090 holding the model**, not a simultaneous 3090 chat.
- Restored the same validated worker histories at 16,384, 32,768, and 50,000 tokens. Generated 256 tokens per chat for solo and simultaneous two-chat phases. The 1060 pair ran before and after the mixed pair.
- Hardware roles were resolved once from the session scan. Docker device selection used UUIDs; host-to-CUDA ordinals were checked against PCI bus IDs. In the `mixed_1070_first` receipt, host GPU 2 / bus `0D:00.0` is CUDA 1 (GTX 1070), and host GPU 1 / bus `03:00.0` is CUDA 2 (GTX 1060). The cross-check used host GPU 3 / bus `10:00.0` as the 1060.
- The live shared-KV service that was running before this campaign had a host/CUDA ordinal mismatch: its purported 1070 worker was actually allocated on a 1060. It was stopped before these tests. Do not use that service's previous labels as 1070 evidence.

## Results

Tokens per second per chat, rounded to one decimal. The two-1060 control is the average of its before and after runs. `solo` is the first card decoding alone; `pair` is simultaneous decode. The mixed pair was tested in both card orders.

| Context | 1060 solo | 1070 solo | 1070 solo gain | Two 1060s, each in pair | 1070 + 1060, pair total | Two 1060s, pair total |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 16K | 56.6 | 65.0 | +14.8% | 56.5 / 56.4 | 100.8–101.8 | 111.6–113.9 |
| 32K | 41.0 | 49.5 | +20.7% | 41.1 / 41.0 | 74.0–74.2 | 82.0–82.1 |
| 50K | 31.5 | 39.2 | +24.4% | 31.2 / 31.2 | 58.3–58.5 | 62.3–62.3 |

The second-1060 cross-check kept the 1070 first and substituted host GPU 3 for host GPU 1. Its mixed-pair totals were 101.3, 74.2, and 59.0 tokens/s at 16K, 32K, and 50K, respectively. This closely matches the first mixed pair. At 50K, its 1070 chat produced 32.2 tokens/s while its 1060 chat produced 29.5 tokens/s.

The 1070's solo advantage is clear but smaller than the hypothesized ~40%, and it increases with context length. In simultaneous worker decode, both cards slow: the 1070 ran about 51/38/31–32 tokens/s, and the 1060 about 50/37/29–30 at 16K/32K/50K. Mixed-pair aggregate throughput was about 10%, 10%, and 6% below the two-1060 control. Swapping chat order and swapping the 1060 card did not remove the effect.

These data do **not** establish that PCIe x1 alone equalizes the cards. Prior solo tracing showed nearly identical pinned host-to-device bandwidth (~0.400 GB/s) while 1070 attention and dequant kernels were faster; the earlier 27B dense weight-split test also favored the 1070. A shared transfer, synchronization, scheduling, or topology limit in concurrent KV decode remains plausible. PCIe counters and an interleaved per-token CPU/GPU trace would separate those mechanisms better than more aggregate tokens/s runs.

## Reproduction and receipts

- Campaigns: `campaigns/qwen35_1060_1070_longdecode_20261112.json` and `campaigns/qwen35_1070_other1060_20261112.json`. They use schema 2 hardware roles and the session scan rather than fixed GPU indices.
- Run receipts: `results/runtime_experiments/model_loading_sequences/qwen35-1060-1070-longdecode-20261112/` and `.../qwen35-1070-other1060-20261112/`. Each contains `session_hardware.json`, stage receipts, comparison, and terminal status.
- Raw logs and telemetry: `/mnt/shared/experiments/kv-matrix-20261107/qwen35_1060_1070_longdecode_20261112_*.{log,cuda_map.json,gpu.csv,gpu_detail.csv,pcie.txt,exit}` on the rig (shared from the Pi under `/home/bryan/llm_orchestration/shared/experiments/`). `GEN_METRIC` and `GEN_AGGREGATE` are the result lines.
- The cross-check's first start failed before measuring because the completed four-stage campaign still held its persistent session claim. That claim was manually released and `rigctl recover` resumed the same run ID; its second attempt passed. The runner now releases an automatically created claim at the end of an all-release campaign.

## Next measurement

The current `moe_two_replay` mode does not include a 3090 chat. A three-chat replay should restore a third validated history on CUDA 0, then compare 3090 + two 1060s with 3090 + 1060 + 1070 at the same depths. Use UUID mapping and verify VRAM on all three cards. The existing six-chat replay is a useful high-concurrency reference, but it is not a substitute for this three-chat measurement. An instrumented mixed-pair run should then time PCIe transfers, GPU kernels, and host scheduling per token to locate the shared limit.
