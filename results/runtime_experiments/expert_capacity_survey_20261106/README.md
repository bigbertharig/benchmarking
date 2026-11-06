# Expert capacity survey — 2026-11-06

This is a read-only capacity screen, not a model load or a speed benchmark. The hardware snapshot came from the rig; the GGUF inventories came from the Pi, using the existing llama.cpp GGUF reader. All JSON files in this directory are small committed receipts.

- `hardware_rig.json`: six GPUs, installed and currently available host RAM, PCIe link status and storage inventory. Current PCIe generation can drop at idle; use the reported maximum for the link ceiling.
- `qwen35_4b_model.json`: parser smoke check on a dense 4B GGUF; no routed expert tensors were found.
- `coder_next_model.json`: 45,531,949,088-byte Qwen3-Coder-Next Q4_K_S file and 48 routed-expert layers.
- `coder_next_capacity_bound.json`: arithmetic bound using the rig snapshot and Coder Next, with `--ram-budget-gb 26`. It reports 49.49 GiB aggregate GPU budget, 24.04 GiB host budget and zero live-storage-read floor under its assumptions. `fit_status` remains `unknown`.

Reproduce from the benchmarking repo, substituting the paths on the relevant machine:

```sh
python3 scripts/analysis/snapshot_expert_hardware.py --output results/runtime_experiments/expert_capacity_survey_20261106/hardware_rig.json
python3 scripts/analysis/inspect_expert_gguf.py --gguf /media/bryan/shared/models/qwen3-coder-next/Qwen3-Coder-Next-Q4_K_S.gguf --gguf-py /path/to/llama.cpp/gguf-py --output results/runtime_experiments/expert_capacity_survey_20261106/coder_next_model.json
python3 scripts/analysis/summarize_expert_capacity.py --hardware results/runtime_experiments/expert_capacity_survey_20261106/hardware_rig.json --model results/runtime_experiments/expert_capacity_survey_20261106/coder_next_model.json --ram-budget-gb 26 --output results/runtime_experiments/expert_capacity_survey_20261106/coder_next_capacity_bound.json
```

The analyzer subtracts provisional per-GPU reserves and the larger of 15% or 4 GiB host reserve. It uses installed GPU memory, so it is a *possible idle-system capacity bound*, not a snapshot of free placement capacity while other work is running. It does not calculate KV cache, per-device layer assignment, converted pack overlap, or Strata support. See [the research note](../../../EXPERT_TENSOR_SHARDING_RESEARCH.md).
