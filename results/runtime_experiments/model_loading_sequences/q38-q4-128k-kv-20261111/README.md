# Qwen3.8 UD-Q4_K_XL: 128K-cap KV comparison (2026-11-11)

The [three-case campaign](../../../../campaigns/strata_q4_128k_kv_comparison_20261111.json) passed on the rig with one Qwen3.8 Flash-Next UD-Q4_K_XL model load per case. Every case used Strata 0.1.56 CUDA12, the same NVMe GGUF and expert profile, GPU0 (3090 Ti) for model and chat, a 12 GiB resident expert RAM budget, 768 MiB GPU0 reserve, one 131,072-token slot, automatic prefill, and MTP/drafting off. Only the KV format changed: INT8, K8V4, or Q4_0. The five 1060s remained idle. The additive prompts occupied **16,893 / 33,726 / 52,959 tokens** and requested 256 generated tokens each. The [sequence terminal](terminal.json), [comparison index](comparison.json), stage receipts, engine logs, response JSON, and tier traces are retained here.

| KV | GPU0 expert slots / GiB | Complete request s, 16/32/50K | Prefill tok/s, 16/32/50K | Generated tok/s, 16/32/50K | Physical NVMe read GB, 16/32/50K |
| --- | --- | --- | --- | --- | --- |
| INT8 | 5,350 / 15.60 | 343.2 / 310.2 / 326.0 | 57.3 / 60.3 / 67.4 | 5.3 / 8.3 / 6.3 | 141.9 / 131.5 / 136.1 |
| K8V4 | 5,469 / 15.95 | 343.4 / **303.5 / 298.2** | 58.0 / 62.0 / 70.2 | 4.9 / 8.1 / **10.6** | 140.7 / 128.1 / **126.2** |
| Q4_0 | **5,590 / 16.30** | **332.1** / 311.2 / 328.0 | 58.4 / 62.9 / 67.2 | 6.0 / 5.9 / 6.1 | 139.6 / 127.9 / 138.0 |

At 50K, K8V4 completed about 9% faster than INT8 and Q4_0 in this single series, with about 10-12 GB fewer host-wide NVMe reads. Q4_0 gave the most GPU0 expert capacity but did not win the 32K or 50K complete-request test. The three runs were sequential and cache warmth, expert routing, and OS page cache can change between them; each depth has one sample. These are observations, **not a stable speed ranking**. The host-wide block counters are not per-expert bytes.

For a prior-cap reference, the [256K INT8/12 GiB series](../q38-q4-256k-tiers-20261110/README.md) held 4,742 GPU0 expert slots and took 354 / 321 / 343 seconds at the same occupied depths. The 128K INT8 load held 608 more slots and took 343 / 310 / 326 seconds. The smaller reservation therefore recovered expert capacity, but the speed difference remains unreplicated. The 256K Q4_0/12 GiB case took 344 / 296 / 325 seconds; 128K Q4_0 is not uniformly faster. No request occupied 128K or 256K.

The timed 256-token requests again spent their output in reasoning and produced no visible final answer. Separate scored probes on each load asked for a sheep count, a Python exception, and recall of the ORCHID code word from the 50K history. **All 9/9 exact answers were correct**. The warm 50K recall took 17.3 / 18.3 / 15.6 seconds for INT8 / K8V4 / Q4_0. These deliberately easy checks establish visible-answer operation and simple long-history recall; they do **not** establish DROP/BBH quality or long-context precision equivalence.

The Manager sequence marked all stages passed, but its job exit stopped the final Strata service despite the freeze request. A direct control launch restored the same **128K Q4_0, 12 GiB expert RAM** layout. [Final loaded-state receipt](final_loaded.json) records healthy service, the live engine command, and GPU0 memory after restoration. The persistent six-card benchmark claim remains held.

Next: repeat INT8 and K8V4 in alternating order with at least two distinct prompt contents and short visible answers; examine expert cache hit/miss and NVMe traces at 50K. Use limited DROP/BBH questions before making a quality-dependent default choice. Q4_0's additional slots alone did not predict speed here, and its quality tradeoff is still unmeasured.
