# Qwen 35B: 3090 chat with 1060 and 1070 workers

Run date: 2026-11-13 (Denver). Both campaigns completed with exit 0. This follows the [two-worker long-decode study](../qwen35_1060_1070_longdecode_20261112/README.md).

## Method

The Qwen3.6 35B A3B Q4_K_XL weights stayed on the RTX 3090 Ti. Independent Q4_1 KV caches were restored from the same validated histories at 16,384, 32,768, and 50,000 tokens. Each chat generated 256 tokens. `moe_three_replay` measured the 3090 chat alone, restored its state, then ran it with two Pascal worker chats. The control used two 1060s before and after the 1070+1060 stage. A separate `moe_two_replay` campaign ran the 3090 chat with one 1060, then one 1070, then the 1060 again.

GPU selection used the session hardware scan and UUIDs; the replay wrapper mapped host GPU IDs to container CUDA ordinals by PCI bus. In the mixed three-chat stage, CUDA 0 was the 3090 Ti (host 0), CUDA 1 the 1070 (host 2), and CUDA 2 the 1060 (host 1). GPU memory samples showed active allocations on all three intended cards. The new replay binary was built separately from the validated Q4_1 tile libraries; the prior build was left intact. All stages within the three-chat comparison used the same new binary.

## Three simultaneous chats

Tokens/s per chat, rounded to one decimal. Control values average the before and after two-1060 runs. Aggregate completion throughput is total generated tokens divided by the time until the last chat finished; it is useful for comparing these identical windows, but is not the sum of per-chat rates.

| Context | 3090 with two 1060s | Two 1060 workers | 3090 with 1070+1060 | 1070 / 1060 workers | Aggregate control → mixed |
| --- | ---: | ---: | ---: | ---: | ---: |
| 16K | 85.0 | 48.1 / 48.1 | 84.1 | 46.7 / 45.7 | 144.3 → 137.2 (−4.9%) |
| 32K | 79.3 | 36.7 / 36.6 | 77.5 | 36.2 / 34.6 | 109.9 → 103.7 (−5.6%) |
| 50K | 70.8 | 28.9 / 28.9 | 69.9 | 29.5 / 27.5 | 86.6 → 82.5 (−4.8%) |

The 3090's solo chat was stable across stages at about 117, 102, and 87 tokens/s. Adding two worker chats reduced its own rate to roughly 85, 79, and 71 tokens/s in the control. Substituting the 1070 changed the 3090 rate by only about 1–2%; most of the mixed-pair loss was in the worker completion window.

## 3090 chat plus one worker

The 1060 figures average the before and after controls. The 1070 retained a clear advantage when it was the only Pascal worker.

| Context | 1060 worker | 1070 worker | 1070 gain | 3090 chat with 1060 / 1070 |
| --- | ---: | ---: | ---: | ---: |
| 16K | 52.2 | 57.6 | +10.3% | 101.5 / 100.5 |
| 32K | 37.8 | 44.7 | +18.3% | 89.9 / 87.5 |
| 50K | 29.9 | 35.9 | +19.9% | 78.2 / 76.6 |

The earlier worker-only solo test likewise favored the 1070 by 15–24%. These results rule out a simple claim that the x1 link makes both cards equally fast. The mixed two-worker combination is the relevant slowdown: it persisted with two different 1060 cards in the prior study, and the 3090 chat did not remove it here. Aggregate decode rates alone cannot distinguish shared PCIe traffic, host scheduling, synchronization, or another topology effect. A per-token mixed-pair trace that records host-to-device transfers and GPU kernel timings is the next useful diagnostic.

## Reproduction and receipts

- Campaigns: `campaigns/qwen35_1060_1070_threechat_20261113.json` and `campaigns/qwen35_main_oneworker_20261113.json`. Both use schema 2 hardware roles and the session scan.
- Replay source and isolated build recipe: `scripts/active/llama_simple_chat_latency.cpp` (`moe_three_replay`) and `scripts/integration/build_three_replay.sh`. The resulting binary was at `/data/bench-staging/kvchat-q41-three-build/bin/llama-simple` on the rig.
- Run receipts: `results/runtime_experiments/model_loading_sequences/qwen35-1060-1070-threechat-20261113/` and `.../qwen35-main-oneworker-20261113/`. Their terminal receipts show all stages passed and the automatic session claims were released.
- Raw logs and telemetry: `/mnt/shared/experiments/kv-matrix-20261107/qwen35_1060_1070_threechat_20261113_*` and `.../qwen35_main_oneworker_20261113_*` on the rig, also under `/home/bryan/llm_orchestration/shared/experiments/` on the Pi. `GEN_METRIC` and `GEN_AGGREGATE` lines contain the values above; `.cuda_map.json` and `.selected_uuids.txt` prove device placement.
