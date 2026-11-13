# Qwen2.5-Coder-7B solo model on GTX 1060 vs GTX 1070 (2026-11-12)

The same NVMe Qwen2.5-Coder-7B-Instruct Q4_K_M GGUF and llama-runtime:b11669 server ran alone on GPU1 (GTX 1060 6GB) and GPU2 (GTX 1070 8GB), in 1060/1070/1060/1070 order. Each run used an 8,192-token context cap, batch and ubatch 64, four CPU threads, temperature 0, a fixed 2,082-token prompt, and two separate 128-token completions with prompt cache disabled. Docker selected each card by GPU UUID, and the runner rejected unexpected GPU allocations. All four stages passed.

| Card and pass | Load, s | VRAM allocation, MiB | Prefill tok/s, repeats | Decode tok/s, repeats |
| --- | ---: | ---: | ---: | ---: |
| 1060 A | 14.38 | 4,712 | 354.8 / 355.3 | 20.77 / 20.81 |
| 1070 B | 12.41 | 4,734 | 512.4 / 510.0 | 29.24 / 29.23 |
| 1060 C | 12.37 | 4,712 | 354.7 / 353.4 | 20.76 / 20.81 |
| 1070 D | 12.37 | 4,734 | 509.0 / 506.4 | 29.17 / 29.14 |

Across both passes, the 1070 averaged **509.4 vs 354.5 prefill tok/s (+43.7%)** and **29.19 vs 20.79 decode tok/s (+40.4%)**. This is a genuine single-card model load: GPU0 remained near idle, and only the selected Pascal card gained about 4.7 GiB. The first load had a different cache state from later loads, so its 14.38 s versus roughly 12.4 s load times do not establish a card loading advantage. The context is a short 8K cap with about 2.1K occupied tokens, not a long-chat curve.

At the end of that solo test, the 1070 container was left loaded and GPU2 had claim qwen25coder7b-1070-resident; subsequent experiments replaced that service. The historical 1060 model range of roughly 10-20 tok/s was from different models and workloads; this matched run establishes a 20.8 tok/s 7B baseline and a 29.2 tok/s 1070 result for this prompt. The earlier [35B KV-chat placement comparison](../qwen35_q41_1060_1070_matched_20261112/README.md) was subsequently corrected: its fallback build showed a small 1060 advantage at 16K-50K, whereas this full small-model placement gains about 40% in decode. That difference helps separate model compute from the shared 3090 and long-context attention path.

[Manifest](../../../campaigns/qwen25coder7b_1060_1070_solo_20261112.json), [metrics](metrics.json), and [sequence receipt](../model_loading_sequences/qwen25coder7b-solo-1060-1070-20261112-v2/terminal.json). The first pre-load attempt failed only because its output path used the Pi mount; [that receipt](../model_loading_sequences/qwen25coder7b-solo-1060-1070-20261112/terminal.json) is retained.
