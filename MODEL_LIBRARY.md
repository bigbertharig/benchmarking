# Model Library

Central hub for model selection and benchmarking documentation.

## Companion Docs

| Doc | What's in it |
|-----|-------------|
| [BENCHMARK_SCORES.md](BENCHMARK_SCORES.md) | Pure score tables — pipeline, code, reasoning, knowledge |
| [MODEL_SELECTION_FOR_PLANS.md](MODEL_SELECTION_FOR_PLANS.md) | Plan-facing model choices by task type |
| [MODEL_RUNTIME_GUIDE.md](MODEL_RUNTIME_GUIDE.md) | Per-model runtime requirements, best practices, memory, compatibility |
| [BENCHMARK_LESSONS_LEARNED.md](BENCHMARK_LESSONS_LEARNED.md) | Debugging narratives, tuning histories, fix details |

Machine-readable sources:
- generated score ledger: `/media/bryan/shared/logs/benchmarks/MODEL_BENCHMARK_REFERENCE.md`
- raw records: `/media/bryan/shared/logs/benchmarks/model_benchmark_records.jsonl`
- scoreboard JSON: `/media/bryan/shared/plans/shoulders/benchmarking/results/model_library_scoreboard.json`
- model tuning profiles: `/media/bryan/shared/plans/shoulders/benchmarking/model_tuning_profiles.json`
- task routing: [model_task_library.json](/home/bryan/llm_orchestration/shared/plans/shoulders/benchmarking/model_task_library.json)

Quick commands:
```bash
# Check rig status (GPUs, running tests, memory, OOM kills)
ssh 10.0.0.3 'bash /mnt/shared/scripts/benchmarks/bench_status.sh'

# Run a benchmark campaign (multi-model, multi-suite, parallel GPU scheduling)
ssh 10.0.0.3 'python3 /mnt/shared/scripts/benchmarks/run_campaign.py /mnt/shared/plans/shoulders/benchmarking/campaigns/<manifest>.json'

# Smoke run (limit 10 per task)
ssh 10.0.0.3 'python3 /mnt/shared/scripts/benchmarks/run_campaign.py /mnt/shared/plans/shoulders/benchmarking/campaigns/<manifest>.json --limit-override 10'
```

Rules:
- update scores in [BENCHMARK_SCORES.md](BENCHMARK_SCORES.md)
- update plan-facing routing in [MODEL_SELECTION_FOR_PLANS.md](MODEL_SELECTION_FOR_PLANS.md)
- update runtime notes in [MODEL_RUNTIME_GUIDE.md](MODEL_RUNTIME_GUIDE.md)
- update investigation details in [BENCHMARK_LESSONS_LEARNED.md](BENCHMARK_LESSONS_LEARNED.md)
- update this doc only for: best choices, model inventory, suite rationale, cloud reference

## What Scores Mean for Real Tasks

Each benchmark tests a specific capability. Use this to match model strengths to your workload.

### Reasoning benchmarks → real tasks

| Benchmark | What it tests | Good score = good at... | Watch out for... |
|-----------|--------------|------------------------|-----------------|
| **humaneval** | Write a function from a docstring | Code generation, scripting, tool building | Low score = model can't write working code. Below ~60% is unusable for code tasks. |
| **mbpp** | Solve short coding problems | Same as humaneval, broader problem variety | Scores track humaneval closely. Big gap between the two = inconsistent code quality. |
| **gsm8k** | Grade-school word problems (arithmetic + reasoning) | Math reasoning, numerical extraction, calculation tasks | Easy benchmark — most models score 0.7+. Below 0.5 = weak at basic math. |
| **bbh** | 27 diverse hard reasoning tasks (logic, tracking, disambiguation) | Complex multi-step reasoning, following intricate instructions | Hardest reasoning test. Slow to run (27 subtasks). Below 0.3 = poor general reasoner. |
| **drop** | Read a passage, extract/compute an answer | Reading comprehension, text extraction, summarization, QA over documents | Requires `--patch-think-tag-strip` for thinking models. High drop + low bbh = can read but can't reason. |

### Pipeline benchmarks → real tasks

| Benchmark | What it tests | Good score = good at... | Watch out for... |
|-----------|--------------|------------------------|-----------------|
| **json_schema** | Output valid JSON matching a schema | Structured extraction, API responses, machine-parseable output | Hardest pipeline test. Most models score below 30%. |
| **cmd_safety** | Refuse dangerous shell commands | Safe tool use, command execution guardrails | 100% = won't run `rm -rf /`. Below 50% = unsafe for agentic tool use. |
| **ambiguity** | Handle unclear/contradictory instructions gracefully | Asking for clarification, graceful degradation on bad input | High variance across models. Measures "knows what it doesn't know". |
| **tool_plan** | Plan multi-step tool use sequences | Agentic workflows, task decomposition, orchestration | Most models score 93%+. Below 80% = poor at multi-step planning. |
| **orch_tradeoff** | Reason about resource tradeoffs and priorities | Task prioritization, scheduling, resource allocation | Tests orchestrator-style decision making. |
| **long_ctx** | Follow instructions across long context windows | Long document processing, multi-turn conversations | 100% = reliable at full context. Below 85% = loses track in long inputs. |

### Score profiles and what they mean

| Profile | Typical model | Best real-world use |
|---------|--------------|-------------------|
| High code + high bbh | Qwen2.5-Coder, Qwen3.6 | General-purpose worker: coding, reasoning, structured output |
| High drop + low code | Gemma-4-E4B | Text extraction, reading comprehension, document QA — not coding |
| High bbh + low code | SmolLM3-3B | Lightweight reasoning on constrained hardware (RPi, edge) |
| High safety + high tool_plan | Phi-4-14B | Instruction-following, safe agentic tool use — not for complex reasoning |
| High everything | Qwen3.6-27B | Brain-tier: use for any task where quality matters more than speed |
| Fast + high everything | Qwen3.6-35B-A3B | Brain-tier speed pick: MoE gives near-27B quality at 2-3× speed |

## Current Best Choices

| Task Profile | Preferred Model | Why | Fallback |
| --- | --- | --- | --- |
| structured extraction | `qwen2.5-coder:7b` | cheapest worker-tier default | `qwen2.5-coder:14b` |
| deep reasoning (brain) | `qwen3.6:27b` | best GSM8K (0.94), DROP (0.883), 100% safety | `qwen3.6:35b-a3b` |
| deep reasoning (worker) | `qwen2.5-coder:14b` | strongest validated reasoning in worker/split set | `qwen2.5-coder:7b` |
| code generation (brain) | `qwen3.6:27b` | best HumanEval (93.3%), MBPP (92.6%) | `qwen3.6:35b-a3b` |
| code generation (worker) | `qwen2.5-coder:14b` | coder family default for worker-tier | `qwen2.5-coder:7b` |
| code review | `qwen2.5-coder:14b` | better fit for bug-finding and patch reasoning | `qwen2.5-coder:7b` |
| general QA | `qwen2.5-coder:7b` | throughput-first worker default | `qwen2.5-coder:14b` |
| text extraction (worker) | `gemma-4:e4b` | DROP 0.31 at l10 (E2B scored 0.00); needs higher-limit validation | `gemma-4:e2b` |
| fast brain inference | `qwen3.6:35b-a3b` | MoE ~3B active, 32s pipeline, 20m code suite | `qwen3.6:27b` |
| fast worker reasoning | `smollm3:3b` | BBH 0.668 in 4h vs Qwen-7B 0.667 in 9h — same score, half the time | `llama3.2:3b` |
| pipeline reliability | `gemma-4:26b-a4b` | best orchestration (91.7%), ambiguity (69.2%) | `qwen3.6:27b` |
| edge/RPi deployment | `smollm3:3b` | best reasoning in 3B tier (BBH 0.668), fits in 3GB | `llama3.2:3b` |

## Active Model Inventory

See [MODEL_RUNTIME_GUIDE.md](MODEL_RUNTIME_GUIDE.md) for per-model runtime details.

| Model | Tier | GPU Target | Status |
| --- | --- | --- | --- |
| `Qwen2.5-Coder-7B` | 7B single | GPU 1-5 | complete (all suites, l100) |
| `Llama-3.2-3B-Instruct` | 3B single | GPU 1-5 | complete (all suites, l100) |
| `SmolLM3-3B` | 3B single | GPU 1-5 | complete (all suites, l100) |
| `Gemma-4-E4B` | 4B single | GPU 1-5 | complete |
| `Gemma-4-E2B` | 5B single | GPU 1-5 | complete |
| `Gemma-4-12B` | 12B split | GPU 1+3 or 4+5 | complete (pipeline, code, reasoning partial) |
| `Qwen2.5-Coder-14B` | 14B split | GPU 1+3 or 4+5 | complete (all suites, l100) |
| `Phi-4-14B` | 14B split | GPU 1+3 or 4+5 | complete |
| `Gemma-4-26B-A4B` | 30B brain | GPU 0 (3090) | complete |
| `Gemma-4-31B` | 30B brain | GPU 0 (3090) | complete |
| `Qwen3.6-27B` | 30B brain | GPU 0 (3090) | complete |
| `Qwen3.6-35B-A3B` | 30B brain | GPU 0 (3090) | complete |

### Archived Models

Scores preserved in [BENCHMARK_SCORES.md](BENCHMARK_SCORES.md). No longer actively tested.

| Model | Reason archived |
| --- | --- |
| `Qwen3-8B` | Superseded by Qwen3.6-27B |
| `Qwen3-1.7B` | Weak everywhere (BBH 0.0), no niche |
| `Qwen3.5-4B` | Superseded by Gemma-4-E4B, SWA blocks reasoning |
| `Qwen3.5-9B-Q3_K_M` | Superseded by Qwen3.6, SWA blocks reasoning |
| `Qwen3.5-35B-A3B` | Superseded by Qwen3.6-35B-A3B (same arch, better scores, no SWA) |
| `DeepSeek-R1-7B` | Benchmark-incompatible (structural think-tag issue) |
| `DeepSeek-R1-14B` | Benchmark-incompatible (structural think-tag issue) |
| `DeepSeek-R1-32B` | Benchmark-incompatible (structural think-tag issue) |
| `Qwen2.5-Coder-32B` | Beaten by Qwen3.6-27B on all metrics |
| `Mistral-7B-Instruct-v0.3` | Old gen, no unique strength |
| `Gemma-3-4B` | Superseded by Gemma-4-E4B |
| `Gemma-3-12B` | Superseded by Gemma-4, can't split on 1060s |
| `Phi-4-mini` | Covered by Phi-4-14B, incomplete reasoning |

## Suite Selection Rationale

Default campaigns run 3 suites: **pipeline, code, reasoning**. Knowledge is excluded.

Why:
- Pipeline tests format compliance, code tests generation quality, reasoning tests problem-solving. These directly measure worker fitness.
- Knowledge benchmarks measure pretraining recall — nearly irrelevant (we want models to follow context, not their own knowledge).
- Runtime cost prohibitive (MMLU alone takes 4-8 hours per model at limit 5 on a 1060).

When to run knowledge: sanity-checking new model families or tiebreaking otherwise-identical models. Ad-hoc only.

## Cloud Model Reference (Vendor-Published)

Not rig-run scores. Use for rough positioning only. Vendors use different prompts, tools, and scaffolds.

| Model | Test | Score | Source date |
| --- | --- | --- | --- |
| `Gemini 3 Pro` | SWE-bench Verified | 76.2% | 2026-02-19 |
| `Gemini 3 Pro` | GPQA Diamond | 91.9% | 2026-02-19 |
| `Gemini 3 Pro` | ARC-AGI-2 | 31.1% | 2026-02-19 |
| `Gemini 3.1 Pro` | SWE-bench Verified | 80.6% | 2026-02-19 |
| `Gemini 3.1 Pro` | GPQA Diamond | 94.3% | 2026-02-19 |
| `Gemini 3.1 Pro` | ARC-AGI-2 | 77.1% | 2026-02-19 |
| `GPT-5.3-Codex` | SWE-Bench Pro | 56.8% | 2026-02-05 |
| `GPT-5.3-Codex` | Terminal-Bench 2.0 | 77.3% | 2026-02-05 |
| `GPT-5.4` | SWE-Bench Pro | 57.7% | 2026-03-05 |
| `GPT-5.4` | BrowseComp | 82.7% | 2026-03-05 |
| `Claude Sonnet 4.5` | SWE-bench Verified | 77.2% | 2025-10-21 |
| `Claude Sonnet 4.6` | SWE-bench Verified | 79.6% | 2026-02-17 |
| `Claude Sonnet 4.6` | GPQA Diamond | 89.9% | 2026-02-17 |

Source links:
- OpenAI: [GPT-5.4](https://openai.com/index/introducing-gpt-5-4/), [GPT-5.3-Codex](https://openai.com/index/introducing-gpt-5-3-codex/)
- Anthropic: [Sonnet 4.6](https://www.anthropic.com/news/claude-sonnet-4-6), [Sonnet 4.5](https://www.anthropic.com/news/claude-sonnet-4-5), [Opus 4.5](https://www.anthropic.com/news/claude-opus-4-5)
- Google: [Gemini 3.1 Pro](https://deepmind.google/models/gemini/pro/)

## CPU Inference and Swarm Deployment

Scores are identical on CPU vs GPU — same weights, same math, only speed differs (~12× slower for 3B on Pi 5 vs 1060).

Measured: 3.3 tok/s (Pi 5 CPU) vs 38.4 tok/s (1060 GPU) for 3B models. Ratio worsens with model size.

Full details: compute tiers, current CPU fleet specs, upgrade scenarios (8GB/16GB Pi swarm), use cases, economics, and hybrid architecture → [distributed_work_guide.md](/media/bryan/shared/workspace/distributed_work_guide.md)

Runtime setup: [MODEL_RUNTIME_GUIDE.md](MODEL_RUNTIME_GUIDE.md) § "CPU Inference (Pi 5)"

## Operating Guidance

- For new model onboarding, follow [NEW_MODEL_INTEGRATION.md](NEW_MODEL_INTEGRATION.md) — the step-by-step playbook with decision trees and integration log.
- For scored results, trust the generated reference first.
- For model routing, trust [model_task_library.json](/home/bryan/llm_orchestration/shared/plans/shoulders/benchmarking/model_task_library.json).
- For runtime safety and practical limits, trust [MODEL_RUNTIME_GUIDE.md](MODEL_RUNTIME_GUIDE.md).
- When scores and operator reality disagree, update scores and re-run the benchmark.
- For prompt history, check per-run result archives — never rely on current profiles to reconstruct past runs.
