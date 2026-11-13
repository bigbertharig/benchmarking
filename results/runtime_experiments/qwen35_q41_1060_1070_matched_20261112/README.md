# Matched 35B MoE 3090 + 1060 vs 3090 + 1070 chat placement (2026-11-12)

Qwen3.6-35B-A3B Q4_K_XL stayed on GPU0 (3090 Ti; 20,764.8 MiB CUDA model buffer). This repeats the November 9 [Q4_1 replay](../model_loading_sequences/qwen35-moe-q41-main-secondary-16k32k50k-20261109/README.md) with the same b11669 build, saved worker1/worker2 states, 262,144-token capacity per chat, Q4_1 K/V, occupied depths, and 64 generated tokens per window. GPU1 is a GTX 1060 6GB; GPU2 is a GTX 1070 8GB. The main chat used GPU1, GPU2, then GPU1 in A/B/A order; the other card held the secondary chat. Each depth ran main solo, reset its state, then ran both chats concurrently. All three stages passed.

| Occupied depth | 1060 before solo tok/s | 1070 solo tok/s | 1060 after solo tok/s | 1070 vs mean 1060 |
| ---: | ---: | ---: | ---: | ---: |
| 16,384 | 46.21 | 50.54 | 47.94 | +7.4% |
| 32,768 | 33.95 | 34.90 | 33.85 | +2.9% |
| 50,000 | 24.09 | 24.53 | 23.99 | +2.0% |

The solo 1070 advantage is modest and shrinks as context grows. In simultaneous windows, the main chat measured 47.26/47.18/47.11 tok/s at 16K, 32.70/32.79/32.53 at 32K, and 23.62/23.76/23.53 at 50K (1060 before / 1070 / 1060 after). The secondary chat was also within about 1 tok/s across assignments. Changing which Pascal card holds the main KV barely changes two-chat decode here. This is a 64-token replay, not a long-turn or prefill comparison; both cards have an allocated context even during main solo. The earlier direct [27B model-weight split](../qwen27_1070_split_20261112_uuid_long/README.md) favored the 1070 by about 21% in decode; its placement differs from this KV-only comparison.

The logs show main single=2 in the 1070 stage and single=1 in both controls, with the same saved worker1 snapshot hash. The model buffer stayed on CUDA0. The result suggests the long-context path has a substantial shared 3090 and/or similar Pascal attention cost; a kernel/transfer trace is needed to assign the limiting cost. A/B/A controls for large warm-up drift, but there is one 64-token sample per depth per stage.

[Manifest](../../../campaigns/qwen35_q41_1060_1070_matched_20261112.json), [metrics](metrics.json), and [sequence receipt](../model_loading_sequences/qwen35-q41-1060-1070-matched-20261112/terminal.json). Raw logs and GPU/PCIe samples are under /mnt/shared/experiments/kv-matrix-20261107/qwen35_q41_1060_1070_matched_20261112_*.
