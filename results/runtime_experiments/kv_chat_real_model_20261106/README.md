# Private llama.cpp per-chat KV prototype: real-model runs

2026-11-06 rig experiment. The runnable source is an isolated copy of the
llama.cpp tree vendored by `/data/bench-staging/strata-v0.2.10/install/third_party/llama.cpp`.
`private_llama_kv.patch` is the exact final source diff against that copy;
`patch.py`, `fix_devices.py`, and `extend_five.py` show the edit sequence.
The private source and build remain under `/mnt/shared/experiments/kvchat-20261106`
and `/data/bench-staging/kvchat-20261106-build`. No serving image was replaced.

The prototype picks one CUDA KV device per llama context, adds that device to
the graph scheduler even when all model layers use GPU0, and pins flash
attention there. Five contexts share one `llama_model`; the harness changes
`LLAMA_KV_DEVICE_INDEX` before each context creation and decode. Decode calls
are **sequential**, while all five contexts and KV allocations coexist.
The process-global environment selector is a test shim, not a safe concurrent API.

| Model | GPU0 model buffer | KV on each GPU1–5 | Peak GPU0 sampled | Peak 1060 sampled | Result |
| --- | ---: | ---: | ---: | ---: | --- |
| Qwen3 1.7B Q4_K_M, dense | 1,050 MiB | 3,584 MiB | 2,907 MiB | 3,700–3,704 MiB | 5/5 first answers correct |
| GPT-OSS 20B MXFP4, MoE | 10,949 MiB | 2 x 768 MiB | 13,311 MiB | 1,612 MiB | 5/5 first answers correct |
| Qwen3.6 27B Q4_K_M, dense | 15,346 MiB | 2,048 MiB | 19,019 MiB | 2,208 MiB | 5/5 first answers correct |

All three runs used five **32,768-token cache allocations** and five different
5-token prompts (France, Japan, Germany, Italy, Spain). Each chat produced
Paris, Tokyo, Berlin, Rome, or Madrid as its first token and continued for
three more tokens. `manifest.json` contains parsed exits, cache buffers,
first tokens, and 1 Hz sampled GPU memory peaks. Raw logs and samples are here.
The 1 Hz peaks can miss transient maxima; the runtime allocation logs give
the exact buffers it reserved.

`run-v1` is the first two-chat attempt. It failed during context creation
because `split_mode=none` exposed only GPU0 through `model.devices`.
`run-v2` is the corrected two-chat 4K test, and `run` is the final five-chat
32K dense 1.7B test. `moe_run` and `dense27_run` are the other five-chat tests.
Every run used a Manager `run-start` reservation for GPU0 plus its cache GPUs.

These runs prove independent *residency and short decode* on one shared model
weight load across dense and MoE architectures. They do not test 32K filled
prompts, 200–250K per chat, simultaneous decode threads, numerically matched
outputs against an unpatched baseline, or a serving API. At 200K, the 27B
model's current F16 KV would exceed a 6 GB 1060; Q4 KV and accurate workspace
admission are required. Five llama contexts also reserve five separate GPU0
compute buffers (505 MiB each for the 27B run), so a production scheduler
should share or cap that workspace. Manager has no profile for this topology yet.
