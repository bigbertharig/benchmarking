# Model loading stage (Phase L)

Phase L records whether we found a workable way to load an **exact model quant** and what context it can use before the full benchmark campaign. It summarizes the context-fit and depth work from Phases 2 and 8 in [NEW_MODEL_INTEGRATION.md](NEW_MODEL_INTEGRATION.md). The small Phase 6 smoke may be used to diagnose settings first. The registry's `status` remains the deployment decision; `loading_stage.state` only describes loading readiness. A model can be `candidate` and `ready_for_benchmark` at the same time.

## What to record

Add `loading_stage` to the model's [registry entry](model_registry.json) when new loading work begins. Use `in_progress`, `ready_for_benchmark`, or `blocked` for `state`; absence means **legacy/untracked**, not untested. Record the working runtime/placement, default context, highest configured context that passed the relevant check, and the basis for that limit. Keep experiment logs and receipts in the runtime research area, not in this library summary. A new quant gets its own entry when registered; do not transfer a loading result across weights or runtimes.

While work is `in_progress` or `blocked`, the context fields can be omitted until a usable limit is known. `ready_for_benchmark` requires them.

```json
"loading_stage": {
  "state": "ready_for_benchmark",
  "runtime": "llama.cpp/b11669",
  "recipe": "GPU 0, full GPU offload, one slot",
  "default_context": 8192,
  "context_limit": 16384,
  "context_basis": "A real load and answer passed at 16K; deep recall was not checked.",
  "limits": "Only the listed placement and context were checked."
}
```

**Simple llama.cpp path:** use the existing context-bounds check, managed load, litmus, and runtime characterization. Record the working recipe and context limit. No memory-tier sweep is required.

**Advanced path:** for a large MoE, partial offload, multiple GPUs, Strata pack, or split runtime, try candidate placements until one is useful or the model is blocked. Check the actual serving route, headroom, and context limit. Measure storage or concurrent chats only when they affect the intended role. Keep those detailed results in the existing loading experiment area; the registry records the chosen way to load and its limit.

The readiness question is deliberately small: **can this recipe load, answer a real request, and run at a useful context and speed?** For a long-context claim, check depth before recording that limit as usable. A configured maximum alone is a fit result, not proof of recall throughout that window. `ready_for_benchmark` means we can run capability tests at the recorded recipe; it is not a model-quality or production judgment.

Review the library without running a model:

```bash
python3 scripts/active/model_loading_status.py
python3 scripts/active/model_loading_status.py '<model-id>' --check-ready
```

The second command checks the state and that the recorded context is internally consistent with the model profile. It reads no experiment artifacts and runs no model.

For existing models, add the field as they are touched; do not backfill every old entry from memory. `STRATA_MEMORY_TEST_PLAN.md`, `MODEL_LOADING_AND_CHAT_PLACEMENT.md`, and their receipts hold detailed experiments. The registry holds only the current load decision and context limit.
