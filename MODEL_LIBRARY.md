# Model Library

This is the operator-facing living doc for model selection, benchmark results,
and runtime best practices.

Use this together with:
- generated score ledger: `/media/bryan/shared/logs/benchmarks/MODEL_BENCHMARK_REFERENCE.md`
- raw records: `/media/bryan/shared/logs/benchmarks/model_benchmark_records.jsonl`
- machine-readable latest scoreboard: `/media/bryan/shared/plans/shoulders/benchmarking/results/model_library_scoreboard.json`
- model tuning profiles: `/media/bryan/shared/plans/shoulders/benchmarking/model_tuning_profiles.json`
- machine-readable task routing: [model_task_library.json](/home/bryan/llm_orchestration/shared/plans/shoulders/benchmarking/model_task_library.json)

Rules:
- update this doc when a model's practical operating envelope changes
- keep exact benchmark scores in the generated reference, not copied by hand into many files
- record stable operator guidance here: what loads, what fails, what ctx is safe, what each model is best at

Current phase:
- worker testing is active
- brain testing is deferred
- assume the brain stays loaded on GPU 0 and is used to coordinate worker meta tasks during benchmark prep

## Current Best Choices

| Task Profile | Preferred Model | Why | Fallback |
| --- | --- | --- | --- |
| structured extraction | `qwen2.5:7b` | cheapest worker-tier default for deterministic short outputs | `qwen2.5-coder:14b` |
| deep reasoning | `qwen2.5-coder:14b` | strongest currently validated reasoning option in the active worker/split set | `qwen2.5:7b` |
| code generation | `qwen2.5-coder:14b` | coder family is the current default for implementation work | `qwen2.5:7b` |
| code review | `qwen2.5-coder:14b` | better fit for bug-finding and patch reasoning | `qwen2.5:7b` |
| general QA | `qwen2.5:7b` | throughput-first worker default | `qwen2.5-coder:14b` |

## Startup Context Policy (Current)

Last validated: 2026-03-10

Saved config locations:
- `/home/bryan/llm_orchestration/shared/agents/config.json` (normal/default startup source)
- `/home/bryan/llm_orchestration/shared/agents/config.benchmark.json` (benchmark startup runtime)
- `/home/bryan/llm_orchestration/shared/plans/shoulders/benchmarking/config.benchmark.json` (benchmark repo copy)

Single-worker context policy:
- `qwen3.5:4b`: `ctx_size=16384`
- `qwen3.5:9b-q3km`: `ctx_size=16384`
- `qwen2.5-coder:7b`: `ctx_size=16384`
- `deepseek-r1:7b`: `ctx_size=16384`
- `mistral:7b-instruct`: `ctx_size=12288` (16384 load failed on 6GB)

Startup commands:
- default mode: `python3 ~/llm_orchestration/scripts/benchmarks/start_default_mode.py`
- empty mode: `python3 ~/llm_orchestration/scripts/benchmarks/start_empty_mode.py`
- custom benchmark load (5 models): `python3 ~/llm_orchestration/scripts/benchmarks/start_custom_mode.py --force-unload-first --models qwen3.5:4b qwen2.5-coder:7b qwen3.5:9b-q3km mistral:7b-instruct deepseek-r1:7b`

## Model Notes

### Live response sanity pass (2026-03-09)

Custom sequential load succeeded for all five worker targets (`qwen3.5:9b-q3km`,
`deepseek-r1:7b`, `qwen2.5-coder:7b`, `mistral:7b-instruct`, `qwen3.5:4b`) with
one-at-a-time `load_llm` meta tasks. Worker hold policy was set to
`max_hot_workers=5` so loaded models remain available for follow-on testing.

Prompt/formatting quirks observed from direct `/completion` probes:

- `Qwen2.5-Coder-7B-Instruct-Q4_K_M.gguf` (port `11437`):
  strong instruction compliance; returned exact strings and concise output.
- `Qwen3.5-9B-Q3_K_M.gguf` (port `11435`):
  generally responsive, but can prepend punctuation and sometimes repeats a short
  answer when asked for strict brevity.
- `DeepSeek-R1-Distill-Qwen-7B-Q4_K_M.gguf` (port `11436`):
  often ignores strict format constraints and expands into long unsolicited text;
  treat strict-output tasks as high-risk without strong stop/format guards.
- `Mistral-7B-Instruct-v0.3-Q4_K_M.gguf` (port `11438`):
  frequently drifts from exact-format prompts into unrelated continuations; use
  for open-ended prose, not strict machine-parseable output.
- `Qwen3.5-4B-Q4_K_M.gguf` (port `11439`):
  tends to emit chain-of-thought-like scaffolding (`<think>`) even on strict
  formatting prompts; requires stronger prompt constraints and post-parse checks.

Operator guidance from this pass:

- for strict JSON / exact token outputs, prefer `qwen2.5-coder:7b`
- treat `deepseek-r1:7b`, `mistral:7b-instruct`, and `qwen3.5:4b` as requiring
  defensive parsing and tighter prompt templates
- keep a post-response validator in benchmark harnesses for exact-output tasks

### Parallel worker suite tracking (last updated: 2026-03-11T07:09:52+00:00)

Latest run source:
- `/mnt/shared/logs/benchmarks/bench-pipeline/history/parallel_worker_suite_20260310_234145/results`

| Model | Total score | Percent | Total suite time (s) | Last tested (UTC) |
| --- | --- | --- | --- | --- |
| `Qwen2.5-Coder-7B-Instruct-Q4_K_M.gguf` | 58/79 | 73.4% | 121 | 2026-03-11T06:44:32+00:00 |
| `Mistral-7B-Instruct-v0.3-Q4_K_M.gguf` | 54/79 | 68.4% | 301 | 2026-03-11T06:47:32+00:00 |
| `Qwen3.5-4B-Q4_K_M.gguf` | 54/79 | 68.4% | 1641 | 2026-03-11T07:09:52+00:00 |
| `DeepSeek-R1-Distill-Qwen-7B-Q4_K_M.gguf` | 35/79 | 44.3% | 1221 | 2026-03-10T22:52:40+00:00 |
| `Qwen3.5-9B-Q3_K_M.gguf` | 11/79 | 13.9% | 2451 | 2026-03-11T01:43:52+00:00 |

Prompt A/B validation (run: `parallel_worker_suite_20260310_180300`):

| Model | A profile (`model_prompt_profiles.json`) | B profile (`model_prompt_profiles_B.json`) | Baseline decision |
| --- | --- | --- | --- |
| `Qwen3.5-4B-Q4_K_M.gguf` | 52/79, 789s | 14/79, 1570s | Keep A |
| `Qwen3.5-9B-Q3_K_M.gguf` | 11/79, 2451s | 7/79, 2600s | Keep A |

### Reasoning full-suite runtime estimates (no partial scores recorded)

Source runs (canceled before completion):
- `/mnt/shared/logs/benchmarks/parallel_reasoning_suite_20260310_112146`
- `/mnt/shared/logs/benchmarks/parallel_reasoning_suite_20260310_125816`

Estimated time to complete one full reasoning run (`4346` requests/model):

| Model | Estimated full run time |
| --- | --- |
| `Qwen3.5-4B-Q4_K_M.gguf` | est ~2h |
| `Qwen3.5-9B-Q3_K_M.gguf` | est ~3h |
| `DeepSeek-R1-Distill-Qwen-7B-Q4_K_M.gguf` | est ~3 to 4h |
| `Qwen2.5-Coder-7B-Instruct-Q4_K_M.gguf` | est ~5 to 7h |
| `Mistral-7B-Instruct-v0.3-Q4_K_M.gguf` | est ~5 to 7h |

### qwen2.5:7b

Status:
- active single-worker default id in config
- practical single-GPU profile now targets `ctx_size=16384` in [config.json](/home/bryan/llm_orchestration/shared/agents/config.json) and [config.benchmark.json](/home/bryan/llm_orchestration/shared/agents/config.benchmark.json)

Best for:
- structured extraction
- general QA
- low-cost worker throughput

Known results:
- `gsm8k`: 0.75 in `initial_matrix_20260305`
- `bbh`: 0.5556 in `initial_matrix_20260305`
- `drop`: 0.14875 in `initial_matrix_20260305`

Best practices:
- use for cheaper single-worker lanes where latency and capacity matter more than deep reasoning
- benchmark and operator paths still refer to this model id even when the loaded GGUF may be a coder-family file selected by runtime resolution
- prefer explicit chat templating for benchmark generation runs

### qwen2.5-coder:7b

Status:
- active 7B GGUF currently proven on the llama runtime
- best current single-GPU coding-oriented 7B option

Known results:
- `gsm8k`: 1.0 in `quick_triplet_l1_20260305`
- `drop`: 0.27 in `quick_triplet_l1_20260305`
- `custom_json_schema_strict`: latest recorded 0.5 in `local_custom_probe_v2`

Context findings:
- on 2026-03-09, direct llama runtime probes on a 6 GB worker succeeded at `ctx_size=12288`, `14336`, `15360`, and `16384`
- at `ctx_size=16384`, the runtime stayed healthy after a real `~7016` prompt-token query and peaked at about `5292 / 6144 MB`
- prior worker benchmark failure at about `1641` prompt tokens was a config ceiling problem from `ctx_size=2048`, not a VRAM ceiling

Best practices:
- use this as the reference 7B model when testing long-prompt worker behavior on llama
- `16384` is currently the benchmark-safe working target for 6 GB worker probing
- if you push beyond `16384`, do it on a cold GPU with a temporary runtime first, not on the orchestrator-owned default worker

### qwen2.5-coder:14b

Status:
- current preferred split-worker reasoning/coding model

Known results:
- `gsm8k`: 1.0 in `quick_triplet_l1_20260305`
- `drop`: 0.57 in `quick_triplet_l1_20260305`

Best practices:
- use for higher-quality coding/reasoning work when split capacity is available
- keep split runtime validation separate from single-worker tuning
- do not assume every candidate pair is stable; pair stability is still an operational variable

### qwen2.5-coder:32b

Status:
- brain-tier option, but currently underperforming in the small recorded sample

Known results:
- `gsm8k`: 0.0 in `quick_triplet_l1_20260305`
- `drop`: 0.18 in `quick_triplet_l1_20260305`

Best practices:
- do not treat parameter count as automatic superiority
- re-benchmark before promoting this model for quality-critical work

### mistral:7b-instruct

Status:
- available as an alternate 7B worker-tier model

Known results:
- `custom_ambiguity_handling`: 1.0 in `local_custom_probe_v2`
- `aime_2024` backend certification probe succeeded on 2026-03-05

Best practices:
- useful as a comparison model for instruction following and clarification behavior
- still needs broader apples-to-apples scoring against the active qwen family before promotion

### qwen3.5 family

Status:
- now loadable in custom sequential worker mode; response behavior still needs
  tighter prompt engineering for strict-format tasks

Best practices:
- use for exploratory/manual prompts first, then promote only after strict-format
  benchmark tasks (JSON/exact-match) are validated
- expect additional output normalization when used in machine-parseable flows

## Prompt Methodology

Prompts are managed in two layers:

### Layer 1: Universal system prompt (per model)

Each model has one universal system prompt that defines its baseline behavior across all tasks.
This is the prompt that deploys with the model for real work.

Where it lives:
- `model_tuning_profiles.json` → `models.<gguf_id>.system_prompt`

This prompt is tuned to address each model's known quirks (e.g. `<think>` tag leakage,
reasoning expansion, punctuation prepending). When a model graduates from "untuned" to
"tuned", it means this universal prompt has been validated across the full test suite.

### Layer 2: Test-specific prompt (per suite/test)

Each test suite can define its own prompt overrides per model. These let us experiment
with test-specific phrasing without changing the universal prompt.

Where it lives:
- `custom_tasks/model_prompt_profiles.json` → `models[].test_overrides.<test_id>`

When a test override exists, the runner uses it instead of the universal prompt for that
test. When no override exists, the universal prompt is used. This lets us learn what
works best per test category before folding improvements back into the universal prompt.

### Prompt history and archiving

The main library and tuning profiles hold only the **current** prompt for each model.
Historical prompt data lives in the per-run result archives.

Every run result (`result.json` in the per-run log directory) captures:
- `prompts_snapshot.resolved_system_prompt`: the exact prompt text used for this run
- `prompts_snapshot.resolved_source`: whether it came from the universal prompt or a test override
- `prompts_snapshot.default_system_prompt`: the fallback prompt at time of run
- per-case `system_prompt_used`: the exact prompt sent with each individual test case

This means you can always reconstruct "we ran test X with prompt Y and got score Z" from
any historical run without needing to know what the profiles looked like at that time.

Run archives live in:
- `/media/bryan/shared/logs/benchmarks/<suite_run_timestamp>/results/<test_id>_<timestamp>/result.json`

### Prompt tuning workflow

1. Start with the universal prompt in `model_tuning_profiles.json`
2. Run the full suite — identify which tests underperform
3. Add `test_overrides` in `model_prompt_profiles.json` to experiment with test-specific phrasing
4. Compare results across runs using the archived `prompts_snapshot` data
5. When an override consistently improves results, fold it back into the universal prompt
6. Remove the override — the universal prompt should be the final deliverable

## Known Compatibility Limits (Living)

Last updated: 2026-03-10

Model/runtime limits:
- `qwen3.5:4b`, `qwen3.5:9b-q3km`, `qwen2.5-coder:7b`, and `deepseek-r1:7b` load and run with `ctx_size=16384`
- `mistral:7b-instruct` is stable at `ctx_size=12288`; `16384` may fail to load on 6GB workers
- `qwen2.5-coder:14b` split baseline on `pair_4_5` is still unstable (warmup failures)

Host llama chat runtime:
- works for generation tasks with `--apply_chat_template`: `gsm8k`, `drop`, `bbh`, `math_500`, `aime_2024`
- works for custom pipeline tests via `local_custom` harness
- generation tasks are unreliable without `--apply_chat_template`
- MC/loglikelihood tasks should use `bench-knowledge` (llama.cpp gguf), not host chat runtime

llama.cpp gguf container:
- intended path for `mmlu`, `arc_challenge`, `hellaswag`, `boolq`, `piqa`, `winogrande`, `truthfulqa_mc2`
- re-certification should be rerun under current naming after migration changes

Other environments:
- evalplus: present, not revalidated in this pass
- lighteval: partially installed, blocked by `latex2sympy2` dependency conflict
- swebench/livecodebench/bfcl/harbor: not fully set up yet

## Operating Guidance

- For scored results, trust the generated reference first.
- For model routing, trust [model_task_library.json](/home/bryan/llm_orchestration/shared/plans/shoulders/benchmarking/model_task_library.json).
- For runtime safety and practical limits, trust this file plus the procedure doc.
- When scores and operator reality disagree, update this file and then re-run the benchmark that should resolve the disagreement.
- For prompt history, check the per-run result archives — never rely on the current profiles to reconstruct past runs.
