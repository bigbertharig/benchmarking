# Five F16 1060 chats: 16K–100K decode and 150K preparation boundary (2026-11-09)

Qwen3.6-35B-A3B Q4_K_XL weights stayed on the RTX 3090 (GPU0), with no
resident GPU0 main chat. Five independent F16 K/V chats stayed on GTX 1060
GPUs1–5; each reserved 262,144 positions. Chats grew additively through
16K, 32K, 50K, and 100K occupied context. All five passed private-code
recall at each completed depth. Worker1 generated 1,000 tokens solo, was
restored to its saved state, and then all five generated 1,000 tokens
concurrently. These forced windows measure sustained decode, not natural
answer quality or complete conversation-turn latency.

| Occupied context | Solo worker1 tok/s | Five concurrent, per-chat tok/s |
| ---: | ---: | ---: |
| 16,384 | 76.54 | 39.55–40.46 |
| 32,768 | 60.00 | 36.13–36.76 |
| 50,000 | 49.61 | 34.66–35.22 |
| 100,000 | 33.01 | 26.94–27.49 |

The first launch failed because the new mode lacked a state-directory setup
step in the shell wrapper; that was fixed. The retry completed through 100K.
At 150K, temporary F16 preparation KV on GPU0 failed a 3,040 MiB CUDA
allocation, despite the absence of a GPU0 main chat. The run resumed from
five saved 100K checkpoints with temporary F16 KV in RAM, while model
computation stayed on GPU0 and worker KV remained F16 on the 1060s.

Four chats finished the 100K → 150K RAM-backed preparation step before the
user canceled the run. Each took 593.2–593.9 seconds to become usable;
GPU0-to-1060 handoff itself took 9.39–9.41 seconds. Total time including
post-preparation bookkeeping was 633.1–633.8 seconds per chat. Preparation
was sequential. The fifth chat had not finished; **there is no valid 150K
or 200K five-chat decode measurement**. The campaign runner recorded exit
137 after its container was stopped intentionally. Completed 16K–100K
measurements and checkpoints were preserved.

Sampled peak memory during GPU preparation (MiB): {'0': 23851, '1': 5201, '2': 5201, '3': 5201, '4': 5201, '5': 5201}.
During RAM preparation: {'0': 22127, '1': 5201, '2': 5201, '3': 5201, '4': 5201, '5': 5197}.
One-second samples may miss short peaks. F16 workers occupied about 5.2 GiB
of each 6 GiB 1060. Preparation/admission and decode are separate costs;
the 1,000-token rates above exclude preparation and checkpoint I/O.

Next: compare compact Q4_1 preparation KV on GPU0 with RAM preparation,
keeping F16 worker KV fixed, and trace solo versus five-chat decode
contention. See the [project test menu](../../../../MODEL_LOADING_AND_CHAT_PLACEMENT.md).

Evidence: [summary receipt](receipt.json),
[original campaign](../../../../campaigns/qwen35_moe_f16_five_16k200k_long_decode_20261109.json),
[RAM-preparation resume campaign](../../../../campaigns/qwen35_moe_f16_five_ram_prep_resume_20261109.json),
[GPU-preparation terminal](../qwen35-f16-five-long-retry-20261109/terminal.json),
[canceled-run terminal](../qwen35-f16-five-ram-prep-20261109/terminal.json),
[six-depth build](build.sh), and [RAM-preparation build](build-cpuprep.sh).
Raw logs, GPU samples, and saved states are under
`/mnt/shared/experiments/kv-matrix-20261107/` with prefix
`qwen35_moe_f16_five_16k200k_long_decode_20261109`.
