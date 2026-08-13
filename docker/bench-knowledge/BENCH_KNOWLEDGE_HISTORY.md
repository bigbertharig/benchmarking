# bench-knowledge Run History

## 2026-08-13 - Methodology 3.0.0

- Moved model ownership to the shared campaign runtime.
- Replaced the incompatible completion-logprob adapter with frozen,
  generation-scored multiple-choice probes.
- Added deterministic model-profile alias resolution and task-level resume.
- Started comparison group `knowledge-chat-mc-v1`; historical v2 scores are not
  comparable.

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

## Historical v2 Notes

- The llama.cpp GGUF container lane is retired because its lm-eval adapter
  requires completion echo/logprob fields no longer supplied by the runtime.
- Backend certification for individual tasks (boolq, arc_challenge, etc.) is tracked in `benchmark_status.json`.
