# Rig limit survey: starting guidance

Run: `rig_work_deep_20261115_v1`; status: **passed**; observed: 2026-11-15T23:57:58+00:00

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

- Host RAM: 23.39 GiB touched; stop: `target_reached`; minimum guard 4.0 GiB. This is observed headroom during this run, not an allocation guarantee.
- GPU copy paths: 128 MiB pinned-copy medians below. Physical labels come from saved PCI buses; unresolved labels retain CUDA IDs.

| Path | Source | Destination | GB/s |
|---|---|---|---:|
| h2d | host RAM | host GPU 0 | 12.452 |
| d2h | host GPU 0 | host RAM | 13.142 |
| h2d | host RAM | host GPU 1 | 0.400 |
| d2h | host GPU 1 | host RAM | 0.418 |
| h2d | host RAM | host GPU 2 | 0.398 |
| d2h | host GPU 2 | host RAM | 0.418 |
| h2d | host RAM | host GPU 3 | 0.400 |
| d2h | host GPU 3 | host RAM | 0.418 |
| h2d | host RAM | host GPU 4 | 0.399 |
| d2h | host GPU 4 | host RAM | 0.418 |
| h2d | host RAM | host GPU 5 | 0.399 |
| d2h | host GPU 5 | host RAM | 0.418 |
| peer_staged | host GPU 0 | host GPU 1 | 0.386 |
| peer_staged | host GPU 0 | host GPU 2 | 0.384 |
| peer_staged | host GPU 0 | host GPU 3 | 0.386 |
| peer_staged | host GPU 0 | host GPU 4 | 0.385 |
| peer_staged | host GPU 0 | host GPU 5 | 0.385 |
| peer_staged | host GPU 1 | host GPU 0 | 0.402 |
| peer_staged | host GPU 1 | host GPU 2 | 0.394 |
| peer_staged | host GPU 1 | host GPU 3 | 0.396 |
| peer_staged | host GPU 1 | host GPU 4 | 0.395 |
| peer_staged | host GPU 1 | host GPU 5 | 0.395 |
| peer_staged | host GPU 2 | host GPU 0 | 0.402 |
| peer_staged | host GPU 2 | host GPU 1 | 0.396 |
| peer_staged | host GPU 2 | host GPU 3 | 0.396 |
| peer_staged | host GPU 2 | host GPU 4 | 0.395 |
| peer_staged | host GPU 2 | host GPU 5 | 0.395 |
| peer_staged | host GPU 3 | host GPU 0 | 0.402 |
| peer_staged | host GPU 3 | host GPU 1 | 0.396 |
| peer_staged | host GPU 3 | host GPU 2 | 0.394 |
| peer_staged | host GPU 3 | host GPU 4 | 0.395 |
| peer_staged | host GPU 3 | host GPU 5 | 0.395 |
| peer_staged | host GPU 4 | host GPU 0 | 0.402 |
| peer_staged | host GPU 4 | host GPU 1 | 0.396 |
| peer_staged | host GPU 4 | host GPU 2 | 0.394 |
| peer_staged | host GPU 4 | host GPU 3 | 0.396 |
| peer_staged | host GPU 4 | host GPU 5 | 0.395 |
| peer_staged | host GPU 5 | host GPU 0 | 0.402 |
| peer_staged | host GPU 5 | host GPU 1 | 0.394 |
| peer_staged | host GPU 5 | host GPU 2 | 0.394 |
| peer_staged | host GPU 5 | host GPU 3 | 0.396 |
| peer_staged | host GPU 5 | host GPU 4 | 0.395 |

- Storage sequential_write: 0.371 GB/s (direct I/O, 512 MiB file).
- Storage sequential_read: 0.403 GB/s (direct I/O, 512 MiB file).
- Storage random read: 8687 4 KiB IOPS at queue depth 1 (direct I/O).

## Synthetic work scan (deep)

Patterned data, no model loaded. Times are median microseconds per operation and are not token-speed predictions. All samples and p95 values are in `synthetic/gpu.jsonl`.

| GPU | Weight resident | Weight RAM upload | Long KV scan | 16-row GPU lookup |
|---|---:|---:|---:|---:|
| host GPU 0 | 300.2 | 11012.0 | 352.9 | 14.4 |
| host GPU 1 | 1776.6 | 337450.8 | 5599.9 | 23.1 |
| host GPU 2 | 1339.1 | 336844.6 | 4466.0 | 23.6 |
| host GPU 3 | 1728.8 | 337256.6 | 5468.3 | 22.5 |
| host GPU 4 | 1776.3 | 338044.5 | 5629.2 | 23.1 |
| host GPU 5 | 1730.3 | 338057.0 | 5458.7 | 17.7 |

Weight arrays are 32/128 MiB in small/deep; the long one-head KV scan covers 32K/128K positions; the GPU lookup gathers sixteen 128-byte rows from a 64/256 MiB table.

| GPU | Expert cache hit µs | RAM miss µs | Realized hit rate |
|---|---:|---:|---:|
| host GPU 0 | 5.1 | 94.2 | 81% |
| host GPU 1 | 21.3 | 2642.6 | 81% |
| host GPU 2 | 15.8 | 2637.7 | 81% |
| host GPU 3 | 20.9 | 2641.6 | 81% |
| host GPU 4 | 21.3 | 2644.4 | 81% |
| host GPU 5 | 20.8 | 2651.4 | 81% |

- Sixteen-row pinned RAM lookup: median 0.9 µs (p95 1.6 µs).

- Simultaneous host-to-GPU copy across 6 cards: 2.355 aggregate GB/s (includes synchronized copy loop; compare with isolated link results).
- 16-row warm page-cache rows: median 14.0 µs; p95 14.8 µs. Direct reads use 4 KiB per row; buffered reads use 128 bytes per row.
- 16-row direct storage rows: median 1707.5 µs; p95 2846.4 µs. Direct reads use 4 KiB per row; buffered reads use 128 bytes per row.

Interpret weight results as resident compute versus upload on the same card. Expert timings use a synthetic 80%-hot route and an LRU cache; real models have different routes and kernels. KV scans are one-head access proxies. The next model-specific stage verifies actual placement.

## Start here

1. Start with the GPU that has enough **free** VRAM for the workload. Add other GPUs only when capacity or measured execution benefits justify them.
2. For data that must cross devices repeatedly, use the measured copy paths above. A slow PCIe path can make helper VRAM expensive to access remotely.
3. Keep the tested RAM headroom and a storage free-space margin. Retest after changing cards, slots, RAM, drives, or the runtime.

These are hardware starting rules. Model fit, context, chat count, and tokens per second require the later model placement tests.
