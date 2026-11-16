# Rig limit test

This is the general rig starting survey. It reuses the rig's `rig observe`
map and the benchmark hardware-session schema, then runs the existing CUDA
copy-path and guarded host-RAM probes. An optional bounded direct-I/O test measures
one caller-selected storage path. The default `--scan small` adds model-free
weight, expert, KV and lookup work classes; `--scan deep` adds larger working
sets and simultaneous GPU traffic. See [SYNTHETIC_WORK_SCAN.md](SYNTHETIC_WORK_SCAN.md)
for the measurements and independent runner. The survey does not load a model
or infer token speed, context quality or chat limits.

First full survey: [prediction](RIG_LIMIT_PREDICTION_2026-11-15.md), [measured comparison](RIG_LIMIT_COMPARISON_2026-11-15.md), and [run receipt](results/runtime_experiments/rig_limits_20261115_v1/START_HERE.md).

## Start here on a new or changed machine

1. Run `check` to confirm the physical GPU map, available RAM, and selected
   storage path. Then run the guarded survey through the Manager.
2. Use `--scan small` for the first model simulation. Run `--scan deep` when a
   larger working set or shared GPU traffic may change the picture. Both
   presets use patterned data and load **no model**. The hardware scan and
   simulation are one managed command; do not rerun them for every model.
3. Choose a particular model and follow [New Model Integration](NEW_MODEL_INTEGRATION.md):
   research gate, exact quant download, registration, `rigctl fit`, real load,
   context checks, smoke, and the existing benchmark campaigns. Use this
   survey's `START_HERE.md` as hardware evidence for the initial fit estimate,
   then let the real model loading checks decide what works.

Completed examples: [small full survey](results/runtime_experiments/rig_work_small_20261115_v1/START_HERE.md)
finished in 3 minutes 12 seconds; [deep full survey](results/runtime_experiments/rig_work_deep_20261115_v1/START_HERE.md)
finished in 3 minutes 48 seconds. The [corrected deep work-only repeat](results/runtime_experiments/rig_work_deep_20261115_v2/START_HERE.md)
adds matched per-card solo and concurrent upload rates and passed in 59 seconds.
Use that repeat for contention interpretation; the first deep report had only
an aggregate copy rate, which mixes cards with very different link speeds.

## Check before running

Run on the rig from this repository:

```bash
python3 scripts/integration/rig_limit_test.py check --gpus all
```

`check` is read-only. It shows detected physical GPU indexes and UUIDs,
current memory, selected probes, and whether Docker and the existing CUDA link
binary are present. The link probe uses the existing
`/data/bench-staging/cuda-link-probe` binary by default; override with
`--link-binary PATH`. Build it from
`scripts/integration/cuda_link_probe.cu` using the command at the top of that
file if it is missing. Choose `--gpus 0,2` to measure only selected host cards.
The script selects by host index only at scan time and freezes the corresponding
UUID and PCI bus in `session_hardware.json`.

## Run

Start a new run through the Manager's `rigctl run-start` path, on an idle rig.
For example, from the Pi:

```bash
python3 ~/llm-gateway/tools/rigctl.py run-start \
  --run rig-limits-YYYYMMDD \
  --cwd /mnt/shared/plans/shoulders/benchmarking \
  -- python3 scripts/integration/rig_limit_test.py run \
  --output results/runtime_experiments/rig_limits_YYYYMMDD \
  --scan small --gpus all --storage-dir /data/bench-staging
```

Use a fresh run ID and output directory. The runner obtains a Manager lease
for the selected GPUs and refuses GPU probing if the Manager is unreachable.
The existing copy probe checks power caps and refuses GPUs using more than
1,024 MiB. RAM is touched in 256 MiB steps with a 4 GiB `MemAvailable` guard
and swap-growth stop. Its default target derives from live available memory;
`--ram-target-gb N` sets a smaller decimal-GB target. The optional storage
probe requires at least the probe size times four plus 2 GiB free and uses
Linux `O_DIRECT` against a temporary 512 MiB file in `--storage-dir`. It
measures sequential read/write and 4 KiB random reads at queue depth one,
then removes only that file. `--storage-size-mib N` changes the bounded file
size. It is a quick starting measurement, not a saturation test for deep NVMe
queues.
Use `--scan deep` for larger synthetic working sets and concurrent GPU copies,
or `--scan off` for the earlier hardware-only survey. The synthetic runner
builds its CUDA binary on the first run or when its source changes. The full
survey still writes one `START_HERE.md`, including model-free work timings.
Pass `--skip-link` or `--skip-ram` to omit a probe, and treat omitted probes as
unmeasured.

Read `START_HERE.md` in the output directory first. `plan.json` and
`session_hardware.json` identify the rig; `checkpoint.json` and
`terminal.json` show progress and completion. Each probe keeps its own logs,
data, and stage receipt. If the run is interrupted, inspect those receipts and
start a new output directory; it does not resume a partial stress run.

The report gives a **starting hierarchy**: use a GPU with adequate free VRAM,
then add helper GPUs when needed, retaining RAM and storage headroom. Its
128 MiB copy-path measurements can flag PCIe bottlenecks. They cannot rank GPU
compute or predict model throughput. Model placement, context depth, and chat
capacity belong to the later model tests documented in
[TIER_DIAGNOSTICS_AND_TEST_SERIES.md](TIER_DIAGNOSTICS_AND_TEST_SERIES.md).
