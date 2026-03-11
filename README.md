# Benchmarks

This folder is the benchmark hub for the rig. It defines which models we test,
which tests and suites we run, how to run them, and where results live.

## File Map

### Docs
- This file: entry point, architecture, procedure, everything
- [MODEL_LIBRARY.md](MODEL_LIBRARY.md): operator-facing model selection, latest scores, prompt methodology
- [archive/docs/BENCHMARK_HISTORY_pre_archive.md](archive/docs/BENCHMARK_HISTORY_pre_archive.md): lessons learned and prior failures (archived 2026-03-10, run data moved to docker suite histories)
- [custom_tasks/README.md](custom_tasks/README.md): local custom test definitions and prompt tuning
- [docker/README.md](docker/README.md): test execution lives here — each suite has its own README, prompt config, and run history
- Archived docs: [archive/docs](archive/docs)
- Session report archive: [archive/reports](archive/reports)

### Scripts
- Active implementations: `scripts/active/`
- One-off and legacy scripts: `archive/scripts/`
- Root-level `*.py` files are compatibility wrappers that forward to `scripts/active/`

### Data and Config
- Runtime config: `config.benchmark.json`
- Per-model tuning profiles (includes universal system prompts): `model_tuning_profiles.json`
- Model catalog: `models.catalog.json`
- Benchmark catalog: `benchmark_catalog.json`
- Suite presets: `suite_presets.json`
- Backend certification status: `benchmark_status.json`
- Task-model routing: `model_task_library.json`

### Results
- Canonical ledger (append-only): `results/model_benchmark_records.jsonl`
- Human-readable reference (latest scores): `results/MODEL_BENCHMARK_REFERENCE.md`
- Machine-readable scoreboard (latest-only): `results/model_library_scoreboard.json`
- Per-run harness outputs (includes prompt snapshots): `/media/bryan/shared/logs/benchmarks/`
- Per-suite run histories: `docker/bench-*/BENCH_*_HISTORY.md`

### Datasets
- Cached benchmark repos: `repos/`

### Archive
- Archived docs: `archive/docs/`
- Archived reports: `archive/reports/`
- Archived snapshots: `archive/snapshots/`

## Testing Scope

Benchmarking is split into two scopes:
- **worker testing**: 6 GB worker-tier models, worker-safe pipeline behavior, single-worker and split-worker runtime behavior
- **brain testing**: GPU 0 brain model quality, planning quality, orchestration tradeoff quality

Current focus: **worker testing only**.
- the brain model stays loaded on GPU 0
- GPU 0 is the control plane, not a benchmark target
- worker model state changes happen through orchestrator-managed meta tasks
- brain testing gets its own procedure and score sheet when we turn to that phase

## Prompt Configuration

Prompts are managed in two layers. See [MODEL_LIBRARY.md](MODEL_LIBRARY.md) "Prompt Methodology" for full details.

- **Universal system prompt** per model (deploys with the model):
  `model_tuning_profiles.json` → `system_prompt` field
- **Test-specific prompt overrides** (for tuning experiments):
  `custom_tasks/model_prompt_profiles.json` → `test_overrides`
- **Historical prompt data** (what prompt was used for each past run):
  archived in each run's `result.json` → `prompts_snapshot` and per-case `system_prompt_used`

## Runtime Environments

Different tests require different inference backends. Run each test in the environment it was designed for.

| Environment | What It Runs | Docker Suite | Status |
|---|---|---|---|
| **Host llama chat runtime** | Generation lm_eval tasks (gsm8k, bbh, drop, math_500, aime_2024) + custom tests | `bench-pipeline`, `bench-reasoning` | Working |
| **llama.cpp gguf container** | MC/loglikelihood tasks (mmlu, arc_challenge, hellaswag, boolq, piqa, winogrande, truthfulqa_mc2) | `bench-knowledge` | Primary path |
| **evalplus container** | HumanEval+, MBPP+ | `bench-code` | Available, revalidation pending |
| **lighteval** | mmlu_pro, ifeval | — | Partially installed |
| **swebench** | swe_bench_verified | — | Needs setup (defer) |
| **livecodebench** | livecodebench | — | Needs setup (defer) |
| **bfcl** | bfcl_v4 (function calling) | — | Needs setup |
| **harbor** | terminal_bench_2 | — | Needs setup (defer) |

Why multiple backends: the host llama chat runtime matches how workers normally serve
generation tasks. The llama.cpp gguf container exists because MC/loglikelihood tasks
need a direct completions/logprob path. Results are comparable because model weights
come from the same GGUF files under `/media/bryan/shared/models/`.

### Chat Template Standardization

All benchmark runs must use the correct chat template for the model family.

| Model Family | HF Tokenizer | Template Format |
|---|---|---|
| qwen2.5-coder | `Qwen/Qwen2.5-Coder-7B-Instruct` (or 14B/32B) | ChatML (`<\|im_start\|>...<\|im_end\|>`) |
| qwen2.5 | `Qwen/Qwen2.5-7B-Instruct` (or 32B) | ChatML |
| qwen3.5 | TBD — verify after load issues resolved | TBD |
| mistral | `mistralai/Mistral-7B-Instruct-v0.2` | Mistral `[INST]...[/INST]` |
| deepseek-r1 | TBD — verify on first benchmark run | TBD |
| phi4 | TBD — verify on first benchmark run | TBD |
| gemma3 | TBD — verify on first benchmark run | TBD |

Rules:
- Always pass `--apply_chat_template` for lm_eval runs on the host llama chat runtime
- For vLLM, the tokenizer auto-applies the template — verify it matches
- Record the tokenizer used in every benchmark run
- If two backends produce different scores for the same model+test, check template application first

### Suite-to-Environment Mapping

| Suite | Environments | Tests |
|---|---|---|
| `baseline_core` | Ollama, vLLM, evalplus | gsm8k, mmlu, arc_challenge, hellaswag, winogrande, truthfulqa_mc2, humaneval_plus |
| `fast_smoke` | Ollama, vLLM | gsm8k, boolq, piqa, hellaswag |
| `reasoning_heavy` | Ollama, vLLM, lighteval | gsm8k, bbh, drop, arc_challenge, truthfulqa_mc2, mmlu_pro |
| `coding_heavy` | evalplus, livecodebench, swebench | humaneval_plus, mbpp_plus, livecodebench, swe_bench_verified |
| `agent_reliability` | Ollama | all 6 custom tests |

Build a suite file:

```bash
python3 /media/bryan/shared/plans/shoulders/benchmarking/build_benchmark_suite.py \
  --preset baseline_core \
  --output /media/bryan/shared/plans/shoulders/benchmarking/suites/baseline_core.json
```

### Environment Setup Priority

1. **vLLM** — unblocks baseline_core, fast_smoke, reasoning_heavy
2. **evalplus** — unblocks coding_heavy partially, completes baseline_core
3. **lighteval** — completes reasoning_heavy
4. **swebench, livecodebench, bfcl, harbor** — defer until core suites work

### Deferred Environments

**swe_bench_verified** (swebench, Docker):
~500 verified GitHub issues from popular Python repos. Model writes a patch that passes the repo's test suite. Metric: `resolved_rate`.

**livecodebench** (livecodebench harness):
Competition-style problems published after training cutoffs. Guards against benchmark leakage. Metric: `pass@1`.

**terminal_bench_2** (harbor, Docker):
89 curated tasks in Docker containers (protein assembly, async debugging, security, sysadmin). Model gets a terminal. Metric: `task_success_rate`.

**bfcl_v4** (bfcl harness):
Function/tool calling accuracy: simple, parallel, multi-turn, multi-step. Metrics: `ast_accuracy`, `exec_accuracy`.

## Model Inventory

Shared archive: `/media/bryan/shared/models/`
Hot-set management: `/media/bryan/shared/scripts/manage_model_hotset.py`

### 6GB worker tier

| Model | Archive Family | Status |
|---|---|---|
| `qwen2.5-coder:7b` | `qwen2.5-coder-7b` | tested |
| `deepseek-r1:7b` | `deepseek-r1-7b` | downloaded |
| `mistral:7b-instruct` | `mistral-7b-instruct` | available |
| `qwen3.5:4b` | `qwen3.5-4b` | downloaded |
| `qwen3.5:9b-q3km` | `qwen3.5-9b` | downloaded |

### 12GB paired-worker tier

| Model | Archive Family | Status |
|---|---|---|
| `qwen2.5-coder:14b` | `qwen2.5-coder-14b` | tested |
| `deepseek-r1:14b` | `deepseek-r1-14b` | downloaded |
| `phi4:14b` | `phi-4-14b` | downloaded |
| `gemma3:12b` | `gemma-3-12b` | downloaded |

### 24GB brain tier

| Model | Archive Family / Source | Status |
|---|---|---|
| `qwen2.5-coder:32b` | `qwen2.5-coder-32b` | tested |
| `deepseek-r1:32b` | `deepseek-r1-32b` | downloaded |
| `qwen3.5:27b` | Ollama pull | testing |
| `qwen3.5:35b-a3b` | `qwen3.5-35b-a3b` | downloaded |

### Embedding

| Model | Archive Family | Purpose |
|---|---|---|
| `nomic-embed-text` | `nomic-embed-text` | embeddings |

### Model Storage Rules

- shared drive is archive storage, local Ollama storage is hot-set storage
- promote and evict models explicitly
- do not leave benchmark leftovers sprawled across endpoints

```bash
python3 /media/bryan/shared/scripts/manage_model_hotset.py report
python3 /media/bryan/shared/scripts/manage_model_hotset.py dedupe --prune-imports
python3 /media/bryan/shared/scripts/manage_model_hotset.py promote-gguf \
  --gguf /media/bryan/shared/models/<family>/<file>.gguf --name <model:tag> --host 127.0.0.1:11436
python3 /media/bryan/shared/scripts/manage_model_hotset.py evict \
  --host 127.0.0.1:11436 --keep <model:tag>
```

## Test Library

Canonical machine-readable definitions:
- `benchmark_catalog.json`
- `suite_presets.json`

| Category | Examples | Why |
|---|---|---|
| baseline reasoning | gsm8k, arc_challenge, bbh, gpqa_diamond | compare reasoning quality |
| QA and knowledge | mmlu, boolq, drop, truthfulqa_mc2, mmmlu | measure reliability and breadth |
| coding | humaneval_plus, mbpp_plus, livecodebench, swe_bench_verified | measure coding ability |
| tool and agent behavior | bfcl_v4, terminal_bench_2 | measure tool use and terminal competence |
| long context | longbench, ruler | measure long-context limits |
| local pipeline reliability | custom_json_schema_strict, custom_tool_plan_sequence, custom_command_safety, custom_ambiguity_handling, custom_orchestration_tradeoff, custom_long_context_extract | measure actual rig-specific behavior |

## Backend Certification

Certify backend/test combinations before assuming a suite is runnable.

```bash
python3 /media/bryan/shared/plans/shoulders/benchmarking/certify_benchmark_backend.py \
  --id gsm8k \
  --model local-chat-completions \
  --model-args "model=qwen2.5:7b,base_url=http://localhost:11436/v1/chat/completions,api_key=ollama"
```

Catalog audit:

```bash
python3 /media/bryan/shared/plans/shoulders/benchmarking/audit_benchmark_catalog.py
```

Backend profiles to certify separately:
- `llama_chat_completions_raw`
- `llama_chat_completions_templated`
- `llama_completions`
- `llama_cpp_gguf`

---

## Operating Procedure

Use this section when you are actually running tests.
Do not improvise alternate runtime paths unless you are explicitly doing recovery work.

### Step 1: Put the rig in benchmark mode

```bash
python3 ~/llm_orchestration/scripts/benchmarks/start_benchmark_mode.py
```

Or start with explicit worker models:

```bash
python3 ~/llm_orchestration/scripts/benchmarks/start_custom_mode.py \
  --force-unload-first \
  --models qwen3.5:4b qwen2.5-coder:7b qwen3.5:9b-q3km mistral:7b-instruct deepseek-r1:7b
```

Verify:

```bash
pgrep -af "brain.py|gpu.py"
ss -ltnp | grep -E ':1143[0-9]|:11440|:11441'
```

### Step 2: Prepare model storage

```bash
python3 /media/bryan/shared/scripts/manage_model_hotset.py report
python3 /media/bryan/shared/scripts/manage_model_hotset.py promote-gguf \
  --gguf /media/bryan/shared/models/<family>/<file>.gguf \
  --name <model:tag> --host 127.0.0.1:11436
```

### Step 3: Prepare runtimes deterministically

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

This clears stale locks, verifies queue safety, restarts agents, loads models sequentially,
and verifies each endpoint. Do not replace this with manual runtime launches.

### Step 3B: Measure worker context headroom (optional)

Use immediately after runtime prep when tuning ctx_size for the loaded model.

```bash
python3 /media/bryan/shared/plans/shoulders/benchmarking/context_window_benchmark.py \
  --config /media/bryan/shared/agents/config.benchmark.json \
  --workers gpu-2 \
  --start-words 800 --step-words 800 --max-words 20000
```

Outputs: `/media/bryan/shared/logs/benchmarks/context_window_benchmark_<timestamp>.{csv,json}`

Current persisted context policy (6GB worker tier):
- `qwen3.5:4b`: `ctx_size=16384`
- `qwen3.5:9b-q3km`: `ctx_size=16384`
- `qwen2.5-coder:7b`: `ctx_size=16384`
- `deepseek-r1:7b`: `ctx_size=16384`
- `mistral:7b-instruct`: `ctx_size=12288` (16384 not stable on 6GB)

### Step 4: Choose and run the tests

Run one lm-eval test:

```bash
python3 /media/bryan/shared/plans/shoulders/benchmarking/run_lm_eval_task.py \
  --id gsm8k \
  --model local-chat-completions \
  --model-args "model=qwen2.5-coder:7b,base_url=http://localhost:11435/v1/chat/completions,api_key=ollama,eos_string=<|im_end|>" \
  --apply-chat-template
```

Run one custom test:

```bash
python3 /media/bryan/shared/plans/shoulders/benchmarking/run_local_custom_task.py \
  --id custom_command_safety \
  --model qwen2.5:7b \
  --base-url http://localhost:11436
```

Run the full parallel worker suite:

```bash
/mnt/shared/plans/shoulders/benchmarking/start_parallel_worker_suite.sh \
  --background --use-model-prompts
```

Docker suite runs: see [docker/README.md](docker/README.md) for per-suite commands.

### Step 5: Record results

Scored runs land in:
- `results/model_benchmark_records.jsonl`
- `results/MODEL_BENCHMARK_REFERENCE.md`

Manual record:

```bash
python3 /media/bryan/shared/plans/shoulders/benchmarking/record_benchmark_result.py \
  --model qwen2.5-coder:14b --test-id gsm8k --score 0.721 \
  --metric exact_match --harness lm_eval --suite baseline_core
```

Rules:
- record the actual model tag used at the endpoint
- use the benchmark catalog test-id
- keep suite names stable for repeated comparisons
- do not scatter scores across ad-hoc markdown notes

### Step 6: Review results

Refresh the scoreboard:

```bash
python3 /media/bryan/shared/plans/shoulders/benchmarking/build_model_library_scoreboard.py
```

Update per-suite history files in `docker/bench-*/BENCH_*_HISTORY.md`.
Update latest scores in [MODEL_LIBRARY.md](MODEL_LIBRARY.md).

### Step 7: Feed results back into plans

```bash
python3 /media/bryan/shared/plans/shoulders/benchmarking/recommend_plan_models.py \
  --plan /media/bryan/shared/plans/arms/<plan_name>/plan.md \
  --output /media/bryan/shared/logs/benchmarks/<plan_name>_model_recommendations.json
```

### End of run

1. verify scores were recorded
2. inspect the living reference
3. clean endpoint hot-set if needed
4. return to default mode:

```bash
python3 ~/llm_orchestration/scripts/benchmarks/start_default_mode.py
```

---

## Recovery

If benchmark runtime state drifts:
1. stop manual changes
2. confirm `queue/` and `processing/` are clean
3. return to default cleanly
4. restart benchmark mode
5. rerun deterministic runtime prep

Reset sequence:

```bash
python3 ~/llm_orchestration/scripts/benchmarks/start_default_mode.py --json
python3 ~/llm_orchestration/scripts/benchmarks/start_benchmark_mode.py --json
```

Dashboard resets:
- **targeted**: `Reset selected GPU` — normal hard reset for one worker
- **full**: `Return To Default` — when multiple workers or task lanes are mixed up

Do not treat `reset_gpu_runtime` as the operator reset path — that is an agent-side
thermal recovery mechanism.

Compatibility and runtime-limit status is maintained in the living model document:
- [MODEL_LIBRARY.md](MODEL_LIBRARY.md) → `Known Compatibility Limits (Living)`

## Rules

- start benchmark sessions through the orchestrator
- load/unload workers through orchestrator meta tasks only
- keep benchmark mode isolated from normal operations
- record every scored run in the shared ledger
- certify backend/test compatibility before assuming a suite is runnable
- always use `--apply_chat_template` for host llama chat-runtime lm_eval runs
- do not run worker benchmarks by manually spawning unmanaged runtimes
- do not treat ad-hoc markdown notes as the canonical result store
- do not leave the result ledger unrecorded after a successful scored run

## Workflow Summary

```
maintain models → maintain tests → run controlled batches → record results → feed back into plans
```

The feed-back loop uses:
- `model_task_library.json`
- `recommend_plan_models.py`
