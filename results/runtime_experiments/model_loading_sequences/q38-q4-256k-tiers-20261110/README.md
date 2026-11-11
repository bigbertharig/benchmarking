# Qwen3.8 Q4 native 256K cap with a GPU0 chat: expert-tier comparison

The model GGUF metadata says `qwen4exp.context_length = 262144`. The [capacity pilot](../q38-q4-256k-cap-20261110/terminal.json) launched and served one 256K-cap INT8 KV chat on GPU0 with an 8 GiB resident expert RAM budget. Four subsequent placements used the same cap and repeated the same additive 16K/32K/50K requests. The actual prompt depths were **16,893 / 33,726 / 52,959 tokens**. This establishes that the native maximum *configured cap* works at these occupied depths; it does **not** prove a 256K occupied chat or retrieval at that depth.

All runs used the NVMe UD-Q4_K_XL shards, Strata CUDA12 engine 0.1.56, one slot, automatic prefill, drafting off, 768 MiB GPU0 reserve, and 256 generated tokens. The live chat stayed on GPU0 in every layout. The 1060 was used only for an expert cache in peer cases. The [capacity manifest](../../../../campaigns/strata_q4_256k_tier_capacity_20261110.json) and [tier manifest](../../../../campaigns/strata_q4_256k_tiers_20261110.json) are reusable.

| Layout | GPU0 expert cache | GPU1 expert cache | Expert RAM | Complete request s, 16/32/50K | Prefill tok/s, 16/32/50K | Generated tok/s, 16/32/50K | NVMe read GB, 16/32/50K |
| --- | ---: | ---: | ---: | --- | --- | --- | --- |
| INT8 KV, GPU0 only | 4,742 / 13.83 GiB | none | 8 GiB | 368 / 312 / 334 | 53.0 / 60.2 / 64.8 | 5.2 / 7.9 / 6.9 | 154 / 133 / 140 |
| INT8 KV, GPU0 only | 4,742 / 13.83 GiB | none | 12 GiB | 354 / 321 / 343 | 55.6 / 58.5 / 63.4 | 5.1 / 7.7 / 6.4 | 147 / 136 / 144 |
| INT8 KV, peer | 4,741 / 13.83 GiB | 1,783 / 5.21 GiB | 8 GiB | 396 / 347 / 353 | 56.5 / 58.3 / 63.2 | 2.7 / 4.4 / 5.3 | 159 / 144 / 148 |
| INT8 KV, peer | 4,741 / 13.83 GiB | about 5.21 GiB | 12 GiB | 402 / 350 / 349 | 57.2 / 57.5 / 65.3 | 2.4 / 4.4 / 4.7 | 160 / 147 / 145 |
| **Q4_0 KV, GPU0 only** | **5,225 / 15.24 GiB** | none | 12 GiB | **344 / 296 / 325** | **57.1 / 63.0 / 65.9** | **5.3 / 8.9 / 7.7** | **142 / 125 / 137** |

The physical NVMe readings are host-wide block-device deltas, not exact bytes consumed by a particular expert. SATA reads were 0.03-0.13 GB per request. Each depth is one request, so the table is a capacity and directional speed comparison, not a stable performance ranking. All 256 generated tokens were spent in `reasoning_content`; the requested visible ORCHID answer was not produced. The receipts establish load and timing, **not** final-answer correctness or Q4 KV quality.

At the native 256K cap, the GPU0 INT8 expert cache shrank from about 5,650 slots at the prior 64K cap to 4,742 slots. Reserving the larger chat therefore costs roughly 2.65 GiB of GPU0 expert capacity even when the prompt is only 16-53K. Increasing expert RAM from 8 to 12 GiB did not consistently reduce physical NVMe reads or request time. A peer 1060 increased total GPU expert capacity to 6,524 slots, but made every complete request slower, and reads did not fall. The engine warned of under 512 MiB free GPU0 VRAM near peer decode; x1 transfer cost and VRAM pressure need separate tracing before assigning cause.

Compact Q4_0 KV recovered about 1.41 GiB of GPU0 expert cache relative to INT8 at this cap and gave the best complete-request time at all three depths in this series. It is a chat-state quantization change, so verify answer quality before treating it as a default. The [sequence-end loaded-state receipt](final_loaded.json) confirms that this Q4_0 KV, 12 GiB expert RAM, GPU0-chat layout remained loaded after that sequence. A subsequent [8 GiB Q4 KV follow-up](../q38-q4-256k-q4kv-ram8-20261111/README.md) measured 362/299/332 s at 16/32/50K and left the 8 GiB layout loaded. The 12 GiB case had shorter complete requests at all three depths in these single series.

## Next probes

1. Repeat the best INT8 and Q4_0 KV cases with varied prompt contents and a visible-answer correctness check. The 256-token reasoning-only responses cannot validate chat quality.
2. Compare a 128K-cap GPU0 chat against 256K at the same 16/32/50K occupied depths to price the expert-cache capacity reserved for unused context.
3. Profile peer decode for GPU0 VRAM pressure, x1 traffic, cache hits and file misses. Tune a peer ranking or reserve only if the trace identifies a recoverable bottleneck.
4. The engine advertises fixed expert caches on up to three extra GPUs (`--expert-cache-device1..3`), but this launcher currently treats a multi-GPU selection as a model layer split unless using the single adaptive peer mode. Validate a no-layer-split launch path before any multi-1060 cache speed claim.
