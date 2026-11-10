# Nemotron expert weights plus one dedicated 1060 chat (2026-11-09)

This experiment loads NVIDIA-Nemotron-3.5-Bolt-74B-A9B-UD-Q3_K_XL weights once on GPU0 (3090) and GPUs1-4 (four 1060s), using the [validated whole-expert tensor map](../kv_expert_chat_20261107/nemo_experts_1234.tsv). GPU5 (the fifth 1060) holds one independent chat. All 89 layers were offloaded to GPU, while the loader also reported a 544.00 MiB CPU-mapped model buffer. The GPU model buffer sizes reported in both runs were 20,558.75 MiB on GPU0 and 4,000.50/3,888.59/4,012.63/4,207.19 MiB on GPUs1-4. The experimental b11669 llama.cpp fork, model file, map, prompt, greedy sampler, and 128 timed output tokens were held fixed. The chat reserved 262,144 positions. The probe adds synthetic repeated-token history to 16K, 32K, and 50K occupied positions; it does not test realistic dialogue or retrieval.

The first Q4_0 run reached 41.9 tok/s at short history, then the *probe* sent a 512-token fill block to a context whose batch limit was 64. That assertion is a harness error. The corrected `r2` run uses 64-token fill blocks; only the corrected depth measurements are compared below. Its source is [nemo_single.cpp](nemo_single.cpp) and the launcher is [run_single.sh](run_single.sh). Compressed raw logs, GPU samples, and terminal start/finish/exit receipts are in this directory. Both corrected depth runs exited 0 and produced `Berlin` as the first answer token.

| Occupied history | Q4_0 KV, GPU5 | F16 KV, GPU5 | F16 gain |
| --- | ---: | ---: | ---: |
| Short (133 tokens) | 41.94 tok/s | 42.98 tok/s | 2.5% |
| 16,384 | 32.10 tok/s | 38.05 tok/s | 18.5% |
| 32,768 | 27.15 tok/s | 34.40 tok/s | 26.7% |
| 50,000 | 22.56 tok/s | 32.50 tok/s | 44.0% |

The F16 chat's 262K-capacity KV allocation was 2,048 MiB on GPU5, versus 576 MiB for Q4_0. Each chat also allocated 164.69 MiB recurrent state on GPU0. Sampled peak GPU5 usage was 2,133 MiB for F16 and 919 MiB for Q4_0; GPU0 peaked at 21,099 MiB during direct-fill runs. The larger F16 allocation fits comfortably on this otherwise chat-only 1060. The improvement grows with occupied depth, consistent with attention work costing more, but these runs alone do not isolate a particular kernel or bus component.

## 3090 preparation and GPU5 handoff

The [handoff launcher](run_prep.sh) used the same F16 context type and model placement, first filling a temporary chat on GPU0, then saving its llama state and restoring it into a fresh GPU5 context. This tests the hybrid model's recurrent state as well as KV transfer. Both runs exited 0, restored the expected occupied count, and kept GPU5 decode speed after transfer.

| Occupied history | Direct GPU5 F16 fill, cumulative | GPU0 F16 preparation, including save | State bytes | GPU5 restore | GPU5 decode after restore |
| --- | ---: | ---: | ---: | ---: | ---: |
| 16,384 | 115.36 s | 34.89 s | 307,102,914 | 0.38 s | 38.12 tok/s |
| 50,000 | 411.31 s | 107.40 s | 582,888,578 | 1.07 s | 32.22 tok/s |

The cumulative direct time sums the three F16 fill phases (115.36 + 136.92 + 159.02 seconds); the 50K preparation is a separate one-pass run, not an extension of the 16K handoff. Both exclude the common cold model load, context initialization, and output-generation window. The 3090 preparation itself used about 23,167 MiB peak sampled GPU0 memory, versus 21,099 MiB during direct fill. This leaves roughly 1.4 GiB below the 24,564 MiB nominal GPU0 total in this single-chat run. GPU0 preparation could delay another live chat; this experiment did not measure that interference. The handoff timings include the in-process state restore but not a durable disk write/read or a network transfer.

## Interpretation and next probes

F16 KV and 3090-side preparation both transfer to this larger hybrid MoE: the first improves *GPU5 decode*, and the second shortens *initial chat fill*. The 50K F16 path is about 32.5 tok/s when running alone on GPU5, with a roughly 108-second 3090 preparation-plus-restore if it starts at 50K. The earlier two-chat 32K layer-split result (about 11 tok/s per chat) is not a matched control: it uses only three weight 1060s and different weight placement.

Useful next measurements are a matched one-chat layer-split versus whole-expert comparison, a 1,000-token decode window, 100K occupied F16 depth, a realistic multi-turn chat with correctness checks, and GPU0 preparation while another chat is generating. The prior 128-thread F16 attention tile was tuned for Qwen3.6's head-256 shape; Nemotron's attention key length is 128, so that patch is not assumed to apply. These are experiment results, not a Manager loading profile.
