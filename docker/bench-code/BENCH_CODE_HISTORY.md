# bench-code Run History

Historical results for the EvalPlus code generation suite (humaneval, mbpp).

The main MODEL_LIBRARY.md holds only the latest score per model/test.
This file holds the full history so we can track how prompt and config changes affect scores.

## How to read this table

Each row is one scored run. Code tasks use EvalPlus's built-in function-signature prompt.
The key variables are model, any injected system prompt, and runtime config.

## Results

| Run Date (UTC) | Model | Tasks | Scores | System Prompt Used | Run Path |
| --- | --- | --- | --- | --- | --- |

No completed code suite runs recorded yet.

## Notes

- Trimmed 50-problem coding scoring is currently blocked by EvalPlus requiring full problem coverage.
- Full humaneval + mbpp runs are supported through the standard `bench-code` docker flow.
