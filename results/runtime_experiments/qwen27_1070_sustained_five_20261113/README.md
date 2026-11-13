# Qwen27 six chats: one 1070 and four 1060 workers (2026-11-13)

The Qwen3.6 27B Q4_K_M weights stayed on the RTX 3090 Ti. One main chat used its KV cache on the 3090, one agent used the GTX 1070, and four agents used the GTX 1060s. This repeats the saved-state, sustained-overlap method of [the November 9 all-1060 run](../model_loading_sequences/qwen27-main-gpu0-sustained-five-20261109/README.md): 262,144-token Q4 KV capacity per chat, 50K/100K/150K/200K occupied contexts, 512 generated main tokens, and 64 generated tokens per worker. The same five validated worker snapshots were used; agent1 is on the 1070. Each depth ran five workers alone, the main chat alone, and then all six together. The benchmark completed all four depths with exit 0, and the session claim was released.

The campaign used schema 2 hardware roles and the session scan. Host GPU2 was the 1070 (UUID `GPU-cc6bc379-2f59-ec6e-00cf-4a9f02d57519`), mapped by PCI bus to CUDA1 inside the selected-device container; host GPU0/3090 mapped to CUDA0. The other four agents mapped to physical 1060s. The model load used CUDA0. The replay was compiled against the original b11669 source/runtime libraries into an isolated six-chat build so the validated old build remained intact.

## All six chats generating

Tokens/s are per-chat wall-time rates, including first token. The 1060 column gives the mean and range across the four cards. The historic all-1060 column is the mean of its five workers at the same occupied depth.

| Context | 3090 main | 1070 worker | Four 1060 workers, mean (range) | 1070 gain over current 1060 mean | Historic five-1060 mean |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 50K | 23.85 | 2.95 | 2.90 (2.83–2.96) | +2.0% | 2.91 |
| 100K | 20.82 | 2.39 | 2.20 (2.18–2.21) | +8.4% | 2.22 |
| 150K | 18.94 | 1.81 | 1.70 (1.69–1.72) | +6.1% | 1.69 |
| 200K | 16.67 | 1.47 | 1.38 (1.36–1.39) | +6.6% | 1.36 |

The main chat in the old all-1060 run measured 23.71, 21.30, 19.07, and 16.92 tok/s at those depths. Its current rates differ by less than 3%. The current 1060 workers also match the earlier run closely, supporting the historical comparison. Across the four occupied depths, replacing one 1060 with a 1070 did not produce a 20–40% gain under six-chat load. The 1070's lead is small but repeatable at 100K–200K. At 50K its rate falls inside the current 1060 range.

## Five workers without the main chat

| Context | 1070 worker | Four 1060 workers, mean (range) | 1070 gain |
| ---: | ---: | ---: | ---: |
| 50K | 5.48 | 5.15 (5.09–5.24) | +6.4% |
| 100K | 3.25 | 3.01 (2.97–3.04) | +7.9% |
| 150K | 2.24 | 2.09 (2.04–2.13) | +7.4% |
| 200K | 1.70 | 1.61 (1.59–1.64) | +5.8% |

The 1070 advantage persists without a 3090 main chat, while all five agents still share one 3090 weight load. This test does not isolate PCIe transfers, host scheduling, or 3090 model execution as the limiting cost. The main generates 512 tokens and each worker 64; at deeper contexts the main can finish before the slowest worker, so worker wall-time rates are partly overlapped. One run per configuration was made, and the old control used a separately compiled replay executable against the same b11669 runtime family.

## Reproduction and evidence

- Campaign: `campaigns/qwen27_1070_sustained_five_20261113.json`; replay mode `main_gpu0_sustained_five` in `scripts/active/llama_simple_chat_latency.cpp`; isolated build recipe `scripts/integration/build_six_chat_replay.sh`.
- Sequence receipts: `results/runtime_experiments/model_loading_sequences/qwen27-1070-sustained-five-20261113/`, including `terminal.json` (passed), `session_hardware.json`, and the stage receipt.
- Derived per-depth metrics: `metrics.csv` beside this README. Raw metrics and placement: `/mnt/shared/experiments/kv-matrix-20261107/qwen27_1070_sustained_five_20261113.log`, `.cuda_map.json`, `.selected_uuids.txt`, and GPU/PCIe telemetry on the rig, shared to the Pi under `/home/bryan/llm_orchestration/shared/experiments/`.
