# Model loading stage (Phase L)

Phase L records whether an **exact model quant, runtime and placement recipe** is usable before capability benchmarking. It sits after registration and first-load checks and before Phase 6 smoke in [NEW_MODEL_INTEGRATION.md](NEW_MODEL_INTEGRATION.md). The registry's `status` remains the deployment decision; `loading_stage.state` is only the readiness of the tested recipe. A model can be `candidate` and `ready_for_benchmark` at the same time.

## What to record

Add `loading_stage` to the model's [registry entry](model_registry.json) when new loading work begins. Use one of `in_progress`, `ready_for_benchmark`, or `blocked` for `state`; absence means **legacy/untracked**, not untested. Record the runtime and exact usable recipe, links to durable receipts, an honest limit, and the next step. A new quant belongs in its own registry entry when registered; never carry a loading result across different weights, engine builds, or placements without a new receipt.

For `in_progress`, `evidence` may start as an empty list and gain receipt paths as experiments finish. `ready_for_benchmark` needs at least one durable receipt.

```json
"loading_stage": {
  "state": "ready_for_benchmark",
  "runtime": "llama.cpp/b11669",
  "recipe": "GPU 0, 8K context, one slot, full GPU offload",
  "evidence": ["results/runtime_experiments/<receipt>.json"],
  "limits": "Only the listed placement and context were checked.",
  "next_step": "Small capability and application smoke."
}
```

**Simple llama.cpp path:** the existing managed load, litmus, and runtime characterization receipts are enough. Record the working recipe and any fit or output problem. No memory-tier sweep is required.

**Advanced path:** for a large MoE, partial offload, multiple GPUs, Strata pack, or split runtime, first verify the complete weight/pack bundle and capture the actual serving route. Measure only the placement questions relevant to that recipe: VRAM and host headroom, cold load, storage reads, useful prefill/decode, context depth, and multiple chats if the role needs them. A blocked fit is a useful result. Use the manager's lease/run path and link existing receipts rather than duplicating experiments.

The readiness question is deliberately small: **can this exact recipe load, answer a real request, release cleanly, and provide enough speed and capacity to justify a quality sample?** `ready_for_benchmark` authorizes only that sample. It does not claim the model is good, production-ready, or equivalent to an official benchmark setup. Keep quality scores in the benchmark ledger, never in this field.

Review the library without running a model:

```bash
python3 scripts/active/model_loading_status.py
python3 scripts/active/model_loading_status.py '<model-id>' --check-ready
```

The second command checks the state and that each linked repository receipt exists. It is a lightweight preflight for the tested recipe, not a new benchmark suite.

For existing models, add the field as they are touched; do not backfill every old entry from memory. `STRATA_MEMORY_TEST_PLAN.md`, `MODEL_LOADING_AND_CHAT_PLACEMENT.md`, and their receipts hold detailed experiments. The registry holds the current concise decision and links. This lets the library show what has been tried without turning the research log into a configuration file.
