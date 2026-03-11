# Current Benchmark Procedure

Archived: 2026-03-10. Original standalone procedure doc before merge into README.md.

This is the current benchmark operating procedure.

Use this doc when you are actually running tests.
Do not improvise alternate runtime paths unless you are explicitly doing recovery work.

## Goal

Run repeatable tests across multiple models, record the results in one place, and keep benchmark setup aligned with the orchestrator.

## Active Scope

This procedure is currently for worker testing, not brain testing.

Assumptions:
- the brain model remains loaded on GPU 0
- GPU 0 is the control plane for benchmark mode, not the benchmark target
- worker model state changes happen through orchestrator-managed meta tasks so runtime ownership stays unified
- if you need ad-hoc runtime experiments, do them on a cold worker with a temporary runtime and do not replace the normal worker-testing path

## Canonical Inputs And Outputs

Inputs:
- model archive: `/media/bryan/shared/models/`
- benchmark catalog: `/media/bryan/shared/plans/shoulders/benchmarking/benchmark_catalog.json`
- suite presets: `/media/bryan/shared/plans/shoulders/benchmarking/suite_presets.json`
- task-profile recommendations: `/media/bryan/shared/plans/shoulders/benchmarking/model_task_library.json`

Outputs:
- raw scored runs: `/media/bryan/shared/plans/shoulders/benchmarking/results/model_benchmark_records.jsonl`
- living reference: `/media/bryan/shared/plans/shoulders/benchmarking/results/MODEL_BENCHMARK_REFERENCE.md`
- latest-only machine-readable scoreboard: `/media/bryan/shared/plans/shoulders/benchmarking/results/model_library_scoreboard.json`
- per-model tuning profiles: `/media/bryan/shared/plans/shoulders/benchmarking/model_tuning_profiles.json`
- backend/test certification status: `/media/bryan/shared/plans/shoulders/benchmarking/benchmark_status.json`
- per-run logs and harness outputs: `/media/bryan/shared/logs/benchmarks/`

## Operating Rules

1. Start benchmark sessions through the orchestrator.
2. Load and unload worker models through orchestrator `meta` tasks only.
3. Keep benchmark mode isolated from normal default operations.
4. Record every scored run in the shared benchmark ledger.
5. Treat the generated reference as the living scoreboard.
6. Certify backend/test compatibility before assuming a suite is runnable.

## Step 1: Put The Rig In Benchmark Mode

Normal benchmark start:

```bash
python3 ~/llm_orchestration/scripts/benchmarks/start_benchmark_mode.py
```

Or start with explicit worker models:

```bash
python3 ~/llm_orchestration/scripts/benchmarks/start_custom_mode.py \
  --force-unload-first \
  --models qwen3.5:4b qwen2.5-coder:7b qwen3.5:9b-q3km mistral:7b-instruct deepseek-r1:7b
```

Verify active agents:

```bash
pgrep -af "brain.py|gpu.py"
pgrep -af "brain.py|gpu.py" | grep config.benchmark.json
ss -ltnp | grep -E ':1143[0-9]|:11440|:11441'
```

## Step 2: Prepare Model Storage

```bash
python3 /media/bryan/shared/scripts/manage_model_hotset.py report
python3 /media/bryan/shared/scripts/manage_model_hotset.py promote-gguf \
  --gguf /media/bryan/shared/models/<family>/<file>.gguf \
  --name <model:tag> --host 127.0.0.1:11436
python3 /media/bryan/shared/scripts/manage_model_hotset.py evict \
  --host 127.0.0.1:11436 --keep <model:tag>
```

## Step 3: Prepare Runtimes Deterministically

```bash
python3 /media/bryan/shared/plans/shoulders/benchmarking/prepare_benchmark_runtimes.py \
  --clear-orphan-queue-locks \
  --strict-processing-empty \
  --force-unload-first \
  --restart-agents-first \
  --brain-endpoint 127.0.0.1:11434 --brain-model qwen2.5-coder:32b \
  --single-endpoint 127.0.0.1:11436 --single-model qwen2.5-coder:7b \
  --split-endpoint 127.0.0.1:11441 --split-model qwen2.5-coder:14b \
  --split-candidate-group pair_4_5
```

## Step 3B: Measure Worker Context Headroom

```bash
python3 /media/bryan/shared/plans/shoulders/benchmarking/context_window_benchmark.py \
  --config /media/bryan/shared/agents/config.benchmark.json \
  --workers gpu-2 \
  --start-words 800 --step-words 800 --max-words 20000
```

## Step 4: Choose The Tests

```bash
python3 /media/bryan/shared/plans/shoulders/benchmarking/certify_benchmark_backend.py \
  --id gsm8k --model local-chat-completions \
  --model-args "model=qwen2.5:7b,base_url=http://localhost:11436/v1/chat/completions,api_key=ollama"
```

```bash
python3 /media/bryan/shared/plans/shoulders/benchmarking/run_lm_eval_task.py \
  --id gsm8k --model local-chat-completions \
  --model-args "model=qwen2.5-coder:7b,base_url=http://localhost:11435/v1/chat/completions,api_key=ollama,eos_string=<|im_end|>" \
  --apply-chat-template
```

```bash
python3 /media/bryan/shared/plans/shoulders/benchmarking/run_local_custom_task.py \
  --id custom_command_safety --model qwen2.5:7b --base-url http://localhost:11436
```

## Step 5: Record Results

```bash
python3 /media/bryan/shared/plans/shoulders/benchmarking/record_benchmark_result.py \
  --model qwen2.5-coder:14b --test-id gsm8k --score 0.721 \
  --metric exact_match --harness lm_eval --suite baseline_core
```

## Step 6: Review The Living Results

```bash
python3 /media/bryan/shared/plans/shoulders/benchmarking/build_model_library_scoreboard.py
```

## Step 7: Feed Results Back Into Plans

```bash
python3 /media/bryan/shared/plans/shoulders/benchmarking/recommend_plan_models.py \
  --plan /media/bryan/shared/plans/arms/<plan_name>/plan.md \
  --output /media/bryan/shared/logs/benchmarks/<plan_name>_model_recommendations.json
```

## Recovery Rules

Reset sequence:

```bash
python3 ~/llm_orchestration/scripts/benchmarks/start_default_mode.py --json
python3 ~/llm_orchestration/scripts/benchmarks/start_benchmark_mode.py --json
```

## Current Known Compatibility Limits

As of 2026-03-09:
- qwen3.5:4b and qwen3.5:9b load attempts failed
- qwen2.5-coder:14b split on pair_4_5 unstable
- host chat runtime works for generation + custom tests with --apply_chat_template
- MC/loglikelihood tasks need bench-knowledge docker lane
- lighteval has dependency conflict
- swebench/livecodebench/bfcl/harbor not yet set up

## End Of Run

```bash
python3 ~/llm_orchestration/scripts/benchmarks/start_default_mode.py
```
