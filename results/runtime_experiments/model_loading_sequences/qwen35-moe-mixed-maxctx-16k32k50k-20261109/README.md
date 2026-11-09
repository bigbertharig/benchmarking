# Qwen3.6 35B-A3B mixed chat placement, full 262K reservations (2026-11-09)

Manager run `qwen35-moe-mixed-maxctx-16k32k50k-20261109` passed all three stages. One Qwen3.6 35B-A3B Q4_K_XL model load per stage placed all weights on RTX 3090 Ti GPU0. Two independent Q4 KV contexts each reserved **262,144 tokens**, while saved occupied histories were 16,384, 32,768, or 50,000 tokens. The same validated checkpoints were replayed in an A/B/A order: both chats on GTX 1060 GPUs1/2, main chat on GPU0 with worker on GPU1, then both chats on GPUs1/2 again. Each stage measured a 64-token solo main window and a 64-token simultaneous window per chat. The checkpoints came from the successful [six-depth two-chat curve](../qwen35-moe-two-curve-20261109/README.md), where both private-code recalls passed at these depths.

| Occupied depth | Both on 1060s: main / worker tok/s, before | Mixed GPU0/1060: main / worker tok/s | Both on 1060s: main / worker tok/s, after |
| ---: | ---: | ---: | ---: |
| 16,384 | 38.44 / 37.77 | **118.42 / 36.63** | 38.25 / 37.59 |
| 32,768 | 23.64 / 23.45 | **110.92 / 23.51** | 23.52 / 23.34 |
| 50,000 | 17.00 / 16.90 | **101.49 / 16.99** | 16.94 / 16.83 |

The GPU0 main chat was 3.1x/4.7x/6.0x as fast as its 1060 baseline at 16K/32K/50K. The 1060 worker stayed within the baseline-repeat range except for a roughly 3% dip at 16K. This proves a fast main chat and a 1060 worker can run concurrently with both chats reserving the full context. It does not establish long-history speed or five-worker scaling for this mixed layout. A fast main chat finishes its 64 tokens before the worker; the worker timing includes its remaining worker-only period, so longer continuous main turns could interfere differently.

The 1-second GPU samples recorded peak mixed-stage GPU0/1 memory of 23,209/2,037 MiB. The earlier [65K-reservation control](../qwen35-moe-mixed-16k32k50k-20261109/README.md) peaked at 21,743/569 MiB with nearly the same decode speeds. Thus the extra reserved capacity cost about 1.47 GiB on each chat card without a meaningful short-depth decode cost in this test. GPU0 still had about 1.35 GiB physical headroom at the observed peak, but other compute or larger live states may consume it. The histories are synthetic and the windows short; these timings are decode rates, not complete conversation-turn latency.

Evidence: `terminal.json` and stage JSON in this directory; manifest `campaigns/qwen35_moe_mixed_maxctx_16k32k50k_20261109.json`; raw logs and GPU/PCIe samples under `/mnt/shared/experiments/kv-matrix-20261107/qwen35_moe_mixed_maxctx_16k32k50k_20261109_*`.
