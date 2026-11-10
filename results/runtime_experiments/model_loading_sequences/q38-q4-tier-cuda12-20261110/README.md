# Qwen3.8 Q4 64K one-chat placement trials (2026-11-10 UTC)

The same NVMe UD-Q4_K_XL pack, one 64K slot, 8 GiB resident expert budget, automatic prefill, and additive 16K/32K/50K conversation were used. The baseline successfully ran on GPU0 only. The other placements reached launch-time hardware limits, so **there is no measured multi-GPU speed curve** from these runs.

| Run | Placement | Outcome |
| --- | --- | --- |
| [CUDA 13 auto](../q38-q4-tier-overnight-auto-20261110/terminal.json) | GPU0, INT8 KV | 16,893 / 33,726 / 52,959 occupied prompt tokens; 6.1 / 7.9 / 6.8 generated tok/s; 54.1 / 60.3 / 67.3 prefill tok/s; 354 / 312 / 324 s complete requests. |
| CUDA 13 auto | GPU0+one or all five 1060s | Launch failed: CUDA 13 engine has no sm_61 kernel. This was an engine-selection failure, not a placement speed result. |
| [CUDA 12 matched](terminal.json) | GPU0, INT8 KV | Same occupied depths; 5.0 / 10.3 / 12.0 generated tok/s; 55.3 / 63.8 / 68.9 prefill tok/s; 357 / 289 / 301 s complete requests. |
| CUDA 12 matched | GPU0+one 1060, INT8 KV | Layer split selected two early layers on the 1060. At 64K its stage had zero expert-cache slots and could not start verify. The log estimated 1,076 MiB more VRAM needed. |
| CUDA 12 matched | All six, INT8 KV or 32K RAM-streamed KV | Layer stages on 1060s had no room for the required expert tier. Both launch attempts failed. |
| [compact KV fit](../q38-q4-64k-q4kv-fit-20261110/terminal.json) | GPU0+one/all 1060s, Q4_0 KV, 128 MiB reserve | More of the load fit, but the two-GPU run failed at cuBLAS prompt-path creation and both six-GPU runs failed prompt-path VRAM fit. No decode sample. |
| [helper roles](../q38-q4-64k-helper-20261110/terminal.json) | GPU0 main plus one/five 1060 helpers, INT8 KV | This Strata build still made layer stages; it hit the same expert-tier fit limit. No independent expert-only helper result. |

Each speed is the engine's reported generated-token rate for a 256-token answer; it is **not a usable chat-response rate** here. All three baseline responses were consumed in `reasoning_content` and returned no visible `content`, so the ORCHID marker was not checked in a final answer. The runner's `passed` status establishes load, request completion, and timing only. Prefill and decode vary by cache warmth and context, so do not infer a smooth depth curve from these three samples.

The engine logs and `tier_trace` directories record actual layer order, cache slots, host/NVMe activity, and memory. CUDA12 was selected through `STRATA_COMPONENTS_DIR=/data/bench-staging/strata-v0.2.10/components-cuda12`; the first matrix accidentally used CUDA13 and is retained as a diagnostic receipt. The earlier forced-1024-prefill run was stopped after a very slow first prompt and is documented in [its README](../q38-q4-tier-overnight-20261110/README.md).

After the failed matrices, the 64K INT8 GPU0-only Q4 load was manually restored with CUDA13 and verified through `/health`; GPU0 held 23,493 MiB and the five 1060s were idle. The claim `qwen38-q4-frozen` still reserves all six cards. A failure-stage `rollback_exit: 0` did not leave a live service after the manager job ended, so do not treat rollback exit alone as freeze proof.

## Next discriminating probes

1. Keep the working 64K GPU0 load and vary only the expert RAM budget (for example 4/8/12 GiB), measuring cache hit rate, actual NVMe reads, prompt latency, and decode rate on the same request.
2. For a genuine multi-GPU stage test, reduce context and explicitly budget stage KV, prompt scratch, and expert cache on each 1060 before load. A 64K all-card INT8 split is beyond this build's observed fit boundary. If comparing at 50K occupied depth, preserve a cap above the actual 52,959-token prompt.
3. For user-visible speed/correctness, turn off thinking if the engine supports it or allocate enough output tokens for a final answer, and validate the marker. Keep that request separate from the 256-token timing series.
4. Verify freeze through `/health` after the manager job exits, not only through the stage rollback exit code.
