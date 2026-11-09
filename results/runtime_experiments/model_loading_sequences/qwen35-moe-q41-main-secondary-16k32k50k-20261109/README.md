# Qwen3.6 35B-A3B Q4_1 main and secondary chats on separate 1060s (2026-11-09)

Run `qwen35-moe-q41-main-secondary-16k32k50k-20261109` passed. One Q4_K_XL model load stayed on RTX 3090 Ti GPU0. The main chat restored independent `q4_1` K/V state on GTX 1060 GPU1, and the secondary chat restored its own state on GTX 1060 GPU2. Both caches reserved 262,144 tokens. At each occupied depth, the runner measured 64 tokens from the main chat alone, restored its starting state, then measured 64 tokens from both chats simultaneously. The source checkpoints came from [passed two-chat Q4_1 preparation](../qwen35-moe-kv-variant-prep-20261109/README.md), where both chats passed private-code recall at each depth.

| Occupied depth | Main alone tok/s | Main with secondary tok/s | Secondary tok/s |
| ---: | ---: | ---: | ---: |
| 16,384 | 50.07 | 53.52 | 52.10 |
| 32,768 | 34.71 | 34.23 | 33.42 |
| 50,000 | 24.10 | 23.46 | 23.30 |

Two active chats stayed close to the main-alone rate at each depth. The 16K simultaneous rate exceeded the solo rate in this short window; treat that as run variation, not a concurrency speedup. These are two independent KV contexts with the same model intelligence and quantization, but the names "main" and "secondary" do not give either chat priority. The replay resets both contexts at each depth; it does not yet measure alternating full conversation turns or five-worker scaling.

The prior Q4_1 preparation built each new history on GPU0 before handing it to a worker. Its incremental usable setup time for main/secondary was 14.08/13.91 s at 16K, 15.26/16.71 s at 32K, and 17.37/24.97 s at 50K. The GPU0 capture plus 1060 restore part was only 0.39/0.39, 0.70/0.72, and 1.05/1.06 s respectively. Thus smaller KV state helps transfer and memory capacity, but total prefill/setup is dominated by GPU0 preparation and can vary across chats. This replay read checkpoints from disk before restoring them (about 5-13 s per file); that disk-read time is a separate cold/warm storage effect, not GPU0 prefill or GPU-to-GPU transfer.

Evidence: `terminal.json` and stage receipt in this directory; manifest `campaigns/qwen35_moe_q41_main_secondary_16k32k50k_20261109.json`; raw log and GPU/PCIe samples under `/mnt/shared/experiments/kv-matrix-20261107/qwen35_moe_q41_main_secondary_16k32k50k_20261109.*`.
