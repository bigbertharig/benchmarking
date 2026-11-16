# Rig limit survey: predictions before the full run

Written before the first full `rig_limit_test.py run` on 2026-11-15. These are
predictions for the current six-GPU rig, not results. The survey runs transfer
paths one at a time, touches host RAM under a 4 GiB guard, and tests one NVMe
directory with 512 MiB direct I/O at queue depth one. It does not test model
tokens/s, GPU compute, or simultaneous PCIe traffic.

| Survey measurement | Prediction | Prior evidence |
|---|---|---|
| Hardware identity | GPU0 RTX 3090 Ti 24 GiB on Gen3 x16; GPU2 GTX 1070 8 GiB and GPU1/3/4/5 GTX 1060 6 GiB on Gen2 x1. No GPU claims or loads at start. | The live `rig observe` preflight on 2026-11-15; IDs and links must be rechecked at run time. |
| 128 MiB pinned host-to-GPU0 | 11.5-13.5 GB/s | [November 12 link probe](results/runtime_experiments/gpu_link_paths_20261112_v2/copies.csv): 12.528 GB/s. |
| 128 MiB pinned GPU0-to-host | 12.0-14.5 GB/s | Same probe: 13.143 GB/s. |
| 128 MiB pinned host-to-each helper | 0.37-0.43 GB/s | Same probe: 1060 and 1070 both about 0.400 GB/s. Other helpers report the same Gen2 x1 width. |
| 128 MiB pinned each helper-to-host | 0.39-0.45 GB/s | Same probe: 1060/1070 about 0.418 GB/s. |
| GPU0-to-helper copy | 0.35-0.43 GB/s, host staged; no direct peer access expected | Same probe: 0.386 GB/s for the tested helpers. |
| Guarded host RAM allocation | At least 95% of the run's auto-calculated decimal-GB target; likely `target_reached`, with `MemAvailable` at least 4 GiB and swap growth under 256 MiB. | [26 GB decimal RAM probe](results/runtime_experiments/host_ram_budget_26gb_decimal_20261103/terminal.json) reached its target. The live preflight's target was 25.13 GB; the actual run recalculates it. |
| NVMe sequential write, 512 MiB | 0.25-0.45 GB/s | The [64 MiB direct-I/O smoke](RIG_LIMIT_TEST.md) measured 0.358 GB/s; a longer write may differ. |
| NVMe sequential read, 512 MiB | 0.32-0.45 GB/s | The same smoke measured 0.403 GB/s. The NVMe sits on a Gen2 x1 link in [rig performance notes](RIG_PERFORMANCE.md). |
| NVMe random 4 KiB read, queue depth one | 6,000-12,000 IOPS | The same smoke measured 8,589 IOPS over 4,096 reads. |

Operational prediction: all selected GPUs will remain below the existing
1,024 MiB busy threshold before the transfer probe, the Manager lease will be
granted, and the hardware-detail, link, RAM, and storage stages will pass.

Comparison rules: use the saved `plan.json` for the actual auto RAM target and
GPU identity. Compare the 128 MiB rows in `link/copies.csv` by PCI bus, not CUDA
ordinal. Use `ram/terminal.json` and `storage/stage.json` for the other values.
Report each miss and any stage failure; do not widen these ranges after seeing
the result. A result inside a predicted range supports only this rig and these
probe settings.
