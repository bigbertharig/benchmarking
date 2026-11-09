# Qwen3.6 35B-A3B two-chat occupied-context curve (2026-11-09)

Run `qwen35-moe-two-curve-20261109` passed all six depths in one continuous model load. The exact NVMe GGUF was `Qwen3.6-35B-A3B-UD-Q4_K_XL.gguf` (22.85 GB). All weights were placed on RTX 3090 Ti GPU0; two independent Q4 KV contexts were allocated on GTX 1060 GPUs1 and 2 with a fixed **262,144-token worker capacity** each. GPU0 built each chat's next history and saved/restored its state to the corresponding 1060. The temporary GPU0 preparation context was right-sized to each depth in 8192-token increments. Private-code recall passed for each chat at each depth. Each speed window generated 64 tokens, first on worker1 alone, then on both workers concurrently, restoring the checkpoint between windows.

| Occupied depth | Solo worker1 tok/s | Two active: worker1 / worker2 tok/s | GPU0 prep + handoff to usable worker, worker1 / worker2 s | GPU0-to-1060 save/restore portion, worker1 / worker2 s |
| ---: | ---: | ---: | ---: | ---: |
| 16,384 | 37.22 | 38.46 / 38.44 | 14.22 / 13.93 | 0.35 / 0.37 |
| 32,768 | 23.32 | 23.67 / 23.59 | 15.19 / 16.60 | 0.64 / 0.65 |
| 50,000 | 16.95 | 17.03 / 17.00 | 17.25 / 19.41 | 0.95 / 0.96 |
| 100,000 | 9.34 | 9.37 / 9.30 | 53.22 / 56.33 | 1.85 / 1.85 |
| 150,000 | 6.44 | 6.38 / 6.38 | 61.98 / 67.52 | 2.75 / 2.74 |
| 200,000 | 4.91 | 4.92 / 4.90 | 70.71 / 78.79 | 3.64 / 3.63 |

`usable` is incremental wall time from starting the GPU0 preparation context through restoring the resulting state on a worker. It is not the elapsed time to create the entire 200K chat from scratch: each later depth continues the prior saved history. The `GPU0-to-1060` portion includes state capture, destruction of the temporary GPU0 context, and restore on the worker, not just PCIe transfer. The run also wrote checkpoint files and performed recall after `usable`; `CHAT_ADD_METRIC total_seconds` includes those costs (17.34/16.99 s at 16K and 91.44/99.68 s at 200K). Initial weight loading took 38.61 s on this run. The six-point Manager stage ran from 02:38:16 to 02:51:15 UTC (12m 59s), including preparation, recalls, checkpoint I/O, and speed windows.

The two active worker speeds closely match solo worker1 speed at each depth. This supports two-way chat isolation for this placement; it does **not** establish five-way scaling at the same speeds. The per-chat decode rate drops by about 7.8x from 16K to 200K. The 16K/32K points are matched anchors for later expert-placement tests; extrapolating a changed placement to longer histories remains a hypothesis until measured. The short prompts are repeated synthetic field notes plus private-code recall. A 64-token window measures steady decode in this workload, not long-form agent quality or a complete turn latency.

Durable evidence: `terminal.json` in this directory; manifest `campaigns/qwen35_moe_two_curve_20261109.json`; raw log and GPU/PCIe samples under `/mnt/shared/experiments/kv-matrix-20261107/qwen35_moe_two_curve_20261109.*`; per-depth worker checkpoints under the adjacent `.states` directory. Each depth emitted `DEPTH_DONE`, both `RECALL_RESULT final_pass=1`, `CHAT_ADD_METRIC`, and `GEN_METRIC` for solo/two-active windows.
