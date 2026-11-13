# 1060 versus 1070 for one resident Qwen3.8 expert (2026-11-13)

The managed campaign selected the 3090 Ti and one Pascal worker by physical UUID, then ran 1060 / 1070 / 1060 stages. It reused the existing, independently verified Qwen3.8 Flash-Next Q2_0 layer-0 expert sample (1,382,400 packed bytes) and Q2_0 CUDA probe. Each mode used 20 warmups and 100 timed calls. All six modes in every stage passed numerical comparison with the independent CPU reference (maximum absolute error 1.19e-8). The three-stage campaign passed and released its GPU claim.

| Weight source and compute | 1060 before mean µs | 1070 mean µs | 1060 after mean µs | 1070 change versus control mean |
| --- | ---: | ---: | ---: | ---: |
| Expert resident in worker VRAM | 352.4 | 333.5 | 348.7 | 4.9% less latency |
| Upload expert from pinned RAM each call | 3,794.6 | 3,794.4 | 3,798.5 | 0.1% less latency |
| Direct NVMe read and upload each call | 7,142.6 | 7,177.8 | 7,128.1 | 0.6% more latency |
| Expert resident on 3090 control | 159.8 | 160.0 | 159.9 | effectively tied |

The resident-worker medians are closer: 335.3 and 337.1 µs for the two 1060 controls versus 331.8 µs on the 1070. Thus the mean advantage is partly tail behavior, not a demonstrated 30–40% per-call improvement. When the full 1.38 MB expert moves over the Pascal x1 link on every call, 1060 and 1070 times are indistinguishable. This supports transport dominating the **upload** mode. The resident mode still includes per-call host-mediated input/output transport and dispatch, and this probe did not split those from GPU kernel time.

This is one small Q2 expert call, without router, multi-layer scheduling, hot-set misses, context/KV, or concurrent chats. The separate 35B KV-worker tile test found a 22% 1070 decode gain at 50K. Neither result predicts a Qwen3.8 full-model 3090+1070 expert-cache speedup. An actual full-model expert placement should compare route-selected throughput and storage reads at equal context and expert-cache budget, with per-card kernels and transfers traced.

[Campaign](../../../campaigns/q38_expert_card_20261113.json), [terminal receipt](../model_loading_sequences/q38-expert-card-20261113/terminal.json), and [compact stage timings](q38_expert_card_20261113_summary.json) preserve the result. Raw stage logs, selected UUIDs, inventory and start/finish markers remain at `/mnt/shared/experiments/kv-matrix-20261107/q38_expert_card_20261113_*`. Replay wrapper: [run_q38_expert_card_probe.sh](../../../scripts/integration/run_q38_expert_card_probe.sh).
