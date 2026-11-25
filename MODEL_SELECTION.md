# Select a model

This is the current entry point for model choice. Model facts and decisions live in JSON, not in this guide.

| Question | Source |
|---|---|
| Which models and profiles are registered? | [`model_registry.json`](model_registry.json) |
| Which model currently fills a task role? | [`model_roles.json`](model_roles.json) |
| What were the measured scores? | [Generated benchmark reference](results/MODEL_BENCHMARK_REFERENCE.md) and its linked result records |
| What speed, memory, context, and power were measured? | [Runtime reference](results/RUNTIME_REFERENCE.md) and its linked receipts |
| Which tiered layouts have evidence? | [`load_recipes.json`](load_recipes.json), with each recipe's evidence links |
| How do I add or change a model? | [New model integration](NEW_MODEL_INTEGRATION.md) |

Choose a model by task and required context from the registry and roles. Compare the relevant measured results and their sample sizes; a 50-question suite is a screening result. Check the exact quant, runtime, context, and load recipe before making a Gateway offer. All registered `active` and `candidate` models are published to backend consumers. `active` permits routine dashboard offers and automatic assignment; `candidate` remains available for explicit tests. Benchmarking does not report whether a model is loaded now; use Gateway's ready roster and the rig's live observation for that.

The registry is the single model list for Benchmarking's published evidence. Orchestration's Planned standalone workflow also accepts local model/profile configuration with separate provenance; it does not rewrite this registry or its evidence. Roles, load recipes, and child-route settings refer to its model IDs; they are not alternate lists of models. `model_library_export.json` is the versioned, hash-checked publication. `models.catalog.json`, `model_tuning_profiles.json`, and consumer catalogs are generated projections. Edit the sources, export, review the diff, then sync consumers as described in [model-library contract](MODEL_LIBRARY_CONTRACT.md).

For a new or changed GPU host, run `rig scan` on the rig to refresh its hardware inventory, then follow [the rig limit survey](RIG_LIMIT_TEST.md). For a specific model, follow [new model integration](NEW_MODEL_INTEGRATION.md) and [placement testing](MODEL_LOADING_AND_CHAT_PLACEMENT.md). A saved scan describes hardware; `rig observe` describes current availability.
