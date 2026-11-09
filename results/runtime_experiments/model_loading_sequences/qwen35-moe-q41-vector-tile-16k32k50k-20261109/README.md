# Qwen3.6 Q4_1 vector versus tile attention (2026-11-09)

An isolated build changed one Pascal dispatch choice: for Q4_1/Q4_1 KV,
256-wide heads, and applicable GQA reuse, decode selects the generic tile
attention kernel instead of the vector kernel. The tile path still converts
Q4_1 to F16 scratch. The model's Q4_K_XL weights were on GPU0 (3090 Ti); one
worker's Q4_1 KV was on GPU1 (GTX 1060). Every stage reserved 262,144 tokens,
restored the same validated 16K/32K/50K chat states, and generated 64 tokens.
The vector/tile/vector A/B/A sequence passed with exit 0 and `ok=1` at all
three depths. It checks that the run completes; it is not a numerical
equivalence or answer-quality evaluation.

| Path | 16K tok/s | 32K tok/s | 50K tok/s |
| --- | ---: | ---: | ---: |
| Vector before | 50.66 | 35.09 | 24.28 |
| Tile | 53.52 | 40.91 | 31.52 |
| Vector after | 50.89 | 34.97 | 23.96 |

Against the mean vector controls, tile improved worker decode by about
**5.4% / 16.8% / 30.7%** at 16K/32K/50K. The 50K worker cleared the
30 tok/s target for one chat. Tile's first-token latency was 117/38/45 ms;
the controls were about 110/42/61 ms. The 16K first token was slower, while
later-token latency improved. Peak sampled GPU1 memory was 2,193 MiB for
tile and 2,197 MiB for the first control; GPU0 tile peak was 21,173 MiB.
The full 262K reservation therefore fit at these occupied depths. These
samples do not prove the same behavior for a fully occupied 262K chat.

Nsight captured only the 64-token decode segments. Across those 64 tokens,
GPU1 `flash_attn_tile<256,256,1,8,false>` took **217/422/633 ms** at
16K/32K/50K. The earlier matched F16 vector traces took **293/661/1,171 ms**.
The Q4_1 dequant kernel remained **242/477/723 ms**, essentially unchanged
from the earlier vector traces (241/477/729 ms). The attention reduction,
especially at 50K, accounts for the observed speedup; dequantization remains
the next measurable cost. The profiler's kernel durations are sums, not
exclusive wall time. The A/B/A speed result was measured without profiling.

Next: verify output quality or logits against the vector control on matched
states, then try a fused quantized tile read or another way to avoid repeated
F16 scratch conversion. After that, check the same gain with two independent
1060 chats and with another head-size/model family. Continue to measure
chat-state preparation and transfer separately from decode.

Evidence: [A/B/A receipt](terminal.json), [trace receipt](trace_terminal.json),
[tile kernel summary](tile_trace_summary.json), [build recipe](build_q41_tile.sh),
[A/B/A campaign](../../../../campaigns/qwen35_moe_q41_vector_tile_16k32k50k_20261109.json),
[trace campaign](../../../../campaigns/qwen35_moe_q41_tile_trace_16k32k50k_20261109.json).
Raw logs, GPU samples, Nsight reports, SQLite exports, and kernel CSVs are
under `/mnt/shared/experiments/kv-matrix-20261107/qwen35_moe_q41_{vector_tile,tile_trace}_16k32k50k_20261109_*`.
