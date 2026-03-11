# Llama Upgrade Audit

This file records the first repo pass for migrating the benchmarking folder to
the current llama-first, docker-guided system.

Date: 2026-03-09

## Decision Rule

- keep and upgrade: files that are part of the docker/container benchmark system
  or the current benchmark ledger/procedure flow
- keep as historical reference: results/history docs that still explain prior
  decisions
- archive: old manual benchmark helpers that depend on direct Ollama control and
  compete with the active system

## Keep And Upgrade

Docs:
- `README.md`
- `CURRENT_BENCHMARK_PROCEDURE.md`
- `MODEL_LIBRARY.md`
- `BENCHMARK_CONTAINERS.md`
- `DOCKER_REBUILD.md`
- `PLAN_FORMAT_INTEGRATION.md`
- `BENCHMARK_HISTORY.md`

Active runners and generators:
- `run_lm_eval_task.py`
- `run_local_custom_task.py`
- `certify_benchmark_backend.py`
- `compatibility.py`
- `build_benchmark_reference.py`
- `build_benchmark_suite.py`
- `record_benchmark_result.py`
- `recommend_plan_models.py`
- `context_window_benchmark.py`
- `prepare_benchmark_runtimes.py`

Container entrypoints:
- `docker/bench-reasoning/run.sh`
- `docker/bench-knowledge/run.sh`
- `docker/bench-code/run.sh`
- `docker/bench-pipeline/run.sh`

Data/config:
- `benchmark_catalog.json`
- `benchmark_status.json`
- `model_task_library.json`
- `suite_presets.json`
- `custom_tasks/cases.json`

## Keep As Historical Reference

- `benchmark_run_report_20260305.md`
- `llm_benchmark_plan.md`
- `llm_benchmark_testing_guide.md`
- `benchmark_audit_summary.json`
- `individual_tests.json`
- `individual_tests.backup.json`
- `suites/*.json`

These are useful for provenance and prior design choices, but they should not
be treated as the active operating surface.

## Archive

- `worker-benchmark.py`
- `gpu-pair-benchmark.py`
- `ollama_completions_proxy.py`

Reason:
- all three assume the old direct Ollama benchmark path
- they bypass the current orchestrator/runtime and container benchmark flow
- they create ambiguity about which benchmark procedure is current

## Immediate Gaps Found

- `BENCHMARK_CONTAINERS.md` still describes containers 1, 3, and 4 as host-Ollama based; that language needs a full llama-first rewrite
- `benchmark_status.json` and the generated reference still use old backend ids such as `ollama_chat_completions_templated`
- active container entrypoints had Ollama-specific reachability checks and naming even when they were already using `/v1/...` APIs
- `run_local_custom_task.py` was still hardwired to `/api/generate`

## First Pass Completed

- custom local task runner upgraded to `/v1/chat/completions`
- active docker run scripts renamed around runtime/llama semantics instead of Ollama-specific naming
- backend id derivation updated toward llama-first names for active paths

## Next Pass

- rewrite `BENCHMARK_CONTAINERS.md` from "host Ollama" to "host llama-compatible worker runtime"
- migrate `benchmark_status.json` backend ids and notes to llama-first naming
- regenerate the human-readable benchmark reference from the updated status file
