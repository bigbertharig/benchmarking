# 3090, 1060, and 1070 bottleneck study (2026-11-12)

This study asks why a 3090+1070 split did not always beat a 3090+1060 split, and which costs grow when a third card or a second chat is added. Four probes completed. The rig's physical IDs must be distinguished from Docker CUDA ordinals: host GPU0 = 3090 (PCI 01:00.0), host GPU1 = 1060 (03:00.0), host GPU2 = 1070 (0D:00.0), while Docker `--gpus all` exposed CUDA0 = 3090, CUDA1 = 1070, CUDA2 = 1060. The UUID and PCI bus mapping is saved with the corrected runs. The earlier [35B fallback replay](../qwen35_q41_1060_1070_matched_20261112/README.md) had its physical-card labels reversed; its result is a small **1060** solo advantage, not a 1070 advantage. The earlier 7B solo and 27B split comparisons used physical UUIDs and are unaffected.

## Results

| Probe | Matched result | What it establishes |
| --- | --- | --- |
| 35B MoE Q4_1 KV worker, tile attention, model weights on 3090 | At 16K occupied, 1060 **51.48** vs 1070 **58.51 tok/s**; at 50K, **29.78** vs **36.45 tok/s** (64-token decode windows). | With this kernel, 1070 improves decode by about **14%/22%**. It is not a model load, prefill, or long-turn comparison. |
| PCIe pinned transfers | At 128 MiB, host-to-1060 **0.4000 GB/s**, host-to-1070 **0.3999 GB/s**; 3090-to-either Pascal card via runtime host staging about **0.386 GB/s**. No direct peer access reported. | Both Pascal x1 links have essentially equal bulk bandwidth. Link rate alone does not explain their decode difference. |
| 27B dense weight-slice sweep, 32K cap | Two-card 3090+1070 control **20.77-20.79 tok/s**. Add a 1060 share of about 995 MiB: **19.50-19.81**; 1,464 MiB: **18.77-19.33**; 2,178 MiB: **18.42-18.59**. Control after **20.78-20.79**. | The first real third-card share costs about 5%; larger shares progressively cost more. This test cannot separate added 1060 compute from its transfers. |
| 35B two workers at 50K, both Q4_1 | Two 1060s: main pair **31.33/31.28**, secondary **31.10/31.00 tok/s** in bracketing controls. 1060+1070: main pair **29.42**, secondary **31.00**. Solo main 1060 stayed at **31.45-31.47**. | A faster secondary card did not improve concurrent per-chat decode here; the main fell about 6%. The shared cause needs a simultaneous trace before attribution. |

In the matched 35B worker trace, summed 50K worker attention time fell from **633.6 ms** on the 1060 to **453.4 ms** on the 1070 across 64 tokens, and Q4_1 dequantization fell from **723.3** to **505.3 ms**. The 3090 graph stayed near **371 ms** and worker H2D stayed **40.9 MB / 106 ms** on either card. These GPU activities overlap and must not be added into a wall-time budget. The different fallback build in the earlier replay was nearly tied and slightly favored 1060; kernel choice changes the card comparison.

## Evidence and replay

- [UUID-selected 35B trace campaign](../../../campaigns/qwen35_worker_card_uuid_trace_20261112.json), [series receipt](../model_loading_sequences/qwen35-worker-card-uuid-trace-20261112/terminal.json), and [compact per-stage timings](../qwen35_worker_card_uuid_trace_20261112/). Four stages passed. The reusable wrapper selects model and worker by physical UUID and records host inventory. The instrumented build lives under `/data/bench-staging/kvchat-q41-worker-card-trace-build` on the rig; raw Nsight reports and logs are in `/mnt/shared/experiments/kv-matrix-20261107/qwen35_worker_card_uuid_trace_20261112_*`.
- [PCIe probe v2](../gpu_link_paths_20261112_v2/) saved `copies.csv`, live inventory, CUDA mapping, diagnostics, and a passed terminal receipt. Reuse [run_cuda_link_probe.py](../../../scripts/integration/run_cuda_link_probe.py) with the generic CUDA binary; its [source](../../../scripts/integration/cuda_link_probe.cu) is in this repo.
- [27B boundary sweep campaign](../../../campaigns/qwen27_boundary_slice_20261112_v2.json), [series receipt](../model_loading_sequences/qwen27-boundary-slice-20261112-v2/terminal.json), and [stage results](../qwen27_boundary_slice_20261112_v2/). Five stages passed; each placement has two warm repeats. The `small_1060` case writes to a historical `tiny_1060` directory. Its predecessor [pilot receipt](../model_loading_sequences/qwen27-boundary-slice-20261112/terminal.json) rejected a tensor split that rounded the 1060 to zero layers; it is not performance evidence.
- [Two-worker campaign](../../../campaigns/qwen35_worker_contention_20261112.json) and [series receipt](../model_loading_sequences/qwen35-worker-contention-20261112/terminal.json). All three 1060+1060 / 1060+1070 / 1060+1060 stages passed at 16K/32K/50K; raw replay logs are in `/mnt/shared/experiments/kv-matrix-20261107/qwen35_worker_contention_20261112_*`.

The first [link pilot](../gpu_link_paths_20261112/) and first [worker trace pilot](../model_loading_sequences/qwen35-worker-card-trace-20261112/terminal.json) used CUDA ordinals as though they were host indexes; **do not cite their physical-card labels**. The UUID and PCI corrected v2 results above replace them. All receipts remain for audit.

## Next focused questions

1. Trace both workers **simultaneously** during the 1060+1070 pair. Compare GPU0 graph queueing, each worker kernel and copy timeline, and CPU scheduling with the two-1060 control. This isolates the shared-load penalty seen with the 1070 secondary.
2. For the 27B weight split, measure actual bytes and launch count over the 1060 x1 link as its share grows. Distinguish extra transfer from compute before designing a placement rule.
3. Keep CUDA kernel/build and saved state fixed when comparing card speed. The fallback and tile builds give different rankings, so a single card label is not a transferable performance rule. Use live UUID/PCI mapping for any swapped rig hardware.

The shared [tier diagnostics](../../../TIER_DIAGNOSTICS_AND_TEST_SERIES.md) describes the reusable inventory, trace, series, and receipt workflow. These are capability and bottleneck measurements, not a Manager load policy.
