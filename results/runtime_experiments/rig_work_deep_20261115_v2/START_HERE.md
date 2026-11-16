# Rig limit survey: starting guidance

Run: `rig_work_deep_20261115_v2`; status: **passed**; observed: 2026-11-16T00:08:17+00:00

## Hardware map

| Host GPU | Card | VRAM MiB | PCI bus | UUID |
|---:|---|---:|---|---|
| 0 | NVIDIA GeForce RTX 3090 Ti | 24564 | 01:00.0 | `GPU-409c0fe8-38ef-14ad-dbc6-a0437261e9cb` |
| 1 | NVIDIA GeForce GTX 1060 6GB | 6144 | 03:00.0 | `GPU-fd82a1a6-06aa-3ec2-1786-ae7b4474105c` |
| 2 | NVIDIA GeForce GTX 1070 | 8192 | 0D:00.0 | `GPU-cc6bc379-2f59-ec6e-00cf-4a9f02d57519` |
| 3 | NVIDIA GeForce GTX 1060 6GB | 6144 | 10:00.0 | `GPU-6073db94-dca6-ba6c-88fb-61f09ff11436` |
| 4 | NVIDIA GeForce GTX 1060 6GB | 6144 | 11:00.0 | `GPU-ac5b4fea-fdd5-947f-892b-5b0cc3f5c225` |
| 5 | NVIDIA GeForce GTX 1060 6GB | 6144 | 12:00.0 | `GPU-8d1110ae-1936-9251-92a8-ceebc6f39b57` |

## Measured limits

- Host RAM: skipped in this run.
- GPU transfer paths: skipped in this run.
- Storage sequential_write: 0.369 GB/s (direct I/O, 64 MiB file).
- Storage sequential_read: 0.401 GB/s (direct I/O, 64 MiB file).
- Storage random read: 8865 4 KiB IOPS at queue depth 1 (direct I/O).

## Synthetic work scan (deep)

Patterned data, no model loaded. Times are median microseconds per operation and are not token-speed predictions. All samples and p95 values are in `synthetic/gpu.jsonl`.

| GPU | Weight resident | Weight RAM upload | Long KV scan | 16-row GPU lookup |
|---|---:|---:|---:|---:|
| host GPU 0 | 299.8 | 11036.3 | 351.4 | 15.3 |
| host GPU 1 | 1777.2 | 337545.1 | 5624.9 | 16.9 |
| host GPU 2 | 1340.0 | 336739.4 | 4464.4 | 23.6 |
| host GPU 3 | 1731.0 | 337168.6 | 5457.9 | 22.8 |
| host GPU 4 | 1776.6 | 338041.4 | 5616.8 | 23.3 |
| host GPU 5 | 1728.4 | 337252.2 | 5464.3 | 17.0 |

Weight arrays are 32/128 MiB in small/deep; the long one-head KV scan covers 32K/128K positions; the GPU lookup gathers sixteen 128-byte rows from a 64/256 MiB table.

| GPU | Expert cache hit µs | RAM miss µs | Realized hit rate |
|---|---:|---:|---:|
| host GPU 0 | 5.1 | 94.3 | 81% |
| host GPU 1 | 21.3 | 2642.1 | 81% |
| host GPU 2 | 15.5 | 2638.2 | 81% |
| host GPU 3 | 20.8 | 2641.6 | 81% |
| host GPU 4 | 21.3 | 2645.9 | 81% |
| host GPU 5 | 20.9 | 2647.9 | 81% |

- Sixteen-row pinned RAM lookup: median 0.8 µs (p95 1.4 µs).

Matched 32 MiB pinned uploads, serial then simultaneous (GB/s on each physical card):

| GPU | Alone | Simultaneous | Slowdown |
|---|---:|---:|---:|
| host GPU 0 | 9.811 | 12.373 | 0.79× |
| host GPU 1 | 0.394 | 0.399 | 0.99× |
| host GPU 2 | 0.396 | 0.400 | 0.99× |
| host GPU 3 | 0.399 | 0.400 | 1.00× |
| host GPU 4 | 0.399 | 0.399 | 1.00× |
| host GPU 5 | 0.400 | 0.400 | 1.00× |

The comparison isolates measured shared-traffic effects; a slowdown above 1 can also include CPU scheduling and pinned-memory pressure.
- 16-row warm page-cache rows: median 16.4 µs; p95 17.5 µs. Direct reads use 4 KiB per row; buffered reads use 128 bytes per row.
- 16-row direct storage rows: median 1698.8 µs; p95 1779.6 µs. Direct reads use 4 KiB per row; buffered reads use 128 bytes per row.

Interpret weight results as resident compute versus upload on the same card. Expert timings use a synthetic 80%-hot route and an LRU cache; real models have different routes and kernels. KV scans are one-head access proxies. The next model-specific stage verifies actual placement.

## Start here

1. Start with the GPU that has enough **free** VRAM for the workload. Add other GPUs only when capacity or measured execution benefits justify them.
2. For data that must cross devices repeatedly, use the measured copy paths above. A slow PCIe path can make helper VRAM expensive to access remotely.
3. Keep the tested RAM headroom and a storage free-space margin. Retest after changing cards, slots, RAM, drives, or the runtime.

These are hardware starting rules. Model fit, context, chat count, and tokens per second require the later model placement tests.
