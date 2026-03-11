# Custom Tasks

These are local acceptance tests for orchestration behavior that public benchmarks do not cover well.

## Tests

| Test ID | What It Measures | Cases |
| --- | --- | --- |
| `custom_json_schema_strict` | Can the model return exact valid JSON with required keys? | 13 |
| `custom_command_safety` | Can it correctly flag unsafe vs safe shell commands? | 12 |
| `custom_ambiguity_handling` | Does it ask for clarification instead of acting blindly? | 13 |
| `custom_tool_plan_sequence` | Can it order dependent steps correctly? | 15 |
| `custom_orchestration_tradeoff` | Can it reason about GPU/scheduling/resource tradeoffs? | 12 |
| `custom_long_context_extract` | Can it pull specific facts from structured logs? | 14 |

## Prompt Methodology

Each model has a universal system prompt in `model_tuning_profiles.json`.
Each test can have its own prompt override per model in `model_prompt_profiles.json`.

When `--use-model-prompts` is enabled:
1. Check `model_prompt_profiles.json` for test-specific override (`model + test_id`)
2. Fall back to `model_prompt_profiles.json` model-level `system_prompt`
3. Fall back to `model_tuning_profiles.json` universal model `system_prompt`
4. Fall back to `model_prompt_profiles.json` default suite prompt

Every run result archives the exact prompt used (`prompts_snapshot` + per-case
`system_prompt_used`), so historical runs are self-contained.

## Files

- `cases.json` — test cases and grading rules (worker-facing suite)
- `brain_decisions_cases.json` — brain/orchestrator decision scenarios (separate from worker pass/fail)
- `model_prompt_profiles.json` — per-model test-specific prompt overrides for tuning
- `model_prompt_profiles_B.json` — failure-tuned B variant for A/B prompt testing

Do not mix brain-decision cases into worker-facing pass/fail comparisons.

## Running

Baseline (no prompt profiles):

```bash
python3 /media/bryan/shared/plans/shoulders/benchmarking/run_local_custom_task.py \
  --id custom_command_safety \
  --model qwen2.5:7b \
  --base-url http://localhost:11436
```

With prompt tuning:

```bash
python3 /media/bryan/shared/plans/shoulders/benchmarking/run_local_custom_task.py \
  --id custom_command_safety \
  --model Qwen3.5-9B-Q3_K_M.gguf \
  --base-url http://localhost:11435 \
  --use-model-prompts \
  --prompt-profiles /media/bryan/shared/plans/shoulders/benchmarking/custom_tasks/model_prompt_profiles.json \
  --tuning-profiles /media/bryan/shared/plans/shoulders/benchmarking/model_tuning_profiles.json
```

A/B prompt profile switch:

```bash
# A profile (baseline)
--prompt-profiles /media/bryan/shared/plans/shoulders/benchmarking/custom_tasks/model_prompt_profiles.json

# B profile (failure-tuned variant)
--prompt-profiles /media/bryan/shared/plans/shoulders/benchmarking/custom_tasks/model_prompt_profiles_B.json
```

## History

Run history for custom pipeline tests is tracked in:
- [bench-pipeline HISTORY](../docker/bench-pipeline/BENCH_PIPELINE_HISTORY.md)

The main MODEL_LIBRARY.md holds only the latest scores.
