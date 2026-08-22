# Model Selection For Plans

Use this doc when writing or updating a plan. It translates benchmark results
into practical `llm_model`, `llm_min_tier`, and `llm_placement` choices.

Source of truth:
- current decisions: [MODEL_BEST_OF.md](MODEL_BEST_OF.md)
- raw scores: [BENCHMARK_SCORES.md](BENCHMARK_SCORES.md)
- runtime requirements: [MODEL_RUNTIME_GUIDE.md](MODEL_RUNTIME_GUIDE.md)
- selection hub: [MODEL_LIBRARY.md](MODEL_LIBRARY.md)
- machine-readable routing: [model_task_library.json](model_task_library.json)
- benchmark prompts/runtime profiles: [model_tuning_profiles.json](model_tuning_profiles.json)

## Rule For Plan Updates

Every plan update that touches LLM work should include this step:

1. Identify the role of each LLM task.
2. Check this guide and the latest scores.
3. Pick the best model per role, not one model for the whole plan.
4. Set plan inputs or `llm_model` fields explicitly.
5. Keep task prompts plan-specific, while preserving benchmark-tested runtime
   settings unless there is a clear reason to override them.

Benchmark profiles prove how each model performs under controlled prompts and
runtime settings. Plans may still use different prompts for their workflow, but
runtime shape should stay explicit: context size, placement, split loading, and
known model quirks belong in docs/config, not hidden in scripts.

## Recommended Models By Task Type

| Plan task type | Preferred model | Plan fields | Fallback | Evidence |
| --- | --- | --- | --- | --- |
| Structured JSON extraction | `qwen2.5-coder:7b` | `llm_min_tier: 1`, `llm_placement: single_gpu` | `qwen2.5-coder:14b` | Best worker JSON schema score: 69.2%; strong code-format discipline. |
| Cheap document claims / summaries | `qwen2.5-coder:7b` | `llm_min_tier: 1`, `llm_placement: single_gpu` | `gemma-4:e2b-q8` for pure extraction | Good throughput, reliable JSON, broad enough for repo/doc work. |
| Text extraction / document QA | `gemma-4:e2b-q8` | `llm_min_tier: 1`, `llm_placement: single_gpu` | `gemma-4:e4b` | Best worker DROP F1: 0.787; not a code model. |
| Fast lightweight reasoning | `smollm3:3b` | `llm_min_tier: 1`, `llm_placement: single_gpu` | `llama3.2:3b` | BBH 0.6678 at 3B tier; weaker ambiguity handling. |
| Worker code generation | `ministral-3:14b` | `llm_min_tier: 2`, `llm_placement: split_gpu` | `ministral-3:8b` | Modern full EvalPlus leader in the split lane: HumanEval+ base 87.2%. |
| Worker code review / verification | `ministral-3:14b` | `llm_min_tier: 2`, `llm_placement: split_gpu` | `qwen2.5-coder:14b` | Best current split-worker code result with completed l50 reasoning/runtime validation. |
| Fast import preparation | `ministral-3:8b` | `llm_min_tier: 2`, `llm_placement: split_gpu` | `ministral-3:14b` | Faster modern split option with 76.0% data and 83.4% geometry smoke results. |
| Worker deep reasoning / adjudication | `ministral-3:14b` | `llm_min_tier: 2`, `llm_placement: split_gpu` | `ministral-3:8b`; active brain model for critical work | Both modern split models completed l50 GSM8K, DROP, and IFEval plus runtime checks. |
| Safe tool-use / command risk checks | `phi-4:14b` | `llm_min_tier: 2`, `llm_placement: split_gpu` | active brain model | 100% command safety and tool-plan/orchestration scores; weak JSON schema. |
| Brain-tier synthesis / final report | active brain model | omit `llm_model` for `executor: brain` | `qwen3.5:27b` for explicit benchmark/operator loads | Plans should not hardcode brain endpoint/model. |
| Brain-tier country/geometry coordination | `qwen3.5:27b` | only for explicit worker/benchmark use; brain runtime otherwise owns it | `devstral-small:24b` | Best complete August import-oriented and geometry smoke result. |
| Brain-tier code generation | `qwen3.5:27b` | only for explicit worker/benchmark use; brain runtime otherwise owns it | `qwen3-coder:30b-a3b` | Qwen 3.5 leads HumanEval+; Qwen Coder leads MBPP+, so choose the fallback for MBPP-style code work. |

## Prompt And Runtime Split

Track two layers separately:

| Layer | Owner | What belongs there |
| --- | --- | --- |
| Benchmark runtime profile | `model_tuning_profiles.json` and runtime guide | model alias, prompt used for benchmark comparability, temperature, max tokens, context, batch size, split/offload notes |
| Plan role prompt | plan script or plan config | task-specific instructions, output schema, examples, role framing, retry/repair behavior |

Do not assume the benchmark prompt is the best prompt for every plan. Use it as
the baseline that made scores comparable, then let plan scripts pass a
role-specific prompt when the workflow needs different behavior.

## Current Cautions

- `gemma-4:e2b-q8` and `gemma-4:e4b` are extraction/document models, not coding
  defaults. Their code scores are very low.
- `smollm3:3b` needs an explicit alias prompt in
  `model_tuning_profiles.json`; `_alias_of` alone is not enough for
  `--require-model-prompt`.
- `phi-4:14b` should not force `--n-gpu-layers 999` on 2x 1060 split runs.
  Let llama.cpp auto-fit or preflight readiness can fail.
- Split-GPU plan tasks should stay single-model. Use separate extractor and
  verifier tasks when a workflow needs multiple roles.
- `ministral-3:3b` completed focused full-code and runtime qualification. It is
  a tested compact alternative, but `qwen2.5-coder:7b` remains the production
  single-GPU default.
- Do not use the preserved failed-attempt rows from the August campaign as the
  final state; use the latest completed run per model, task, and methodology.
- Do not use the brain rows from `20260820_modern_validation_l50_retry3`; the
  endpoint served Qwen3.6 while the controller labeled three other models.
  Brain l50 validation remains pending a model-identity-enforced rerun.
- For `executor: brain` LLM tasks, do not set `llm_model`; the active brain
  runtime is the owner of model selection.
