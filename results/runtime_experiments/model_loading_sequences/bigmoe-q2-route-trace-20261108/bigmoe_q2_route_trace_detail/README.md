# BigMoe Q2 expert routing diagnostic

The `bigmoe-q2-route-trace-20261108` sequence passed on 2026-11-08. The
BigMoe v0.40.1 CLI ran the NVMe-backed Qwen3.8 Flash Next Q2 model with an
8 GiB expert cache, CPU decode, and `--route-trace`. It generated 64 output
steps. The prompt asked for a voxel pagoda garden; the visible response
mentioned the path, pond, and lighting. The trace has 15,520 prefill and
30,720 decode routing rows across 48 layers. The CLI ran for 220.0 seconds.

The analysis ranks experts separately per layer using the first 32 decode
steps, then checks which routed experts appear in the next 32 steps. The
estimated weight budget uses the largest `expert_bytes` observation per layer
and excludes cache metadata and runtime buffers.

| Experts per layer | Estimated expert weights | Later-route coverage | Later-route weight coverage |
| ---: | ---: | ---: | ---: |
| 16 | 1.06 GB | 46.5% | 48.8% |
| 32 | 2.12 GB | 60.1% | 62.6% |
| 64 | 4.25 GB | 76.0% | 78.3% |
| 128 | 8.49 GB | 84.1% | 86.5% |

The in-sample top-64 coverage was 88.7%, illustrating why the later-token
check matters. These are route frequencies from one nearby-token split, not
observed cache hits, tensor placement, or measured speedups. A follow-up
should replay a route-derived 16/32/64-per-layer cache policy on new prompts
and compare physical reads and decode speed with the 8 GiB LRU baseline.

Evidence: [`terminal.json`](terminal.json),
[`trace_summary.json`](trace_summary.json),
[`heldout_summary.json`](heldout_summary.json), and
[`route_trace.csv`](route_trace.csv). The route trace perturbs timing, so this
run is diagnostic only.
