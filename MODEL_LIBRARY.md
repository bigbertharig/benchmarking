# Model Library

This is the operator-facing living doc for model selection, benchmark results,
and runtime best practices.

Use this together with:
- generated score ledger: `/media/bryan/shared/logs/benchmarks/MODEL_BENCHMARK_REFERENCE.md`
- raw records: `/media/bryan/shared/logs/benchmarks/model_benchmark_records.jsonl`
- machine-readable latest scoreboard: `/media/bryan/shared/plans/shoulders/benchmarking/results/model_library_scoreboard.json`
- model tuning profiles: `/media/bryan/shared/plans/shoulders/benchmarking/model_tuning_profiles.json`
- machine-readable task routing: [model_task_library.json](/home/bryan/llm_orchestration/shared/plans/shoulders/benchmarking/model_task_library.json)

Quick commands:
```bash
# Check rig status (GPUs, running tests, memory, OOM kills)
ssh 10.0.0.3 'bash /mnt/shared/scripts/benchmarks/bench_status.sh'
```

Rules:
- update this doc when a model's practical operating envelope changes
- keep exact benchmark scores in the generated reference, not copied by hand into many files
- record stable operator guidance here: what loads, what fails, what ctx is safe, what each model is best at

## Pre-Flight Litmus Test (BEFORE full suite)

Before committing a model to the full benchmark suite, run a quick litmus to catch
output format issues (e.g. `<think>` wrappers, broken JSON, refusal loops) that would
waste hours and produce all-zero scores.

```bash
# 1. One-shot reasoning check — does the model answer cleanly?
curl -s http://localhost:PORT/v1/chat/completions -d '{
  "model": "MODEL_ID",
  "messages": [{"role":"user","content":"What is 15 * 37? Reply with ONLY the number."}],
  "temperature": 0
}' | python3 -c "import json,sys; r=json.load(sys.stdin); c=r['choices'][0]['message']['content']; print(c); ok='555' in c and '<think>' not in c; print('PASS' if ok else 'FAIL: check for think tags or wrong answer')"

# 2. JSON format check — can it produce clean structured output?
curl -s http://localhost:PORT/v1/chat/completions -d '{
  "model": "MODEL_ID",
  "messages": [{"role":"user","content":"Return a JSON object with keys \"name\" and \"age\" for a 30-year-old named Alice. Output ONLY valid JSON, no explanation."}],
  "temperature": 0
}' | python3 -c "import json,sys; r=json.load(sys.stdin); c=r['choices'][0]['message']['content']; print(c); json.loads(c); print('PASS')"

# 3. Code generation check — does it output bare code without wrappers?
curl -s http://localhost:PORT/v1/chat/completions -d '{
  "model": "MODEL_ID",
  "messages": [{"role":"user","content":"Write a Python function is_palindrome(s) that returns True if s is a palindrome. Output ONLY the function, no explanation."}],
  "temperature": 0
}' | python3 -c "import json,sys; c=json.load(sys.stdin)['choices'][0]['message']['content']; print(c); ok='def is_palindrome' in c and '<think>' not in c; print('PASS' if ok else 'FAIL')"
```

If any check FAILs, investigate the output format before running benchmarks.
Common issues:
- **`<think>` wrappers**: R1-family models wrap output in `<think>...</think>` blocks, breaking answer extraction in lm-eval-harness (BBH, DROP score 0.0). May need custom post-processing.
- **Markdown code fences**: Some models wrap code in \`\`\`python blocks, breaking evalplus codegen parsing.
- **Refusal/safety loops**: Model refuses to answer simple math or produces disclaimers instead of answers.

Known affected models (`<think>` tag family) — two distinct mechanisms:

**Type A: Chat template thinking mode** (fix: `--reasoning-budget 0` on llama-server)
- `qwen3:8b` — **fixed with --reasoning-budget 0** (2026-03-16). BBH 0.0→0.6244, DROP 0.0→0.3848 at limit 50
- `qwen3.5:4b` — **fixed with --reasoning-budget 0** (2026-03-15). Pipeline improved: command_safety 91.7%→100%, json_schema 0%→15.4%
- `qwen3.5:9b` — same mechanism, testing with fix in progress
- `qwen3.5:35b-a3b` — **fixed with --reasoning-budget 0** (2026-03-15). Was all-zero pipeline, now: command_safety 100%, long_context 100%, tool_plan 93.3%
- These models use the chat template's native thinking mode. llama-server puts reasoning in a separate `reasoning_content` API field, leaving `content` empty. The fix disables the template thinking feature server-side.

**Type B: Model-trained `<think>` tokens** (partial fix: `--patch-think-tag-strip`)
- `deepseek-r1:7b` — **confirmed: --reasoning-budget 0 does NOT help** (2026-03-15). Model still emits `<think>` tags in content. The thinking is baked into the model's generation vocabulary, not the chat template.
- `deepseek-r1:14b` — **partially fixed with --patch-think-tag-strip** (2026-03-16). BBH 0.0→0.5852 (limit 5). GSM8K 0.0→0.2. DROP still 0.0 (stop sequence `.` truncates inside think chains). The patch removes `\n\n` from API stop sequences, strips `<think>...</think>` from responses, then re-applies stopping client-side. Very slow: BBH limit 5 takes ~2.5 hours on split 1060s because full think chains generate.
- `deepseek-r1:32b` — **tested, confirmed broken**: HumanEval 9% (140/164 empty solutions), Mbpp 26% (226/378 empty), BBH 0.0 all subtasks, DROP em=0 f1=0. Only GSM8K flexible-extract works (0.8). Think tags get stripped by evalplus sanitizer and take actual code with them.
- Any model fine-tuned with reasoning traces (QwQ, R1-distill variants)

**Remaining issues for Type B**: DROP still broken (`.` stop sequence truncates inside think chains — same mechanism as BBH's `\n\n` but harder to fix since `.` is content-meaningful). Code generation still broken (evalplus sanitizer strips think tags + code together). The think-tag strip is a viable approach for tasks with non-content stop sequences (`\n\n`, `Q:`) but needs per-task stop sequence handling for others.

Current phase:
- smoke testing all available models through pipeline + code + reasoning (limit 5)
- worker testing is active (GPUs 1-5, 1060 6GB cards)
- brain testing is active (GPU 0, 3090 24GB)
- brain benchmarks use `config.benchmark-brain.json` and separate campaign manifests
- brain-tier models (GPU 0, single 3090): 30B+ only — qwen2.5-coder:32b (tested), deepseek-r1:32b (tested, broken by think tags), qwen3.5:35b-a3b (tested, pipeline+code done)
- split-worker models (2x 1060, GPU 1+3 or 4+5): 14B class — qwen2.5-coder:14b (tested), deepseek-r1:14b (tested), phi-4:14b (untested), gemma-3:12b (untested)
- single-worker models (1x 1060, GPU 2): 7B class — all 5 models tested
- do not load 7B or smaller on GPU 0, and do not load 30B+ on 1060 workers
- **load models one at a time** — never load multiple models simultaneously. Parallel loading clogs the shared USB/PCIe bus, causing 3-5x longer load times and timeouts. Load one, wait for `/v1/models` to respond, then load the next.
- bench-knowledge is excluded from default campaigns (see "Suite Selection Rationale" below)

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

### Unified benchmark completion table (latest-only, per-test)

Use this single table to filter either way:
- pick a model and scan its test rows
- pick a suite and scan all model rows

Primary sources:
- bench-pipeline: `/mnt/shared/logs/benchmarks/bench-pipeline/history/parallel_worker_suite_20260310_234145/results`
- bench-pipeline (14B split): `/mnt/shared/logs/benchmarks/bench-pipeline/history/bench-pipeline_*_split_smoke_v1`
- bench-pipeline (14B/32B full): `/mnt/shared/logs/benchmarks/bench-pipeline/history/bench-pipeline_*_full_v2`
- bench-pipeline (R1-14B full): `/mnt/shared/logs/benchmarks/bench-pipeline/history/bench-pipeline_deepseek-r1_14b_pipeline_dsr1_14b_full_v3`
- bench-code: `/mnt/shared/plans/shoulders/benchmarking/docker/bench-code/history/parallel_bench_code_resume_20260311_122032`
- bench-code (14B split): `/mnt/shared/logs/benchmarks/bench-code/history/bench-code_*_split_smoke_v1`
- bench-reasoning: `/mnt/shared/logs/benchmarks/bench-reasoning/history/reasoning_top3_l100_20260312_2105`
- bench-reasoning (14B split): `/mnt/shared/logs/benchmarks/bench-reasoning/history/bench-reasoning_*_split_smoke_v1`
- bench-reasoning (7B limit 100): `/mnt/shared/logs/benchmarks/bench-reasoning/history/bench-reasoning_qwen2.5-coder_7b_reasoning_coder7b_l100_v1`
- bench-reasoning (Qwen3-8B l50): `/mnt/shared/logs/benchmarks/bench-reasoning/history/bench-reasoning_qwen3_8b_reasoning_qwen3_8b_nothink_l50_v1`
- bench-reasoning (Coder-14B l100): `/mnt/shared/logs/benchmarks/bench-reasoning/history/bench-reasoning_qwen2.5-coder_14b_reasoning_coder14b_l100_v1`
- bench-knowledge: `/mnt/shared/logs/benchmarks/bench-knowledge/history/bench-knowledge_*_knowledge_smoke_v1`
- bench-knowledge (32B): `/mnt/shared/logs/benchmarks/bench-knowledge/history/bench-knowledge_qwen2.5-coder-32b_knowledge_brain_smoke_v1`
- brain campaign (32B): `/mnt/shared/logs/benchmarks/campaigns/history/gpu0_brain_qwen25coder32b_smoke/smoke_v1`

### Model inventory and GGUF availability

All models with GGUF files on `/mnt/shared/models/`:

| Model | GGUF File | Tier | GPU Target | Status |
| --- | --- | --- | --- | --- |
| `Qwen2.5-Coder-7B` | `Qwen2.5-Coder-7B-Instruct-Q4_K_M.gguf` | 7B single | GPU 1-5 | tested |
| `Mistral-7B-Instruct-v0.3` | `Mistral-7B-Instruct-v0.3-Q4_K_M.gguf` | 7B single | GPU 1-5 | tested |
| `DeepSeek-R1-Distill-Qwen-7B` | `DeepSeek-R1-Distill-Qwen-7B-Q4_K_M.gguf` | 7B single | GPU 1-5 | tested |
| `Qwen3.5-4B` | `Qwen3.5-4B-Q4_K_M.gguf` | 7B single | GPU 1-5 | tested |
| `Qwen3.5-9B-Q3_K_M` | `Qwen3.5-9B-Q3_K_M.gguf` | 7B single | GPU 1-5 | tested (pipeline complete, code complete, reasoning pending) |
| `Qwen3-8B` | `Qwen3-8B-Q4_K_M.gguf` | 7B single | GPU 1-5 | tested (reasoning l50 complete) |
| `Qwen3-1.7B` | `Qwen3-1.7B-Q4_K_M.gguf` | 3B single | GPU 1-5 | tested |
| `SmolLM3-3B` | `SmolLM3-3B-Q4_K_M.gguf` | 3B single | GPU 1-5 | tested |
| `Llama-3.2-3B-Instruct` | `Llama-3.2-3B-Instruct-Q4_K_M.gguf` | 3B single | GPU 1-5 | tested |
| `Phi-4-mini` | `Phi-4-mini-instruct-Q4_K_M.gguf` | 4B single | GPU 1-5 | tested |
| `Gemma-3-4B` | `gemma-3-4b-it-Q4_K_M.gguf` | 4B single | GPU 1-5 | tested |
| `Qwen2.5-Coder-14B` | `Qwen2.5-Coder-14B-Instruct-Q4_K_M.gguf` | 14B split | GPU 1+3 or 4+5 | tested (reasoning l100 complete) |
| `DeepSeek-R1-Distill-Qwen-14B` | `DeepSeek-R1-Distill-Qwen-14B-Q4_K_M.gguf` | 14B split | GPU 1+3 or 4+5 | tested (pipeline 5/6) |
| `Phi-4-14B` | `phi-4-Q4_K_M.gguf` | 14B split | GPU 1+3 or 4+5 | tested |
| `Gemma-3-12B` | `gemma-3-12b-it-Q4_K_M.gguf` | 14B split | GPU 1+3 or 4+5 | partial — **cannot split-load on 1060s** (262K vocab = ~3.1GB embedding per GPU, OOM). Needs brain GPU (3090). |
| `Qwen2.5-Coder-32B` | `Qwen2.5-Coder-32B-Instruct-Q4_K_M.gguf` | 30B brain | GPU 0 (3090) | tested (all suites complete) |
| `DeepSeek-R1-Distill-Qwen-32B` | `DeepSeek-R1-Distill-Qwen-32B-Q4_K_M.gguf` | 30B brain | GPU 0 (3090) | tested (pipeline done, think-tag broken) |
| `Qwen3.5-35B-A3B` | `Qwen3.5-35B-A3B-Q4_K_M.gguf` | 30B brain | GPU 0 (3090) | tested (pipeline+code done, reasoning expect SWA failure) |

#### bench-pipeline (worker reliability)

Pipeline tests run all cases (fixed test sets), no limit parameter.

| Model | Test | Pass | Total | Score | Limit | Date (UTC) |
| --- | --- | --- | --- | --- | --- | --- |
| `Qwen2.5-Coder-7B` | json_schema_strict | 9 | 13 | `69.2%` | full | 2026-03-11 |
| `Qwen2.5-Coder-7B` | command_safety | 11 | 12 | `91.7%` | full | 2026-03-11 |
| `Qwen2.5-Coder-7B` | ambiguity_handling | 2 | 13 | `15.4%` | full | 2026-03-11 |
| `Qwen2.5-Coder-7B` | tool_plan_sequence | 14 | 15 | `93.3%` | full | 2026-03-11 |
| `Qwen2.5-Coder-7B` | orchestration_tradeoff | 9 | 12 | `75.0%` | full | 2026-03-11 |
| `Qwen2.5-Coder-7B` | long_context_extract | 13 | 14 | `92.9%` | full | 2026-03-11 |
| `Mistral-7B-Instruct-v0.3` | json_schema_strict | 3 | 13 | `23.1%` | full | 2026-03-11 |
| `Mistral-7B-Instruct-v0.3` | command_safety | 10 | 12 | `83.3%` | full | 2026-03-11 |
| `Mistral-7B-Instruct-v0.3` | ambiguity_handling | 6 | 13 | `46.2%` | full | 2026-03-11 |
| `Mistral-7B-Instruct-v0.3` | tool_plan_sequence | 12 | 15 | `80.0%` | full | 2026-03-11 |
| `Mistral-7B-Instruct-v0.3` | orchestration_tradeoff | 10 | 12 | `83.3%` | full | 2026-03-11 |
| `Mistral-7B-Instruct-v0.3` | long_context_extract | 14 | 14 | `100%` | full | 2026-03-11 |
| `DeepSeek-R1-Distill-Qwen-7B` | json_schema_strict | 2 | 13 | `15.4%` | full | 2026-03-11 |
| `DeepSeek-R1-Distill-Qwen-7B` | command_safety | 7 | 12 | `58.3%` | full | 2026-03-11 |
| `DeepSeek-R1-Distill-Qwen-7B` | ambiguity_handling | 0 | 13 | `0%` | full | 2026-03-11 |
| `DeepSeek-R1-Distill-Qwen-7B` | tool_plan_sequence | 11 | 15 | `73.3%` | full | 2026-03-11 |
| `DeepSeek-R1-Distill-Qwen-7B` | orchestration_tradeoff | 4 | 12 | `33.3%` | full | 2026-03-11 |
| `DeepSeek-R1-Distill-Qwen-7B` | long_context_extract | — | — | incomplete | full | 2026-03-11 |
| `Qwen3.5-4B` | json_schema_strict | 2 | 13 | `15.4%` | full | 2026-03-15 |
| `Qwen3.5-4B` | command_safety | 12 | 12 | `100%` | full | 2026-03-15 |
| `Qwen3.5-4B` | ambiguity_handling | 4 | 13 | `30.8%` | full | 2026-03-15 |
| `Qwen3.5-4B` | tool_plan_sequence | 14 | 15 | `93.3%` | full | 2026-03-15 |
| `Qwen3.5-4B` | orchestration_tradeoff | 7 | 12 | `58.3%` | full | 2026-03-15 |
| `Qwen3.5-4B` | long_context_extract | 14 | 14 | `100%` | full | 2026-03-15 |
| `Qwen3.5-9B-Q3_K_M` | json_schema_strict | 5 | 13 | `38.5%` | full | 2026-03-15 |
| `Qwen3.5-9B-Q3_K_M` | command_safety | 11 | 12 | `91.7%` | full | 2026-03-15 |
| `Qwen3.5-9B-Q3_K_M` | ambiguity_handling | 7 | 13 | `53.8%` | full | 2026-03-15 |
| `Qwen3.5-9B-Q3_K_M` | tool_plan_sequence | 14 | 15 | `93.3%` | full | 2026-03-15 |
| `Qwen3.5-9B-Q3_K_M` | orchestration_tradeoff | 9 | 12 | `75.0%` | full | 2026-03-15 |
| `Qwen3.5-9B-Q3_K_M` | long_context_extract | 14 | 14 | `100%` | full | 2026-03-15 |
| `Qwen3-1.7B` | pipeline_total | 6 | 6 | `100%` | full | 2026-03-17 |
| `SmolLM3-3B` | pipeline_total | 6 | 6 | `100%` | full | 2026-03-17 |
| `Llama-3.2-3B-Instruct` | pipeline_total | 6 | 6 | `100%` | full | 2026-03-17 |
| `Phi-4-mini` | pipeline_total | 6 | 6 | `100%` | full | 2026-03-17 |
| `Gemma-3-4B` | pipeline_total | 6 | 6 | `100%` | full | 2026-03-17 |
| `Qwen2.5-Coder-14B` | json_schema_strict | 3 | 13 | `23.1%` | full | 2026-03-14 |
| `Qwen2.5-Coder-14B` | command_safety | 3 | 12 | `25.0%` | full | 2026-03-14 |
| `Qwen2.5-Coder-14B` | ambiguity_handling | 1 | 13 | `7.7%` | full | 2026-03-14 |
| `Qwen2.5-Coder-14B` | tool_plan_sequence | 14 | 15 | `93.3%` | full | 2026-03-14 |
| `Qwen2.5-Coder-14B` | orchestration_tradeoff | 9 | 12 | `75.0%` | full | 2026-03-14 |
| `Qwen2.5-Coder-14B` | long_context_extract | 13 | 14 | `92.9%` | full | 2026-03-14 |
| `DeepSeek-R1-Distill-Qwen-14B` | json_schema_strict | 1 | 13 | `7.7%` | full | 2026-03-14 |
| `DeepSeek-R1-Distill-Qwen-14B` | command_safety | 1 | 12 | `8.3%` | full | 2026-03-14 |
| `DeepSeek-R1-Distill-Qwen-14B` | ambiguity_handling | 0 | 13 | `0%` | full | 2026-03-14 |
| `DeepSeek-R1-Distill-Qwen-14B` | tool_plan_sequence | 12 | 15 | `80.0%` | full | 2026-03-14 |
| `DeepSeek-R1-Distill-Qwen-14B` | orchestration_tradeoff | — | — | failed (timeout) | full | 2026-03-14 |
| `DeepSeek-R1-Distill-Qwen-14B` | long_context_extract | 11 | 14 | `78.6%` | full | 2026-03-14 |
| `Phi-4-14B` | json_schema_strict | 0 | 13 | `0%` | full | 2026-03-14 |
| `Phi-4-14B` | command_safety | 12 | 12 | `100%` | full | 2026-03-14 |
| `Phi-4-14B` | ambiguity_handling | 5 | 13 | `38.5%` | full | 2026-03-14 |
| `Phi-4-14B` | tool_plan_sequence | 15 | 15 | `100%` | full | 2026-03-14 |
| `Phi-4-14B` | orchestration_tradeoff | 11 | 12 | `91.7%` | full | 2026-03-14 |
| `Phi-4-14B` | long_context_extract | 14 | 14 | `100%` | full | 2026-03-14 |
| `Gemma-3-12B` | json_schema_strict | 0 | 13 | `0%` | full | 2026-03-14 |
| `Gemma-3-12B` | command_safety | 7 | 12 | `58.3%` | full | 2026-03-14 |
| `Gemma-3-12B` | ambiguity_handling | 7 | 13 | `53.8%` | full | 2026-03-14 |
| `Gemma-3-12B` | tool_plan_sequence | 14 | 15 | `93.3%` | full | 2026-03-14 |
| `Gemma-3-12B` | orchestration_tradeoff | 9 | 12 | `75.0%` | full | 2026-03-14 |
| `Gemma-3-12B` | long_context_extract | 13 | 14 | `92.9%` | full | 2026-03-14 |
| `Qwen2.5-Coder-32B` | json_schema_strict | 4 | 13 | `30.8%` | full | 2026-03-14 |
| `Qwen2.5-Coder-32B` | command_safety | 10 | 12 | `83.3%` | full | 2026-03-14 |
| `Qwen2.5-Coder-32B` | ambiguity_handling | 2 | 13 | `15.4%` | full | 2026-03-14 |
| `Qwen2.5-Coder-32B` | tool_plan_sequence | 14 | 15 | `93.3%` | full | 2026-03-14 |
| `Qwen2.5-Coder-32B` | orchestration_tradeoff | 10 | 12 | `83.3%` | full | 2026-03-14 |
| `Qwen2.5-Coder-32B` | long_context_extract | 14 | 14 | `100%` | full | 2026-03-14 |
| `DeepSeek-R1-Distill-Qwen-32B` | json_schema_strict | 0 | 13 | `0%` | full | 2026-03-15 |
| `DeepSeek-R1-Distill-Qwen-32B` | command_safety | 1 | 12 | `8.3%` | full | 2026-03-15 |
| `DeepSeek-R1-Distill-Qwen-32B` | ambiguity_handling | 0 | 13 | `0%` | full | 2026-03-15 |
| `DeepSeek-R1-Distill-Qwen-32B` | tool_plan_sequence | 12 | 15 | `80.0%` | full | 2026-03-15 |
| `DeepSeek-R1-Distill-Qwen-32B` | orchestration_tradeoff | 1 | 12 | `8.3%` | full | 2026-03-15 |
| `DeepSeek-R1-Distill-Qwen-32B` | long_context_extract | 12 | 14 | `85.7%` | full | 2026-03-15 |
| `Qwen3.5-35B-A3B` | json_schema_strict | 3 | 13 | `23.1%` | full | 2026-03-15 |
| `Qwen3.5-35B-A3B` | command_safety | 12 | 12 | `100%` | full | 2026-03-15 |
| `Qwen3.5-35B-A3B` | ambiguity_handling | 5 | 13 | `38.5%` | full | 2026-03-15 |
| `Qwen3.5-35B-A3B` | tool_plan_sequence | 14 | 15 | `93.3%` | full | 2026-03-15 |
| `Qwen3.5-35B-A3B` | orchestration_tradeoff | 10 | 12 | `83.3%` | full | 2026-03-15 |
| `Qwen3.5-35B-A3B` | long_context_extract | 14 | 14 | `100%` | full | 2026-03-15 |

#### bench-code (EvalPlus generation)

Scores shown as base / plus (EvalPlus+ stricter evaluation). Code tests run all problems (fixed sets), no limit parameter.

| Model | Test | Pass (base) | Pass (plus) | Total | Score (base / plus) | Limit | Date (UTC) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `Qwen2.5-Coder-7B` | humaneval | 145 | 139 | 164 | `88.4%` / `84.8%` | full | 2026-03-11 |
| `Qwen2.5-Coder-7B` | mbpp | 312 | 266 | 378 | `82.5%` / `70.4%` | full | 2026-03-11 |
| `Mistral-7B-Instruct-v0.3` | humaneval | 73 | 62 | 164 | `44.5%` / `37.8%` | full | 2026-03-11 |
| `Mistral-7B-Instruct-v0.3` | mbpp | 188 | 159 | 378 | `49.7%` / `42.1%` | full | 2026-03-11 |
| `DeepSeek-R1-Distill-Qwen-7B` | humaneval | 8 | 8 | 164 | `4.9%` / `4.9%` | full | 2026-03-11 |
| `DeepSeek-R1-Distill-Qwen-7B` | mbpp | 73 | 74 | 378 | `19.3%` / `19.6%` | full | 2026-03-11 |
| `Qwen3.5-4B` | humaneval | 62 | 60 | 164 | `37.8%` / `36.6%` | full | 2026-03-11 |
| `Qwen3.5-4B` | mbpp | 248 | 212 | 378 | `65.6%` / `56.1%` | full | 2026-03-11 |
| `Qwen3.5-9B-Q3_K_M` | humaneval | 66 | 64 | 164 | `40.2%` / `39.0%` | full | 2026-03-12 |
| `Qwen3.5-9B-Q3_K_M` | mbpp | 256 | 220 | 378 | `67.7%` / `58.2%` | full | 2026-03-12 |
| `Qwen2.5-Coder-14B` | humaneval | 148 | 142 | 164 | `90.2%` / `86.6%` | full | 2026-03-14 |
| `Qwen2.5-Coder-14B` | mbpp | 321 | 278 | 378 | `84.9%` / `73.5%` | full | 2026-03-14 |
| `DeepSeek-R1-Distill-Qwen-14B` | humaneval | 10 | 10 | 164 | `6.1%` / `6.1%` | full | 2026-03-14 |
| `DeepSeek-R1-Distill-Qwen-14B` | mbpp | 84 | 79 | 378 | `22.2%` / `20.9%` | full | 2026-03-14 |
| `Phi-4-14B` | humaneval | 129 | 120 | 164 | `78.7%` / `73.2%` | full | 2026-03-14 |
| `Phi-4-14B` | mbpp | 279 | 242 | 378 | `73.8%` / `64.0%` | full | 2026-03-14 |
| `Gemma-3-12B` | humaneval | — | — | — | interrupted | — | 2026-03-14 |
| `Gemma-3-12B` | mbpp | — | — | — | untested | — | — |
| `Qwen2.5-Coder-32B` | humaneval | 150 | 143 | 164 | `91.5%` / `87.2%` | full | 2026-03-14 |
| `Qwen2.5-Coder-32B` | mbpp | 339 | 291 | 378 | `89.7%` / `77.0%` | full | 2026-03-14 |
| `DeepSeek-R1-Distill-Qwen-32B` | humaneval | — | — | — | untested | — | — |
| `DeepSeek-R1-Distill-Qwen-32B` | mbpp | — | — | — | untested | — | — |
| `Qwen3.5-35B-A3B` | humaneval | 149 | 143 | 164 | `90.9%` / `87.2%` | full | 2026-03-15 |
| `Qwen3.5-35B-A3B` | mbpp | 326 | 273 | 378 | `86.2%` / `72.2%` | full | 2026-03-15 |
| `Qwen3-1.7B` | humaneval | 9 | 9 | 164 | `5.5%` / `5.5%` | full | 2026-03-17 |
| `Qwen3-1.7B` | mbpp | 82 | 77 | 378 | `21.7%` / `20.4%` | full | 2026-03-17 |
| `SmolLM3-3B` | humaneval | 108 | 98 | 164 | `65.9%` / `59.8%` | full | 2026-03-17 |
| `SmolLM3-3B` | mbpp | 241 | 208 | 378 | `63.8%` / `55.0%` | full | 2026-03-17 |
| `Llama-3.2-3B-Instruct` | humaneval | 105 | 97 | 164 | `64.0%` / `59.1%` | full | 2026-03-17 |
| `Llama-3.2-3B-Instruct` | mbpp | 241 | 202 | 378 | `63.8%` / `53.4%` | full | 2026-03-17 |
| `Phi-4-mini` | humaneval | 117 | 105 | 164 | `71.3%` / `64.0%` | full | 2026-03-17 |
| `Phi-4-mini` | mbpp | 204 | 183 | 378 | `54.0%` / `48.4%` | full | 2026-03-17 |
| `Gemma-3-4B` | humaneval | 111 | 99 | 164 | `67.7%` / `60.4%` | full | 2026-03-17 |
| `Gemma-3-4B` | mbpp | 291 | 249 | 378 | `77.0%` / `65.9%` | full | 2026-03-18 |

#### bench-reasoning (lm-eval generation)

| Model | Test | Score | Metric | Limit | Date (UTC) |
| --- | --- | --- | --- | --- | --- |
| `Qwen2.5-Coder-7B` | gsm8k | `0.75` | exact_match | 100 | 2026-03-12 |
| `Qwen2.5-Coder-7B` | bbh | `0.6674` | exact_match | 100 | 2026-03-14 |
| `Qwen2.5-Coder-7B` | drop | `0.576` | f1 | 100 | 2026-03-14 |
| `Mistral-7B-Instruct-v0.3` | gsm8k | `0.48` | exact_match | 100 | 2026-03-12 |
| `Mistral-7B-Instruct-v0.3` | bbh | `0.5393` | exact_match | 100 | 2026-03-13 |
| `Mistral-7B-Instruct-v0.3` | drop | `0.126` | f1 | 100 | 2026-03-13 |
| `DeepSeek-R1-Distill-Qwen-7B` | gsm8k | `0.08` | exact_match | 100 | 2026-03-12 |
| `DeepSeek-R1-Distill-Qwen-7B` | bbh | `0.0` | exact_match | 100 | 2026-03-12 |
| `DeepSeek-R1-Distill-Qwen-7B` | drop | `0.0` | f1 | 100 | 2026-03-12 |
| `Qwen3.5-4B` | gsm8k | `0.80` | exact_match (strict=flex) | 5 | 2026-03-15 |
| `Qwen3.5-4B` | bbh | — | — | failed (SWA issue) | 2026-03-15 |
| `Qwen3.5-4B` | drop | — | — | failed (SWA issue) | 2026-03-15 |
| `Qwen3.5-9B-Q3_K_M` | gsm8k | `0.80` | exact_match (strict=flex) | 5 | 2026-03-15 |
| `Qwen3.5-9B-Q3_K_M` | bbh | — | — | failed (SWA issue) | 2026-03-15 |
| `Qwen3.5-9B-Q3_K_M` | drop | — | — | failed (SWA issue) | 2026-03-15 |
| `Qwen2.5-Coder-14B` | gsm8k | `0.80` | exact_match | 5 | 2026-03-14 |
| `Qwen2.5-Coder-14B` | bbh | `0.6370` | exact_match | 5 | 2026-03-14 |
| `Qwen2.5-Coder-14B` | drop | `0.558` | f1 | 5 | 2026-03-14 |
| `DeepSeek-R1-Distill-Qwen-14B` | gsm8k | `0.2` | exact_match (flex) | 5 | 2026-03-16 |
| `DeepSeek-R1-Distill-Qwen-14B` | bbh | `0.5852` | exact_match | 5 | 2026-03-16 |
| `DeepSeek-R1-Distill-Qwen-14B` | drop | `0.0` | f1 | 5 | 2026-03-16 |
| `Phi-4-14B` | gsm8k | `0.70` | exact_match (flex) | 50 | 2026-03-15 |
| `Phi-4-14B` | bbh | `0.283` | exact_match | 50 | 2026-03-16 |
| `Phi-4-14B` | drop | `0.070` | f1 | 50 | 2026-03-16 |
| `Gemma-3-12B` | gsm8k | `0.60` | exact_match | 5 | 2026-03-14 |
| `Gemma-3-12B` | bbh | — | — | failed (OOM on split) | 2026-03-14 |
| `Gemma-3-12B` | drop | — | — | failed (OOM on split) | 2026-03-14 |
| `Qwen2.5-Coder-32B` | gsm8k | `0.92` | exact_match | 100 | 2026-03-15 |
| `Qwen2.5-Coder-32B` | bbh | `0.4837` | exact_match | 100 | 2026-03-15 |
| `Qwen2.5-Coder-32B` | drop | `0.756` | f1 | 100 | 2026-03-15 |
| `DeepSeek-R1-Distill-Qwen-32B` | gsm8k | — | — | untested | — |
| `DeepSeek-R1-Distill-Qwen-32B` | bbh | — | — | untested | — |
| `DeepSeek-R1-Distill-Qwen-32B` | drop | — | — | untested | — |
| `Qwen3-8B` | gsm8k | `0.90` | exact_match | 50 | 2026-03-15 |
| `Qwen3-8B` | bbh | `0.6244` | exact_match | 50 | 2026-03-15 |
| `Qwen3-8B` | drop | `0.3848` | f1 | 50 | 2026-03-15 |
| `Qwen3-1.7B` | gsm8k | `0.40` | exact_match (strict=flex) | 5 | 2026-03-17 |
| `Qwen3-1.7B` | bbh | `0.0` | exact_match | 5 | 2026-03-17 |
| `Qwen3-1.7B` | drop | `0.70` | f1 | 5 | 2026-03-17 |
| `Qwen3-1.7B` | gsm8k | `0.44` | exact_match (strict) / `0.46` (flex) | 100 | 2026-03-18 |
| `Qwen3-1.7B` | bbh | `0.0` | exact_match | 100 | 2026-03-18 |
| `Qwen3-1.7B` | drop | `0.1661` | f1 | 100 | 2026-03-18 |
| `SmolLM3-3B` | gsm8k | `0.80` | exact_match (strict=flex) | 5 | 2026-03-17 |
| `SmolLM3-3B` | bbh | `0.5704` | exact_match | 5 | 2026-03-17 |
| `SmolLM3-3B` | drop | `0.232` | f1 | 5 | 2026-03-17 |
| `SmolLM3-3B` | gsm8k | `0.79` | exact_match (strict=flex) | 100 | 2026-03-18 |
| `SmolLM3-3B` | bbh | `0.6678` | exact_match | 100 | 2026-03-18 |
| `SmolLM3-3B` | drop | `0.3302` | f1 | 100 | 2026-03-18 |
| `Llama-3.2-3B-Instruct` | gsm8k | `0.80` | exact_match (strict=flex) | 5 | 2026-03-17 |
| `Llama-3.2-3B-Instruct` | bbh | `0.5111` | exact_match | 5 | 2026-03-17 |
| `Llama-3.2-3B-Instruct` | drop | `0.312` | f1 | 5 | 2026-03-17 |
| `Llama-3.2-3B-Instruct` | gsm8k | `0.72` | exact_match (flex) | 100 | 2026-03-18 |
| `Llama-3.2-3B-Instruct` | bbh | `0.5896` | exact_match | 100 | 2026-03-18 |
| `Llama-3.2-3B-Instruct` | drop | `0.4326` | f1 | 100 | 2026-03-18 |
| `Phi-4-mini` | gsm8k | `1.00` | exact_match (strict=flex) | 5 | 2026-03-17 |
| `Phi-4-mini` | bbh | `0.6370` | exact_match | 5 | 2026-03-17 |
| `Phi-4-mini` | drop | `0.40` | f1 | 5 | 2026-03-17 |
| `Phi-4-mini` | gsm8k | `0.70` | exact_match (strict) / `0.69` (flex) | 100 | 2026-03-18 |
| `Gemma-3-4B` | gsm8k | `0.80` | exact_match (strict=flex) | 5 | 2026-03-17 |
| `Gemma-3-4B` | bbh | `0.5481` | exact_match | 5 | 2026-03-17 |
| `Gemma-3-4B` | drop | `0.266` | f1 | 5 | 2026-03-17 |
| `Qwen3.5-35B-A3B` | gsm8k | — | — | untested | — |
| `Qwen3.5-35B-A3B` | bbh | — | — | untested (expect SWA failure, see notes) | — |
| `Qwen3.5-35B-A3B` | drop | — | — | untested (expect SWA failure, see notes) | — |

RPi-tier small-model cohort update (2026-03-18 UTC): `Qwen3-1.7B`, `SmolLM3-3B`, `Llama-3.2-3B-Instruct`, `Phi-4-mini`, and `Gemma-3-4B` have completed `bench-pipeline` totals (`6/6` each) and full `bench-code` smoke coverage. Completed `bench-reasoning --limit 100` baselines now exist for `Qwen3-1.7B` (`gsm8k 0.44 strict / 0.46 flex`, `bbh 0.0`, `drop f1 0.1661`), `SmolLM3-3B` (`gsm8k 0.79`, `bbh 0.6678`, `drop f1 0.3302`), and `Llama-3.2-3B-Instruct` (`gsm8k 0.72 flex`, `bbh 0.5896`, `drop f1 0.4326`). `Phi-4-mini` has completed `gsm8k` (`0.70 strict / 0.69 flex`) and is still in progress on the resumed `bbh`/`drop` retry. `Gemma-3-4B` is now a known high-limit reasoning failure case on this rig: both the initial run and a dedicated 3-model retry dropped the worker runtime mid-run, with the second retry failing `gsm8k`, `bbh`, and `drop` again on `2026-03-18` after `Connection refused` on `localhost:11436`. Treat `Gemma-3-4B` `bench-reasoning --limit 100` as benchmark-unstable on the 1060 worker path unless the runtime-loss issue is fixed separately.

Qwen3-8B reasoning (limit 50, completed 2026-03-15): **`--reasoning-budget 0` confirmed as fix**. gsm8k 0.90, bbh 0.6244, drop 0.3848 f1 / 0.18 em. Same Type A thinking mode issue as Qwen3.5 family. Also requires `--cache-ram 0` to prevent prompt cache OOM on 6GB VRAM.

Qwen3.5 reasoning (with `--reasoning-budget 0`): GSM8K now works (0.80 strict across 4b, 9b). BBH and DROP both fail with exit code 1 on all Qwen3.5 models — likely caused by SWA (Sliding Window Attention) hybrid memory architecture incompatibility with lm-eval's longer prompt sequences, same issue that blocks bench-knowledge. GSM8K uses shorter prompts and works fine.

Qwen2.5-Coder-14B reasoning (limit 100, completed 2026-03-16): gsm8k 0.89, bbh 0.5937, drop 0.4802 f1 / 0.28 em. Run via split-worker pair (gpu-4 + gpu-5). Scores decreased from limit 5 smoke test as expected — limit 100 values are the reliable baseline.

DeepSeek-R1-Distill-Qwen-14B reasoning (2026-03-16, multiple tuning passes): BBH **0.5852** with `--patch-think-tag-strip` v2 (removed `\n\n` stop only). GSM8K and DROP remain 0.0 across all prompt and patch variants. **Root cause is structural**: llama-server splits `<think>` content into `reasoning_content` API field before client-side patches see it, and the model outputs math answers in `\boxed{}` format instead of `####`. Fixing requires changes to llama-server or lm-eval internals — not solvable with prompt tuning. Marked as benchmark-incompatible; may still work in real plan execution where `reasoning_content` can be parsed directly.

Qwen2.5-Coder-7B reasoning (limit 100): bbh improved from 0.6481 (limit 10) to 0.6674 (limit 100). Drop decreased from 0.622 to 0.576, likely more representative at higher sample count.

Qwen2.5-Coder-32B reasoning (limit 100, completed 2026-03-15): gsm8k 0.92 (best in fleet), bbh 0.4837 (improved from 0.4593 at limit 5), drop 0.756 f1 / 0.62 em (best drop in fleet). Full limit 100 run across all 3 tasks now complete.

#### bench-knowledge (lm-eval loglikelihood)

Source: `/mnt/shared/logs/benchmarks/bench-knowledge/history/bench-knowledge_*_knowledge_smoke_v1`

| Model | Test | Score | Metric | Limit | Date (UTC) |
| --- | --- | --- | --- | --- | --- |
| `Mistral-7B-Instruct-v0.3` | mmlu | `0.593` | accuracy | 5 | 2026-03-13 |
| `Mistral-7B-Instruct-v0.3` | arc_challenge | `0.60` | acc_norm | 5 | 2026-03-13 |
| `Mistral-7B-Instruct-v0.3` | hellaswag | `0.80` | acc_norm | 5 | 2026-03-13 |
| `Mistral-7B-Instruct-v0.3` | truthfulqa_mc2 | `0.671` | accuracy | 5 | 2026-03-13 |
| `Mistral-7B-Instruct-v0.3` | boolq | `0.80` | accuracy | 5 | 2026-03-13 |
| `Qwen2.5-Coder-7B` | mmlu | `0.270` | accuracy | 5 | 2026-03-13 |
| `Qwen2.5-Coder-7B` | arc_challenge | `0.20` | accuracy | 5 | 2026-03-13 |
| `Qwen2.5-Coder-7B` | hellaswag | `0.40` | accuracy | 5 | 2026-03-13 |
| `Qwen2.5-Coder-7B` | truthfulqa_mc2 | `0.200` | accuracy | 5 | 2026-03-13 |
| `Qwen2.5-Coder-7B` | boolq | `0.20` | accuracy | 5 | 2026-03-13 |
| `DeepSeek-R1-Distill-Qwen-7B` | mmlu | `0.618` | accuracy | 5 | 2026-03-13 |
| `DeepSeek-R1-Distill-Qwen-7B` | arc_challenge | `0.20` | acc_norm | 5 | 2026-03-13 |
| `DeepSeek-R1-Distill-Qwen-7B` | hellaswag | `0.40` | acc_norm | 5 | 2026-03-13 |
| `DeepSeek-R1-Distill-Qwen-7B` | truthfulqa_mc2 | `0.644` | accuracy | 5 | 2026-03-13 |
| `DeepSeek-R1-Distill-Qwen-7B` | boolq | `0.80` | accuracy | 5 | 2026-03-13 |
| `Qwen3.5-4B` | (all) | N/A | — | — | 2026-03-13 |
| `Qwen2.5-Coder-32B` | mmlu | `0.270` | accuracy | 5 | 2026-03-14 |
| `Qwen2.5-Coder-32B` | arc_challenge | `0.20` | acc_norm | 5 | 2026-03-14 |
| `Qwen2.5-Coder-32B` | hellaswag | `0.40` | acc_norm | 5 | 2026-03-14 |
| `Qwen2.5-Coder-32B` | truthfulqa_mc2 | `0.200` | accuracy | 5 | 2026-03-14 |
| `Qwen2.5-Coder-32B` | boolq | `0.20` | accuracy | 5 | 2026-03-14 |
| `Qwen3.5-9B-Q3_K_M` | (all) | N/A | — | — | 2026-03-13 |

Qwen3.5 knowledge: N/A — llama.cpp server returns 503 errors due to SWA/hybrid memory architecture forcing full prompt reprocessing on every request (no KV cache reuse), overwhelming the server.

Qwen2.5-Coder-32B knowledge: scores are identical to 7B coder across all 5 tasks. At limit 5, this is almost certainly noise — both models are answering ~1 of 5 samples correctly. These are coder-family models; low knowledge scores are expected and not a concern (see Suite Selection Rationale).

Note: limit 5 scores have high variance (especially on small tasks like arc_challenge and boolq where n=5). Run at higher limits for reliable comparisons. Smoke test runtimes at limit 5: Mistral ~1.5h, DeepSeek ~7h, Qwen2.5-Coder ~7.5h.

#### Prompt impact on knowledge scores (A/B test, 2026-03-14)

Ran all 3 compatible models with `--no-model-prompts` and compared to prompted runs.
Result: **system prompts have no meaningful effect on loglikelihood-based knowledge scores.**

| Model | Task | With Prompt | No Prompt | Delta |
| --- | --- | --- | --- | --- |
| `Mistral-7B` | mmlu | 0.593 | 0.593 | 0.000 |
| `Mistral-7B` | arc_challenge | 0.60 | 0.40 | -0.20 |
| `Mistral-7B` | hellaswag | 0.40 | 0.60 | +0.20 |
| `Mistral-7B` | truthfulqa_mc2 | 0.671 | 0.607 | -0.064 |
| `Mistral-7B` | boolq | 0.80 | 0.80 | 0.000 |
| `Qwen2.5-Coder-7B` | (all 5 tasks) | — | — | 0.000 |
| `DeepSeek-R1-7B` | (all 5 tasks) | — | — | 0.000 |

Qwen2.5-Coder and DeepSeek showed zero difference across all tasks. Mistral's deltas are noise at limit 5 (1 sample = 0.20 swing). Loglikelihood evaluation measures token probabilities, not generated text, so system prompts have minimal influence on the scoring mechanism. The low Qwen2.5-Coder knowledge scores (0.20-0.27) are the model's actual baseline, not prompt interference.

### Suite Selection Rationale

Default campaigns run 3 suites: **pipeline, code, reasoning**. Knowledge is excluded.

Why:
- The orchestrator's job is to make models follow instructions, not recall training data.
  Pipeline tests strict format compliance, code tests generation quality, reasoning tests
  problem-solving ability. These directly measure worker fitness.
- Knowledge benchmarks (MMLU, ARC, HellaSwag, TruthfulQA, BoolQ) measure how well a
  model recalls facts from pretraining. This is nearly irrelevant to our use case — we
  *want* models to ignore their own knowledge and use the context we provide.
- Runtime cost is prohibitive. Loglikelihood evaluation requires multiple completions per
  item. At limit 5, MMLU alone takes 4-8 hours per model on a 1060. A realistic limit 100
  run would take days per model. The signal-to-cost ratio is too low.
- A model that scores high on knowledge benchmarks may actually be worse for our pipeline
  because it's more likely to deviate from instructions based on its own "opinions."

When to run knowledge anyway:
- Sanity-checking a brand new model family (is the quant catastrophically broken?)
- Comparing two otherwise-identical models where knowledge is the tiebreaker
- Ad-hoc, not as part of the default campaign

The bench-knowledge infrastructure is validated and available. Run it standalone when needed:
```bash
docker run --rm --gpus '"device=0"' \
  -v /mnt/shared:/mnt/shared -v /mnt/shared/models:/models:ro \
  -v /mnt/shared/logs/benchmarks/bench-knowledge/history:/results \
  -v /mnt/shared/plans/shoulders/benchmarking:/benchmark-scripts:ro \
  bench-knowledge /models/<model>/<file>.gguf \
  --limit 5 --run-name knowledge_adhoc_v1
```

Decision made: 2026-03-14.

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

### qwen3:8b

Status:
- single-worker model (1x 1060 6GB)
- first benchmark results 2026-03-16 (reasoning l50, `--reasoning-budget 0`)
- same thinking mode issue as Qwen3.5 family — **requires `--reasoning-budget 0`**
- without the fix, BBH and DROP score 0.0 (answer routed to `reasoning_content` field)
- also requires `--cache-ram 0` to prevent prompt cache OOM at Docker memory limit

Known results (nothink_l50_v1, 2026-03-16):
- `gsm8k`: 0.90 (limit 50, flex) — strong math performance
- `bbh`: 0.6244 (limit 50) — best BBH in single-worker tier
- `drop`: 0.3848 f1 / 0.18 em (limit 50)
- pipeline: untested
- code: untested

Runtime notes:
- Docker memory limit: 4g (with `--cache-ram 0`) — prompt cache disabled to prevent OOM
- at 6g limit with prompt cache enabled, OOM'd during BBH (cache accumulated 127 MiB per prompt)
- VRAM: ~5.8 GB loaded

Best practices:
- always launch with `--reasoning-budget 0` (same mechanism as Qwen3.5 family)
- always launch with `--cache-ram 0` to prevent prompt cache OOM in long benchmark runs
- strong reasoning candidate for single-worker tier — BBH 0.6244 beats qwen2.5:7b (0.5556)
- needs pipeline and code testing to determine full potential

GGUF: `Qwen3-8B-Q4_K_M.gguf`

### qwen2.5-coder:14b

Status:
- current preferred split-worker reasoning/coding model
- first full split benchmark results 2026-03-14 (pipeline, code, reasoning smoke)
- strong code generation, close to 32B performance

Known results (full_v2 + l100, 2026-03-14/16):
- `humaneval`: 90.2% base / 86.6% plus — second best in fleet after 32B
- `mbpp`: 84.9% / 73.5% — best mbpp score in fleet
- `gsm8k`: 0.89 (limit 100) — down from 1.0 at limit 5 (noise), stable at scale
- `bbh`: 0.5937 (limit 100) — down from 0.6370 at limit 5
- `drop`: 0.4802 f1 / 0.28 em (limit 100) — down from 0.558 at limit 5
- `json_schema_strict`: 23.1% (3/13) — improved from earlier 0% run (split_smoke_v1 had prompt issue)
- `command_safety`: 25.0% (3/12)
- `ambiguity_handling`: 7.7% (1/13)
- `tool_plan_sequence`: 93.3% (14/15)
- `orchestration_tradeoff`: 75.0% (9/12)
- `long_context_extract`: 92.9% (13/14)

Earlier results:
- `gsm8k`: 1.0 in `quick_triplet_l1_20260305`
- `drop`: 0.57 in `quick_triplet_l1_20260305`

Best practices:
- use for higher-quality coding/reasoning work when split capacity is available
- code generation quality nearly matches 32B — viable alternative when 3090 is busy
- keep split runtime validation separate from single-worker tuning
- do not assume every candidate pair is stable; pair stability is still an operational variable

### qwen2.5-coder:32b

Status:
- brain-tier model (GPU 0, 3090 24GB)
- first sequenced campaign completed 2026-03-14 (pipeline + code + reasoning smoke test)
- strong on code generation, underperforms 7B on pipeline reliability tests

Known results (full_v2 + campaign, 2026-03-14/15):
- `humaneval`: 91.5% base / 87.2% plus
- `mbpp`: 89.7% base / 77.0% plus (339/291 of 378) — best mbpp base score in fleet
- `gsm8k`: 0.92 (limit 100) — best gsm8k score in fleet
- `bbh`: 0.4837 (limit 100) — improved from 0.4593 at limit 5
- `drop`: 0.756 f1 / 0.62 em (limit 100) — best drop score in fleet
- `json_schema_strict`: 30.8% (4/13) — worse than 7B (69.2%)
- `command_safety`: 83.3% (10/12)
- `ambiguity_handling`: 15.4% (2/13)
- `tool_plan_sequence`: 93.3% (14/15)
- `orchestration_tradeoff`: 83.3% (10/12)
- `long_context_extract`: 100% (14/14)
- `mmlu`: 0.270, `arc_challenge`: 0.20, `hellaswag`: 0.40, `truthfulqa_mc2`: 0.200, `boolq`: 0.20 (all limit 5) — knowledge scores identical to 7B coder, likely noise at limit 5

Earlier results:
- `gsm8k`: 0.0 in `quick_triplet_l1_20260305` (likely prompt/config issue)
- `drop`: 0.18 in `quick_triplet_l1_20260305`

Best practices:
- use for code generation tasks where quality matters more than throughput
- pipeline test underperformance likely caused by system prompt mismatch — the "strict worker assistant" prompt is tuned for 7B response style
- re-run pipeline with a tuned prompt before drawing conclusions about reliability
- do not treat parameter count as automatic superiority on structured output tasks

### deepseek-r1:14b

Status:
- split-worker model (2x 1060 6GB)
- first benchmark results 2026-03-14 (pipeline, code, reasoning smoke)
- complete failure on reasoning and code generation benchmarks

Known results (full_v3 + split smoke, 2026-03-14):
- `humaneval`: 6.1% base / 6.1% plus — near-total failure
- `mbpp`: 22.2% / 20.9% — marginal
- `gsm8k`: 0.0, `bbh`: 0.0, `drop`: 0.0 — answer extraction incompatibility (N/A — `<think>` tag issue)
- `json_schema_strict`: 7.7% (1/13)
- `command_safety`: 8.3% (1/12)
- `ambiguity_handling`: 0% (0/13)
- `tool_plan_sequence`: 80.0% (12/15)
- `orchestration_tradeoff`: failed (ReadTimeout — model too slow for 180s timeout)
- `long_context_extract`: 78.6% (11/14)

Tuning history (2026-03-16):
- v1: boolean-only evaluator prompt ("So the answer is True/False") — forced wrong format on math tasks, all-zero GSM8K/DROP
- v2: general worker prompt — no improvement, GSM8K still 0
- Root cause: **structural, not prompt-tunable**. llama-server splits `<think>` into `reasoning_content` API field before any client-side patches see it. Model outputs math answers in LaTeX `\boxed{}` format instead of `#### number`. The `--patch-think-tag-strip` operates on `content` which is already clean (think content already separated by server).
- BBH 0.5852 was achieved only because BBH's `\n\n` stop was the specific stop removed in patch v2. Generalizing the patch to all stops didn't help other tasks.
- Very slow on split 1060s: full think chains generate for every request (~500-1000 tokens), BBH limit 5 took ~2.5 hours

Best practices:
- do not use for code generation or structured output tasks
- the DeepSeek-R1 family's `<think>` output format is fundamentally incompatible with standard benchmark harnesses — this is a **structural issue** requiring changes to llama-server or lm-eval internals, not solvable with prompt tuning or client-side patches
- tool_plan_sequence works because it doesn't require strict format compliance
- 14B variant shows same failure modes as 7B — this is a model family issue, not a size issue
- may still be valuable in real plan execution where we control prompting and can parse `reasoning_content` directly

### phi-4:14b

Status:
- split-worker model (2x 1060 6GB)
- first benchmark results 2026-03-14 (pipeline, code), reasoning tuning 2026-03-16
- strong on pipeline tasks (100% command_safety, tool_plan_sequence, long_context_extract)
- strong on code (78.7% humaneval, 73.8% mbpp)
- reasoning benchmarks underperform due to output format incompatibilities

Tuning history (2026-03-16, 5 prompt iterations):
- baseline (l50): GSM8K 0.70, BBH **0.283**, DROP 0.070 — best BBH score
- v2 (JSON hints + "keep output minimal"): GSM8K 0.80, BBH 0.044, DROP 0.384 — "minimal" killed CoT for BBH
- v3 ("think step by step"): GSM8K 1.0, BBH 0.1185, DROP 0.008 — markdown `\n\n` hits stop sequences
- v4 (stop-strip patch): GSM8K 1.0, BBH 0.0519, DROP 0.008 — stop removal let model ramble past answer
- v5 ("So the answer is" format): GSM8K 1.0, BBH 0.1259, DROP 0.0 — slight BBH gain, DROP destroyed

Root cause: Phi-4 formats CoT with markdown (numbered lists with `\n\n` between steps). BBH's `\n\n` stop truncates reasoning before the answer. Removing stops lets the model finish but it doesn't reliably follow the fewshot "So the answer is X" pattern for complex answer types. DROP's `.` stop has the same issue. Further prompt tuning shows diminishing/negative returns — baseline l50 scores remain the best overall balance.

Best practices:
- use for pipeline and code tasks where it excels
- for reasoning benchmarks, accept baseline scores as representative
- do not use stop-strip patch (hurts more than helps for this model)

### mistral:7b-instruct

Status:
- available as an alternate 7B worker-tier model

Known results:
- `custom_ambiguity_handling`: 1.0 in `local_custom_probe_v2`
- `aime_2024` backend certification probe succeeded on 2026-03-05

Best practices:
- useful as a comparison model for instruction following and clarification behavior
- still needs broader apples-to-apples scoring against the active qwen family before promotion

### deepseek-r1:32b

Status:
- brain-tier model (GPU 0, 3090 24GB)
- pipeline tested 2026-03-15 — confirms R1 family pattern at 32B scale

Known results (pipeline_r1_32b_smoke_v1, 2026-03-15):
- `json_schema_strict`: 0% (0/13)
- `command_safety`: 8.3% (1/12)
- `ambiguity_handling`: 0% (0/13)
- `tool_plan_sequence`: 80.0% (12/15)
- `orchestration_tradeoff`: 8.3% (1/12)
- `long_context_extract`: 85.7% (12/14)
- Code: HumanEval 9%, Mbpp 26% (from earlier run — think tags corrupt code extraction)
- Reasoning: GSM8K 0.8 (flex extract only), BBH 0.0, DROP 0.0 (from earlier run)

GGUF: `DeepSeek-R1-Distill-Qwen-32B-Q4_K_M.gguf`
Tuning profile: exists (`deepseek-r1:32b` alias in `model_tuning_profiles.json`)

Best practices:
- confirmed: same `<think>` tag incompatibilities as 7B and 14B — scaling doesn't help
- pipeline scores mirror R1 family pattern: tool_plan + long_context are usable, everything else near zero
- do not use for structured output, code generation, or reasoning benchmarks

### phi-4:14b

Status:
- split-worker model (2x 1060 6GB)
- first benchmark results 2026-03-14 (pipeline, code, reasoning smoke)
- strong instruction following (100% command_safety, tool_plan, long_context)
- code generation mid-tier (humaneval 78.7%, mbpp 73.8%)

Known results (smoke_v1 + l50_v1, 2026-03-14/15):
- `humaneval`: 78.7% base / 73.2% plus
- `mbpp`: 73.8% / 64.0%
- `gsm8k`: 0.70 (limit 50, flex) — dropped from 0.80 at limit 5 (limit 5 was noise)
- `bbh`: 0.283 (limit 50) — consistent with limit 5 (0.274), confirms weak BBH performance
- `drop`: 0.070 f1 / 0.0 em (limit 50) — confirmed very low, up from 0.024 at limit 5 but still near-zero
- `json_schema_strict`: 0% (0/13) — complete failure on structured JSON output
- `command_safety`: 100% (12/12)
- `ambiguity_handling`: 38.5% (5/13)
- `tool_plan_sequence`: 100% (15/15)
- `orchestration_tradeoff`: 91.7% (11/12)
- `long_context_extract`: 100% (14/14)

Best practices:
- excellent for instruction-following tasks (safety, tool planning, context extraction)
- weak on structured JSON output — do not use for JSON schema compliance tasks
- drop score needs higher-limit run to validate (0.024 at limit 5 is suspiciously low)

GGUF: `phi-4-Q4_K_M.gguf`

### gemma-3:12b

Status:
- **Cannot split-load on 1060 GPUs** (2026-03-16 confirmed). 262K vocab produces ~3.1GB embedding matrix per GPU — exceeds 6GB VRAM even with reduced layers/ctx. Would need brain GPU (3090) to run.
- partial benchmark results 2026-03-14 (pipeline complete on split before OOM issue was understood)
- reasoning bbh and drop failed (exit code 1, empty output dirs — likely VRAM pressure during generation)

Known results (smoke_v1, 2026-03-14):
- `humaneval`: interrupted (was generating when system OOM killed containers)
- `mbpp`: untested
- `gsm8k`: 0.60 (limit 5)
- `bbh`: failed (OOM on split pair — 262K vocab too large for 2x 6GB)
- `drop`: failed (same OOM cause)
- `json_schema_strict`: 0% (0/13)
- `command_safety`: 58.3% (7/12)
- `ambiguity_handling`: 53.8% (7/13) — best ambiguity score in fleet
- `tool_plan_sequence`: 93.3% (14/15)
- `orchestration_tradeoff`: 75.0% (9/12)
- `long_context_extract`: 92.9% (13/14)

Best practices:
- must run on brain GPU (3090) — will not fit on 1060 split pairs
- ambiguity_handling score (53.8%) is notably higher than most other models
- pipeline scores obtained before OOM was understood, may have been under VRAM pressure

GGUF: `gemma-3-12b-it-Q4_K_M.gguf`

### qwen3.5:35b-a3b

Status:
- brain-tier model (GPU 0, 3090 24GB)
- MoE architecture (35B total, ~3B active)
- first pipeline run 2026-03-15: mostly 0% scores due to thinking mode
- litmus test passes when thinking is disabled (`--reasoning-budget 0` or `chat_template_kwargs.enable_thinking=false`)

Known results (q35_35b_nothink_v2, 2026-03-15 — thinking disabled):
- `json_schema_strict`: 23.1% (3/13)
- `command_safety`: 100% (12/12) — best in fleet (tied with phi-4)
- `ambiguity_handling`: 38.5% (5/13)
- `tool_plan_sequence`: 93.3% (14/15)
- `orchestration_tradeoff`: 83.3% (10/12)
- `long_context_extract`: 100% (14/14)
- `humaneval`: 90.9% base / 87.2% plus (149/143 of 164) — second best humaneval in fleet (tied with 32B coder)
- `mbpp`: 86.2% base / 72.2% plus (326/273 of 378)
- `gsm8k`: untested
- `bbh`, `drop`: expect SWA failure (same as 4b/9b)

Thinking mode issue:
- llama-server detects the Qwen3.5 chat template's `<think>` support and enables `thinking = 1`
- model puts its entire answer into `reasoning_content` API field, leaving `content` empty
- **different from qwen3.5:4b/9b** which embed `<think>` tags directly in content text
- fix: launch with `--reasoning-budget 0` (server-side) or set `chat_template_kwargs.enable_thinking=false` per-request
- with thinking disabled, litmus test passes: clean reasoning (555), clean JSON, correct code (with markdown fences)

Memory:
- VRAM: 20.5 GB on GPU 0 + 515 MB host buffer
- Docker memory limit: 11g/13g (brain tier)
- first run used 4g limit (7B tier) — container was OOM-killed by Docker

Best practices:
- always launch with `--reasoning-budget 0` for benchmarking (or any use case that reads `content` field)
- may still trigger SWA/hybrid memory issues with bench-knowledge (same as other Qwen3.5 models)
- tuning profile exists (`Qwen3.5-35B-A3B-Q4_K_M.gguf` in `model_tuning_profiles.json`)

### qwen3.5 family

Status:
- **`--reasoning-budget 0` is required** for all Qwen3.5 models on llama-server (2026-03-15 finding)
- without it, llama-server's chat template activates thinking mode, routing all output to `reasoning_content` API field and leaving `content` empty — causing all-zero benchmark scores
- with the fix, all three sizes (4b, 9b, 35b) produce competitive pipeline and gsm8k scores
- BBH and DROP still fail across all sizes (SWA hybrid memory issue, not a thinking problem)

Benchmark summary (all with `--reasoning-budget 0`):

| Model | cmd_safety | long_ctx | tool_plan | orch | ambiguity | json | gsm8k |
|-------|-----------|----------|-----------|------|-----------|------|-------|
| 4b | 100% | 100% | 93.3% | 58.3% | 30.8% | 15.4% | 0.80 |
| 9b | 91.7% | 100% | 93.3% | 75.0% | 53.8% | 38.5% | 0.80 |
| 35b | 100% | 100% | 93.3% | 83.3% | 38.5% | 23.1% | pending (expect SWA failure) |

Best practices:
- always launch with `--extra-arg "--reasoning-budget" --extra-arg "0"` via run_runtime.sh
- 9b is the best overall Qwen3.5 for pipeline reliability (best ambiguity + json scores)
- 35b has strongest instruction following (100% cmd_safety + long_ctx, 83.3% orchestration)
- do not use for BBH/DROP reasoning benchmarks until SWA issue is resolved
- code generation looks promising (35b: 542/542 non-empty solutions)

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
