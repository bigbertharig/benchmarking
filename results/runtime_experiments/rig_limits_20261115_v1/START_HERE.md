# Rig limit survey: starting guidance

Run: `rig_limits_20261115_v1`; status: **passed**; observed: 2026-11-15T23:21:29+00:00

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

- Host RAM: 23.37 GiB touched; stop: `target_reached`; minimum guard 4.0 GiB. This is observed headroom during this run, not an allocation guarantee.
- GPU copy paths: 128 MiB pinned-copy medians below. Physical labels come from saved PCI buses; unresolved labels retain CUDA IDs.

| Path | Source | Destination | GB/s |
|---|---|---|---:|
| h2d | host RAM | host GPU 0 | 12.505 |
| d2h | host GPU 0 | host RAM | 13.118 |
| h2d | host RAM | host GPU 1 | 0.400 |
| d2h | host GPU 1 | host RAM | 0.418 |
| h2d | host RAM | host GPU 2 | 0.399 |
| d2h | host GPU 2 | host RAM | 0.418 |
| h2d | host RAM | host GPU 3 | 0.398 |
| d2h | host GPU 3 | host RAM | 0.418 |
| h2d | host RAM | host GPU 4 | 0.400 |
| d2h | host GPU 4 | host RAM | 0.418 |
| h2d | host RAM | host GPU 5 | 0.400 |
| d2h | host GPU 5 | host RAM | 0.418 |
| peer_staged | host GPU 0 | host GPU 1 | 0.384 |
| peer_staged | host GPU 0 | host GPU 2 | 0.385 |
| peer_staged | host GPU 0 | host GPU 3 | 0.384 |
| peer_staged | host GPU 0 | host GPU 4 | 0.386 |
| peer_staged | host GPU 0 | host GPU 5 | 0.386 |
| peer_staged | host GPU 1 | host GPU 0 | 0.402 |
| peer_staged | host GPU 1 | host GPU 2 | 0.396 |
| peer_staged | host GPU 1 | host GPU 3 | 0.394 |
| peer_staged | host GPU 1 | host GPU 4 | 0.396 |
| peer_staged | host GPU 1 | host GPU 5 | 0.396 |
| peer_staged | host GPU 2 | host GPU 0 | 0.402 |
| peer_staged | host GPU 2 | host GPU 1 | 0.396 |
| peer_staged | host GPU 2 | host GPU 3 | 0.394 |
| peer_staged | host GPU 2 | host GPU 4 | 0.396 |
| peer_staged | host GPU 2 | host GPU 5 | 0.396 |
| peer_staged | host GPU 3 | host GPU 0 | 0.402 |
| peer_staged | host GPU 3 | host GPU 1 | 0.396 |
| peer_staged | host GPU 3 | host GPU 2 | 0.395 |
| peer_staged | host GPU 3 | host GPU 4 | 0.396 |
| peer_staged | host GPU 3 | host GPU 5 | 0.396 |
| peer_staged | host GPU 4 | host GPU 0 | 0.402 |
| peer_staged | host GPU 4 | host GPU 1 | 0.396 |
| peer_staged | host GPU 4 | host GPU 2 | 0.395 |
| peer_staged | host GPU 4 | host GPU 3 | 0.394 |
| peer_staged | host GPU 4 | host GPU 5 | 0.396 |
| peer_staged | host GPU 5 | host GPU 0 | 0.402 |
| peer_staged | host GPU 5 | host GPU 1 | 0.396 |
| peer_staged | host GPU 5 | host GPU 2 | 0.396 |
| peer_staged | host GPU 5 | host GPU 3 | 0.394 |
| peer_staged | host GPU 5 | host GPU 4 | 0.396 |

- Storage sequential_write: 0.372 GB/s (direct I/O, 512 MiB file).
- Storage sequential_read: 0.404 GB/s (direct I/O, 512 MiB file).
- Storage random read: 8653 4 KiB IOPS at queue depth 1 (direct I/O).

## Start here

1. Start with the GPU that has enough **free** VRAM for the workload. Add other GPUs only when capacity or measured execution benefits justify them.
2. For data that must cross devices repeatedly, use the measured copy paths above. A slow PCIe path can make helper VRAM expensive to access remotely.
3. Keep the tested RAM headroom and a storage free-space margin. Retest after changing cards, slots, RAM, drives, or the runtime.

These are hardware starting rules. Model fit, context, chat count, and tokens per second require the later model placement tests.
