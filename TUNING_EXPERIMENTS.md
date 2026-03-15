# Tuning Experiments Queue

Experiments to A/B test after smoke testing is complete.
Each experiment targets a specific failure mode observed in benchmark data.

## Experiment 1: Structured Output Prompt Pattern

**Target test:** `json_schema_strict` (13 cases, fast turnaround)
**Target models:** phi-4:14b (0%), gemma-3:12b (0%), qwen3.5-4b (0%), deepseek-r1 family (7-15%)
**Baseline:** current tuning profile prompts at temperature 0.0

**Hypothesis:** Models fail json_schema_strict because their top-1 token preference is to wrap JSON in commentary or markdown. A stronger prompt with explicit output boundary rules will shift the top-1 prediction toward raw JSON.

**Test prompt (Profile B):**
```
You are a function executor.

Follow these rules strictly:

1. Think about the problem internally.
2. Do not show your reasoning.
3. The final output must be ONLY valid JSON.
4. Do not include explanations, comments, or markdown.
5. Do not wrap the JSON in code blocks.
6. The first character of your response must be "{" and the last must be "}".

If you cannot produce valid JSON, return:
{"error":"invalid_request"}
```

**Why this might work:**
- "First character must be {" is a stronger constraint than "return raw JSON" — it gives the model a concrete token-level rule
- "Think internally, don't show reasoning" addresses `<think>` tag leakage (qwen3.5, deepseek-r1)
- Explicit fallback `{"error":"invalid_request"}` prevents improvised explanations on uncertain inputs
- Coder-14B already improved from 0% to 23.1% when we added markdown suppression — this goes further

**Control:** Current system_prompt from `model_tuning_profiles.json` (Profile A)
**Method:** Run json_schema_strict only, same model, same runtime, swap only the system prompt
**Success criteria:** Score improvement > 15% absolute on at least 2 models
**Priority:** High — 0% scores on 3+ models means there's a lot of room to improve

### Test matrix

| Model | Profile A (current) | Profile B (experiment) | Delta |
|---|---|---|---|
| phi-4:14b | 0% | pending | — |
| gemma-3:12b | 0% | pending | — |
| qwen3.5-4b | 0% | pending | — |
| qwen2.5-coder:14b | 23.1% | pending | — |
| deepseek-r1:14b | 7.7% | pending | — |

Run order: phi-4 first (already loaded on split), then gemma-3 (already loaded).

## Experiment 2: Sampling Parameter Tuning (top_k + repeat_penalty)

**Target tests:** `json_schema_strict`, `command_safety`, `tool_plan_sequence`
**Target models:** same as Experiment 1
**Baseline:** temperature 0.0, top_p 1.0 (greedy decoding)

**Hypothesis:** Pure greedy decoding (temp 0) can get stuck in degenerate loops. A small amount of controlled randomness with tight top_k may actually produce better structured output than greedy.

**Test profile (Profile C):**
```json
{
  "temperature": 0.1,
  "top_p": 0.9,
  "top_k": 10,
  "repeat_penalty": 1.05
}
```

**Why this might work:**
- At temp 0, the model always picks token #1 — if token #1 is "Sure," the output is broken with 100% certainty
- At temp 0.1 + top_k 10, tokens #2-#3 get a small chance, which can break out of degenerate patterns
- repeat_penalty 1.05 discourages the repetitive reasoning chains seen in deepseek-r1

**Caveats:**
- At temp 0 top_k is irrelevant (no sampling occurs), so this is only useful if we move off pure greedy
- May introduce variance between runs — need to run 2-3x to confirm stability
- Impact on reasoning/code benchmarks expected to be minimal

**Control:** Current inference settings (temp 0.0, top_p 1.0)
**Method:** Run json_schema_strict + tool_plan_sequence on 2 models, compare
**Success criteria:** Score improvement > 10% absolute without regression on tool_plan_sequence
**Priority:** Medium — try Experiment 1 first since prompt changes are simpler

## Experiment 3: Combined Prompt + Sampling

**Prerequisite:** Experiments 1 and 2 results
**Hypothesis:** If both prompt and sampling changes independently help, combining them may compound the improvement.
**Method:** Best prompt from Exp 1 + best sampling from Exp 2, run full pipeline suite
**Priority:** Low — only if Exp 1 and 2 both show improvement

## Experiment 4: Tool Selection Prompt Refinement

**Target tests:** `tool_plan_sequence`, `orchestration_tradeoff`, `command_safety`
**Target models:** all — especially models scoring below 80% on tool tasks

**Hypothesis:** Models force tool calls even when the task doesn't match, or narrate multiple options instead of picking one. Giving an explicit "no tool" fallback and "single best tool" constraint reduces both false-positive tool calls and multi-tool narration.

**Key prompt additions:**
```
Select the single best tool for the task.
If no tool is appropriate, return: {"tool":"none"}
Do not narrate options or explain your choice.
```

**Why this might work:**
- "Single best tool" suppresses the common failure mode of listing multiple tools with commentary
- `{"tool":"none"}` gives a safe deterministic output when the model is uncertain — prevents drift into explanations
- Complements the JSON boundary rules from Experiment 1

**Method:** Add these lines to the system prompt for tool-related tests, run tool_plan_sequence + orchestration_tradeoff
**Success criteria:** Improvement on orchestration_tradeoff (where R1-14B timed out) or command_safety
**Priority:** Medium — run after Experiment 1 since the prompt patterns combine naturally

## Experiment 5: Grammar Constraints (--grammar json.gbnf)

**Target test:** `json_schema_strict`
**Target models:** worst performers (0% models)

**Hypothesis:** llama-server's GBNF grammar enforcement can structurally prevent invalid JSON output, regardless of model behavior.

**Caveats:**
- Grammar constraints enforce syntax only, not semantic correctness
- Requires passing grammar file to llama-server at request time (not at startup)
- bench-pipeline would need modification to pass grammar parameter in API calls
- May slow generation due to constrained decoding

**Priority:** Low — investigate feasibility first, then test if Experiments 1-2 don't solve the problem

## How to Run These Tests

All experiments use `json_schema_strict` as the primary canary (13 cases, ~1 min per model).

Quick single-test run command:
```bash
# On rig 10.0.0.3, with model already loaded on target port
docker run --rm --network host \
  -e BENCHMARK_DISABLE_AUTO_RESERVE=1 \
  -v /mnt/shared:/mnt/shared \
  -v /mnt/shared/logs/benchmarks/bench-pipeline/history:/results \
  -v /mnt/shared/plans/shoulders/benchmarking:/benchmark-scripts:ro \
  bench-pipeline \
  --model <model-id> \
  --runtime-base http://localhost:<port> \
  --tests custom_json_schema_strict \
  --run-name json_ab_<experiment>_<model>_v1
```

To swap prompts: edit `model_tuning_profiles.json` system_prompt for the target model, then run.
To swap sampling: modify inference parameters in tuning profile or pass via API request body.

## Notes

- Source: external research on llama.cpp structured output reliability (2026-03-14)
- These experiments are lower priority than completing smoke tests across all models
- Run these after all models have baseline scores in MODEL_LIBRARY.md
- Document results back in this file, then fold winners into `model_tuning_profiles.json`
