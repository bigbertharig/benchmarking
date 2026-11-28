# Harness session-retention trial ? 2026-11-27

The owned Harness retains at most four prior exchanges (12,000 characters). This
trial checks corrected fictional facts inside that window, after they leave it,
and after two explicit model-written checkpoints. It uses Benchmarking's
`scripts/integration/harness_session_trial.py`, `harness-control/1`, the Coding
role with no tools, 1,024 output tokens per turn, and one ready model at a time.
Each model completed 22 turns across three cases. The ready roster and served
model identity were checked before and after every invocation; all were stable.

| Served model | Context offered | Recent correction | Outside window | Checkpoints 1/2 + final | Checkpoint output tokens | Total turn time, 22 turns |
| --- | ---: | --- | --- | --- | ---: | ---: |
| `gpt-oss:20b` | 131,072 | pass | fail | pass / pass / pass | 456 / 196 | 98.9 s |
| `gemma-4:e4b` | 131,072 | pass | fail | pass / pass / pass | 76 / 111 | 48.8 s |
| `gemma-4:12b` | 262,144 | pass | fail | pass / pass / pass | 66 / 56 | 65.2 s |

The outside-window failures are expected from Harness's current four-turn
selection; they do not establish an inherent model memory limit. Explicit
checkpoint answers preserved the corrected values through two truncation
boundaries on all three models. None of the final runs hit the output-token
limit. GPT-OSS used 456 completion tokens for its first two-fact checkpoint,
so a future automatic compactor needs a tight summary budget and fidelity
checks rather than assuming a requested short summary will be short.

This is one controlled run per model, not a stochastic reliability estimate.
It did not run automatic compaction, tool calls, coding edits, or a full-context
stress test. The next runtime gate is an actual bounded summary policy that
preserves corrections, rejects superseded values, and reports summary latency
and output limits on repeated checkpoints before replacing the four-turn path.

The raw per-turn run IDs, answers, timings, token usage and roster snapshots are
retained on the Pi under `results/harness_session_trials/20261127/` (ignored by
Git). Final receipt files and SHA-256 prefixes:

| Model | Base receipt | Checkpoint receipt |
| --- | --- | --- |
| GPT-OSS 20B | `gpt-oss-20b-v3.json` ? `0448e9708b99` | `gpt-oss-20b-checkpoints.json` ? `11302ac43e38` |
| Gemma E4B | `gemma4-e4b.json` ? `0adc3bed2e6a` | `gemma4-e4b-checkpoints.json` ? `585a88a16516` |
| Gemma 12B | `gemma4-12b.json` ? `67c435f1d205` | `gemma4-12b-checkpoints.json` ? `df5f2a41d329` |
