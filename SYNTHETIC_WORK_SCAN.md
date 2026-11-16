# Model-free rig work scan

Start with [RIG_LIMIT_TEST.md](RIG_LIMIT_TEST.md). The integrated survey takes
`--scan small` (default), `--scan deep`, or `--scan off`. The work scan measures
**classes of memory access and computation** without loading a GGUF or serving
a model. The rig survey owns the Manager lease, hardware guard, and combined
`START_HERE.md`; `scripts/integration/run_synthetic_work_probe.py` is an
independent runner so orchestration can reuse it with its own lease workflow.

## Work classes

| Class | Synthetic operation | Controlled comparison |
|---|---|---|
| Weight step | Touch a patterned float weight array and run the same GPU kernel, either resident or uploaded from pinned RAM on every step | Resident compute versus repeated host transfer plus compute on each card |
| Expert route | Route to 1 MiB patterned expert blocks; 80% of calls target four hot experts and 20% sample a wider tail; cache slots use LRU | GPU cache hits, RAM-upload misses, realized hit rate and mixed call latency |
| KV scan | One synthetic attention-like head reads 128 FP16 key and value elements per position | Access cost as occupied history grows on each card; it is not a full attention implementation |
| Lookup | Gather sixteen random 128-byte rows into one GPU result; run the same row pattern in pinned host RAM | Small random access plus one batched transfer, rather than bulk bandwidth |
| Storage lookup | Sixteen random rows from one temporary file via warm buffered reads or 4 KiB `O_DIRECT` reads | Page-cache hits versus physical-read class and I/O amplification |
| Concurrent copy | In the deep preset, run matched 32 MiB pinned H2D loops alone and then start them together | Per-card slowdown under shared traffic, including possible CPU scheduling and pinned-memory pressure |

The small preset uses 32 MiB weight arrays, a 64 MiB lookup table, 4K and 32K
KV positions, 32 synthetic experts with four GPU cache slots, and a 64 MiB
storage file. The deep preset uses 128 MiB weights, a 256 MiB table, 32K and
128K KV positions, 128 experts with sixteen slots, a 256 MiB storage file,
more samples, and simultaneous GPU transfers. Card tests run serially except
for the explicit concurrent-copy stage. All row contents are deterministic
patterns and checked after the GPU and host lookup operations.

## Run

From the Pi, use a fresh Manager run ID and output directory:

```bash
python3 ~/llm-gateway/tools/rigctl.py run-start \
  --run rig-work-small-YYYYMMDD \
  --cwd /mnt/shared/plans/shoulders/benchmarking \
  -- python3 scripts/integration/rig_limit_test.py run \
  --scan small --gpus all --storage-dir /data/bench-staging \
  --output results/runtime_experiments/rig_work_small_YYYYMMDD
```

Change `small` to `deep` and use a different ID and output directory for the
extended scan. `check --scan deep` prints the hardware plan without running a
probe. The first run builds `synthetic_work_probe.cu` in the local CUDA 12.9
development image and saves a source-hash marker beside the binary; subsequent
runs reuse it until the source changes. `--scan off` retains the original
hardware-only survey. A work-only invocation may use `--skip-link --skip-ram`,
but still requires a Manager lease through the integrated runner.

The independent runner accepts `--preset small|deep --gpus HOST_IDS
--output DIR [--storage-dir DIR] [--binary PATH] [--cuda-image IMAGE]`.
It verifies idle cards, power policy and physical PCI buses, but **does not
obtain a Manager lease**; its caller must own the GPUs. It mounts the binary
into an isolated, network-free CUDA container. This separation keeps the
measurement portable to a future orchestration workflow.

## Read the result

The combined `START_HERE.md` reports per-card median and p95 microseconds.
`synthetic/gpu.jsonl`, `synthetic/storage.json`, `synthetic/inventory.json`,
`synthetic/build.log`, `synthetic/gpu.log`, and the terminal receipt preserve
the raw work scan. Compare **the same operation and working-set size** across
locations. The expert hit rate in this scan is a controlled example, not a
prediction of a real router. Cached file reads are page-cache results; direct
4 KiB reads intentionally include read amplification for a 128-byte row.

These measurements give hardware cost curves, not tokens per second, real
model fit, model correctness, or a placement policy. Runtime-specific kernels,
tensor geometry, routing, batching, cache replacement and overlap change the
answer. The later model-specific stage maps actual components and access traces
onto these curves, then validates the candidate placement in a matched run.
The handoff is the existing [New Model Integration](NEW_MODEL_INTEGRATION.md)
playbook: a candidate's `fit_estimate` may cite this scan, while its real load
and context gates establish whether the chosen quant and runtime actually work.

Related existing probes: [tiered expert execution](results/runtime_experiments/q38_tiered_expert_probe_20261106/README.md),
[KV worker residency](results/runtime_experiments/kv_cache_residency_20261106/README.md),
[PLE lookup and bus](results/runtime_experiments/q38_ple_bus_probe_20261113/README.md),
and [transport fan-out](results/runtime_experiments/moe_transport_probe_20261106/README.md).
