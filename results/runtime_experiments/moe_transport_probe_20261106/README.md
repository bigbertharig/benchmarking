# Within-expert transport feasibility probe — 2026-11-06

Question: what latency does this rig impose on a host-staged fan-out/reduction path before any real expert math is added? This is a transport microbenchmark, not model inference and not an implementation of m10dis.

## Rig and method

- RTX 3090 Ti is GPU0. GPUs 1–5 are GTX 1060 6GB cards. All were idle and no model was loaded.
- nvidia-smi topology reports no GPU0-to-1060 peer reads or writes. The saved idle PCIe snapshot shows link power management at Gen1; the live link generation during the brief microbenchmark was not sampled, so do not attribute these latencies to a particular PCIe generation.
- Existing nvidia/cuda:12.9.2-devel-ubuntu24.04 image compiled scripts/active/moe_transport_probe.cu with sm_61 and sm_86 targets. No driver, model, or runtime setting was changed.
- For each iteration, GPU0 copies a float32 hidden vector to portable pinned host memory. One persistent CPU thread per 1060 copies that vector to its GPU, optionally launches a one-element-per-thread copy kernel, and returns a same-size partial vector to pinned host memory. The CPU sums partial vectors and copies the result back to GPU0. CUDA streams are synchronized before timing ends.
- Width 2,048 models Coder Next's hidden dimension (8 KiB each direction per worker); width 4,096 models Nemotron's (16 KiB). Runs used one, four, or five 1060 workers, 20 warmups and 300 measured iterations per case. The full 12-case matrix was repeated in a fresh container. GPU0 starts with a known nonzero pattern; every case verifies the reduced vector returned to GPU0. Each case reports mean, median, p95, and cudaDeviceCanAccessPeer; all peer results were zero.
- Raw container output, normalized JSONL, compiler logs, topology snapshots, and the verified summary.json are retained here. An earlier zero-pattern pilot is preserved with preliminary names and excluded from the table. The CUDA image banner in the raw text is excluded from normalized JSONL.

## Measured round-trip latency

Two-run mean of the per-run means, microseconds:

| 1060 workers | Hidden width | Copy only | Copy plus tiny kernel |
| ---: | ---: | ---: | ---: |
| 1 | 2,048 | 73.0 | 76.6 |
| 4 | 2,048 | 78.5 | 88.3 |
| 5 | 2,048 | 81.5 | 90.0 |
| 1 | 4,096 | 116.5 | 120.6 |
| 4 | 4,096 | 127.7 | 135.8 |
| 5 | 4,096 | 128.2 | 137.5 |

The verified four-worker copy-only result was 78.2 and 78.8 microseconds for width 2,048, and 128.2 and 127.2 for width 4,096. This includes host dispatch, synchronization, CPU reduction, and copies; it does not include expert weight reads or matrix multiplication. In a strictly serial 48-layer Coder Next route, 78.5 microseconds per layer would be about 3.8 ms per token. For Nemotron's 40 routed-expert layers, 127.7 microseconds would be about 5.1 ms per token. These are illustrative transport costs, not predicted end-to-end speed: a real backend could overlap work, reuse resident buffers, or incur larger compute and synchronization costs.

## Block-alignment sizing

The existing GGUF headers report Coder Next hidden width 2,048 and expert intermediate width 512. Nemotron has hidden width 4,096 and expert intermediate widths 1,536, 2,048, 2,304, and 2,560 across layers. If an equal expert-row shard must be a multiple of 32 or 64 elements, all these expert widths divide cleanly across four workers: Coder Next gets 128 rows each; Nemotron gets 384, 512, 576, or 640. Five equal Coder Next shards would round 512/5 up to 128 rows each, a 640-row allocation with 25% padding. An uneven block assignment could avoid storing that padding but would make the slowest worker do more rows. Nemotron's five-way padding depends on the layer width and required block size.

The published m10dis architecture uses 20 routed GM107 workers, each holding 32 of Qwen3.8's 640 expert intermediate rows, with PCIe multicast and peer transfers. This rig has no such peer path. The alignment arithmetic therefore informs a future kernel design; it does not change our earlier whole-expert-tensor placement results.

## Next gate

To decide whether to build an actual within-expert backend, benchmark a representative quantized expert GEMM plus the return reduction on these GPUs, and compare a four-worker implementation against the existing whole-tensor placement under the same model and prompt. Do not infer model throughput from this transport-only probe.

Upstream architecture: https://github.com/crgregersen/m10dis/blob/main/docs/ARCHITECTURE.md
