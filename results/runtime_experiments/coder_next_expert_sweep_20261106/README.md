# Qwen3-Coder-Next 32K expert placement sweep — 2026-11-06

Same Q4_K_S GGUF and llama-runtime:b11669 throughout. Runs used context 32,768, batch 64, one slot, temperature 0, seed 42, cache_prompt false, and ignore_eos true for the fixed-length timing probe. Synthetic timing prompts were 2,416 and 28,766 tokens with exactly 1,024 generated tokens. The practical LRU-cache prompt used normal chat completion and could stop early. Each row is one fresh load and one timing pass; the prior matched practical standard response is linked below.

| Layout | GPUs used | 2.4K wall s | 28.8K prefill tok/s | 28.8K decode tok/s | 28.8K wall s | Practical wall s | Minimum loaded GPU headroom |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Published layer split | 3090 + five 1060s | 36.4 | 239.0 | 27.0 | 158.3 | 23.8 (prior matched receipt) | see prior experiment |
| Routed experts, 24 layers, contiguous | 3090 + five 1060s | 26.8 | 215.6 | 60.6 | 150.3 | 13.7 | about 1.4 GiB |
| Routed experts, 28 layers, contiguous | 3090 + five 1060s | 30.0 | 187.7 | 56.3 | 171.4 | 14.9 | about 0.78 GiB |
| Routed experts, 24 layers, contiguous | 3090 + four 1060s | 26.0 | 225.6 | 60.9 | 144.3 | 13.3 | about 0.47 GiB |
| Routed experts, 28 layers, round robin | 3090 + five 1060s | 30.3 | 186.5 | 55.8 | 172.6 | 15.3 | about 0.72 GiB |

The 24-layer five-1060 division is the best tested layout with comfortable headroom. It reduces the 28.8K/1,024-token wall time by 5% and raises decode 2.25x versus the published layout. The four-1060 division is faster and frees one card, but its 1060 has only about 482 MiB free at idle after load; do not promote that allocation without more safety work. Moving 28 layers slows both prompt processing and decode, whether the layers are contiguous or round robin. More offload is not always better.

At this prompt depth the 24-layer layout's slower prefill costs about 13 seconds; the decode rate repays that after roughly 640 output tokens. A prior 28.8K/128-token request favored the standard layout. These crossover estimates apply to this synthetic prompt, one slot, and this rig. The practical task is a separate short-prompt check, and its standard receipt is in the previous experiment directory: results/runtime_experiments/coder_next_expert_placement_20261105/practical_standard_32k.json.

All receipts include prompt and generated token counts, llama timings, wall time, and truncation status. Per-layout GPU snapshots are CSV. The runner is scripts/active/run_coder_next_expert_sweep.py and the placement definitions are in orchestration's qwen3_coder_next_expert_sweep.py. The experimental wrappers use the existing run_runtime.sh path and do not change gateway routes or the model library. Quality, sustained concurrency, and load-to-load variance remain to be evaluated before a manager recipe.
