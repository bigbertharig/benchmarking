# Overnight model and chat placement probes — 2026-11-08

Manager run: `overnight-loading-probes-20261108`; job: `job-37d087143517`.
The [manifest](../../../campaigns/overnight_loading_probes_20261108.json) is run by the guarded, serial model-loading sequence. The regular `chat-27b` profile was unloaded before the job and must be restored after it reaches a terminal state.

## Scope

1. BigMoe Qwen3.8 Q2: one CPU/flash server load, 70 distinct notes each in A and B, then A → B → A → A. Per-turn usage, server completion events, wall time, memory and block counters are captured. Reopening A tests whether its earlier context must be prefetched again.
2. Route-selected Qwen3.8 Q2 expert: choose the most frequently routed layer-0 expert from the first half of the earlier decode trace, measure held-out coverage, extract the actual Q2 expert weights, and run the existing two-worker CUDA matrix for GPU-resident, RAM-upload, and direct-NVMe placement. This is a physical expert-kernel control, not an end-to-end route-aware model loader.
3. Qwen3.6 27B Q4: one weight load per layout, distinct field notes and A/B/A/C/A accumulation to roughly 16K/6K/10K positions, then simultaneous generation and recall in three independent contexts. Compare KV on separate 1060s with host-RAM KV. Caps are 32K per chat.
4. Strata Qwen3.8 Q2 KV growth: **capacity blocked before launch**. The installed `experts.bin` is 32 GiB, while the host had about 28 GiB `MemAvailable` at preflight. Installed KV growth requires the full expert set resident in host RAM and a one-GPU expert profile. The 4 GiB safety floor and 26 GB allocation ceiling would be exceeded. This is not a failed runtime test or a performance result.

The route-selected probe uses an existing trace, so its selected expert represents one prior prompt. Its CUDA timings cannot establish a full-model speedup. BigMoe route tracing is not used for a throughput comparison.

## Receipts

The sequence writes `terminal.json` and per-stage JSON files here. Each Python stage also writes a detail `terminal.json`; the 27B wrapper writes a `.log`, `.exit`, GPU memory sample, and PCIe sample under `/mnt/shared/experiments/kv-matrix-20261107/`. The normal chat service should be restored after the terminal receipt is recorded.
