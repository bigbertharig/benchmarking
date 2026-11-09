# Qwen27 main chat on GPU0 with five active 1060 agents

Run `qwen27-main-gpu0-five-agents-20261109` passed. The Qwen3.6 27B Q4 model stayed on GPU0. A main chat used GPU0 Q4 KV, and five independently restored agent states used Q4 KV on GPUs1–5, one per 1060. Each chat had a 262K context cap. At each depth, the same main checkpoint was replayed for 64 generated tokens alone and with five 64-token agents. Agent1 and the main used cloned worker1 state; the other four agents used distinct states. This is a compute contention probe, not a natural conversation.

| Occupied depth | Main alone tok/s | Main with five tok/s | Five agents, per-chat tok/s |
| ---: | ---: | ---: | ---: |
| 50K | 32.36 | 24.93 | 4.84–4.92 |
| 100K | 26.87 | 20.63 | 2.85–2.96 |
| 150K | 22.92 | 19.41 | 2.00–2.06 |
| 200K | 19.86 | 17.28 | 1.53–1.62 |

All measurements are generated-token wall time, including the first token. The main finishes after roughly 2.6–3.7 seconds; agents continue for 13–42 seconds. Therefore this run measures startup overlap and cannot establish the effect of a continuously busy main on agent throughput. The matched `main_gpu0_sustained_five` follow-up generates 512 main tokens and 64 agent tokens, with a five-agent-only control from the same states.

The main was 13–23% slower during six-way startup than alone. Longer occupied context produced the much larger slowdown for the 1060 chats. The 30 tok/s per-chat target for five simultaneous long-context 1060 chats is far above these observed rates. Measure the sustained overlap and phase-level attention/transfer costs before attributing the loss to the PCIe link or 3090 contention alone.

Sources: `campaigns/qwen27_main_gpu0_five_agents_20261109.json`, `main_gpu0_five_agents.json`, `terminal.json`, and the raw log at `/mnt/shared/experiments/kv-matrix-20261107/qwen27_main_gpu0_five_agents_20261109.log`.
