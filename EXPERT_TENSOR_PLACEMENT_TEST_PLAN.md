# Expert tensor placement experiment

Status: design and preflight, 2026-11-06. This experiment consumes the rig profile in [RIG_PERFORMANCE.md](RIG_PERFORMANCE.md) and the [read-only hardware survey](results/runtime_experiments/expert_capacity_survey_20261106/README.md). Those sources own the rig specifications. This document owns the candidate model, placement matrix, measurement protocol, and admission gates. The broader cross-repository research is in [EXPERT_TENSOR_SHARDING_RESEARCH.md](EXPERT_TENSOR_SHARDING_RESEARCH.md).

## Resume here: Q4 Strata and expert placement

This is the entry point for the next rig session. The [Strata baseline and Q2 controls](STRATA_MEMORY_TEST_PLAN.md), [tensor-sharding research](EXPERT_TENSOR_SHARDING_RESEARCH.md), and [rig limits](RIG_PERFORMANCE.md) provide the surrounding evidence. The upstream [UD-Q4_K_XL setup guide](https://github.com/Niko1221/Strata/blob/main/docs/UNSLOTH_Q4.md) defines this quant's pack format. Do not describe an unrun combined Strata-plus-M10 prototype as a measured speedup.

**Current handoff (2026-11-07):** the pinned Q4 download on the 4 TB drive passed per-shard SHA-256 in `/mnt/shared/models/qwen3.8-flash-next-ud-q4_k_xl/download_terminal.json`. The canonical four shards total 111,334,654,784 bytes. The copy to `/data/model-hotset/qwen3.8-flash-next-ud-q4_k_xl/` completed at 02:38:47 UTC; `results/storage_inventory_20261106/q4_nvme_stage.json` records `complete` and `verified` for all four shards. The 4 TB source stays in place. The runtime pack and Q4 full-model baseline have not yet been recorded, nor has a combined worker run.

The Q4 runtime pack belongs under the same model folder at `/data/model-hotset/qwen3.8-flash-next-ud-q4_k_xl/runtime/strata-ud-q4_k_xl/`. Once all four shards are verified on NVMe, build it from shard 1 with the installed Strata control Python:

```bash
STRATA=/data/bench-staging/strata-v0.2.10
MODEL=/data/model-hotset/qwen3.8-flash-next-ud-q4_k_xl
"$STRATA/control/python/bin/python" "$STRATA/control/tools/iq_pack.py"   --gguf "$MODEL/Qwen3.8-Flash-Next-UD-Q4_K_XL-00001-of-00004.gguf"   --out "$MODEL/runtime/strata-ud-q4_k_xl" --compat-bf16
```

The Q4 guide specifies about 1.4 GB for this pack and **no** `experts.bin`: experts are read directly from the GGUF files. Do not pass `--experts-bin`, which would create a roughly 77 GB duplicate and exceed the available NVMe headroom. Preserve the pack and its hash manifest with the four shards as one model bundle. The shared Strata expert profile is at `$STRATA/control/data/expert-profile.bin`; an MTP draft is optional for the first matched run and should be disabled unless its asset and memory budget are verified.

Before allocating GPU memory, run the read-only model inventory and capacity screen below. Write new receipts under a dated `results/runtime_experiments/q38_q4_expert_*/` directory and record the code revision, shard hashes, context, each GPU's usable memory, host budget and file-tier bytes. The rig's tested host planning ceiling is 26 GB decimal, including all new resident allocations.

```bash
cd /mnt/shared/plans/shoulders/benchmarking
STRATA=/data/bench-staging/strata-v0.2.10
MODEL=/data/model-hotset/qwen3.8-flash-next-ud-q4_k_xl
OUT=results/runtime_experiments/q38_q4_expert_preflight_20261107
mkdir -p "$OUT"
python3 scripts/analysis/snapshot_expert_hardware.py --output "$OUT/hardware.json"
python3 scripts/analysis/inspect_expert_gguf.py --gguf "$MODEL"/*.gguf   --gguf-py "$STRATA/install/third_party/llama.cpp/gguf-py" --output "$OUT/model.json"
python3 scripts/analysis/summarize_expert_capacity.py --hardware "$OUT/hardware.json"   --model "$OUT/model.json" --ram-budget-gb 26 --output "$OUT/capacity.json"
```

Then follow the [execution sequence](#execution-sequence-and-durable-evidence): non-allocating Strata plan; below-48-GB one-3090 Strata launch with an initial 8 GiB resident budget; same-file llama.cpp control if safely loadable; standalone real-expert worker correctness; and finally a matched 32K full-model comparison under an exclusive rig lease. The installed Strata CUDA 13 engine cannot run GTX 1060 `sm_61` workers directly. The combined test requires a separate 1060 worker bridge or engine extension. The Q2 one-expert and full-model receipts are controls, not Q4 results.

## Question and model selection

**Primary experiment:** retain Strata's model loader, bounded expert RAM cache, and file-backed expert/lookup tiers, then add M10-style expert placement/sharding across the 3090 and 1060s. Ask whether that changes full-model latency and physical storage reads without losing correctness. Use the **same GGUF bytes and context** in every comparable full-model run. Record actual tensor residency, not only a requested budget.

The primary capacity candidate is **Qwen3.8 Flash-Next UD-Q4_K_XL** (pinned Unsloth revision `38bb39ee97821de2c9009abb7e93950eec396e66`). Its [Strata guide](https://github.com/Niko1221/Strata/blob/main/docs/UNSLOTH_Q4.md) specifies 111,334,654,784 bytes across four shards, including a 28.8 GB decimal PLE/n-gram table and 71.7 GiB routed experts. The files are being staged on the 4 TB shared drive, with per-shard SHA-256 checks in `download_terminal.json`.

For a *capacity screen only*, the six-card survey reports about 49.49 GiB aggregate GPU budget after provisional per-card reserves and 24.04 GiB host budget from that snapshot. The Q4 file is about 103.69 GiB, so even putting its ~26.8 GiB table on storage leaves roughly **3.3 GiB beyond those GPU and RAM budgets**. KV, buffers, packing and per-card fragmentation make the real storage requirement larger. This arithmetic does **not** show that the current runtime can execute the placement.

**Workaround and admission gate:** the Q4 guide calls for at least 48 GB RAM for its normal setup, but explicitly allows `strata launch --family unsloth --model UD-Q4_K_XL --yes` below that recommendation. Its mapped mode uses `--resident-budget-gib` to keep a smaller set of hot experts in RAM and read the rest from the GGUF on storage. The download therefore has a real purpose on this 32 GB rig: test a controlled **3090 + limited RAM + NVMe** Q4 run before a multi-GPU optimizer exists. The first launch should request **8 GiB** resident experts, then measure actual total host use and physical reads; only raise the budget under the 26 GB decimal *total new host allocation* ceiling and 4 GiB `MemAvailable` guard. Keep the source shards on the 4 TB drive for verification, but a live cold-read comparison needs a deliberate NVMe hot copy with enough free space. The `--yes` switch bypasses setup's recommendation, **not** the rig's memory guard or any runtime allocation failure.

The installed Strata CUDA 13 engine does not support the GTX 1060's `sm_61` worker path, so the primary experiment requires a **custom expert-worker bridge or engine extension**: Strata keeps model execution, hot-expert cache, bounded host-resident experts, and file-backed misses; 1060 workers hold selected expert tensors or row shards and return partial results to the 3090's Strata execution. The worker implementation must preserve Strata's expert routing and numerical results and account for PCIe/host transport. This is the actual Strata-plus-M10 integration target, not a standard launch flag.

The rig also has a **separate llama.cpp placement control**: `llm_orchestration/shared/scripts/rig/experiments/qwen3_coder_next_expert_sweep.py` assigns whole expert tensors to 1060s with `--override-tensor` while the main CUDA split remains on the 3090. Adapt it for Q4 only to learn feasible per-card allocations, verify whole-expert placement and compare cost. A CPU-mapped tensor can be served from OS page cache or faulted from storage; this control does not implement Strata's explicit RAM/cache policy or m10dis row sharding. It is not the final combined runtime.

After download verification, inventory Q4 tensors and run non-allocating plans. The conservative Strata one-GPU launch establishes the Q4 RAM/storage baseline. A matched llama.cpp Q4 placement, if safely loadable, is a calibration/control. The combined Strata-plus-worker prototype must then be admitted under an exclusive lease, a 26 GB decimal total host ceiling and at least 4 GiB `MemAvailable`, with the same model bytes and prompt for comparison. Do not infer a runnable plan from aggregate bytes alone.

The existing **Qwen3.8 Q2_0** is the secondary control: it already runs with live NVMe-backed lookup/experts, and its one-expert and full-model Strata receipts exist. It can be forced through three tiers to study their costs, but its smaller weights do **not** intrinsically fill all available GPU and host capacity. Label any such result a constrained-tier comparison, not the oversized-model result.

## Target topology and the 48 GB distinction

The intended full experiment uses **3090 VRAM for dense/attention work and hot experts**, **the five 1060s as separately addressable expert-worker VRAM**, **safe system RAM for additional experts**, and **NVMe for remaining expert and lookup reads**. This is a useful capacity and scheduling target, but the 1060s are not host RAM: Strata's published 48 GB recommendation refers to physical host memory. Adding 24 GB of 1060 VRAM to 24 GB of system RAM does not make the existing Strata setup see 48 GB RAM. The documented `--yes` override is the first way to run below that recommendation.

Five 6 GB cards offer 30 GB nominal 1060 VRAM, but a 24 GB *usable* worker target must be checked per card after CUDA, transport, KV and per-worker buffers. The rig's 26 GB decimal host ceiling is for **all new host-resident allocations**, so assigning 24 GB to expert weights alone would leave only 2 GB for other new allocations and is too close to the measured edge. Begin with an 8 GiB Strata expert RAM budget; increase it only after measuring total host allocation and preserving the 4 GiB `MemAvailable` guard. The 3090 likewise needs space for dense weights, cache and context; its full 24 GB cannot be counted as free expert capacity.

Strata's current multi-GPU mode assigns layers and caches each card's layer experts. It is not the proposed 3090-plus-dedicated-1060-expert-worker architecture, and the installed CUDA 13 engine cannot execute `sm_61` kernels on the 1060s. The staged path is therefore: (1) verify Q4 on the 3090 plus bounded host RAM plus storage using Strata's documented override; (2) use the proven llama.cpp whole-expert tensor overrides as a placement control; (3) build and validate a 1060-compatible expert-worker bridge for Strata, using whole experts first and row shards where they improve placement or latency; (4) compare matched Strata-alone and Strata-plus-workers full-model requests. The 1060 extension needs an actual runtime integration, not a memory-budget flag.

## Controls and placement matrix

| Level | Same-model measurement | Why keep it |
|---|---|---|
| Pure VRAM, one extracted expert | Real packed expert weights and compute resident on a selected GPU | Establishes the compute floor and checks numerical parity. A whole Q4 model cannot use this placement on the rig. |
| VRAM plus RAM, same extracted expert | Upload or compute the same weights from host RAM on every invocation | Isolates the host boundary before adding storage and distinguishes transfer from compute. |
| VRAM plus NVMe, same extracted expert | Direct-read the same weights from the chosen NVMe, then execute | Isolates a cold storage miss. Repeat on SATA SSD only for a matched storage-device comparison. |
| GPU workers plus RAM and storage | Route real expert shards to available workers; record cache hits, misses and bytes by tier | Tests placement and shard scheduling. It is not a full-model result. |
| Full model, default engine vs new placement | Matched model, quant, context, prompt, output cap and warmed/cold-cache policy | Only this can support an end-to-end speed or quality claim. Run after the admission gate passes. |

The [Q2_0 one-expert receipt](results/runtime_experiments/q38_tiered_expert_probe_20261106/README.md) already provides the first three controls for that quantization on the 3090 and one/two/five 1060 workers. Its resident, RAM-upload and direct-NVMe timings should be reused. Repeat a tensor control for Q4 only if its different quantization or kernel path makes the Q2_0 control non-comparable; do not redo the whole small-model matrix for its own sake.

For a full placement, first seek the best **all-GPU fit**. If no all-GPU fit exists, use all *useful* available GPU capacity before host RAM, then put the unavoidable remainder on supported live storage. Compare candidate plans on prefill, decode, total request latency, physical device reads, `MemAvailable`, swap, and answer correctness. More cards are not automatically faster; the measured Strata Q2_0 mixed-card comparison found fewer file-tier experts but slower output on six cards.

## Execution sequence and durable evidence

1. Verify Q4's four shard hashes and enough **free** 4 TB/NVMe/SATA space for any pack or staging. Keep the source shards on the 4 TB drive until a validated hot-copy plan needs them. Record model SHA-256 and code/build revisions.
2. Run the GGUF tensor inventory and capacity screen. Record per-layer routed expert shapes and quant formats, PLE table bytes, KV/context reservation, each GPU's actual free memory, safe host budget and any duplicate pack bytes. Do not equate the file size with resident bytes.
3. Run a non-allocating Strata plan. Exercise the documented below-48-GB Strata `--yes` path with an initial 8 GiB expert RAM budget on GPU0. Separately prepare a llama.cpp `--override-tensor` placement control. Build the Strata-plus-1060 worker integration only after the standalone worker kernels and routing interface pass correctness checks. Lease exactly the GPUs used, cap and monitor host memory, stop if `MemAvailable` nears 4 GiB or swap grows materially, and preserve terminal receipts even on failure.
4. Use the existing Q2_0 controls and, if needed, a Q4 real-expert kernel control with fixed 20 warmups and 100 timed calls. Record maximum absolute error against independent CPU output, mean/median/p95, PCIe transfers, direct-read bytes and GPU allocation.
5. For an admitted full-model candidate, compare at one useful context (start at 32K), one short prompt and one long/depth prompt, with the same output cap and two warm repetitions plus a cold-read run. Preserve raw terminal receipts, server logs, per-tier allocation and physical block I/O counters. A later 256K run is a separate capacity/depth question.
6. Summarize quality and speed separately. Include failed fits and the exact memory limit that stopped them. Do not extrapolate tokens/s by multiplying the one-expert timings.

The rig inventory and 26 GB host limit remain in [RIG_PERFORMANCE.md](RIG_PERFORMANCE.md); the experimental results and failures belong under `results/runtime_experiments/` and should be linked here when complete.
