# Paired KV decode speed: dense 27B and MoE 20B

Run date: 2026-11-07. This uses the private llama.cpp paired-worker fork in
`kv_pair_dynamic_20261107`. One model weight load stays on GPU0 (3090 Ti).
Chat A has a KV cache and flash attention split across GPUs1+2, chat B across
GPUs3+4, and a smaller chat C uses GPU5. Each chat is a separate context;
decodes are sequential. K and V are Q4_0, with `n_batch=64`, `n_ubatch=8`,
greedy sampling and short capital prompts. Each timing measures only the
additional token decode loop after the three chats have been created and
continued. It excludes model load, context creation, and prompt processing.

| Model | Pair capacity A/B | Single capacity C | Timed tokens per chat | A tok/s | B tok/s | C tok/s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Qwen3.6 27B Q4_K_M, dense | 32K | 8K | 16 | 33.62 | 33.45 | 32.98 |
| GPT-OSS 20B MXFP4, MoE | 32K | 8K | 16 | 51.78 | 51.92 | 51.58 |
| Qwen3.6 27B Q4_K_M, dense | 256K | 32K | 16 | 33.71 | 33.24 | 32.89 |
| GPT-OSS 20B MXFP4, MoE | 256K | 32K | 16 | 51.76 | 51.86 | 50.87 |
| Qwen3.6 27B Q4_K_M, dense | 256K | 32K | 64 | 33.67 | 33.51 | 33.44 |
| GPT-OSS 20B MXFP4, MoE | 256K | 32K | 64 | 51.90 | 50.93 | 51.18 |

The 64-token paired-chat mean is 33.59 tok/s for dense 27B and 51.42 tok/s
for MoE 20B (about 1.53x here). These are different models and weight
quantizations, so this is a comparison of these concrete configurations,
not a controlled architecture-only speed ratio. All three chats were served
one at a time: their rates cannot be added into a concurrent aggregate.
The near-equal 32K and 256K-capacity rates reflect short **occupied**
histories. A near-full 256K cache may cost much more per token and has not
been benchmarked or checked for retrieval quality.

The first attempt accidentally launched dense and MoE jobs concurrently on
the same GPUs. Those runs were stopped and excluded. The six runs in this
directory were launched and finished serially; `manifest.json` checks every
exit and three timing lines per run. The exact timed harness, harness edit,
run script, raw logs, timestamps and 1 Hz GPU samples are preserved here.
The normal `chat-27b` route was restored after benchmarking.
