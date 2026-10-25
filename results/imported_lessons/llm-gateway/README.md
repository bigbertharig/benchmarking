# Lessons

What this repo has learned from running the rig, kept here so it carries across sessions and machines, and
so benchmarking can read it. This is one half of how the four repos share knowledge without depending on
each other:

- **In:** benchmarking keeps its lessons in the model library (registry and roles). This repo's importer,
  `tools/generate_profiles.py`, reads the library and writes this repo's own `model_catalog.json` and
  `remote_profiles.json`.
- **Out:** this folder. Benchmarking (or anyone) reads it when it wants to; this repo never writes into
  another repo, and nothing here needs another repo to run.

## Files

| File | What | Written by |
|---|---|---|
| `load_observations.jsonl` | every load the manager placed (`kind: load`) or that failed (`kind: load_failed`): model, GGUF, micro-batch, use, cards by UUID with link and root port, the estimate per card, what llama.cpp allocated, memory in use once serving, load time, error and out-of-memory flag | the manager, on every load (`src/llm_gateway/manager/observations.py`) |

The manager also plans from this file (compute buffer and overhead per card size, failed-load ceilings:
`docs/MANAGER.md`, "Learning from loads"). It started on 2026-10-25 from the loads in the benchmarking
capacity records up to then; those rows carry `from_record` (the record's file name in benchmarking).

Append only. A row that turns out wrong is corrected by a later row, not edited. Commit it like any other
file.
