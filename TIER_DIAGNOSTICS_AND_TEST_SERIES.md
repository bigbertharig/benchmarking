# Tier diagnostics and test series

Use this workflow to compare model and chat placement across the scanned GPUs,
RAM, and NVMe. It adds a common measurement layer to the existing experiment
scripts. Keep the engine-specific receipt: the shared trace cannot infer tensor
residence, cache hits, token counts, or PCIe byte traffic by itself.

## Physical GPU identity and reusable probes

Host `nvidia-smi` indexes are physical selectors. Docker CUDA ordinals can differ
even with `--gpus all`: on the November 12 rig, host GPU1 is a 1060 but CUDA1
is the host GPU2 1070. Select cards by UUID and save the live index, UUID, and
PCI bus ID for every run. `cuda_device_map.py` maps requested host GPUs to
container CUDA ordinals by PCI bus; `hardware_inventory.py` scans the live
cards. Treat a run labeled only by a CUDA number as physically ambiguous.

The reusable [link probe](scripts/integration/run_cuda_link_probe.py) measures
pinned host-to-device and device-to-host copies and reports peer capability.
The [35B worker trace wrapper](scripts/integration/run_qwen35_decode_trace.sh)
accepts `KV_MODEL_HOST_GPU` and `KV_REPLAY_CHAT_HOST_GPU`, selects their UUIDs,
and profiles the worker kernels. `summarize_nsys_decode.py` reduces Nsight
SQLite output to compact timing JSON. The [chat replay wrapper](scripts/integration/run_qwen27_chat_latency.sh)
accepts `KV_HOST_GPU_IDS` and `KV_REPLAY_CHAT_HOST_GPUS`; use those for split
weights and concurrent chats. `run_ram_offload_comparison.py` accepts
`--min-selected-vram-mib` for deliberately small but real weight slices.
The named 35B and 27B replay modes still require their model-specific build
and saved states; these wrappers make hardware selection and diagnostics
reusable without claiming a model-independent replay engine.

See the [November 12 bottleneck study](results/runtime_experiments/gpu_bottleneck_study_20261112/README.md)
for the matched examples and the corrected physical-card mapping.

## A measured case

Record the actual model, quant, engine version, configured and occupied context,
slot count, weight/expert/KV placement, and cache budgets in a placement JSON.
`campaigns/placements/qwen38_q4_strata_gpu0_32k_2slot.json` is an example.
The placement is an experimental claim; verify physical residency with engine
logs, GPU allocation, and any available tensor maps.

Wrap the experiment:

```bash
python3 scripts/integration/tier_trace.py run --output TRACE_DIR --placement LAYOUT.json -- COMMAND
```

A wrapped probe can mark `load`, `prefill`, `decode`, `handoff`, or a
`chat_turn` by calling `tier_trace.mark(Path(os.environ["TIER_TRACE_DIR"]),
phase, "begin")` and a matching `"end"`. Put request usage and engine timings
in the end marker's `details` map. `run_strata_q4_multichat.py` now marks
its load and chat requests. Existing probes can opt in one at a time.

The trace saves 1-second samples of GPU memory, utilization, power, active
compute PIDs, host available memory, swap, and physical NVMe/SATA counters.
Its terminal receipt summarizes elapsed time, minimum available RAM, peak GPU
memory/utilization, and disk bytes per marked phase. Device counters include
other activity on the rig, so use a reserved, quiet rig for attribution.
`nvidia-smi` PCIe generation and width describe the link, **not transferred
bytes**. Use Nsight or engine copy instrumentation for traffic. Use engine
request timings for prefill and decode tok/s; phase wall time includes overhead.

Compare matched prompt, occupied history, output length, quant/KV, slot count,
and temperature. Separate cold load, cold prompt, warm continuation, and
steady 256-1000-token decode. A short warm continuation can report misleading
tok/s. Capture both first-token time and full-turn time when available.

## Back-to-back cases

`run_model_loading_sequence.py` accepts schema 2: one `defaults` object and
an ordered `cases` list. Case keys override defaults. GPU cases default to
`freeze: true`, so reserve a persistent claim with `--claim` or
`--session-gpus`. Specify `freeze: false` only when the next test truly
requires release. A case with `restart_loaded: true` and `--restart-loaded`
in its command may stop and replace a frozen service under the named persistent
claim; it skips a new lease because the live service is already busy. Use this
only for a controlled replacement of the claimed model.
Set `continue_on_failure: true` on independent fit probes so later variants
run even if one fails; the series still exits nonzero and lists failures. The runner stops on failure or a blocked case, resumes passed
cases only under the same manifest hash, and writes a single
`comparison.json` beside `terminal.json`. Each case retains its own stage
receipt, log, and tier trace for audit. A new manifest requires a new run ID.

```json
{
  "schema": 2,
  "name": "matched-cache-budget",
  "defaults": {
    "state": "ready",
    "gpus": [0],
    "timeout_s": 3600,
    "freeze": true,
    "trace": true,
    "placement": "campaigns/placements/qwen38_q4_strata_gpu0_32k_2slot.json"
  },
  "cases": [
    {"id": "baseline", "label": "8 GiB resident experts",
     "command": ["python3", "scripts/integration/my_probe.py", "--budget", "8"]},
    {"id": "variant", "label": "12 GiB resident experts", "baseline": "baseline",
     "command": ["python3", "scripts/integration/my_probe.py", "--budget", "12"]}
  ]
}
```

This is a **format example**, not a runnable Qwen campaign: changing a budget
requires a controlled engine restart, and each case must have a placement
record matching its true settings. Start with `--check`, then run through the
Manager's `rigctl run-start` path with a claim covering all GPUs planned for
the series. Use `--through CASE_ID` to stop after a case while keeping its
loaded state. `comparison.json` is the read-first index; individual receipts
are retained rather than merged away.

## Reuse across the model sizes

- 27B dense and 35B MoE: use the same phase names for GPU0 model computation,
  1060 attention, KV handoff, and solo/parallel decode. Keep the engine trace
  that separates kernels and transfers.
- 74B Nemo: record weight split, each card's VRAM, and which GPU holds each
  independent chat; distinguish preparation from per-token decode.
- 125B Qwen Strata: record GPU expert cache, RAM resident complement, file-tier
  reads, actual split layers and cache occupancy, cold prefill, and steady
  decode. Compare one and five 1060 layer splits with the GPU0 control;
  test native helper caches later as a distinct decode-only path. The Q4
  service stays frozen after the final scheduled variant.

See [main placement guide](MODEL_LOADING_AND_CHAT_PLACEMENT.md),
[MoE baseline reloads](MOE_CHAT_BASELINE_RELOAD_2026-11-09.md), and
[Strata memory plan](STRATA_MEMORY_TEST_PLAN.md).

The Qwen3.8 [tier campaign](campaigns/strata_q4_onechat_tier_overnight_20261110.json)
is a concrete schema-2 example with four placements and
`continue_on_failure: true`. It uses the persistent `qwen38-q4-frozen`
claim to restart the frozen Strata model between cases. Its all-card RAM-KV
case tests live RAM streaming, while NVMe remains the expert and n-gram
backing tier. A stopped/parked chat file is not live NVMe attention.
