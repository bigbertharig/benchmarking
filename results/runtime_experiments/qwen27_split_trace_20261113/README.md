# 27B weight split CUDA trace (2026-11-13)

Qwen3.6-27B-Q4_K_M decoded 64 tokens from the same saved F16 50K chat state with the chat on the 3090 Ti. The model's 3090 weight buffer stayed 11,538 MiB. Tensor split values identify the 1070 and 1060 shares; UUID, PCI bus, host ID, and CUDA ordinal are checked per stage. This is a profile of one decode window per placement, bracketed by the two-card control, not a full load or long conversation benchmark.

| Split (3090,1070,1060) | 1060 weight MiB | 1060 kernels / 64 tokens | 1060 D2H MB | Decode tok/s | Change vs control mean |
| --- | ---: | ---: | ---: | ---: | ---: |
| 8,2,0 before | 0 | 0 | 0 | 18.613 | — |
| 8,1.75,0.25 | 995 | 192 | 63.570 | 17.908 | −4.5% |
| 8,1.5,0.5 | 1,464 | 3,328 | 68.747 | 17.172 | −8.4% |
| 8,1,1 | 2,178 | 8,064 | 73.925 | 16.868 | −10.0% |
| 8,2,0 after | 0 | 0 | 0 | 18.891 | — |

The two-card controls average 18.752 tok/s. The smallest real 1060 share already runs a roughly 599 ms quantized matvec kernel total on that card: 64 costly `mul_mat_vec_q` launches, one per decoded token, plus 128 small kernels. Its 1060 D2H includes 64 transfers of 993,280 bytes, taking about 151 ms. **That transfer is relocated from the 1070**, which performs the same 64 transfers in the two-card controls. Across 1070+1060, D2H volume is 79.102 MB for the controls and 80.413 MB for every three-card stage. The 1060's H2D volume grows from 1.311 to 4.458 MB across its three shares. Combined worker copy durations remain roughly 202–205 ms, whereas summed worker kernel durations rise as the 1060 share grows. The totals contain overlapping device work and are not an additive wall-time model; the consistent trend supports 1060 compute and extra per-token launches as the larger penalty here, rather than added PCIe bytes.

The absolute tok/s differs from the earlier unprofiled 32K-cap sweep, so use this trace for within-campaign attribution. It does not prove an optimal placement rule for other model layers or contexts. A practical next experiment would compare a few nonuniform layer assignments at equal 1060 weight MiB, because the first assigned layers trigger a disproportionately costly matvec.

[Campaign](../../../campaigns/qwen27_split_trace_20261113.json), [terminal receipt](../model_loading_sequences/qwen27-split-trace-20261113/terminal.json), and five compact per-stage JSON files in this directory preserve the evidence. Raw Nsight `.nsys-rep`, `.sqlite`, logs, and CUDA maps are in `/mnt/shared/experiments/kv-matrix-20261107/qwen27_split_trace_20261113_*`. Replay wrapper: [run_qwen27_split_trace.sh](../../../scripts/integration/run_qwen27_split_trace.sh); summarizer: [summarize_nsys_split.py](../../../scripts/integration/summarize_nsys_split.py).
