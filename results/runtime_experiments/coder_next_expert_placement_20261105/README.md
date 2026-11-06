# Qwen3-Coder-Next expert placement experiments — 2026-11-05

Status: experimental. The 262K 90%-depth timing and marker-recall requests completed. The saved orchestration wrapper passed a matched 32K practical comparison. This report separates measured loads and timings from a future m10dis-style within-expert backend.

## Scope and method

- Model: qwen3-coder-next:80b-a3b, Qwen3-Coder-Next-Q4_K_S.gguf (45,531,949,088 bytes), same file for every run.
- Rig: RTX 3090 Ti plus five GTX 1060 6GB cards. The 1060 links report PCIe Gen2 x1; nvidia-smi topo reports no GPU0-to-1060 peer reads/writes.
- Runtime: llama-runtime:b11669, llama-server, 32K context unless indicated, batch size 64, one parallel slot, q8_0 K/V, flash attention on.
- Probe: deterministic /completion requests, temperature 0, seed 42, cache_prompt false, ignore_eos true. Short decode is the mean of three 41-prompt-token, 256-output-token trials. The 2.4K case uses 2,416 prompt and 256 output tokens. Depth probes use 3,016 and 28,766 prompt tokens with 128 output tokens.
- Reusable runner: scripts/active/probe_coder_next_placement.py. The raw JSON receipts in this directory contain each timing, token count, and wall time.

## 32K-context scorecard

| Placement | Short decode tok/s | 2.4K prompt tok/s | 2.4K decode tok/s | 28.8K prompt tok/s | 28.8K decode tok/s |
| --- | ---: | ---: | ---: | ---: | ---: |
| Standard six-card layer split, 3090 first | 38.04 | 285.2 | 37.96 | 239.2 | 28.53 |
| Reversed six-card layer split, 3090 last | 41.25 | 275.0 | 40.91 | — | — |
| Reversed balanced layer split, 3090 last | 42.35 | 283.6 | 42.20 | 251.0 | 31.82 |
| Routed experts by layer on 1060s, dense/KV on 3090 | 65.96 | 223.4 | 67.29 | 216.2 | 61.07 |

The expert placement raises short decode by 73% and 28.8K-depth decode by 114% against the standard split. Prompt processing is slower: 22% lower at 2.4K and 10% lower at 28.8K. The complete 28.8K-input/128-output request took 135.2 seconds with expert placement versus 124.8 seconds standard. Workloads with more generated tokens may benefit more; test task-shaped workloads before promoting this placement.

The first reversed layer split put about 5,952 MiB on GPU1 after probing, leaving only 192 MiB; it is not a safe recipe. Balancing it to 4,5,5,5,5,24 (device order CUDA1,CUDA2,CUDA3,CUDA4,CUDA5,CUDA0) restored headroom and improved decode further.

## Expert tensor inventory and placement

The GGUF header lists 843 tensors. 384 expert-related tensors account for 41.151 GiB, about 97% of the 42.4 GiB model. There are 48 layers, 512 routed experts per layer, and 10 selected experts per token. Routed up/gate tensors use Q4_K; down tensors use Q4_K or Q5_K. See tensor_inventory.json for exact shapes and sizes.

With --tensor-split 48,0,0,0,0,0, llama keeps dense layers, attention, shared experts, and KV on the 3090. --override-tensor assigns whole routed-expert tensors from selected layers to 1060s. This is model-aware expert placement, not slicing each expert across cards. The 32K placement sends layers 0–23 to 1060s (5,5,5,5,4); the remaining 24 stay on the 3090. It loaded and served. The deterministic coding/JSON/arithmetic smoke completed all three requests and returned plausible answers; it is not a substitute for the model's normal quality suite.

## Full native context

An initial 262,144-context expert load placed 28 expert layers on 1060s (6,6,6,6,4). It allocated the full context and served short prompts at 60.32 tok/s mean short decode and 60.94 tok/s after a 2.4K prompt. GPU1 had only about 482 MiB free, so this is a capacity result, not a recommended placement.

The rebalanced 262,144-context load uses 5,6,6,6,5 expert layers across the 1060s. It also allocated the full 262,144 context and served a 25,016-token prompt at 188.6 prompt tok/s and 56.67 decode tok/s. GPU1 had about 1.4 GiB free; GPUs 2–4 had about 0.85 GiB free. At 90% depth, a cold 235,016-token prompt plus 128 output tokens completed without truncation. Prompt processing was 178.7 tok/s, decode 33.03 tok/s, and wall time 1,319.2 seconds (22.0 minutes). A first attempt was stopped after 95,040 input tokens because its temporary client had only a 900-second socket timeout; the corrected 3,600-second client restarted with zero cached tokens and completed. The timeout was a probe issue, not a model failure.

A two-marker recall control at 23,563 prompt tokens returned both markers exactly with zero cached tokens. The matching 235,063-token recall run also returned both exact markers with zero cached tokens and finish_reason stop; it took 1,323.2 seconds (22.1 minutes). This checks two positions in one synthetic prompt, not general long-context reasoning.

## Matched practical and smoke checks

The saved orchestration wrapper loaded at 32K with the existing run_runtime.sh path and 20g container memory limit. An identical 65-token LRU-cache coding prompt at temperature 0 completed in 13.99 seconds with expert placement (882 output tokens) and 23.76 seconds on the gateway's published six-card layer placement (874 output tokens). Both finish reasons were stop, and both used zero cached prompt tokens. This is one task and one run per placement.

Running the generated Python unit tests found that the expert-placement answer passed 3 tests. The standard-placement answer failed its own test: after an update made key 1 most recently used, it asserted that the next insert evicted key 1, but the correct eviction was key 3. This is a response-sampling observation, not evidence that placement itself changes model quality. Both placements finished the same three separate coding, JSON, and arithmetic smoke prompts normally; the visible JSON and arithmetic answers matched. Raw responses and the executable check receipt are in this directory.

## Unsupported or failed paths

- llama row split refused this mixed rig with “device CUDA0 does not support split buffers.”
- llama tensor split with ratio 4,1,1,1,1,1 tried to allocate 7,419.97 MiB on a 6 GiB 1060 and failed. This was one configuration, not a proof that every tensor-mode configuration fails.
- The rig lacks direct GPU0-to-1060 P2P. A genuine m10dis-style per-expert shard backend would need new transport, packing, and Q4_K/Q5_K kernels; the m10dis FP8/M10 code cannot be dropped onto this GGUF and topology.

## Ownership and next checks

Benchmarking owns these measurements. Orchestration owns the experimental wrapper at shared/scripts/rig/experiments/qwen3_coder_next_expert_split.sh. The gateway's published model recipe remains unchanged.

The gateway manager/fit.py already reads per-tensor GGUF byte counts, and rig.py already passes extra_args to run_runtime.sh. A managed recipe needs an expert-versus-dense placement calculation and a distinct placement identity so the standard layer recipe's failed-context ceiling does not reject it.

Before making a manager recipe: repeat matched practical tasks and quality suites under a normal manager lease, including long-context agent workloads, and measure sustained thermal and memory headroom. The one matched LRU task favored expert placement; the near-32K short-output request favored the standard layout because of faster prefill. The existing model-library candidate status and its 185,600-context manager-placement issue remain separate from this experimental load.

## Upstream references

- [Qwen3-Coder-Next model card](https://huggingface.co/Qwen/Qwen3-Coder-Next): model architecture and 262,144 native context.
- [llama.cpp multi-GPU guide](https://github.com/ggml-org/llama.cpp/blob/master/docs/multi-gpu.md): layer, row, and tensor split behavior.
- [m10dis architecture](https://github.com/crgregersen/m10dis/blob/main/docs/ARCHITECTURE.md): per-expert row sharding on a different Qwen model and PCIe topology.
