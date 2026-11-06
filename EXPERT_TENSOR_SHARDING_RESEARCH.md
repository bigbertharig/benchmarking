# Tiered expert execution research

Status: research prototype, 2026-11-06. Benchmarking owns measurements and reproducibility. This is a candidate paper topic, not a claim of an end-to-end Strata plus M10 speedup.

## Repositories and boundaries

- [Benchmarking](https://github.com/bigbertharig/benchmarking): model and rig inventories, matched comparisons, correctness checks, receipts and conclusions. See [rig performance](RIG_PERFORMANCE.md), [Strata memory plan](STRATA_MEMORY_TEST_PLAN.md), [Coder Next sweep](results/runtime_experiments/coder_next_expert_sweep_20261106/README.md), [Nemotron sweep](results/runtime_experiments/nemotron_expert_sweep_20261106/README.md), and [Qwen3.8 real-weight tier probe](results/runtime_experiments/q38_tiered_expert_probe_20261106/README.md).
- [Strata](https://github.com/Niko1221/Strata): upstream tiered expert engine and its [implementation details](https://github.com/Niko1221/Strata/blob/main/docs/DETAILS.md). The [UD-Q4_K_XL guide](https://github.com/Niko1221/Strata/blob/main/docs/UNSLOTH_Q4.md) specifies model-specific packing and a 48 GB RAM minimum for normal setup. Treat compatibility as an explicit upstream/runtime capability, not something inferred from GGUF size.
- [m10dis](https://github.com/crgregersen/m10dis): original within-expert tensor slicing and peer/multicast design. Our comparison is described in its local contribution branch `research/mixed-gpu-expert-placement`, `docs/research/MIXED_GPU_EXPERT_PLACEMENT.md`. It is independent of the original M10 hardware and does not reproduce its end-to-end path.
- [Orchestration](https://github.com/bigbertharig/llm_orchestration): rig topology, model lifecycle and experimental launchers. [Gateway](https://github.com/bigbertharig/llm-gateway): request routing and placement selection. A future validated recipe belongs in orchestration; the gateway should ask for a model/context, not manipulate individual expert tensors.

## Capacity and placement rule

Inventory **model weights, n-gram/lookup table, KV/context, runtime buffers, and any converted pack** separately. A file on disk is not automatically resident in RAM. Summed VRAM is not a unified pool; each GPU must hold its assigned tensors and local overhead, and the runtime must support the proposed split.

For a quick capacity screen, calculate **usable VRAM + usable host RAM + engine-supported live storage** against **weights + n-gram table + KV at the requested context + runtime buffers**. Subtract local overhead on every GPU and a measured host reserve first. Count converted packs separately if they coexist with the source model. This is an upper bound on bytes available, not proof that the partition will execute or run at useful speed. Storage capacity is only part of the live inference sum when the serving engine can read the relevant tensors from storage during inference.

1. If the model at the requested context runs entirely on GPUs, use the fewest **measured-fast** cards that fit. Extra cards can slow decode.
2. If a host-RAM tier is needed, evaluate using **all useful available GPU capacity before placing more model data in RAM**. A four-card-plus-RAM plan should be compared with a six-card plan before accepting RAM offload. Do not assume that all six cards beat a different mixed placement: measure prefill, decode and total request time.
3. Reserve RAM for the OS/runtime before assigning weights. On the current 32 GB marketed rig, the tested planning ceiling is **26 GB decimal** (24.2 GiB) of new host-resident data, leaving roughly **6 GB decimal** (about 19% of marketed RAM) for the OS/runtime; require at least **4 GiB MemAvailable** after load and during work. The 10-20% reserve is a useful initial screen, not a universal constant. Other machines require their own reserve measurement.
4. Only a runtime that actually supports file-backed experts or lookup tables can use storage as an inference tier. Model files still need disk space even if inference is entirely VRAM resident.

The current gateway's llama RAM plan and managed Strata plan are each one-GPU paths. They do not yet search arbitrary GPU-plus-RAM-plus-storage placements. This note is the requirement for that future planner, not a statement that the manager already implements it.

## Existing evidence

| Experiment | What was measured | Result and limit |
|---|---|---|
| Coder Next 32K whole-expert placement | Same GGUF/runtime, 3090 plus five 1060s | Decode 27.0 -> 60.6 tok/s; 28.8K prompt plus 1,024 output wall 158.3 -> 150.3 s. This moves whole expert tensors with llama.cpp overrides, not m10dis row shards. |
| Nemotron 32K whole-expert placement | Same GGUF/runtime, 3090 plus four 1060s | Decode 19.0 -> 42.4 tok/s; full long request 170.8 -> 157.8 s. |
| Qwen3.8 Q2_0 one real expert | 3090 and 1/2/5 1060 worker shards, Q2_0 weights, independent CPU output | One worker: 338 us resident, 3,786 us RAM upload, 7,176 us direct NVMe. Five workers: 285/997/4,263 us. One worker has one timed run; 2/5 workers have two. This excludes attention, routing, KV and full-model scheduling. |
| Strata mixed-card full model | Qwen3.8 Q2_0 at 8K, matched 512-token warm requests | 3090 only 80.3 effective tok/s with 12.9 GiB expert file tier; 3090 plus five 1060s 38.0 with 2.5 GiB file tier. Fewer file reads did not guarantee faster output. |

## First reusable analysis path

The read-only tools [snapshot_expert_hardware.py](scripts/analysis/snapshot_expert_hardware.py), [inspect_expert_gguf.py](scripts/analysis/inspect_expert_gguf.py), and [summarize_expert_capacity.py](scripts/analysis/summarize_expert_capacity.py) produce a hardware snapshot, model tensor inventory, and arithmetic capacity bound. The current [survey receipts](results/runtime_experiments/expert_capacity_survey_20261106/) validate these on this rig and Coder Next. The bound reserves per-GPU headroom and a host-RAM fraction or measured cap, assigns an identified n-gram table to storage, and reports remaining bytes. **Its fit status is always unknown**: it does not know per-layer allocations, KV size, topology cost, pack support or whether the engine can execute the candidate split. It must never be used to launch a model directly.

Next implementation stages: (a) record a verified model architecture/quantization adapter, including hidden/intermediate dimensions and legal row-block alignments; (b) enumerate feasible tensor placements under per-card, RAM and storage budgets; (c) calibrate transfer and compute costs by hardware and quantization; (d) replay representative expert routing traces, including cold and warm misses; (e) validate the winner with matched full-model prompts, deep-context recall and final-answer correctness. Model-specific kernels can then be adapters to a common plan, rather than rewriting the planner for each model.

## Next full-model gate

The [expert tensor placement test plan](EXPERT_TENSOR_PLACEMENT_TEST_PLAN.md) selects a genuinely oversized Q4 capacity candidate, defines the VRAM/RAM/NVMe tensor controls and keeps all launch gates explicit. Rig limits and measured hardware remain in [RIG_PERFORMANCE.md](RIG_PERFORMANCE.md) and the [hardware survey](results/runtime_experiments/expert_capacity_survey_20261106/README.md). A genuine oversized end-to-end case remains an open experiment until the engine can safely execute it.

For a paper, keep architectural claims, microbenchmarks, full-model latency, quality/recall, and hardware-specific conclusions separate. Publish commands, revisions, quantizations, context, output length, link topology, memory residency, file-read counters and failures with each result.
