# 35B simultaneous worker trace (2026-11-13)

This 50K occupied-context, 64-token Q4_1 KV replay traces both 35B MoE workers at once, with model weights on the 3090 Ti. The tile attention build and saved states are fixed. Each stage resolves physical cards by UUID; the compact JSON records CUDA ordinal, host GPU, PCI bus, and UUID. The bracketing control puts both worker contexts on the same 1060, as in the prior two-worker comparison.

| Stage | Pair wall seconds | Aggregate tok/s | First worker tok/s | Second worker tok/s |
| --- | ---: | ---: | ---: | ---: |
| 1060 + 1060 before | 2.098 | 61.016 | 30.93 | 30.51 |
| 1070 + 1060 | 2.270 | 56.384 | 29.02 | 28.19 |
| 1060 + 1060 after | 2.098 | 61.012 | 30.92 | 30.51 |

The mixed pair is about 8.2% slower by wall time. Its 1070 worker executes 962 ms of kernels versus 1,370 ms for the first 1060 worker in the controls; attention tile falls from about 634 to 449 ms, and Q4_1 dequantization from about 723 to 500 ms. H2D and D2H counts and bytes are unchanged on either worker (2,816 / 40.895 MB and 640 / 10.486 MB). The 1070's measured activity gap across its trace span rises to 1,114 ms, versus about 571 ms for the first control worker; the concurrent 1060's gap rises to 752 ms, versus about 589 ms for the second control worker. These gaps are wall intervals without recorded GPU activity; they cannot by themselves identify CPU scheduling, CUDA synchronization, or graph queueing as the cause. Summed CUDA API durations across threads also overlap and must not be read as a wall-time breakdown.

The finding is narrower than a general card-speed rule: this tile build is faster on the 1070 in isolation, but its spare compute does not improve this two-worker arrangement. The paired penalty is associated with idle/synchronization time, not added bulk transfer or a slower 1070 kernel. A CPU scheduling and CUDA API correlation trace is the next useful discriminator if this exact workload is a deployment target.

[Campaign](../../../campaigns/qwen35_pair_trace_20261113.json), [terminal receipt](../model_loading_sequences/qwen35-pair-trace-20261113/terminal.json), and the three compact per-stage JSON files in this directory preserve the evidence. Raw Nsight `.nsys-rep`, `.sqlite`, logs, and CUDA maps are in `/mnt/shared/experiments/kv-matrix-20261107/qwen35_pair_trace_20261113_*`. The capture used `--sample=none --cpuctxsw=none`, so it does not establish a host scheduler cause. Replay wrapper: [run_qwen35_pair_trace.sh](../../../scripts/integration/run_qwen35_pair_trace.sh); summarizer: [summarize_nsys_pair.py](../../../scripts/integration/summarize_nsys_pair.py).
