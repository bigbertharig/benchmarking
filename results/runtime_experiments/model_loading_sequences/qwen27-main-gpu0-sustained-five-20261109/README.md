# Qwen27 five 1060 agents with sustained 3090 main chat

Run `qwen27-main-gpu0-sustained-five-20261109` compares five independent Qwen3.6 27B Q4 chats at 50K/100K/150K/200K occupied context, with model weights on GPU0 and one Q4 KV chat on each GTX 1060. Every worker has the same validated checkpoint in both conditions and generates 64 tokens. In the mixed condition a cloned main state on GPU0 generates 512 tokens. The five-only condition has no main context allocated. The model is loaded once.

| Occupied depth | Five only, per-agent tok/s | Main solo tok/s | Main + five, main tok/s | Main + five, per-agent tok/s |
| ---: | ---: | ---: | ---: | ---: |
| 50K | 5.31–5.47 | 33.84 | 23.71 | 2.86–2.95 |
| 100K | 2.98–3.10 | 27.37 | 21.30 | 2.21–2.22 |
| 150K | 2.05–2.14 | 23.02 | 19.07 | 1.65–1.72 |
| 200K | 1.56–1.61 | 19.69 | 16.92 | 1.34–1.37 |

The main and agents start together. At deeper depths the 512-token main may finish before the slowest 64-token agent; the mixed result is then a partly overlapped wall-time rate. It does not isolate model execution contention from GPU0 KV allocation. The five-only condition measures the user's intended deployment configuration: GPU0 holds weights and handles five agents, without a main chat. Each 1060's PCIe link is x1 Gen2 during activity, but these rates do not prove that link bandwidth is the decode limiter. The strong depth dependence also implicates attention work on the 1060s.

The result establishes that keeping GPU0 free of its own generation materially helps agent throughput: the five-agent-only range is 5.31–5.47/2.98–3.10/2.05–2.14/1.56–1.61 tok/s versus 2.86–2.95/2.21–2.22/1.65–1.72/1.34–1.37 with a main generating. The wall-time effect is largest at 50K, where all agent tokens overlap the main; at 200K the main finishes about 17 seconds before the slowest agent. It does not bring the current five-chat path close to 30 tok/s per chat. Next compare a MoE model with weights on GPU0 and five chats on GPUs1–5, then test smaller reserved KV capacity and profile attention, graph crossings, and GPU0 model execution.

Sources: `campaigns/qwen27_main_gpu0_sustained_five_20261109.json`, `main_gpu0_sustained_five.json`, `terminal.json`, and the raw log at `/mnt/shared/experiments/kv-matrix-20261107/qwen27_main_gpu0_sustained_five_20261109.log`.
