# bench-knowledge Run History

Historical results for the lm-eval knowledge/loglikelihood suite (llama.cpp GGUF inside container).

The main MODEL_LIBRARY.md holds only the latest score per model/test.
This file holds the full history so we can track how config changes affect scores.

## How to read this table

Each row is one scored run. Knowledge tasks use loglikelihood scoring, so system prompts
have minimal impact. The key variables are GGUF file, quantization, and runtime config.

## Results

| Run Date (UTC) | Model (GGUF) | Tasks | Scores | Runtime Config | Run Path |
| --- | --- | --- | --- | --- | --- |

No completed knowledge suite runs recorded yet.

## Notes

- The llama.cpp gguf container lane has been validated as the intended path for MC/loglikelihood tasks.
- Backend certification for individual tasks (boolq, arc_challenge, etc.) is tracked in `benchmark_status.json`.
