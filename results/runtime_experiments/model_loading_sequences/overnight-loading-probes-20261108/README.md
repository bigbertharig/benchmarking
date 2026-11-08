# Overnight model and chat placement probes — 2026-11-08

Manager run: `overnight-loading-probes-20261108`; job: `job-37d087143517`.
The [manifest](../../../campaigns/overnight_loading_probes_20261108.json) is run by the guarded, serial model-loading sequence. The regular `chat-27b` profile was unloaded before the job and must be restored after it reaches a terminal state.

## Scope

1. BigMoe Qwen3.8 Q2: one CPU/flash server load, 70 distinct notes each in A and B, then A → B → A → A. Per-turn usage, server completion events, wall time, memory and block counters are captured. Reopening A tests whether its earlier context must be prefetched again.
2. Route-selected Qwen3.8 Q2 expert: choose the most frequently routed layer-0 expert from the first half of the earlier decode trace, measure held-out coverage, extract the actual Q2 expert weights, and run the existing two-worker CUDA matrix for GPU-resident, RAM-upload, and direct-NVMe placement. This is a physical expert-kernel control, not an end-to-end route-aware model loader.
3. Qwen3.6 27B Q4: one weight load per layout, distinct field notes and A/B/A/C/A accumulation to roughly 16K/6K/10K positions, then simultaneous generation and recall in three independent contexts. Compare KV on separate 1060s with host-RAM KV. Caps are 32K per chat.
4. Strata Qwen3.8 Q2 KV growth: **capacity blocked before launch**. The installed `experts.bin` is 32 GiB, while the host had about 28 GiB `MemAvailable` at preflight. Installed KV growth requires the full expert set resident in host RAM and a one-GPU expert profile. The 4 GiB safety floor and 26 GB allocation ceiling would be exceeded. This is not a failed runtime test or a performance result.

The route-selected probe uses an existing trace, so its selected expert represents one prior prompt. Its CUDA timings cannot establish a full-model speedup. BigMoe route tracing is not used for a throughput comparison.

## Results so far

- BigMoe stage **passed**. The A and B first requests prefetched 1,463 and 1,464 tokens in 130.4 and 129.5 seconds. Reopening A after B prefetched 1,488 tokens in 131.6 seconds; immediate continuation of A prefetched only 22 tokens in 10.5 seconds. All four one-word responses were correct. At this history length, returning to an older chat costs a near-full prefill, while continuing the active chat reuses its current KV. These are CPU/flash timings with a warm server and are not comparable to a GPU resident model.
- The route-selected physical expert stage **passed**. Layer-0 expert 403 was the most frequent in the earlier first-half decode trace, but covered only 2.19% of held-out layer-0 routes. For this one real Q2 expert, median invocation was 159 µs on GPU0 resident, 277 µs with RAM upload, and 12,673 µs with direct NVMe read. The two-1060 row-shard modes were 328 µs resident, 2,017 µs RAM, and 14,362 µs NVMe. All six output checks matched the reference within about 1.5e-8 maximum absolute error. These are one-expert kernel timings; they do not imply full-model acceleration.
- Both deeper Qwen3.6 27B layouts **passed** with exactly one model weight load per layout. Before simultaneous generation, A/B/C had 16,408/6,168/10,264 occupied positions, respectively. Each chat generated 32 tokens concurrently, then all three concurrently recalled its own original code from the long history. Aggregate generation was 29.38 tok/s with KV on separate 1060s versus 12.76 tok/s with RAM KV; concurrent recall finished in 0.77 versus 1.22 seconds. These are one run per layout, with a fixed generated-token count and no normalization for physical KV size or separate first-token latency. The result supports independent growth and correct concurrent access, not a general speed ranking across all prompt depths.
- The sequence terminal status is `blocked` solely because the final Strata KV growth stage was intentionally capacity blocked. The four runnable stages all passed. The normal `chat-27b` Manager profile was restored and reported `ready` after the sequence.

## Receipts

The sequence writes `terminal.json` and per-stage JSON files here. Each Python stage also writes a detail `terminal.json`; the 27B wrapper writes a `.log`, `.exit`, GPU memory sample, and PCIe sample under `/mnt/shared/experiments/kv-matrix-20261107/`. The normal chat service should be restored after the terminal receipt is recorded.
