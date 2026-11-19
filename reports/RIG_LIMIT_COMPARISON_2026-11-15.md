# Rig limit survey: prediction compared with first full run

Prediction was [written before the run](RIG_LIMIT_PREDICTION_2026-11-15.md).
The managed survey `rig-limits-20261115-v1` ran on 2026-11-15 from
23:21:29 to 23:24:40 UTC and **passed all four stages**. The complete local
receipt is in [rig_limits_20261115_v1](../results/runtime_experiments/rig_limits_20261115_v1/START_HERE.md).
The Pi has the same receipt under
`/mnt/shared/plans/shoulders/benchmarking/results/runtime_experiments/rig_limits_20261115_v1`.

| Measurement | Predicted | Observed | Result |
|---|---:|---:|---|
| GPU 0 pinned host to device, 128 MiB | 11.5–13.5 GB/s | 12.505 GB/s | In range |
| GPU 0 pinned device to host, 128 MiB | 12.0–14.5 GB/s | 13.118 GB/s | In range |
| Each helper host to device, 128 MiB | 0.37–0.43 GB/s | 0.398–0.400 GB/s | All in range |
| Each helper device to host, 128 MiB | 0.39–0.45 GB/s | 0.418 GB/s | All in range |
| GPU 0 to each helper, 128 MiB | 0.35–0.43 GB/s, host staged | 0.384–0.386 GB/s, host staged | All in range |
| Guarded RAM touch | At least 95% of auto target | 23,927 MiB = 25.09 decimal GB, essentially 100% of the 25.09 GB target | Met |
| RAM guard | At least 4 GiB `MemAvailable` | 5.10 GiB at peak allocation | Met |
| Swap growth | Under 256 MiB | 117 MiB | Met |
| NVMe sequential write, 512 MiB | 0.25–0.45 GB/s | 0.372 GB/s | In range |
| NVMe sequential read, 512 MiB | 0.32–0.45 GB/s | 0.404 GB/s | In range |
| NVMe random 4 KiB read, depth 1 | 6,000–12,000 IOPS | 8,653 IOPS | In range |

The hardware map also matched: GPU 0 is the RTX 3090 Ti on PCIe Gen3 x16;
the GTX 1070 and four GTX 1060 helpers are on Gen2 x1 links. The Manager
granted the GPU lease; no cards were claimed or busy at the start. The CUDA
probe found no direct peer access among the selected cards, so GPU-to-GPU
copy measurements used a host staging buffer. Physical card comparisons use
the PCI buses recorded in `plan.json`, since CUDA ordinals differ from host
indexes for the 1060 on `03:00.0` and 1070 on `0D:00.0`.

There were **no misses** against the stated predictions. The near match to
the earlier copy measurements suggests those individual links are stable under
this serial probe. It does not measure simultaneous transfers or model
throughput. The 512 MiB storage result reflects one direct-I/O path at queue
depth one; the 25.09 GB RAM result is guarded headroom during this run, not a
promised model allocation. Use these figures as the starting hardware map for
the later model-placement tests.

Primary evidence: [run plan](../results/runtime_experiments/rig_limits_20261115_v1/plan.json),
[link copy CSV](../results/runtime_experiments/rig_limits_20261115_v1/link/copies.csv),
[RAM terminal receipt](../results/runtime_experiments/rig_limits_20261115_v1/ram/terminal.json),
and [storage stage](../results/runtime_experiments/rig_limits_20261115_v1/storage/stage.json).
