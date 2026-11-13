# PLE lookup versus PCIe and NVMe isolation (2026-11-13)

The managed [v4 campaign](../model_loading_sequences/q38-ple-bus-probe-v4-20261113/terminal.json) passed on the GTX 1070 (bus 0D) and one GTX 1060 (bus 03). It measured the existing Qwen3.8 PLE GGUF's direct-storage and buffered file reads, synthetic GPU copies of the same 90-byte row size, 16-row gather, and 32 MiB transfer ceilings. The [probe](../../../scripts/integration/ple_bus_probe.cu) and [wrapper](../../../scripts/integration/run_ple_bus_probe.sh) preserve the method; [compact metrics](summary.json) include all timed calls and link-state samples. Raw logs and link samples remain under `/mnt/shared/experiments/kv-matrix-20261107/q38_ple_bus_probe_20261113_v4.*` on the rig. Earlier runs v1-v3 are retained there and in managed receipts; v1's device-local copy omitted synchronization, and v3's first gather included kernel startup. The final v4 warms the kernel and synchronizes local copies.

| Operation | GTX 1070 median | GTX 1060 median | Meaning |
| --- | ---: | ---: | --- |
| Direct NVMe 4 KiB random read | 114.9 us | same storage test | Bypasses page cache with `O_DIRECT` |
| Warm buffered file 90-byte read | 0.86 us | same storage test | Page-cache hit, not physical NVMe |
| GPU to ordinary host buffer, 90 bytes | 7.79 us | 7.58 us | Current model plugin uses this class of copy |
| GPU to pinned host buffer, 90 bytes | 6.56 us | 6.50 us | One selected packed row |
| Sixteen separate GPU row copies, pinned | 105.2 us | 104.4 us | Sixteen 90-byte rows on one card |
| GPU gathers 16 rows, one return copy | 15.7 us | 20.9 us | Correctness checked against patterned device rows |
| GPU to host, 32 MiB | 80.26 ms | 80.27 ms | About 0.389 GiB/s per card |
| Host to GPU, 32 MiB | 83.93 ms | 84.19 ms | About 0.37 GiB/s per card |
| Same-GPU 32 MiB copy | 0.340 ms | 0.445 ms | About 92 / 70 GiB/s; bypasses PCIe |

During active copies, telemetry sampled **Gen2 x1** on both cards; at idle it often sampled Gen1 x1. `lspci -t` places each selected card on its own chipset root port. The ASMedia switch visible in the machine has no GPU beneath it. The model's `/data` NVMe device is also negotiated at Gen2 x1. Gen2 x1's nominal one-direction bandwidth is 500 MB/s, so the observed ~418 MB/s GPU return rate is strong evidence that the **PCIe link limits bulk transfers**. Device-local copies are over two orders of magnitude faster. The cold NVMe read is around 15 times slower than a small GPU return, while a warm page-cache hit is faster than that return. These tests do not measure simultaneous card contention or the chipset uplink ceiling. [PCI-SIG bandwidth reference](https://pcisig.com/faq?keys=3.0) documents the link-rate conversion.

The 1070 and 1060 delivered essentially identical 32 MiB host-transfer rates despite differing device-local copy rates. That is the clearest current evidence that the link, rather than the Pascal VRAM, caps **bulk** helper traffic on this layout.

The Qwen3.8 header has three-gram PLE with eight heads per n-gram, so the graph requests 16 rows per token. On the current 35B model smoke, the GPU row path's roughly 0.1 ms for 16 copies is tiny beside roughly 1.17 seconds per generated token. A faster PCIe link would not plausibly transform **this full model's** tokens/s by accelerating only PLE lookups. Gathering helps the lookup microbenchmark around five to sevenfold, but is not yet integrated into the model plugin. A wider link could meaningfully shorten loading the 28.8 GB table and could help if routed experts stream substantial bytes each token. That expert-traffic hypothesis still needs an end-to-end transfer trace.

PCIe 4.0 x4 and 5.0 x16 offer much higher theoretical aggregate bandwidth than this Gen2 x1 connection, but actual improvement depends on the GPU endpoint, storage, software, and available CPU/chipset lanes. These GTX 1070/1060 cards are PCIe 3 era devices; a new Gen4/5 motherboard would not turn their endpoints into Gen4/5 devices. [PCI-SIG link rates](https://pcisig.com/what-bit-rates-does-pcie-50-specification-support-and-how-does-it-compare-prior-pcie-generations) and [NVIDIA GTX 1070](https://www.nvidia.com/content/geforce-gtx/GEFORCE_GTX_1070_USER_GUIDE_v02.pdf) / [GTX 1060](https://www.nvidia.com/content/geforce-gtx/GEFORCE_GTX_1060_USER_GUIDE_v02.pdf) user guides document these limits.
